"""Bridge kernel SIP decisions to call-path metrics (M5.1 / M7 seam)."""

from __future__ import annotations

from as_platform.decision.decide import DecisionAction
from as_platform.sip.adapter import STATUS_CONTINUE, decision_to_status_code
from as_platform.telemetry.metrics import CallMetrics


def record_sip_status_code(
    call_metrics: CallMetrics,
    use_case: str,
    status_code: int,
) -> None:
    """Record one SIP response on the call-path metrics (deploy/alerts contract)."""
    call_metrics.record_response(use_case, status_code)


def record_terminal_decision_response(
    call_metrics: CallMetrics,
    use_case: str,
    action: DecisionAction,
) -> None:
    """Count terminal SIP responses implied by a kernel decision.

    ``FORWARD`` / ``TRANSLATE`` do not emit a terminal SIP code at the boundary.
    The product SIP adapter must call this when it sends a final response (M7).
    """
    status_code = decision_to_status_code(action)
    if status_code == STATUS_CONTINUE:
        return
    call_metrics.record_response(use_case, status_code)
