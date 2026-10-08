#!/usr/bin/env bash
# Write redacted M5.1 verification transcripts into docs/acceptance/artifacts/m5/ (review G-1 / G-5).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DATE="${M5_ARTIFACT_DATE:-$(date -u +%Y-%m-%d)}"
OUT="${ROOT}/docs/acceptance/artifacts/m5/${DATE}"
mkdir -p "${OUT}"

export NO_COLOR=1
export TERM=dumb
if [[ -x /tmp/prometheus-2.55.1.linux-amd64/promtool ]]; then
  export PATH="/tmp/prometheus-2.55.1.linux-amd64:${PATH}"
fi

strip_ansi() {
  sed -E 's/\x1B\[[0-9;]*[[:alpha:]]//g'
}

cd "${ROOT}"
echo "==> gate"
make gate 2>&1 | strip_ansi >"${OUT}/gate-full.txt"
tail -5 "${OUT}/gate-full.txt" >"${OUT}/gate-sample.txt"

echo "==> chart-check"
make chart-check 2>&1 | strip_ansi >"${OUT}/chart-check-full.txt"
cp "${OUT}/chart-check-full.txt" "${OUT}/chart-check-sample.txt"

echo "==> alert-check"
make alert-check 2>&1 | strip_ansi >"${OUT}/alert-check-full.txt"
cp "${OUT}/alert-check-full.txt" "${OUT}/alert-check-sample.txt"

CLUSTER="${KIND_CLUSTER_NAME:-as-m5}"
STRICT_LOG="${OUT}/m5-strict-context.txt"
{
  echo "M5_STRICT=1 cluster=kind-${CLUSTER}"
  echo "host has no guarantee of a live kind cluster; this transcript records the fail-closed path."
} >"${STRICT_LOG}"
set +e
bash -c "source '${ROOT}/deploy/kind/m5-lib.sh'; export M5_STRICT=1; export KIND_CLUSTER_NAME='${CLUSTER}'; m5_require_kind_context" \
  >>"${STRICT_LOG}" 2>&1
STRICT_RC=$?
set -e
echo "exit=${STRICT_RC}" >>"${STRICT_LOG}"
if kubectl config get-contexts -o name 2>/dev/null | grep -qx "kind-${CLUSTER}"; then
  if [[ "${STRICT_RC}" -ne 0 ]]; then
    echo "ERROR: kind-${CLUSTER} exists but strict context check failed" >&2
    exit 1
  fi
  echo "==> live cluster: M5_STRICT=1 m5-verify (may take several minutes)"
  set +e
  M5_STRICT=1 bash "${ROOT}/deploy/kind/m5-verify.sh" 2>&1 | strip_ansi >"${OUT}/m5-verify-strict.txt"
  echo "m5-verify exit=${PIPESTATUS[0]}" >>"${OUT}/m5-verify-strict.txt"
  set -e
else
  if [[ "${STRICT_RC}" -eq 0 ]]; then
    echo "ERROR: missing kind-${CLUSTER} must fail under M5_STRICT=1" >&2
    exit 1
  fi
  echo "no live kind-${CLUSTER}; fail-closed transcript is ${STRICT_LOG}" >>"${STRICT_LOG}"
fi

echo "m5-record-artifacts: wrote under ${OUT}"
