"""Product-path reSIProcate listener wired to ingress gate and decide().

The native extension (``_resip_runtime``) runs SipStack + DUM on a background
thread. Python supplies ``on_invite(peer_dict, sip_summary) -> status_code``;
:class:`ResipRuntimeListener` implements that callback with
:class:`~as_platform.sip.ingress.TransportIngressGate` and :func:`decide`.
"""

from __future__ import annotations

import importlib
import importlib.machinery
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

from as_platform.decision import Decision, RuleSet, decide
from as_platform.sip.adapter import SipRequestView, to_decision_request
from as_platform.sip.call_controller import (
    CallController,
    ControllerEffect,
    LegId,
    RejectInboundLeg,
    StartOutboundInvite,
)
from as_platform.sip.ingress import TransportIngressGate, reject_plaintext_when_tls_required
from as_platform.sip.transport import PeerIdentity, TransportSeam

_INGRESS_DENIED_STATUS = 403
_FORWARD_WIRE_STATUS = 0
_DEFAULT_BUILD_DIR = Path(__file__).resolve().parents[3] / "native" / "resip_runtime" / "build"


def _extension_build_dir() -> Path:
    override = os.environ.get("AS_RESIP_RUNTIME_BUILD")
    if override:
        return Path(override)
    return _DEFAULT_BUILD_DIR


def load_resip_runtime_extension() -> ModuleType | None:
    """Import ``_resip_runtime`` when the cmake module is on disk."""
    build_dir = _extension_build_dir()
    suffixes = importlib.machinery.EXTENSION_SUFFIXES
    candidates = [build_dir / f"_resip_runtime{suffix}" for suffix in suffixes]
    candidates.append(build_dir / "_resip_runtime.so")
    module_path = next((path for path in candidates if path.is_file()), None)
    if module_path is None:
        return None

    build_str = str(build_dir)
    if build_str not in sys.path:
        sys.path.insert(0, build_str)

    return importlib.import_module("_resip_runtime")


def sip_summary_to_view(summary: dict[str, Any]) -> SipRequestView:
    """Build a boundary view from fields parsed by the native binding."""
    body = summary.get("body", b"")
    if isinstance(body, str):
        body = body.encode("utf-8")
    return SipRequestView(
        method=str(summary["method"]),
        request_uri=str(summary["request_uri"]),
        call_id=str(summary["call_id"]),
        calling_number=str(summary["calling_number"]),
        called_number=str(summary["called_number"]),
        body=bytes(body),
    )


def status_code_from_controller_effects(effects: tuple[ControllerEffect, ...]) -> int:
    """Map the first controller effect to a UAS status for the runtime binding."""
    if not effects:
        return 500
    effect = effects[0]
    if isinstance(effect, RejectInboundLeg):
        return effect.sip_status
    if isinstance(effect, StartOutboundInvite):
        return _FORWARD_WIRE_STATUS
    return 500


def invite_callback_result(
    effects: tuple[ControllerEffect, ...],
) -> int | dict[str, object]:
    """Return value for the native ``on_invite`` callback (int or forward dict)."""
    if not effects:
        return 500
    effect = effects[0]
    if isinstance(effect, RejectInboundLeg):
        return effect.sip_status
    if isinstance(effect, StartOutboundInvite):
        return {"status": _FORWARD_WIRE_STATUS, "route_target": effect.route_target}
    return 500


def controller_effects_for_inbound_invite(
    controller: CallController,
    inbound_call_id: str,
    decision: Decision,
) -> tuple[ControllerEffect, ...]:
    """Run ``decide()`` output through the product :class:`CallController`."""
    inbound = LegId(call_id=inbound_call_id)
    return controller.on_inbound_invite_from_decision(inbound, decision)


def peer_dict_to_identity(peer: dict[str, Any]) -> PeerIdentity:
    """Translate the native peer dict into :class:`PeerIdentity`."""
    certificate_id = peer.get("certificate_id")
    if certificate_id is not None:
        certificate_id = str(certificate_id)
    return PeerIdentity(
        address=str(peer["address"]),
        port=int(peer["port"]),
        certificate_id=certificate_id,
    )


