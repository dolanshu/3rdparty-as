#!/usr/bin/env bash
# Shared helpers for pre-M8 demo story scripts.
set -euo pipefail

DEMO_REVIEW_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${DEMO_REVIEW_LIB_DIR}/../.." && pwd)"
FIXTURES_DIR="${DEMO_REVIEW_LIB_DIR}/fixtures"
ARTIFACT_ROOT="${DEMO_REVIEW_ARTIFACT_ROOT:-${REPO_ROOT}/artifacts/demo-review}"

demo_log() {
  echo "[demo-review] $*"
}

demo_die() {
  echo "[demo-review] ERROR: $*" >&2
  exit 1
}

demo_story_banner() {
  local id="$1"
  local title="$2"
  echo ""
  echo "================================================================================"
  echo "  Story ${id}: ${title}"
  echo "================================================================================"
}

demo_step() {
  local n="$1"
  local title="$2"
  echo ""
  echo "--- Step ${n}: ${title} ---"
}

demo_show_customer() {
  echo ""
  echo ">> 对客户展示:"
  while IFS= read -r line; do
    echo "   ${line}"
  done <<<"$1"
}

demo_artifact_dir() {
  local story="$1"
  local dir="${ARTIFACT_ROOT}/$(date +%Y-%m-%d)/story-${story}"
  mkdir -p "${dir}"
  echo "${dir}"
}

demo_require_uv() {
  cd "${REPO_ROOT}"
  command -v uv >/dev/null 2>&1 || demo_die "uv not found; run: cd ${REPO_ROOT} && uv sync"
}

demo_require_native_runtime() {
  local build_dir="${AS_RESIP_RUNTIME_BUILD:-${REPO_ROOT}/platform/native/resip_runtime/build}"
  if ! compgen -G "${build_dir}/_resip_runtime"*.so >/dev/null; then
    demo_log "building _resip_runtime..."
    make -C "${REPO_ROOT}" m2-platform-resip-build
  fi
}

demo_pg_reachable() {
  local dsn="${AS_PG_TEST_DSN:-postgresql://postgres:postgres@127.0.0.1:55432/as_config}"
  AS_PG_TEST_DSN="${dsn}" uv run python - <<'PY' >/dev/null 2>&1
import os, sys
dsn = os.environ["AS_PG_TEST_DSN"]
try:
    import psycopg
    with psycopg.connect(dsn, connect_timeout=3):
        pass
except Exception:
    sys.exit(1)
PY
}

demo_redis_reachable() {
  local url="${AS_REDIS_URL:-redis://127.0.0.1:6379/0}"
  AS_REDIS_URL="${url}" uv run python - <<'PY' >/dev/null 2>&1
import os, sys
try:
    import redis
    r = redis.from_url(os.environ["AS_REDIS_URL"], socket_connect_timeout=2)
    r.ping()
except Exception:
    sys.exit(1)
PY
}

demo_compose_ready() {
  local compose_dir="${REPO_ROOT}/deploy/compose"
  [[ -f "${compose_dir}/.env" && -f "${compose_dir}/certs/tls.crt" ]]
}

demo_kind_context() {
  local cluster="${KIND_CLUSTER_NAME:-as-m5}"
  kubectl config get-contexts -o name 2>/dev/null | grep -qx "kind-${cluster}"
}
