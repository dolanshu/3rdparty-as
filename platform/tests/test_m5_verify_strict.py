"""M5.1 G-5: strict kind scripts must fail when cluster context is missing."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_m5_require_kind_context_strict_exits_nonzero_without_cluster() -> None:
    repo = Path(__file__).resolve().parents[2]
    lib = repo / "deploy/kind/m5-lib.sh"
    cmd = (
        f"set -euo pipefail; source '{lib}'; "
        "export M5_STRICT=1; export KIND_CLUSTER_NAME=as-m5-nonexistent-strict-test; "
        "m5_require_kind_context"
    )
    result = subprocess.run(
        ["bash", "-c", cmd],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "kind-as-m5-nonexistent-strict-test" in result.stderr + result.stdout
