"""Unit tests for the HTTP health and metrics server."""

from __future__ import annotations

import http.client

import pytest

from as_platform.runtime.health import HealthServer, HealthServerConfig
from as_platform.telemetry.metrics import CallMetrics, MetricsRegistry

pytestmark = pytest.mark.unit


def test_ready_flips_when_draining() -> None:
    import socket

    registry = MetricsRegistry()
    ready = True

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    server = HealthServer(
        HealthServerConfig(host="127.0.0.1", port=port),
        is_ready=lambda: ready,
        metrics_registry=registry,
    )
    server.start()
    try:

        def get(path: str) -> int:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            conn.request("GET", path)
            response = conn.getresponse()
            response.read()
            conn.close()
            return response.status

        assert get("/health/live") == 200
        assert get("/health/ready") == 200
        ready = False
        assert get("/health/ready") == 503
        metrics = CallMetrics(registry)
        metrics.set_active_calls("pod-a", "translation", 2)
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("GET", "/metrics")
        body = conn.getresponse().read().decode()
        conn.close()
        assert "as_active_calls" in body
    finally:
        server.stop()
