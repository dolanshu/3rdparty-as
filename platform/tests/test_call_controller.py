"""Unit tests for the product CallController (ADR-0022, M7 slice)."""

from __future__ import annotations

import pytest

from as_platform.decision.decide import (
    REASON_MATCH_FORWARD,
    REASON_NO_MATCH,
    Decision,
    DecisionAction,
)
from as_platform.sip.adapter import STATUS_DECLINE, STATUS_NOT_FOUND
from as_platform.sip.call_controller import (
    CallController,
    CallCorrelation,
    CallMapping,
    LegId,
    PropagateOutboundFailure,
    RejectInboundLeg,
    StartOutboundInvite,
    map_outbound_failure_to_inbound_status,
    mapping_from_decision,
)

pytestmark = pytest.mark.unit


def _inbound(call_id: str = "in-1") -> LegId:
    return LegId(call_id=call_id)


def _outbound(call_id: str = "out-1") -> LegId:
    return LegId(call_id=call_id)


def test_forward_inbound_starts_outbound_and_tracks_correlation() -> None:
    controller = CallController()
    inbound = _inbound()

    effects = controller.on_inbound_invite(
        inbound,
        mapping=CallMapping.FORWARD,
        route_target="sip:peer@127.0.0.1:5060",
    )

    assert effects == (
        StartOutboundInvite(
            inbound=inbound,
            route_target="sip:peer@127.0.0.1:5060",
        ),
    )
    assert controller.correlation_for_inbound(inbound) == CallCorrelation(
        inbound=inbound,
        outbound=None,
    )
    assert controller.active_call_count() == 1


def test_reject_inbound_emits_terminal_status_without_state() -> None:
    controller = CallController()

    effects = controller.on_inbound_invite(
        _inbound(),
        mapping=CallMapping.REJECT,
        reject_status=STATUS_NOT_FOUND,
    )

    assert effects == (RejectInboundLeg(inbound=_inbound(), sip_status=404),)
    assert controller.active_call_count() == 0
    assert controller.correlation_for_inbound(_inbound()) is None


def test_mapping_from_decision_forward_and_reject() -> None:
    forward = Decision(
        action=DecisionAction.FORWARD,
        target="sip:next@example.com",
        reason_code=REASON_MATCH_FORWARD,
        matched_rule_id="r1",
    )
    assert mapping_from_decision(forward) == (
        CallMapping.FORWARD,
        "sip:next@example.com",
        None,
    )

    reject = Decision(
        action=DecisionAction.NOT_FOUND,
        target=None,
        reason_code=REASON_NO_MATCH,
        matched_rule_id=None,
    )
    assert mapping_from_decision(reject) == (CallMapping.REJECT, None, STATUS_NOT_FOUND)


def test_on_inbound_invite_from_decision_reject_decline() -> None:
    controller = CallController()
    inbound = _inbound("decline-me")
    decision = Decision(
        action=DecisionAction.DECLINE,
        target=None,
        reason_code="MATCH_BLOCK",
        matched_rule_id="block-1",
    )
    effects = controller.on_inbound_invite_from_decision(inbound, decision)
    assert effects == (RejectInboundLeg(inbound=inbound, sip_status=STATUS_DECLINE),)


def test_outbound_486_propagates_to_inbound_486() -> None:
    controller = CallController()
    inbound = _inbound("in-486")
    outbound = _outbound("out-486")
    controller.on_inbound_invite(
        inbound,
        mapping=CallMapping.FORWARD,
        route_target="sip:down@127.0.0.1:5070",
    )

    effects = controller.on_outbound_response(
        outbound,
        status_code=486,
        is_final=True,
        inbound=inbound,
    )

    assert effects == (
        PropagateOutboundFailure(inbound=inbound, outbound=outbound, sip_status=486),
    )
    assert controller.correlation_for_inbound(inbound) is not None
    assert controller.correlation_for_inbound(inbound).outbound == outbound


def test_outbound_passthrough_and_unmapped_final() -> None:
    assert map_outbound_failure_to_inbound_status(486) == 486
    assert map_outbound_failure_to_inbound_status(503) == 503
    assert map_outbound_failure_to_inbound_status(600) == 502

    controller = CallController()
    inbound = _inbound()
    outbound = _outbound()
    controller.on_inbound_invite(
        inbound,
        mapping=CallMapping.FORWARD,
        route_target="sip:down@127.0.0.1:5070",
    )
    effects = controller.on_outbound_response(
        outbound,
        status_code=503,
        is_final=True,
        inbound=inbound,
    )
    assert effects[0].sip_status == 503


def test_restore_from_checkpoint_and_route_bye() -> None:
    from as_platform.state.call_checkpoint import CallStateCheckpoint, DialogLegCheckpoint

    controller = CallController()
    leg = DialogLegCheckpoint(
        call_id="in@host",
        local_tag="l1",
        remote_tag="r1",
        local_uri="sip:as@127.0.0.1",
        remote_uri="sip:peer@127.0.0.1",
        remote_target="sip:peer@127.0.0.1",
        route_set=(),
        local_cseq=1,
        remote_cseq=1,
    )
    uac = DialogLegCheckpoint(
        call_id="out@host",
        local_tag="l2",
        remote_tag="r2",
        local_uri="sip:as@127.0.0.1",
        remote_uri="sip:down@127.0.0.1:5070",
        remote_target="sip:down@127.0.0.1:5070",
        route_set=(),
        local_cseq=2,
        remote_cseq=1,
    )
    checkpoint = CallStateCheckpoint(
        state="established",
        uas_leg=leg,
        uac_leg=uac,
        committed=True,
    )
    controller.restore_from_checkpoint(checkpoint)
    assert controller.route_in_dialog_bye("in@host") == "sip:down@127.0.0.1:5070"
    with pytest.raises(ValueError, match="duplicate inbound"):
        controller.restore_from_checkpoint(checkpoint)
    assert controller.route_in_dialog_bye("missing") is None


def test_provisional_outbound_response_emits_no_effects() -> None:
    controller = CallController()
    inbound = _inbound()
    outbound = _outbound()
    controller.on_inbound_invite(
        inbound,
        mapping=CallMapping.FORWARD,
        route_target="sip:down@127.0.0.1:5070",
    )
    assert (
        controller.on_outbound_response(
            outbound,
            status_code=180,
            is_final=False,
            inbound=inbound,
        )
        == ()
    )


def test_on_leg_terminated_drops_inbound_mapping() -> None:
    controller = CallController()
    inbound = _inbound()
    outbound = _outbound()
    controller.on_inbound_invite(
        inbound,
        mapping=CallMapping.FORWARD,
        route_target="sip:down@127.0.0.1:5070",
    )
    controller.on_outbound_response(
        outbound,
        status_code=180,
        is_final=False,
        inbound=inbound,
    )
    controller.on_leg_terminated(inbound)
    assert controller.active_call_count() == 0


def test_duplicate_inbound_invite_raises() -> None:
    controller = CallController()
    inbound = _inbound()
    controller.on_inbound_invite(
        inbound,
        mapping=CallMapping.FORWARD,
        route_target="sip:down@127.0.0.1:5070",
    )
    with pytest.raises(ValueError, match="duplicate inbound"):
        controller.on_inbound_invite(
            inbound,
            mapping=CallMapping.FORWARD,
            route_target="sip:down@127.0.0.1:5070",
        )


def test_unknown_outbound_without_inbound_hint_raises() -> None:
    controller = CallController()
    with pytest.raises(ValueError, match="unknown outbound"):
        controller.on_outbound_response(_outbound(), status_code=486, is_final=True)
