#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CLUSTER_NAME="${KIND_CLUSTER_NAME:-as-m5}"
RELEASE="${HELM_RELEASE_NAME:-as}"
PLATFORM_TAG="${AS_PLATFORM_IMAGE:-as-platform:m5}"
HELM="${HELM_BIN:-helm}"
if [[ ! -x "${HELM}" ]] && command -v helm >/dev/null 2>&1; then
  HELM=helm
fi

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

"${HELM}" upgrade --install "${RELEASE}" "${ROOT}/deploy/helm" \
  --namespace as-m5 \
  --set image.repository="${PLATFORM_TAG%%:*}" \
  --set image.tag="${PLATFORM_TAG##*:}" \
  "${STATE_SET[@]}" \
  --wait --timeout 300s

kubectl -n as-m5 rollout status deployment -l "app.kubernetes.io/instance=${RELEASE}" --timeout=300s
if [[ "${BUNDLED_STATE}" == "1" ]]; then
  kubectl -n as-m5 rollout status "statefulset/${RELEASE}-3rdparty-as-postgres" --timeout=300s 2>/dev/null \
    || kubectl -n as-m5 rollout status statefulset -l app.kubernetes.io/component=state-postgres --timeout=300s
  kubectl -n as-m5 rollout status deployment -l app.kubernetes.io/component=state-redis --timeout=300s
fi
