#!/usr/bin/env bash
# Compile first-edition rules on the as-m71 config-service database and mount
# the activated bundle into the translation process.
set -euo pipefail

# shellcheck source=scripts/demo-review/lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

demo_m71_require
# shellcheck source=scripts/lib/repo-toolchain.sh
source "${REPO_ROOT}/scripts/lib/repo-toolchain.sh"
repo_toolchain_prepend_path "${REPO_ROOT}"

proxy_args=(
  --build-arg "HTTP_PROXY=${http_proxy:-}"
  --build-arg "HTTPS_PROXY=${https_proxy:-}"
  --build-arg "http_proxy=${http_proxy:-}"
  --build-arg "https_proxy=${https_proxy:-}"
)

if [[ "${M71_SKIP_IMAGE:-}" != "1" ]]; then
  demo_log "build as-config-service:m71-lab"
  docker build -t as-config-service:m71-lab \
    "${proxy_args[@]}" \
    -f "${REPO_ROOT}/deploy/docker/config-service.Dockerfile" \
    "${REPO_ROOT}"
  kind load docker-image as-config-service:m71-lab --name as-m71
fi

demo_log "install config-service (ruleset JSON stays until the bundle is mounted)"
demo_m71_kubectl -n as-sut delete job as-sut-config-migrate --ignore-not-found
helm upgrade --install as-sut "${REPO_ROOT}/deploy/helm" \
  --namespace as-sut \
  -f "${REPO_ROOT}/testbed/sim-platform/values-product-as.yaml" \
  --set image.repository=as-sut \
  --set image.tag=dev
demo_m71_kubectl -n as-sut wait --for=condition=complete job/as-sut-config-migrate --timeout=180s
demo_m71_kubectl -n as-sut rollout status deploy/as-sut-config-service --timeout=180s

dsn="$(demo_m71_kubectl -n as-sut get secret as-sut-config-runtime -o jsonpath='{.data.AS_CONFIG_DSN}' | base64 -d)"
hmac="$(demo_m71_kubectl -n as-sut get secret as-sut-config-runtime -o jsonpath='{.data.AS_AUDIT_RESOURCE_HMAC_KEY_B64}' | base64 -d)"

port=15432
demo_m71_kubectl -n as-sut port-forward pod/as-sut-postgres-0 "${port}:5432" >/tmp/m71-pg-forward.log 2>&1 &
forward_pid=$!
cleanup() {
  kill "${forward_pid}" >/dev/null 2>&1 || true
}
trap cleanup EXIT
for _ in $(seq 1 50); do
  if (echo >/dev/tcp/127.0.0.1/"${port}") >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done

out="${REPO_ROOT}/artifacts/demo-review/m71-runtime-bundle.json"
mkdir -p "$(dirname "${out}")"
demo_log "propose / approve / distribute / activate"
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
  uv run --project "${REPO_ROOT}" python "${REPO_ROOT}/scripts/demo-review/publish_m71_bundle.py" \
  --dsn "${dsn}" \
  --port "${port}" \
  --hmac-b64 "${hmac}" \
  --out "${out}"

demo_m71_kubectl -n as-sut create configmap as-sut-runtime-bundle \
  --from-file=bundle.json="${out}" \
  --dry-run=client -o yaml | demo_m71_kubectl apply -f -

demo_log "point translation at the mounted bundle and drop AS_RULESET_JSON"
demo_m71_kubectl -n as-sut delete job as-sut-config-migrate --ignore-not-found
helm upgrade --install as-sut "${REPO_ROOT}/deploy/helm" \
  --namespace as-sut \
  -f "${REPO_ROOT}/testbed/sim-platform/values-product-as.yaml" \
  -f "${REPO_ROOT}/testbed/sim-platform/values-product-as-bundle.yaml" \
  --set image.repository=as-sut \
  --set image.tag=dev
demo_m71_kubectl -n as-sut rollout status deploy/as-sut-translation --timeout=180s
demo_m71_kubectl -n as-sut rollout status deploy/as-sut-config-service --timeout=180s

demo_m71_kubectl -n as-sut exec deploy/as-sut-translation -- \
  python -c 'import os; assert not os.environ.get("AS_RULESET_JSON", "").strip(); assert os.environ["AS_CONFIG_BUNDLE_PATH"].endswith("bundle.json"); text=open(os.environ["AS_CONFIG_BUNDLE_PATH"], encoding="utf-8").read(); assert "t1-plus86" in text and "f2-block" in text'
demo_log "translation is reading the compiled bundle"
