"""The test page drives call load through its own HTTP API."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

import pytest

from as_simulators.platform import start_local_platform
from as_simulators.ui import make_ui_server

pytestmark = pytest.mark.integration

# The page is on loopback. A developer HTTP proxy must not sit in between.
_OPENER = build_opener(ProxyHandler({}))


def _get(base: str, path: str) -> Any:
    with _OPENER.open(base + path, timeout=5) as response:
        return json.loads(response.read())


def _post(base: str, path: str, body: dict[str, Any]) -> tuple[int, Any]:
    request = Request(
        base + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with _OPENER.open(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())


def _wait_finished(base: str, seconds: float) -> Any:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        snapshot = _get(base, "/api/runs/latest")
        if not snapshot["running"]:
            return snapshot
        time.sleep(0.1)
    raise AssertionError("run did not finish")


def test_page_selects_call_types_runs_each_transport_and_shows_analysis(tmp_path: Path) -> None:
    """The page lists the first edition, rejects bad input, and reports each run."""
    platform = start_local_platform(tls_directory=tmp_path / "ca")
    server = make_ui_server(platform, "127.0.0.1", 0, tmp_path / "runs")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with _OPENER.open(base + "/", timeout=5) as response:
            page = response.read().decode("utf-8")
        meta = _get(base, "/api/meta")

        missing, refused = _post(base, "/api/runs", {"transport": "udp", "scenarios": []})
        unknown, _ = _post(base, "/api/runs", {"transport": "udp", "scenarios": ["T9"]})
        negative, _ = _post(base, "/api/runs", {"scenarios": ["T5"], "cps": -1})

        results: dict[str, Any] = {}
        for transport in ("udp", "tcp", "tls"):
            code, started = _post(
                base,
                "/api/runs",
                {
                    "transport": transport,
                    "scenarios": ["T1", "T4", "T5", "F1", "F2"],
                    "cps": 10,
                    "duration_seconds": 0.5,
                    "hold_seconds": 0.2,
                    "workers": 10,
                },
            )
            assert (code, started) == (200, {"started": True})
            busy, _ = _post(base, "/api/runs", {"transport": transport, "scenarios": ["T5"]})
            assert busy == 409
            results[transport] = _wait_finished(base, 20)
    finally:
        server.shutdown()
        server.server_close()
        platform.close()

    assert "非运营商 PKI" in page
    assert 'type="password"' not in page
    assert "测试工具不登录" in page
    assert [item["id"] for item in meta["scenarios"]] == ["T1", "T4", "T5", "F1", "F2"]
    assert meta["login_required"] is False
    assert meta["transports"] == ["udp", "tcp", "tls"]
    assert missing == 400
    assert "call type" in refused["error"]
    assert unknown == 400
    assert negative == 400
    for transport, snapshot in results.items():
        summary = snapshot["summary"]
        assert snapshot["error"] is None, transport
        assert snapshot["request"]["transport"] == transport
        assert snapshot["pki_notice"] == "非运营商 PKI"
        assert summary["capacity_commitment"] is False
        assert summary["invites_sent"] == 5, transport
        assert summary["response_code_distribution"] == {"200": 3, "404": 1, "603": 1}
        assert summary["unresolved"] == 0, transport
        assert summary["by_scenario"]["F2"]["response_codes"] == {"603": 1}
        assert summary["by_scenario"]["T4"]["response_codes"] == {"404": 1}
