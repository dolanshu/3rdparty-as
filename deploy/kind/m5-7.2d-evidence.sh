#!/usr/bin/env bash
# M4b-7.2d / M5-1c closure: runbook items 1–6 (kind via ingress port-forward + browser).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=deploy/kind/m5-lib.sh
source "${ROOT}/deploy/kind/m5-lib.sh"

NS="${K8S_NAMESPACE:-as-m5}"
HOST="${M5_INGRESS_HOST:-console.m5.test}"
HTTP_PORT="${M5_INGRESS_HTTP_PORT:-18080}"
HTTPS_PORT="${M5_INGRESS_HTTPS_PORT:-18443}"
DATE="$(date -u +%Y-%m-%d)"
ART="${ROOT}/artifacts/m5/${DATE}"
mkdir -p "${ART}"
LOG="${ART}/7.2d-evidence.log"
exec > >(tee -a "${LOG}") 2>&1

: "${M5_7_2D_E2E_PASSWORD:?Set M5_7_2D_E2E_PASSWORD (12+ chars, dev-only)}"

kubectl config use-context "kind-${KIND_CLUSTER_NAME:-as-m5}"

if [[ "${M5_7_2D_SKIP_INGRESS:-0}" != "1" ]]; then
  echo "==> ensure ingress + config-service (m5-ingress-evidence)"
  M5_BUNDLED_STATE="${M5_BUNDLED_STATE:-1}" bash "${ROOT}/deploy/kind/m5-ingress-evidence.sh"
else
  echo "==> skip ingress install (M5_7_2D_SKIP_INGRESS=1)"
fi

echo "==> schema migrate (bundled PG)"
bash "${ROOT}/deploy/kind/m5-config-migrate-kind.sh"

echo "==> seed console users (owner DSN)"
LOCAL_PG="${M5_PG_LOCAL_PORT:-15432}"
kubectl -n "${NS}" port-forward pod/as-3rdparty-as-postgres-0 "${LOCAL_PG}:5432" >/tmp/m5-pg-seed-pf.log 2>&1 &
PG_PF=$!
sleep 2
export AS_CONFIG_OWNER_DSN="postgresql://as_config_owner:${AS_CONFIG_OWNER_PASSWORD:-as_config_owner_dev}@127.0.0.1:${LOCAL_PG}/as_config"
export M4B8_E2E_PASSWORD="${M5_7_2D_E2E_PASSWORD}"
if ! printf 'admin\n%s\n%s\n' "${M5_7_2D_E2E_PASSWORD}" "${M5_7_2D_E2E_PASSWORD}" \
  | uv run as-config-bootstrap-admin 2>/dev/null; then
  echo "bootstrap-admin: already complete or skipped"
fi
uv run --directory "${ROOT}/services/config-service" python "${ROOT}/deploy/compose/scripts/m4b-8-seed-users.py"
kill "${PG_PF}" 2>/dev/null || true
wait "${PG_PF}" 2>/dev/null || true

echo "==> runbook item 1: ingress annotation prefix"
ING_YAML="$(kubectl -n "${NS}" get ingress -o yaml)"
if ! grep -q 'nginx.ingress.kubernetes.io/ssl-redirect' <<<"${ING_YAML}"; then
  echo "ERROR: missing nginx.ingress.kubernetes.io annotations" >&2
  exit 1
fi
echo "item-1: PASS"

echo "==> runbook item 2: controller no-tls-redirect-locations (document)"
CM="$(kubectl -n ingress-nginx get configmap ingress-nginx-controller -o yaml 2>/dev/null || true)"
if grep -q 'no-tls-redirect-locations' <<<"${CM}"; then
  if grep -E 'no-tls-redirect-locations:.*/' <<<"${CM}" | grep -qvE '=.*\^?/'; then
    echo "WARN: review no-tls-redirect-locations value in controller ConfigMap"
  fi
  echo "item-2: documented (ConfigMap lists no-tls-redirect-locations)"
else
  echo "item-2: PASS (default controller config — / not exempt)"
fi