class ResipRuntimeListener:
    """reSIProcate DUM listener that enforces ingress policy then calls ``decide()``."""

    def __init__(
        self,
        gate: TransportIngressGate,
        rules: RuleSet,
        *,
        tls_only: bool = False,
        enable_tcp: bool = False,
        received_at: Callable[[], float] | None = None,
        extension: ModuleType | None = None,
        on_overlap_started: Callable[[], None] | None = None,
        accept_all_invites: bool = False,
        early_cancel_harness: bool = False,
        call_controller: CallController | None = None,
        on_dialog_established: Callable[[dict[str, Any]], None] | None = None,
        on_dialog_terminated: Callable[[str], None] | None = None,
        bind_address: str = "127.0.0.1",
        advertised_address: str = "127.0.0.1",
        on_connection_closed: Callable[[str], None] | None = None,
    ) -> None:
        """Configure gate, rules, and optional clock injection for decide().

        Args:
            gate: Ingress gate consulted before ``decide()``.
            rules: Routing policy for inbound INVITEs.
            received_at: Callable returning ``received_at`` for ``decide()``; defaults
                to :func:`time.time` at the IO boundary.
            extension: Pre-loaded ``_resip_runtime`` module (tests); loaded on
                :meth:`start` when omitted.
            on_overlap_started: Optional overlap hook; defaults to calling native
                ``reload_certificates`` on the running listener when built.
            tls_only: When ``True``, bind only a TLS listener (no UDP) and reject
                plaintext transports at ingress.
            enable_tcp: When ``True`` and not ``tls_only``, also bind a TCP listener
                (mirrors testbed ``resip_probe --tcp``).
            accept_all_invites: Testbed-only harness mode: after ingress policy passes,
                complete the UAS 100/180/200/ACK path with minimal SDP (native DUM).
            early_cancel_harness: With ``accept_all_invites``, hold early dialog (no 200)
                so inbound CANCEL yields 487 (E1 S4 shape).
            call_controller: Cross-leg controller for the product path; defaults to a new
                :class:`~as_platform.sip.call_controller.CallController` when omitted.
            on_dialog_established: Optional native hook when a UAS dialog becomes established
                (accept-all harness / checkpoint seam).
            on_dialog_terminated: Optional native hook with the UAS Call-ID when the dialog ends.
            bind_address: Local socket bind address passed to the native stack.
            advertised_address: Contact/SDP address advertised to peers.
            on_connection_closed: Optional hook when a transport connection closes (connection_id).
        """
        self._gate = gate
        self._rules = rules
        self._tls_only = tls_only
        self._enable_tcp = enable_tcp
        self._accept_all_invites = accept_all_invites
        self._early_cancel_harness = early_cancel_harness
        self._call_controller = call_controller if call_controller is not None else CallController()
        self._received_at = received_at or time.time
        self._extension = extension
        self._on_overlap_started = on_overlap_started
        self._on_dialog_established = on_dialog_established
        self._on_dialog_terminated = on_dialog_terminated
        self._bind_address = bind_address
        self._advertised_address = advertised_address
        self._on_connection_closed = on_connection_closed
        self._last_connection_id: str | None = None
        self._handle: Any = None
        self._port: int | None = None
        self._tls_port: int | None = None
        self._tcp_port: int | None = None

    @property
    def port(self) -> int:
        """Bound primary listen port after :meth:`start` (UDP, or TLS when ``tls_only``)."""
        if self._port is None:
            raise RuntimeError("ResipRuntimeListener is not started")
        return self._port

    @property
    def tls_port(self) -> int | None:
        """Bound TLS port when TLS transport is enabled; ``None`` if not started or no TLS."""
        return self._tls_port

    @property
    def tcp_port(self) -> int | None:
        """Bound TCP port when TCP transport is enabled; ``None`` if not started or no TCP."""
        return self._tcp_port

    def _reload_certificates_on_overlap(self) -> None:
        if self._handle is None or self._extension is None:
            return
        reload_fn = getattr(self._extension, "reload_certificates", None)
        if reload_fn is None:
            return
        reload_fn(self._handle)

    def _tls_plaintext_rejected(self) -> bool:
        seam = self._gate.current_seam()
        return self._tls_only or seam.tls.require_client_certificate

    def _native_transport_config(self, seam: TransportSeam) -> dict[str, Any]:
        tls = seam.tls
        cert_path = Path(tls.certificate_path)
        key_path = Path(tls.private_key_path)
        enable_tls = bool(
            tls.certificate_path.strip()
            and tls.private_key_path.strip()
            and cert_path.is_file()
            and key_path.is_file()
        )
        request_client_certificate = bool(seam.peer_policy.allowed_certificate_ids)
        return {
            "enable_udp": not self._tls_only,
            "enable_tcp": self._enable_tcp and not self._tls_only,
            "enable_tls": enable_tls,
            "tls_only": self._tls_only,
            "require_client_certificate": tls.require_client_certificate,
            "request_client_certificate": request_client_certificate,
            "accept_all_invites": self._accept_all_invites,
            "early_cancel_harness": self._early_cancel_harness,
            "certificate_path": tls.certificate_path,
            "private_key_path": tls.private_key_path,
            "ca_path": tls.ca_path or "",
            "bind_address": self._bind_address,
            "advertised_address": self._advertised_address,
        }

    def _on_invite(
        self, peer_dict: dict[str, Any], sip_summary: dict[str, Any]
    ) -> int | dict[str, object]:
        transport = str(peer_dict.get("transport", "udp"))
        if reject_plaintext_when_tls_required(self._tls_plaintext_rejected(), transport):
            return _INGRESS_DENIED_STATUS

        peer = peer_dict_to_identity(peer_dict)
        connection_id = peer_dict.get("connection_id")
        if connection_id is not None:
            connection_id = str(connection_id)
            self._gate.register_connection(connection_id)
            self._last_connection_id = connection_id
        else:
            self._last_connection_id = None
        if not self._gate.check_peer(peer, connection_id=connection_id):
            return _INGRESS_DENIED_STATUS

        if self._accept_all_invites:
            return 0

        view = sip_summary_to_view(sip_summary)
        decision = decide(to_decision_request(view, self._received_at()), self._rules)
        effects = controller_effects_for_inbound_invite(
            self._call_controller,
            view.call_id,
            decision,
        )
        return invite_callback_result(effects)

    def notify_outbound_response(
        self,
        outbound_call_id: str,
        *,
        status_code: int,
        is_final: bool,
        inbound_call_id: str | None = None,
    ) -> tuple[ControllerEffect, ...]:
        """Update controller state when the native bridge reports an outbound response."""
        inbound = LegId(call_id=inbound_call_id) if inbound_call_id is not None else None
        return self._call_controller.on_outbound_response(
            LegId(call_id=outbound_call_id),
            status_code=status_code,
            is_final=is_final,
            inbound=inbound,
        )

    def notify_leg_terminated(self, call_id: str) -> tuple[ControllerEffect, ...]:
        """Drop controller correlation when DUM reports a leg terminated."""
        if self._on_connection_closed is not None and self._last_connection_id is not None:
            self._on_connection_closed(self._last_connection_id)
            self._last_connection_id = None
        return self._call_controller.on_leg_terminated(LegId(call_id=call_id))

    @property
    def call_controller(self) -> CallController:
        """The listener's in-memory cross-leg controller."""
        return self._call_controller

    def start(self) -> None:
        """Start the native listener on ``127.0.0.1:0``."""
        if self._handle is not None:
            raise RuntimeError("ResipRuntimeListener is already started")

        extension = self._extension or load_resip_runtime_extension()
        if extension is None:
            raise RuntimeError(
                "platform resip_runtime extension not built; run make m2-platform-resip-build"
            )
        self._extension = extension

        overlap_hook = self._on_overlap_started or self._reload_certificates_on_overlap
        self._gate.attach_overlap_hook(overlap_hook)

        seam = self._gate.current_seam()
        transport_config = self._native_transport_config(seam)
        established = self._on_dialog_established
        terminated = self._on_dialog_terminated
        if established is None and terminated is None:
            self._handle = extension.start(self._on_invite, transport_config)
        else:
            self._handle = extension.start(
                self._on_invite,
                transport_config,
                established,
                terminated,
            )
        self._port = int(extension.get_port(self._handle))
        get_tls_port = getattr(extension, "get_tls_port", None)
        if get_tls_port is not None:
            tls_port = int(get_tls_port(self._handle))
            self._tls_port = tls_port if tls_port > 0 else None
        get_tcp_port = getattr(extension, "get_tcp_port", None)
        if get_tcp_port is not None:
            tcp_port = int(get_tcp_port(self._handle))
            self._tcp_port = tcp_port if tcp_port > 0 else None

    def stop(self) -> None:
        """Stop and join the native worker."""
        if self._handle is None or self._extension is None:
            return
        self._extension.stop(self._handle)
        self._handle = None
        self._port = None
        self._tls_port = None
        self._tcp_port = None
