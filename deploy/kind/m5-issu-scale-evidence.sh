#!/usr/bin/env bash
# M5 §217①② + H10: kind evidence for draining/ISSU and plan_scale_down from live metrics.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=deploy/kind/m5-lib.sh
source "${ROOT}/deploy/kind/m5-lib.sh"
# shellcheck source=deploy/kind/m5-metrics-lib.sh
source "${ROOT}/deploy/kind/m5-metrics-lib.sh"

NS="${K8S_NAMESPACE:-as-m5}"
RELEASE="${HELM_RELEASE_NAME:-as}"
CLUSTER="${KIND_CLUSTER_NAME:-as-m5}"
SIM_CALLS="${M5_SIMULATED_ACTIVE_CALLS:-3}"
DATE="$(date -u +%Y-%m-%d)"
ART="${ROOT}/artifacts/m5/${DATE}"
mkdir -p "${ART}"
LOG="${ART}/issu-scale-evidence.log"
exec > >(tee -a "${LOG}") 2>&1

echo "==> M5 ISSU/scale evidence (${DATE}) namespace=${NS} simulated_calls=${SIM_CALLS}"

kubectl config use-context "kind-${CLUSTER}" >/dev/null

TR_DEPLOY="$(m5_use_case_deployment "${NS}" translation "${RELEASE}")"
AF_DEPLOY="$(m5_use_case_deployment "${NS}" anti-fraud "${RELEASE}")"

echo "==> set AS_M5_SIMULATED_ACTIVE_CALLS on ${TR_DEPLOY}"
kubectl -n "${NS}" set env "deployment/${TR_DEPLOY}" "AS_M5_SIMULATED_ACTIVE_CALLS=${SIM_CALLS}"
kubectl -n "${NS}" rollout status "deployment/${TR_DEPLOY}" --timeout=180s
sleep 2
TR_POD="$(m5_list_use_case_pods "${NS}" translation "${RELEASE}" | head -1)"
echo "translation pod=${TR_POD}"

calls="$(m5_pod_active_calls "${NS}" "${TR_POD}")"
echo "pre-issu as_active_calls=${calls}"
[[ "${calls}" -ge "${SIM_CALLS}" ]] || {
  echo "ERROR: expected as_active_calls >= ${SIM_CALLS}" >&2
  exit 1
}
ready="$(m5_pod_ready_http_code "${NS}" "${TR_POD}")"
echo "pre-issu /health/ready HTTP ${ready}"
[[ "${ready}" == "200" ]] || exit 1

echo "==> ISSU: delete pod (SIGTERM + draining)"
SAW_503=0
kubectl -n "${NS}" delete pod "${TR_POD}" --grace-period=120 --wait=false
deadline=$(( $(date +%s) + 90 ))
while kubectl -n "${NS}" get pod "${TR_POD}" >/dev/null 2>&1; do
  if [[ "$(date +%s)" -ge "${deadline}" ]]; then
    echo "ERROR: pod still terminating after 90s" >&2
    kubectl -n "${NS}" describe pod "${TR_POD}" | tail -20 >&2 || true
    exit 1
  fi
  code="$(m5_pod_ready_http_code "${NS}" "${TR_POD}" || echo 000)"
  cur_calls="$(m5_pod_active_calls "${NS}" "${TR_POD}" 2>/dev/null || echo "?")"
  echo "  terminating ready=${code} as_active_calls=${cur_calls}"
  if [[ "${code}" == "503" ]]; then
    SAW_503=1
  fi
  sleep 1
done
[[ "${SAW_503}" == "1" ]] || {
  echo "ERROR: never saw readiness 503 during drain" >&2
  exit 1
}
echo "ISSU drain: saw HTTP 503 during termination"

kubectl -n "${NS}" rollout status "deployment/${TR_DEPLOY}" --timeout=180s
TR_POD="$(m5_list_use_case_pods "${NS}" translation "${RELEASE}" | head -1)"
calls="$(m5_pod_active_calls "${NS}" "${TR_POD}")"
echo "post-issu pod=${TR_POD} as_active_calls=${calls}"
[[ "${calls}" -ge "${SIM_CALLS}" ]] || exit 1

echo "==> H10: plan_scale_down allowed path (anti-fraud 2 -> 1, zero calls)"
kubectl -n "${NS}" scale "deployment/${AF_DEPLOY}" --replicas=2
kubectl -n "${NS}" rollout status "deployment/${AF_DEPLOY}" --timeout=180s
bash "${ROOT}/deploy/kind/m5-plan-scale-down-from-metrics.sh" anti-fraud 1
kubectl -n "${NS}" scale "deployment/${AF_DEPLOY}" --replicas=1
kubectl -n "${NS}" rollout status "deployment/${AF_DEPLOY}" --timeout=180s

echo "==> H10: plan_scale_down blocked path (translation 2 replicas, simulated calls)"
kubectl -n "${NS}" scale "deployment/${TR_DEPLOY}" --replicas=2
kubectl -n "${NS}" rollout status "deployment/${TR_DEPLOY}" --timeout=180s
set +e
bash "${ROOT}/deploy/kind/m5-plan-scale-down-from-metrics.sh" translation 1
blocked_rc=$?
set -e
[[ "${blocked_rc}" -ne 0 ]] || {
  echo "ERROR: expected plan_scale_down to refuse translation 2->1 with active calls" >&2
  exit 1
}
echo "blocked scale-down: plan correctly refused (exit ${blocked_rc})"

echo "==> restore replicas and simulation env"
kubectl -n "${NS}" scale "deployment/${TR_DEPLOY}" --replicas=1
kubectl -n "${NS}" rollout status "deployment/${TR_DEPLOY}" --timeout=180s
kubectl -n "${NS}" set env "deployment/${TR_DEPLOY}" AS_M5_SIMULATED_ACTIVE_CALLS-

echo "issu-scale-evidence: OK log=${LOG}"