echo "==> runbook item 3: TLS secret on Ingress"
TLS_SECRET="$(kubectl -n "${NS}" get ingress -o jsonpath='{.items[0].spec.tls[0].secretName}')"
[[ -n "${TLS_SECRET}" ]] && kubectl -n "${NS}" get secret "${TLS_SECRET}" >/dev/null
echo "item-3: PASS secret=${TLS_SECRET}"

echo "==> runbook item 6: trustedProxies on config-service"
TP="$(kubectl -n "${NS}" get deploy -l app.kubernetes.io/component=config-service -o yaml | grep -A1 AS_CONFIG_TRUSTED_PROXIES || true)"
if grep -qE '10\.0\.0\.0/8' <<<"${TP}"; then
  echo "item-6: PASS"
else
  echo "ERROR: trustedProxies not as expected" >&2
  exit 1
fi

echo "==> items 4–5: L7 via port-forward to ingress-nginx-controller"
kubectl -n ingress-nginx port-forward svc/ingress-nginx-controller "${HTTP_PORT}:80" "${HTTPS_PORT}:443" \
  >/tmp/m5-ing-pf.log 2>&1 &
ING_PF=$!
sleep 2
m5_noproxy_env
export M5_INGRESS_HOST="${HOST}"

for attempt in $(seq 1 15); do
  REDIR="$(
    curl --noproxy '*' -sS -o /dev/null -w '%{http_code}' --resolve "${HOST}:${HTTP_PORT}:127.0.0.1" \
      "http://${HOST}:${HTTP_PORT}/" 2>/dev/null || echo 000
  )"
  if [[ "${REDIR}" =~ ^(301|302|308)$ ]]; then
    break
  fi
  sleep 2
done

REDIR="${REDIR:-000}"
# shellcheck disable=SC2312
if [[ ! "${REDIR}" =~ ^(301|302|308)$ ]]; then
  REDIR="$(
    kubectl -n ingress-nginx run "m5-l7-http-${attempt}" --rm -i --restart=Never \
      --image=curlimages/curl:8.5.0 --command -- \
      curl -sS -o /dev/null -w '%{http_code}' -H "Host: ${HOST}" \
      "http://ingress-nginx-controller.ingress-nginx.svc/" 2>/dev/null || echo 000
  )"
fi

echo "HTTP GET (expect 301/302/308): ${REDIR}"
[[ "${REDIR}" =~ ^(301|302|308)$ ]] || {
  echo "ERROR: item-4 HTTP redirect failed" >&2
  kill "${ING_PF}" 2>/dev/null || true
  exit 1
}
echo "item-4: PASS"

HTTPS_CODE="000"
for _ in $(seq 1 15); do
  HTTPS_CODE="$(
    curl --noproxy '*' -sk -o /dev/null -w '%{http_code}' --resolve "${HOST}:${HTTPS_PORT}:127.0.0.1" \
      "https://${HOST}:${HTTPS_PORT}/" 2>/dev/null || echo 000
  )"
  [[ "${HTTPS_CODE}" == "200" ]] && break
  sleep 2
done
echo "HTTPS GET root: ${HTTPS_CODE}"
[[ "${HTTPS_CODE}" == "200" ]] || {
  echo "ERROR: item-4/5 HTTPS root expected 200" >&2
  kill "${ING_PF}" 2>/dev/null || true
  exit 1
}

echo "==> item 5: browser HTTPS login (no plain HTTP POST)"
export M5_INGRESS_HOST="${HOST}"
export M5_INGRESS_HTTPS_PORT="${HTTPS_PORT}"
export M5_ARTIFACT_DATE="${DATE}"
HOSTS_ALIAS="${ART}/hosts-alias"
echo "127.0.0.1 ${HOST}" > "${HOSTS_ALIAS}"
export HOSTALIASES="${HOSTS_ALIAS}"

COMPOSE_DIR="${ROOT}/deploy/compose"
if [[ ! -d "${COMPOSE_DIR}/node_modules/playwright" ]]; then
  (cd "${COMPOSE_DIR}" && npm install --no-fund --no-audit)
fi
(cd "${COMPOSE_DIR}" && node scripts/m5-7.2d-browser-evidence.mjs)
echo "item-5: PASS"

kill "${ING_PF}" 2>/dev/null || true
wait "${ING_PF}" 2>/dev/null || true

echo "7.2d-evidence: OK log=${LOG}"
