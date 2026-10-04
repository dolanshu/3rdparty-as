#!/usr/bin/env bash
# H10 / ADR-0010: build InstanceLoad rows from live /metrics and run plan_scale_down.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=deploy/kind/m5-metrics-lib.sh
source "${ROOT}/deploy/kind/m5-metrics-lib.sh"

NS="${K8S_NAMESPACE:-as-m5}"
RELEASE="${HELM_RELEASE_NAME:-as}"
USE_CASE="${1:?use-case name (e.g. anti-fraud)}"
DESIRED="${2:?desired replica count}"

pods="$(m5_list_use_case_pods "${NS}" "${USE_CASE}" "${RELEASE}")"
if [[ -z "${pods}" ]]; then
  echo "no pods for use-case=${USE_CASE}" >&2
  exit 1
fi

loads=()
while IFS= read -r pod; do
  [[ -z "${pod}" ]] && continue
  calls="$(m5_pod_active_calls "${NS}" "${pod}")"
  loads+=("${pod}:${calls}:false")
done <<<"${pods}"

cd "${ROOT}"
export M5_LOADS="${loads[*]}"
export M5_DESIRED="${DESIRED}"
uv run python - <<'PY'
import os
from as_platform.ops.downscale_guard import InstanceLoad, plan_scale_down

raw = os.environ.get("M5_LOADS", "").split()
loads = []
for item in raw:
    pod, calls, draining = item.split(":")
    loads.append(
        InstanceLoad(
            instance_id=pod,
            active_calls=int(calls),
            draining=draining.lower() == "true",
        )
    )
desired = int(os.environ["M5_DESIRED"])
plan = plan_scale_down(tuple(loads), desired_replicas=desired, protect_above=0)
print("instances", len(loads))
print("desired_replicas", desired)
print("allowed", plan.allowed)
print("candidates", plan.candidates)
print("reason", plan.reason)
if not plan.allowed and desired < len(loads):
    raise SystemExit(1)
PY
