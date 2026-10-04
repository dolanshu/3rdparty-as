#!/usr/bin/env bash
# M5-3a/b: rollout restart + ISSU/scale evidence (§217①②, H10).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=deploy/kind/m5-metrics-lib.sh
source "${ROOT}/deploy/kind/m5-metrics-lib.sh"
NS="${K8S_NAMESPACE:-as-m5}"
RELEASE="${HELM_RELEASE_NAME:-as}"

deploy="$(m5_use_case_deployment "${NS}" anti-fraud "${RELEASE}")"
echo "==> rollout restart ${deploy}"
kubectl -n "${NS}" rollout restart "deployment/${deploy}"
kubectl -n "${NS}" rollout status "deployment/${deploy}" --timeout=180s

bash "${ROOT}/deploy/kind/m5-issu-scale-evidence.sh"
echo "rollout-scale: OK"
