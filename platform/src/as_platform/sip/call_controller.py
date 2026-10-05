"""Product CallController: pure cross-leg correlation and FORWARD/REJECT mapping.

Maps kernel decisions onto B2BUA leg lifecycle without sockets or DUM handles.
See ADR-0022 and ``docs/architecture/lld.md`` §5.1.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from as_platform.decision.decide import Decision
from as_platform.sip.adapter import decision_to_status_code
from as_platform.state.call_checkpoint import CallStateCheckpoint

# Non-SIP sentinel: continue on an outbound leg (``adapter.STATUS_CONTINUE``).
STATUS_CONTINUE = 0

# Internal / unmapped failures map to 502 on the inbound UAS leg (REQ-F-10 passthrough set below).
_UPSTREAM_FAILURE_FALLBACK = 502
_PASSTHROUGH_FAILURE_STATUSES = frozenset({408, 480, 486, 503, 504})


class CallMapping(str, Enum):
    """Terminal vs continuing disposition for an inbound INVITE."""

    FORWARD = "forward"
    REJECT = "reject"


@dataclass(frozen=True)
class LegId:
    """One SIP dialog leg; distinct per REQ-F-2."""

    call_id: str


@dataclass(frozen=True)
class CallCorrelation:
    """Semantic mapping from one business call to one or two legs."""

    inbound: LegId
    outbound: LegId | None = None


@dataclass(frozen=True)
class StartOutboundInvite:
    """Adapter should create a UAC INVITE toward ``route_target``."""

    inbound: LegId
    route_target: str


@dataclass(frozen=True)
class RejectInboundLeg:
    """Adapter should answer the inbound UAS leg with ``sip_status``."""

    inbound: LegId
    sip_status: int


@dataclass(frozen=True)
class PropagateOutboundFailure:
    """Map a final non-2xx outbound response onto the correlated inbound leg."""

    inbound: LegId
    outbound: LegId
    sip_status: int


ControllerEffect = StartOutboundInvite | RejectInboundLeg | PropagateOutboundFailure


@dataclass
class _ActiveCall:
    mapping: CallMapping
    inbound: LegId
    outbound: LegId | None = None
    route_target: str | None = None


def mapping_from_decision(decision: Decision) -> tuple[CallMapping, str | None, int | None]:
    """Translate a :func:`~as_platform.decision.decide.decide` result for the controller.

    Returns:
        ``(mapping, route_target, reject_status)`` where ``reject_status`` is a SIP
        code for ``REJECT``, and ``route_target`` is set for ``FORWARD`` / ``TRANSLATE``.
    """
    status = decision_to_status_code(decision.action)
    if status != STATUS_CONTINUE:
        return CallMapping.REJECT, None, status
    if decision.target is None:
        msg = "FORWARD/TRANSLATE decision must include a route target"
        raise ValueError(msg)
    return CallMapping.FORWARD, decision.target, None


def map_outbound_failure_to_inbound_status(downstream_status: int) -> int:
    """Map a final outbound failure code onto the inbound UAS response code (REQ-F-10)."""
    if downstream_status in _PASSTHROUGH_FAILURE_STATUSES:
        return downstream_status
    if 400 <= downstream_status <= 699:
        return _UPSTREAM_FAILURE_FALLBACK
    return _UPSTREAM_FAILURE_FALLBACK


class CallController:
    """In-memory cross-leg map; recoverable checkpoints are a separate concern (ADR-0023)."""

    def __init__(self) -> None:
        """Create an empty controller with no active calls."""
        self._by_inbound: dict[str, _ActiveCall] = {}
        self._inbound_for_outbound: dict[str, str] = {}

    def correlation_for_inbound(self, inbound: LegId) -> CallCorrelation | None:
        """Return the current correlation for an inbound leg, if any."""
        active = self._by_inbound.get(inbound.call_id)
        if active is None:
            return None
        return CallCorrelation(inbound=active.inbound, outbound=active.outbound)

    def on_inbound_invite(
        self,
        inbound: LegId,
        *,
        mapping: CallMapping,
        route_target: str | None = None,
        reject_status: int | None = None,
    ) -> tuple[ControllerEffect, ...]:
        """Register an inbound INVITE and emit adapter effects."""
        if inbound.call_id in self._by_inbound:
            msg = f"duplicate inbound leg: {inbound.call_id!r}"
            raise ValueError(msg)

        if mapping is CallMapping.REJECT:
            if reject_status is None:
                msg = "reject_status required for REJECT mapping"
                raise ValueError(msg)
            if reject_status < 400 or reject_status > 699:
                msg = f"reject_status out of SIP range: {reject_status}"
                raise ValueError(msg)
            return (RejectInboundLeg(inbound=inbound, sip_status=reject_status),)

        if mapping is not CallMapping.FORWARD:
            msg = f"unsupported mapping: {mapping!r}"
            raise ValueError(msg)
        if not route_target:
            msg = "route_target required for FORWARD mapping"
            raise ValueError(msg)

        self._by_inbound[inbound.call_id] = _ActiveCall(
            mapping=CallMapping.FORWARD,
            inbound=inbound,
            route_target=route_target,
        )
        return (StartOutboundInvite(inbound=inbound, route_target=route_target),)

    def on_inbound_invite_from_decision(
        self, inbound: LegId, decision: Decision
    ) -> tuple[ControllerEffect, ...]:
        """Convenience wrapper around :func:`mapping_from_decision`."""
        mapping, route_target, reject_status = mapping_from_decision(decision)
        return self.on_inbound_invite(
            inbound,
            mapping=mapping,
            route_target=route_target,
            reject_status=reject_status,
        )

    def on_outbound_response(
        self,
        outbound: LegId,
        *,
        status_code: int,
        is_final: bool,
        inbound: LegId | None = None,
    ) -> tuple[ControllerEffect, ...]:
        """Observe an outbound leg response; correlate on first sight if needed."""
        inbound_id = self._inbound_for_outbound.get(outbound.call_id)
        if inbound_id is None:
            if inbound is None:
                msg = f"unknown outbound leg: {outbound.call_id!r}"
                raise ValueError(msg)
            active = self._by_inbound.get(inbound.call_id)
            if active is None or active.mapping is not CallMapping.FORWARD:
                msg = f"no pending FORWARD call for inbound {inbound.call_id!r}"
                raise ValueError(msg)
            if active.outbound is not None and active.outbound.call_id != outbound.call_id:
                msg = "inbound leg already bound to a different outbound Call-ID"
                raise ValueError(msg)
            active.outbound = outbound
            self._inbound_for_outbound[outbound.call_id] = inbound.call_id
            inbound_id = inbound.call_id
        elif inbound is not None and inbound.call_id != inbound_id:
            msg = "outbound leg already correlated to a different inbound leg"
            raise ValueError(msg)

        if not is_final:
            return ()
        if 200 <= status_code < 300:
            return ()

        active = self._by_inbound[inbound_id]
        mapped = map_outbound_failure_to_inbound_status(status_code)
        return (
            PropagateOutboundFailure(
                inbound=active.inbound,
                outbound=outbound,
                sip_status=mapped,
            ),
        )

    def on_leg_terminated(self, leg: LegId) -> tuple[ControllerEffect, ...]:
        """Drop correlation state when DUM reports a leg terminated."""
        active = self._by_inbound.pop(leg.call_id, None)
        if active is not None:
            if active.outbound is not None:
                self._inbound_for_outbound.pop(active.outbound.call_id, None)
            return ()

        mapped_inbound = self._inbound_for_outbound.pop(leg.call_id, None)
        if mapped_inbound is not None:
            remaining = self._by_inbound.get(mapped_inbound)
            if (
                remaining is not None
                and remaining.outbound is not None
                and remaining.outbound.call_id == leg.call_id
            ):
                remaining.outbound = None
        return ()

    def active_call_count(self) -> int:
        """Number of inbound legs currently tracked (tests and metrics hooks)."""
        return len(self._by_inbound)

    def restore_from_checkpoint(self, checkpoint: CallStateCheckpoint) -> None:
        """Rebuild inbound/outbound leg correlation from a durable two-leg checkpoint."""
        if checkpoint.state != "established":
            msg = f"unsupported checkpoint state for restore: {checkpoint.state!r}"
            raise ValueError(msg)
        inbound = LegId(call_id=checkpoint.uas_leg.call_id)
        outbound = LegId(call_id=checkpoint.uac_leg.call_id)
        if inbound.call_id in self._by_inbound:
            msg = f"duplicate inbound leg on restore: {inbound.call_id!r}"
            raise ValueError(msg)
        if outbound.call_id in self._inbound_for_outbound:
            msg = f"duplicate outbound leg on restore: {outbound.call_id!r}"
            raise ValueError(msg)
        self._by_inbound[inbound.call_id] = _ActiveCall(
            mapping=CallMapping.FORWARD,
            inbound=inbound,
            outbound=outbound,
            route_target=checkpoint.uac_leg.remote_target,
        )
        self._inbound_for_outbound[outbound.call_id] = inbound.call_id

    def route_in_dialog_bye(self, inbound_call_id: str) -> str | None:
        """Return the downstream BYE target for a restored in-dialog upstream BYE, if known."""
        active = self._by_inbound.get(inbound_call_id)
        if active is None or active.mapping is not CallMapping.FORWARD:
            return None
        return active.route_target
