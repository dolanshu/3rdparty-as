#!/usr/bin/env bash
# Owner migrate against bundled chart Postgres (ADR-0026 kind profile).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
NS="${K8S_NAMESPACE:-as-m5}"
PG_POD="${M5_PG_POD:-as-3rdparty-as-postgres-0}"
LOCAL_PORT="${M5_PG_LOCAL_PORT:-15432}"
OWNER_PASS="${AS_CONFIG_OWNER_PASSWORD:-as_config_owner_dev}"

kubectl -n "${NS}" wait --for=condition=ready "pod/${PG_POD}" --timeout=120s
kubectl -n "${NS}" port-forward "pod/${PG_POD}" "${LOCAL_PORT}:5432" >/tmp/m5-pg-pf.log 2>&1 &
PF_PID=$!
sleep 2

export AS_CONFIG_OWNER_DSN="postgresql://as_config_owner:${OWNER_PASS}@127.0.0.1:${LOCAL_PORT}/as_config"
export AS_CONFIG_RUNTIME_ROLE="${AS_CONFIG_RUNTIME_ROLE:-as_config_runtime}"
export AS_CONFIG_SCHEMA="${AS_CONFIG_SCHEMA:-as_config}"
export AS_AUDIT_SCHEMA="${AS_AUDIT_SCHEMA:-console_audit}"

cd "${ROOT}"
uv run as-config-migrate
kill "${PF_PID}" 2>/dev/null || true
wait "${PF_PID}" 2>/dev/null || true
echo "m5-config-migrate-kind: OK"
