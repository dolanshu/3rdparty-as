#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=deploy/kind/m5-lib.sh
source "${ROOT}/deploy/kind/m5-lib.sh"
NS="${K8S_NAMESPACE:-as-m5}"
RELEASE="${HELM_RELEASE_NAME:-as}"
CONFIG_TAG="${AS_CONFIG_IMAGE:-as-config-service:m5}"
HELM="${HELM_BIN:-helm}"
HOST="${M5_INGRESS_HOST:-console.m5.test}"
CERT_DIR="${ROOT}/deploy/kind/certs"

kubectl config use-context "kind-${KIND_CLUSTER_NAME:-as-m5}"

BUNDLED_STATE="${M5_BUNDLED_STATE:-1}"
if [[ "${BUNDLED_STATE}" == "1" ]]; then
  echo "==> M5-1d: in-cluster PostgreSQL (ADR-0026 stateStores; skip compose PG)"
else
  echo "==> M5-1d: compose PostgreSQL for config-service runtime DSN"
  m5_ensure_compose_postgres "${ROOT}"
  RUNTIME_DSN="$(m5_compose_runtime_dsn)"
  echo "runtime DSN host: $(echo "${RUNTIME_DSN}" | sed -E 's#://[^@]+@#://***@#')"
fi

if [[ ! -f "${CERT_DIR}/tls.crt" ]]; then
  M5_INGRESS_HOST="${HOST}" "${ROOT}/deploy/kind/m5-gen-certs.sh"
fi

echo "==> ingress-nginx (kind manifest)"
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
kubectl -n ingress-nginx wait --for=condition=ready pod -l app.kubernetes.io/component=controller --timeout=300s

ADMISSION_OK=0
if kubectl -n ingress-nginx wait --for=condition=complete job/ingress-nginx-admission-create --timeout=180s 2>/dev/null; then
  ADMISSION_OK=1
  echo "ingress-nginx admission-create job: complete"
else
  echo "WARN: ingress-nginx-admission-create job not complete in 180s (kind/dev flake)"
  if kubectl get validatingwebhookconfigurations ingress-nginx-admission >/dev/null 2>&1; then
    echo "WARN: VWC ingress-nginx-admission exists but job incomplete — review before production"
  else
    echo "NOTE: no ingress-nginx-admission VWC; kind dev may continue (track in m5-7.2d runbook)"
  fi
fi

kubectl -n "${NS}" create secret generic console-tls \
  --from-file=tls.crt="${CERT_DIR}/tls.crt" \
  --from-file=tls.key="${CERT_DIR}/tls.key" \
  --dry-run=client -o yaml | kubectl apply -f -

if [[ "${BUNDLED_STATE}" != "1" ]]; then
  kubectl -n "${NS}" create secret generic as-config-runtime \
    --from-literal=AS_CONFIG_DSN="${RUNTIME_DSN}" \
    --from-literal=AS_AUDIT_RESOURCE_HMAC_KEY_B64='a2tra2tra2tra2tra2tra2tra2tra2tra2tra2tra2s=' \
    --dry-run=client -o yaml | kubectl apply -f -
fi

HELM_STATE_SET=()
CONFIG_SECRET_SET=()
if [[ "${BUNDLED_STATE}" == "1" ]]; then
  HELM_STATE_SET=(
    --set stateStores.enabled=true
    --set stateStores.bootstrapDevCredentials=true
    --set stateStores.networkPolicy.enabled=true
  )
else
  CONFIG_SECRET_SET=(
    --set services.configService.secretName=as-config-runtime
  )
fi

"${HELM}" upgrade "${RELEASE}" "${ROOT}/deploy/helm" \
  --namespace "${NS}" \
  --reuse-values \
  "${HELM_STATE_SET[@]}" \
  --set services.configService.enabled=true \
  "${CONFIG_SECRET_SET[@]}" \
  --set services.configService.runtimeRole=as_config_runtime \
  --set services.configService.image.repository="${CONFIG_TAG%%:*}" \
  --set services.configService.image.tag="${CONFIG_TAG##*:}" \
  --set services.configService.proxyHeaders=true \
  --set 'services.configService.trustedProxies={10.0.0.0/8}' \
  --set services.configService.ingress.enabled=true \
  --set services.configService.ingress.host="${HOST}" \
  --set services.configService.ingress.tlsSecretName=console-tls \
  --wait --timeout=300s

CFG_DEPLOY="$(kubectl -n "${NS}" get deploy -l app.kubernetes.io/component=config-service -o jsonpath='{.items[0].metadata.name}')"
kubectl -n "${NS}" rollout status "deployment/${CFG_DEPLOY}" --timeout=300s

echo "==> ingress object annotations"
kubectl -n "${NS}" get ingress -o yaml | grep -E 'nginx.ingress.kubernetes.io|host:' || true

echo "==> in-cluster HTTP redirect check (bypasses host proxy / missing hostPort 80)"
_m5_ingress_curl() {
  local scheme="$1"
  local url="$2"
  local out
  out="$(kubectl -n ingress-nginx run "m5-curl-${scheme}" --rm -i --restart=Never \
    --image=curlimages/curl:8.5.0 --command -- \
    curl -s -o /dev/null -w '%{http_code}' -H "Host: ${HOST}" "${url}" 2>&1 || true)"
  echo "${out}" | grep -oE '[0-9]{3}' | tail -1
}
HTTP_CODE="$(_m5_ingress_curl http "http://ingress-nginx-controller.ingress-nginx.svc.cluster.local/")"
HTTP_CODE="${HTTP_CODE:-000}"
echo "in-cluster HTTP (expect 301/302/308): ${HTTP_CODE}"
# K-1 (M5.1 minimal): a non-redirect HTTP code is evidence failure, not a
# warning — WARN-only checks can never turn red. See ADR-0013.
if [[ ! "${HTTP_CODE}" =~ ^(301|302|308)$ ]]; then
  echo "ERROR: ingress HTTP check not a redirect (got ${HTTP_CODE})" >&2
  exit 1
fi

HTTPS_CODE="$(_m5_ingress_curl https "https://ingress-nginx-controller.ingress-nginx.svc.cluster.local/")"
HTTPS_CODE="${HTTPS_CODE:-000}"
echo "in-cluster HTTPS root: ${HTTPS_CODE}"
# K-1 (M5.1 minimal): a missing HTTPS code fails the evidence run.
if [[ "${HTTPS_CODE}" == "000" ]]; then
  echo "ERROR: ingress HTTPS check returned no status code" >&2
  exit 1
fi

m5_noproxy_env
CFG_POD="$(kubectl -n "${NS}" get pod -l app.kubernetes.io/component=config-service -o jsonpath='{.items[0].metadata.name}')"
kubectl -n "${NS}" port-forward "pod/${CFG_POD}" 18001:8000 >/tmp/m5-ingress-pf.log 2>&1 &
PF_PID=$!
sleep 2
m5_noproxy_env
PF_CODE="$(curl --noproxy '*' -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18001/ || echo 000)"
kill "${PF_PID}" 2>/dev/null || true
wait "${PF_PID}" 2>/dev/null || true
echo "config-service port-forward (NO_PROXY): ${PF_CODE}"
# K-1 (M5.1 minimal): the port-forward code is asserted, not merely recorded.
if [[ "${PF_CODE}" != "200" ]]; then
  echo "ERROR: expected 200 from config-service port-forward (got ${PF_CODE})" >&2
  exit 1
fi

echo "admission_job_ok=${ADMISSION_OK}"
echo "ingress-evidence: OK"
