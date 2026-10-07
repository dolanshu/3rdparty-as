"""Field contract for native reSIProcate runtime stdout/stderr lines.

The C++ binding (``platform/native/resip_runtime/runtime_module.cxx``) reports
runtime progress as ``RESIP_RUNTIME_*`` ``key=value`` lines on stdout (info) or
stderr (errors). This module parses those lines into typed events so REQ-NF-13
(JSON logs with timestamp/level/trace_id/call_id/direction/method linked to
metrics/traces) assertions have a stable evidence hook: Python-side JSON
enrichment in ``resip_runtime.emit_native_log_event`` hangs off this contract.
"""

# See ADR-0005 (observability: structured logs/traces linkage for REQ-NF-13).
# See ADR-0019 (SIP stack selection: reSIProcate runtime is the bound stack).

from __future__ import annotations

from dataclasses import dataclass, field

_LOG_PREFIX = "RESIP_RUNTIME_"

# Events the native binding emits (see runtime_module.cxx). Kept as an explicit
# allowlist so a renamed/added C++ line fails closed (returns ``None``) instead
# of silently passing through.
_KNOWN_EVENTS = frozenset(
    {
        "RESIP_RUNTIME_LISTENING",
        "RESIP_RUNTIME_UAC_INVITE_SENT",
        "RESIP_RUNTIME_UAC_NEW_SESSION",
        "RESIP_RUNTIME_UAC_FAILURE",
        "RESIP_RUNTIME_UAS_FAILURE_MAPPED",
        "RESIP_RUNTIME_OUTBOUND_CANCEL_FORWARD",
        "RESIP_RUNTIME_UAS_ANSWER_RELAYED",
        "RESIP_RUNTIME_RELOAD_CERTIFICATES",
        "RESIP_RUNTIME_FORWARD_ERROR",
        "RESIP_RUNTIME_UAC_CORRELATION_MISS",
        "RESIP_RUNTIME_OUTBOUND_CANCEL_ERROR",
        "RESIP_RUNTIME_ANSWER_RELAY_ERROR",
        "RESIP_RUNTIME_CALLBACK_ERROR",
        "RESIP_RUNTIME_DIALOG_CALLBACK_ERROR",
        "RESIP_RUNTIME_DIALOG_NOTIFY_ERROR",
        "RESIP_RUNTIME_WORKER_ERROR",
    }
)

# Native error lines go to stderr (see runtime_module.cxx ``std::cerr`` sites).
_ERROR_EVENTS = frozenset(
    {
        "RESIP_RUNTIME_FORWARD_ERROR",
        "RESIP_RUNTIME_UAC_CORRELATION_MISS",
        "RESIP_RUNTIME_OUTBOUND_CANCEL_ERROR",
        "RESIP_RUNTIME_ANSWER_RELAY_ERROR",
        "RESIP_RUNTIME_CALLBACK_ERROR",
        "RESIP_RUNTIME_DIALOG_CALLBACK_ERROR",
        "RESIP_RUNTIME_DIALOG_NOTIFY_ERROR",
        "RESIP_RUNTIME_WORKER_ERROR",
    }
)

# Events tied to the outbound (UAC) leg of the two-leg forward path.
_OUTBOUND_EVENTS = frozenset(
    {
        "RESIP_RUNTIME_UAC_INVITE_SENT",
        "RESIP_RUNTIME_UAC_NEW_SESSION",
        "RESIP_RUNTIME_UAC_FAILURE",
        "RESIP_RUNTIME_UAS_FAILURE_MAPPED",
        "RESIP_RUNTIME_UAS_ANSWER_RELAYED",
    }
)


@dataclass(frozen=True)
class ResipRuntimeLogEvent:
    """One parsed ``RESIP_RUNTIME_*`` line: event name plus string fields."""

    event: str
    fields: dict[str, str] = field(default_factory=dict)

    def to_nf13_fields(self) -> dict[str, str | None]:
        """Map this event onto REQ-NF-13 log keys.

        Native lines carry no timestamp/level (Python enrichment in
        ``resip_runtime.emit_native_log_event`` fills those in), so timestamp is
        always ``None`` here and level is derived from the error allowlist.
        """
        call_id = self.fields.get("outgoing_call_id") or self.fields.get("inbound_call_id")
        if "CANCEL" in self.event:
            method: str | None = "CANCEL"
            direction: str | None = "inbound"
        elif self.event in _OUTBOUND_EVENTS:
            method = "INVITE"
            direction = "outbound"
        else:
            method = None
            direction = None
        return {
            "timestamp": None,
            "level": "error" if self.event in _ERROR_EVENTS else "info",
            "trace_id": call_id,
            "call_id": call_id,
            "direction": direction,
            "method": method,
        }


def is_resip_runtime_log_line(line: str) -> bool:
    """Return ``True`` when ``line`` looks like a native runtime log line."""
    return parse_resip_runtime_log_line(line) is not None


def parse_resip_runtime_log_line(line: str) -> ResipRuntimeLogEvent | None:
    """Parse one stdout/stderr line into an event, or ``None`` when not ours.

    Format: ``RESIP_RUNTIME_<EVENT> [key=value ...]``. Values contain no spaces
    in current C++ emitters (Call-IDs, URIs, ports, numeric statuses); a token
    without ``=`` after the event name means the line drifted and fails closed.
    """
    text = line.strip()
    if not text.startswith(_LOG_PREFIX):
        return None
    head, _, tail = text.partition(" ")
    if head not in _KNOWN_EVENTS:
        return None
    fields: dict[str, str] = {}
    if tail:
        tokens = tail.split()
        # Single bare word (``RESIP_RUNTIME_RELOAD_CERTIFICATES invoked``) is a
        # fixed C++ literal, recorded as detail; anything else without ``=``
        # means the format drifted and fails closed.
        if len(tokens) == 1 and "=" not in tokens[0]:
            fields["detail"] = tokens[0]
        else:
            for token in tokens:
                key, separator, value = token.partition("=")
                if not separator or not key or not value:
                    return None
                fields[key] = value
    return ResipRuntimeLogEvent(event=head, fields=fields)
