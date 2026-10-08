"""Tests for SIP respond + metrics wiring (M5.1 G-4 / M7 seam)."""

from __future__ import annotations

import pytest

from as_platform.sip.adapter import SipRequestView, respond_with_metrics
from as_platform.telemetry.metrics import SIP_RESPONSES_TOTAL, CallMetrics, MetricsRegistry

pytestmark = pytest.mark.unit


class _StubAdapter:
    def respond(self, view: SipRequestView, status_code: int) -> bytes:
        return f"{status_code}:{view.call_id}".encode()

    def parse(self, raw: bytes) -> SipRequestView | None:
        raise NotImplementedError

    def forward(self, view: SipRequestView, target: str) -> bytes:
        raise NotImplementedError


def test_respond_with_metrics_increments_counter() -> None:
    registry = MetricsRegistry()
    metrics = CallMetrics(registry)
    view = SipRequestView(
        method="INVITE",
        request_uri="sip:x",
        call_id="c-1",
        calling_number="1",
        called_number="2",
        body=b"",
    )
    body = respond_with_metrics(_StubAdapter(), metrics, "translation", view, 404)
    assert body == b"404:c-1"
    points = [p for p in registry.snapshot() if p.name == SIP_RESPONSES_TOTAL]
    assert len(points) == 1
    assert points[0].labels["status_code"] == "404"
