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

demo_m71_kubectl() {
  PATH="${REPO_ROOT}/.tools/m71-bin:${PATH}"
  command -v kubectl >/dev/null 2>&1 || demo_die "kubectl not found on PATH or in ${REPO_ROOT}/.tools/m71-bin"
  kubectl --context kind-as-m71 "$@"
}

demo_m71_present() {
  PATH="${REPO_ROOT}/.tools/m71-bin:${PATH}"
  kubectl config get-contexts -o name 2>/dev/null | grep -qx "kind-as-m71"
}

demo_m71_require() {
  demo_m71_present \
    || demo_die "kind context kind-as-m71 missing; run: bash testbed/sim-platform/kind-up.sh"
}

# Drive the ims-sim test page on kind as-m71. Kernel rules come from the
# mounted config-service bundle. Counts describe this run only.
demo_m71_signal() {
  local transport="$1"
  local art="$2"
  case "${transport}" in
    udp | tcp | tls) ;;
    *) demo_die "unsupported transport ${transport}" ;;
  esac
  demo_m71_require
  local out="${art}/m71-${transport}.json"
  local product_log="${art}/m71-${transport}-product.log"
  demo_log "as-m71 test page ${transport} -> ${out}"
  demo_show_customer "$(cat <<EOF
测试页在 ims-sim，不是产品控制台：无登录，不签 REQ-S-4。
证书是测试 CA，不是运营商 PKI。本轮次数不是容量承诺。
传输 ${transport}。判决规则来自 config-service 编译的 bundle（AS_CONFIG_BUNDLE_PATH）。
+86 改成 0 开头仍是翻译应用的 AS_TRANSLATION_RULES_JSON，bundle 带不了这条改号表。
进程不拉包；本场把已激活的 JSON 挂进 Pod。控制台 HTTPS 登录不在这个集群。
T1 改号后 200，T4 404，T5 / F1 200，F2 603（不是 608）。接通的对话 BYE 2xx。
EOF
)"
  demo_m71_kubectl -n ims-sim exec -i deploy/call-load -- \
    env "M71_TRANSPORT=${transport}" python - >"${out}" <<'PY'
import json, os, time, urllib.request
transport = os.environ["M71_TRANSPORT"]
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def call(method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:8088" + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with opener.open(req, timeout=15) as response:
        return json.loads(response.read().decode())

call("POST", "/api/runs", {
    "transport": transport,
    "scenarios": ["T1", "T4", "T5", "F1", "F2"],
    "duration_seconds": 3,
    "cps": 5,
    "workers": 8,
    "hold_seconds": 0.2,
})
snap = {}
for _ in range(40):
    snap = call("GET", "/api/runs/latest")
    if not snap.get("running"):
        break
    time.sleep(1)
else:
    raise SystemExit("call-load run still active")
print(json.dumps(snap))
PY
  python3 - "${out}" <<'PY'
import json, sys
snap = json.load(open(sys.argv[1], encoding="utf-8"))
if snap.get("running") or snap.get("error"):
    raise SystemExit(f"run failed: running={snap.get('running')} error={snap.get('error')}")
summary = snap.get("summary") or {}
errors = summary.get("error_distribution") or {}
bye = {name: count for name, count in errors.items() if name.startswith("bye_") or name == "timeout_bye"}
if bye or summary.get("unresolved"):
    raise SystemExit(f"BYE not clean: unresolved={summary.get('unresolved')} errors={bye}")
by = summary.get("by_scenario") or {}

def codes(scenario):
    bucket = by.get(scenario) or {}
    found = bucket.get("response_codes") or {}
    if not found:
        raise SystemExit(f"{scenario} missing from {list(by)}")
    return found

expected = {"T1": "200", "T4": "404", "T5": "200", "F1": "200", "F2": "603"}
for scenario, code in expected.items():
    found = codes(scenario)
    if code not in found:
        raise SystemExit(f"{scenario} expected {code}, got {found}")
if "608" in codes("F2"):
    raise SystemExit(f"F2 must stay 603, got {codes('F2')}")
print("m71", summary.get("response_code_distribution"), "unresolved", summary.get("unresolved"))
PY
  demo_m71_kubectl -n as-sut logs deploy/as-sut-translation --since=3m >"${product_log}"
  grep -q "013800138000" "${product_log}" \
    || demo_die "product log missing T1 rewrite 013800138000 (${product_log})"
  grep -q "OUTBOUND_BYE_FORWARD" "${product_log}" \
    || demo_die "product log missing outbound BYE forward (${product_log})"
}
