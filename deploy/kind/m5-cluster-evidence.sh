#!/usr/bin/env bash
# M5-3a/b + 7.2d: kind cluster evidence bundle (plan.md §4.4).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DATE="$(date -u +%Y-%m-%d)"
ART="${ROOT}/artifacts/m5/${DATE}"
mkdir -p "${ART}"
LOG="${ART}/cluster-evidence.log"
exec > >(tee -a "${LOG}") 2>&1

echo "M5 cluster evidence ${DATE}"
cd "${ROOT}"

if [[ ! -f deploy/compose/certs/tls.crt ]]; then
  (cd deploy/compose && ./scripts/gen-certs.sh)
fi

./deploy/kind/m5-kind-up.sh
./deploy/kind/m5-images.sh
./deploy/kind/m5-helm-install.sh
./deploy/kind/m5-rollout-scale.sh   # includes m5-issu-scale-evidence.sh
./deploy/kind/m5-ingress-evidence.sh

echo "DONE log=${LOG}"
