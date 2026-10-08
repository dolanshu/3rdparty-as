"""Unit tests for decision → SIP metrics bridge."""

from __future__ import annotations

import pytest

from as_platform.decision.decide import DecisionAction
from as_platform.sip.metrics_bridge import record_terminal_decision_response
from as_platform.telemetry.metrics import SIP_RESPONSES_TOTAL, CallMetrics, MetricsRegistry

pytestmark = pytest.mark.unit


def test_records_terminal_codes_only() -> None:
    registry = MetricsRegistry()
    metrics = CallMetrics(registry)
    record_terminal_decision_response(metrics, "translation", DecisionAction.DECLINE)
    record_terminal_decision_response(metrics, "translation", DecisionAction.FORWARD)
    points = [p for p in registry.snapshot() if p.name == SIP_RESPONSES_TOTAL]
    assert len(points) == 1
    assert points[0].labels["status_code"] == "603"
