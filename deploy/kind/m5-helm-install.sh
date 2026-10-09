#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=scripts/lib/repo-toolchain.sh
source "${ROOT}/scripts/lib/repo-toolchain.sh"
repo_toolchain_prepend_path "${ROOT}"
CLUSTER_NAME="${KIND_CLUSTER_NAME:-as-m5}"
RELEASE="${HELM_RELEASE_NAME:-as}"
PLATFORM_TAG="${AS_PLATFORM_IMAGE:-as-platform:m5}"
HELM="$(repo_require_helm "${ROOT}")"

kubectl config use-context "kind-${CLUSTER_NAME}"
kubectl create namespace as-m5 --dry-run=client -o yaml | kubectl apply -f -

BUNDLED_STATE="${M5_BUNDLED_STATE:-1}"
STATE_SET=()
if [[ "${BUNDLED_STATE}" == "1" ]]; then
  STATE_SET=(
    --set stateStores.enabled=true
    --set stateStores.bootstrapDevCredentials=true
    --set stateStores.networkPolicy.enabled=true
  )
  echo "==> ADR-0026 bundled in-cluster PostgreSQL + Redis (M5 §4.6 / D12 kind profile)"
fi

kubectl create secret generic as-m5-dev-tls -n as-m5 \
  --from-literal=tls.crt=dev \
  --from-literal=tls.key=dev \
  --from-literal=ca.crt=dev \
  --dry-run=client -o yaml | kubectl apply -f -

"${HELM}" upgrade --install "${RELEASE}" "${ROOT}/deploy/helm" \
  --namespace as-m5 \
  --set image.repository="${PLATFORM_TAG%%:*}" \
  --set image.tag="${PLATFORM_TAG##*:}" \
  --set sip.peerAllowlist=10.0.0.0/8 \
  --set tls.secretName=as-m5-dev-tls \
  --set m5.probeSipStatusCode=404 \
  "${STATE_SET[@]}" \
  --wait --timeout 300s

kubectl -n as-m5 rollout status deployment -l "app.kubernetes.io/instance=${RELEASE}" --timeout=300s
if [[ "${BUNDLED_STATE}" == "1" ]]; then
  kubectl -n as-m5 rollout status "statefulset/${RELEASE}-3rdparty-as-postgres" --timeout=300s 2>/dev/null \
    || kubectl -n as-m5 rollout status statefulset -l app.kubernetes.io/component=state-postgres --timeout=300s
  kubectl -n as-m5 rollout status deployment -l app.kubernetes.io/component=state-redis --timeout=300s
fi
