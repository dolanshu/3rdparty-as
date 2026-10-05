#!/usr/bin/env bash
# REQ-NF-1 engineering harness (not maintainer D10 sign-off).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
timeout 40m make m2-platform-resip-build m7-platform-recovery-build
uv run pytest platform/tests/test_d10_req_nf1_harness_integration.py -m integration -q
