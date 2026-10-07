"""Operator page for the simulation platform.

The page does not authenticate. It is not the product console and it does not
share that console's session. Counts on the page are one run, not a capacity
commitment. TLS material is a test CA, not an operator PKI.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from as_load.harness import LoadConfig, run_load
from as_load.scenarios import FIRST_EDITION
from as_simulators.platform import LocalPlatform

_STATIC = Path(__file__).resolve().parent / "static"
_CAPACITY_NOTE = (
    "Counts and latencies describe this run only. They are not a published capacity target."
)


class RunController:
    """One load run at a time, aimed at the simulated S-CSCF."""

    def __init__(self, platform: LocalPlatform) -> None:
        """Bind the controller to a started platform."""
        self.platform = platform
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._running = False
        self._summary: dict[str, Any] | None = None
        self._error: str | None = None
        self._request: dict[str, Any] | None = None

    def snapshot(self) -> dict[str, Any]:
        """Return the latest run state."""
        with self._lock:
            return {
                "running": self._running,
                "error": self._error,
                "request": self._request,
                "summary": _public_summary(self._summary),
                "capacity_commitment": False,
                "capacity_note": _CAPACITY_NOTE,
                "pki": "test-ca",
                "pki_notice": "非运营商 PKI",
            }

    def start(self, body: dict[str, Any], output_dir: Path) -> None:
        """Validate the request and start a run.

        Raises:
            ValueError: The request names no call type, an unknown call type,
                a transport that is not listening, or a load value out of range.
            RuntimeError: A run is already active.
        """
        config = self._config(body, output_dir)
        with self._lock:
            if self._running:
                raise RuntimeError("a run is already active")
            self._running = True
            self._error = None
            self._summary = None
            self._request = {
                "transport": config.transport,
                "scenarios": list(config.scenarios),
                "cps": config.target_cps,
                "duration_seconds": config.duration_seconds,
                "hold_seconds": config.hold_seconds,
                "workers": config.workers,
            }
            self._stop = threading.Event()
        self._thread = threading.Thread(target=self._execute, args=(config,), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Ask the scheduler to stop starting new attempts."""
        self._stop.set()

    def wait(self, timeout: float) -> None:
        """Block until the active run finishes or ``timeout`` passes."""
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def _config(self, body: dict[str, Any], output_dir: Path) -> LoadConfig:
        transport = str(body.get("transport", "udp"))
        if transport not in self.platform.transports:
            raise ValueError(f"transport {transport} is not listening")
        raw = body.get("scenarios", [])
        if not isinstance(raw, list) or not raw:
            raise ValueError("select at least one call type")
        try:
            return LoadConfig(
                host=self.platform.host,
                port=self.platform.port("scscf", transport),
                target_cps=float(body.get("cps", 1)),
                duration_seconds=float(body.get("duration_seconds", 1)),
                hold_seconds=float(body.get("hold_seconds", 2)),
                workers=int(body.get("workers", 32)),
                timeout_seconds=float(body.get("timeout_seconds", 5)),
                stack_name="ims-sim",
                stack_version="m7.1",
                output_dir=output_dir,
                transport=transport,
                tls_ca_file=self.platform.tls_ca,
                scenarios=tuple(str(item) for item in raw),
            )
        except (TypeError, KeyError) as error:
            raise ValueError(str(error)) from error

    def _execute(self, config: LoadConfig) -> None:
        try:
            summary = run_load(config, stop_event=self._stop)
        except Exception as error:
            with self._lock:
                self._error = str(error)
                self._running = False
            return
        with self._lock:
            self._summary = summary
            self._running = False


def _public_summary(summary: dict[str, Any] | None) -> dict[str, Any] | None:
    if summary is None:
        return None
    counts = summary.get("counts", {})
    return {
        "invites_sent": counts.get("invite_datagrams_sent", 0),
        "established": counts.get("established_sessions", 0),
        "failed": int(counts.get("invite_datagrams_sent", 0))
        - int(counts.get("established_sessions", 0)),
        "response_code_distribution": summary.get("response_code_distribution", {}),
        "error_distribution": summary.get("error_distribution", {}),
        "unresolved": counts.get("unresolved_sessions", 0),
        "peak_established": counts.get("peak_established_sessions", 0),
        "setup_latency_ms": summary.get("setup_latency_ms", {}),
        "by_scenario": summary.get("by_scenario", {}),
        "capacity_commitment": False,
        "capacity_note": summary.get("capacity_note", _CAPACITY_NOTE),
    }


def serve_ui(platform: LocalPlatform, host: str, port: int, output_dir: Path) -> None:
    """Serve the static page and the run API until the process is stopped."""
    server = make_ui_server(platform, host, port, output_dir)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def make_ui_server(
    platform: LocalPlatform, host: str, port: int, output_dir: Path
) -> ThreadingHTTPServer:
    """Bind the page and its run API. The caller runs ``serve_forever``.

    Args:
        platform: Where the S-CSCF listens. Load is aimed only there.
        host: Bind address.
        port: Bind port. ``0`` asks the kernel for one.
        output_dir: Where each run writes its summary.

    Returns:
        A bound server. Its ``controller`` attribute is the run controller.
    """
    controller = RunController(platform)
    output_dir.mkdir(parents=True, exist_ok=True)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/api/meta":
                self._json(
                    {
                        "scenarios": [
                            {
                                "id": item.scenario_id,
                                "title": item.title,
                                "description": item.description,
                            }
                            for item in FIRST_EDITION
                        ],
                        "transports": list(platform.transports),
                        "pki_notice": "非运营商 PKI",
                        "capacity_note": _CAPACITY_NOTE,
                        "login_required": False,
                    }
                )
                return
            if path == "/api/runs/latest":
                self._json(controller.snapshot())
                return
            if path in {"/", "/index.html"}:
                self._file(_STATIC / "index.html", "text/html; charset=utf-8")
                return
            if path == "/app.css":
                self._file(_STATIC / "app.css", "text/css; charset=utf-8")
                return
            if path == "/app.js":
                self._file(_STATIC / "app.js", "text/javascript; charset=utf-8")
                return
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/api/runs":
                try:
                    controller.start(self._body(), output_dir)
                except RuntimeError as error:
                    self._json({"error": str(error)}, status=409)
                    return
                except (ValueError, TypeError) as error:
                    self._json({"error": str(error)}, status=400)
                    return
                self._json({"started": True})
                return
            if path == "/api/runs/stop":
                controller.stop()
                self._json({"stopping": True})
                return
            self.send_error(404)

        def _body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            parsed = json.loads(raw.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise ValueError("JSON object required")
            return parsed

        def _json(self, payload: dict[str, Any], status: int = 200) -> None:
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _file(self, path: Path, content_type: str) -> None:
            if not path.is_file():
                self.send_error(404)
                return
            payload = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

    server = ThreadingHTTPServer((host, port), Handler)
    server.controller = controller  # type: ignore[attr-defined]
    return server
