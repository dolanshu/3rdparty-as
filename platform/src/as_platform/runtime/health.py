"""Minimal HTTP health and Prometheus metrics for Kubernetes probes (M5)."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from as_platform.telemetry.metrics import MetricsRegistry, render_prometheus_text


@dataclass(frozen=True)
class HealthServerConfig:
    """Binding and behaviour for the health server.

    Attributes:
        host: Listen address.
        port: Listen port (``AS_HEALTH_PORT`` in deployment).
    """

    host: str = "0.0.0.0"
    port: int = 8080


class HealthServer:
    """Serves liveness/readiness and a Prometheus metrics snapshot."""

    def __init__(
        self,
        config: HealthServerConfig,
        *,
        is_ready: Callable[[], bool],
        metrics_registry: MetricsRegistry,
    ) -> None:
        """Bind readiness predicate and metrics for HTTP handlers."""
        self._config = config
        self._is_ready = is_ready
        self._metrics_registry = metrics_registry
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Listen in a background thread; safe to call twice."""
        if self._httpd is not None:
            return

        registry = self._metrics_registry
        ready = self._is_ready

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format: str, *_args: Any) -> None:
                return

            def do_GET(self) -> None:
                if self.path == "/health/live":
                    self._respond(200, b"ok\n")
                    return
                if self.path == "/health/ready":
                    if ready():
                        self._respond(200, b"ready\n")
                    else:
                        self._respond(503, b"draining\n")
                    return
                if self.path == "/metrics":
                    body = render_prometheus_text(registry).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self._respond(404, b"not found\n")

            def _respond(self, status: int, body: bytes) -> None:
                self.send_response(status)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self._httpd = ThreadingHTTPServer((self._config.host, self._config.port), Handler)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="as-health-http",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Shut down the listener and join the worker thread."""
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
