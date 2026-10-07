#!/usr/bin/env bash
# Quick M5 acceptance checks: gate + chart + kind cluster smoke (existing as-m5).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=deploy/kind/m5-lib.sh
source "${ROOT}/deploy/kind/m5-lib.sh"
NS="${K8S_NAMESPACE:-as-m5}"
CLUSTER="${KIND_CLUSTER_NAME:-as-m5}"

cd "${ROOT}"
echo "==> make gate"
make gate
echo "==> make chart-check"
make chart-check

if ! kubectl config get-contexts -o name 2>/dev/null | grep -qx "kind-${CLUSTER}"; then
  # K-1 (M5.1 minimal): a missing cluster is evidence failure (nonzero exit),
  # not a silent SKIP that still prints OK. See ADR-0013.
  echo "ERROR: no kind-${CLUSTER} context (run make m5-cluster-evidence first)" >&2
  exit 1
fi

kubectl config use-context "kind-${CLUSTER}"
echo "==> pods in ${NS}"
kubectl -n "${NS}" get pods

TR_POD="$(kubectl -n "${NS}" get pod -l app.kubernetes.io/use-case=translation -o jsonpath='{.items[0].metadata.name}')"
kubectl -n "${NS}" exec "${TR_POD}" -- python -c \
  "import urllib.request; lines=urllib.request.urlopen('http://127.0.0.1:8080/metrics').read().decode().splitlines(); assert any(l.startswith('as_active_calls') for l in lines); print(lines[1])"

CFG_POD="$(kubectl -n "${NS}" get pod -l app.kubernetes.io/component=config-service -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
if [[ -n "${CFG_POD}" ]]; then
  kubectl -n "${NS}" wait --for=condition=ready "pod/${CFG_POD}" --timeout=120s
  m5_noproxy_env
  kubectl -n "${NS}" port-forward "pod/${CFG_POD}" 18000:8000 >/tmp/m5-pf.log 2>&1 &
  PF_PID=$!
  sleep 2
  CODE="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18000/ || echo 000)"
  kill "${PF_PID}" 2>/dev/null || true
  wait "${PF_PID}" 2>/dev/null || true
  echo "config-service via port-forward (NO_PROXY): HTTP ${CODE}"
  [[ "${CODE}" == "200" ]] || { echo "ERROR: expected 200 from config-service" >&2; exit 1; }
else
  # K-1 (M5.1 minimal): a missing config-service Pod fails the run instead of
  # WARN-skipping the assertion while still printing OK.
  echo "ERROR: no config-service pod (ingress evidence not run?)" >&2
  exit 1
fi

echo "m5-verify: OK"
