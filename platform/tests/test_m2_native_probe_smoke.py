"""Optional integration smoke for the native resip_probe S1 UDP path (M2 P0).

Runs only when a built ``resip_probe`` is available via ``AS_RESIP_PROBE_BIN``
or the default repo cache path from ``m2-native.sh``. Otherwise skipped.
"""

from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PROBE = _REPO_ROOT / ".cache/m2-resiprocate/probe-build/resip_probe"
_SUCCESS_MARKERS = ("probe 退出 OK", "probe exit OK", "=== probe")
_S1_DONE_MARKER = "reason=RemoteBye"
_POLL_INTERVAL_S = 0.1
_TIMEOUT_S = 120.0


def _resolve_probe_bin() -> Path | None:
    env = os.environ.get("AS_RESIP_PROBE_BIN")
    if env:
        path = Path(env)
        return path if path.is_file() else None
    return _DEFAULT_PROBE if _DEFAULT_PROBE.is_file() else None


def test_m2_native_probe_s1_smoke() -> None:
    probe = _resolve_probe_bin()
    if probe is None:
        pytest.skip("resip_probe not built; run make m2-native or set AS_RESIP_PROBE_BIN")

    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "probe.log"
        with log_path.open("w") as log_file:
            proc = subprocess.Popen(
                [str(probe), "S1"],
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
            deadline = time.monotonic() + _TIMEOUT_S
            try:
                while proc.poll() is None:
                    log_file.flush()
                    combined = log_path.read_text(errors="replace")
                    if _S1_DONE_MARKER in combined:
                        proc.send_signal(signal.SIGINT)
                        break
                    if time.monotonic() >= deadline:
                        proc.send_signal(signal.SIGINT)
                        proc.wait(timeout=10)
                        pytest.fail(f"resip_probe S1 smoke timed out after {_TIMEOUT_S}s")
                    time.sleep(_POLL_INTERVAL_S)
                proc.wait(timeout=10)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
            log_file.flush()

        combined = log_path.read_text(errors="replace")

    assert proc.returncode == 0, combined
    assert any(marker in combined for marker in _SUCCESS_MARKERS), combined
