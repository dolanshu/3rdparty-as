"""Optional integration smoke: as_load against product ResipRuntimeListener (M6)."""

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

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[3]
_LOAD_UAS = _REPO_ROOT / "platform/tests/fixtures/load_uas_runtime.py"
_DEFAULT_BUILD = _REPO_ROOT / "platform/native/resip_runtime/build"
_LISTEN_RE = re.compile(r"RESIP_RUNTIME_LISTENING address=127\.0\.0\.1 udp_port=(\d+)")
_POLL_INTERVAL_S = 0.1
_START_TIMEOUT_S = 60.0
_LOAD_TIMEOUT_S = 30.0


def _runtime_extension_built() -> bool:
    build_dir = Path(os.environ.get("AS_RESIP_RUNTIME_BUILD", _DEFAULT_BUILD))
    if (build_dir / "_resip_runtime.so").is_file():
        return True
    return any(build_dir.glob("_resip_runtime*.so"))


def test_product_resip_runtime_uas_smoke() -> None:
    if not _runtime_extension_built():
        pytest.skip("platform resip_runtime extension not built; run make m2-platform-resip-build")

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "load-evidence"
        out_dir.mkdir()
        log_path = Path(tmp) / "uas.log"

        write_fd = os.open(os.fspath(log_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
        proc = subprocess.Popen(
            ["uv", "run", "python", str(_LOAD_UAS)],
            cwd=_REPO_ROOT,
            stdout=write_fd,
            stderr=subprocess.STDOUT,
        )
        os.close(write_fd)
        port_holder: list[int] = []
        port_ready = threading.Event()

        def _poll_uas_log() -> None:
            while not port_ready.is_set() and proc.poll() is None:
                combined = log_path.read_text(errors="replace")
                match = _LISTEN_RE.search(combined)
                if match:
                    port_holder.append(int(match.group(1)))
                    port_ready.set()
                    return
                time.sleep(_POLL_INTERVAL_S)

        poller = threading.Thread(target=_poll_uas_log, daemon=True)
        poller.start()

        load: subprocess.CompletedProcess[str] | None = None
        try:
            if not port_ready.wait(timeout=_START_TIMEOUT_S):
                combined = log_path.read_text(errors="replace")
                pytest.fail(f"timed out waiting for RESIP_RUNTIME_LISTENING:\n{combined}")
            if proc.poll() is not None and not port_holder:
                combined = log_path.read_text(errors="replace")
                pytest.fail(f"load_uas_runtime exited before listen line:\n{combined}")
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
                    "1",
                    "--duration",
                    "0.2",
                    "--hold",
                    "0",
                    "--workers",
                    "1",
                    "--timeout",
                    "5",
                    "--stack",
                    "as-platform-resip-runtime",
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
        assert summary["counts"]["established_sessions"] >= 1
