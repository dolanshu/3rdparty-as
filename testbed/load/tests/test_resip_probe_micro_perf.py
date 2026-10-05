"""Optional performance slice: short real-socket load vs resip_probe external UAS.

M6 precursor only. Establishes multi-session UDP load; not capacity or O1 evidence.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.performance

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_PROBE = _REPO_ROOT / ".cache/m2-resiprocate/probe-build/resip_probe"
_UAS_UDP_RE = re.compile(r"\[UAS\] 监听 UDP 127\.0\.0\.1:(\d+)")
_POLL_INTERVAL_S = 0.1
_START_TIMEOUT_S = 60.0
_LOAD_TIMEOUT_S = 120.0


def _resolve_probe_bin() -> Path | None:
    env = os.environ.get("AS_RESIP_PROBE_BIN")
    if env:
        path = Path(env)
        return path if path.is_file() else None
    return _DEFAULT_PROBE if _DEFAULT_PROBE.is_file() else None


def test_resip_probe_external_uas_micro_load_establishes_sessions() -> None:
    probe = _resolve_probe_bin()
    if probe is None:
        pytest.skip("resip_probe not built; run make m2-native-build or set AS_RESIP_PROBE_BIN")

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "load-evidence"
        out_dir.mkdir()
        log_path = Path(tmp) / "probe.log"

        write_fd = os.open(os.fspath(log_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
        proc = subprocess.Popen(
            [str(probe), "--external", "S1"],
            stdout=write_fd,
            stderr=subprocess.STDOUT,
        )
        os.close(write_fd)
        port_holder: list[int] = []
        port_ready = threading.Event()

        def _poll_probe_log() -> None:
            while not port_ready.is_set() and proc.poll() is None:
                combined = log_path.read_text(errors="replace")
                match = _UAS_UDP_RE.search(combined)
                if match:
                    port_holder.append(int(match.group(1)))
                    port_ready.set()
                    return
                time.sleep(_POLL_INTERVAL_S)

        poller = threading.Thread(target=_poll_probe_log, daemon=True)
        poller.start()

        load: subprocess.CompletedProcess[str] | None = None
        try:
            if not port_ready.wait(timeout=_START_TIMEOUT_S):
                combined = log_path.read_text(errors="replace")
                pytest.fail(f"timed out waiting for UAS UDP listen line:\n{combined}")
            if proc.poll() is not None and not port_holder:
                combined = log_path.read_text(errors="replace")
                pytest.fail(f"resip_probe exited before UAS listen line:\n{combined}")
            port = port_holder[0]

            load = subprocess.run(
                [
                    "uv",
                    "run",
                    "python",
                    "-m",
                    "as_load",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--cps",
                    "2",
                    "--duration",
                    "1",
                    "--hold",
                    "0.5",
                    "--workers",
                    "4",
                    "--timeout",
                    "5",
                    "--stack",
                    "resip-probe",
                    "--stack-version",
                    "1.14.0-632e215c",
                    "--out",
                    str(out_dir),
                ],
                cwd=_REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=_LOAD_TIMEOUT_S,
                check=False,
            )
        finally:
            if proc.poll() is None:
                proc.send_signal(signal.SIGINT)
            proc.wait(timeout=10)

        assert load is not None
        assert load.returncode == 0, load.stdout + load.stderr
        summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
        assert summary["counts"]["established_sessions"] > 0
