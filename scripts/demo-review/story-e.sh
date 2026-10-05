#!/usr/bin/env bash
# Story E — 我们能扛多少（容量研究，非 SLA）
set -euo pipefail
# shellcheck source=scripts/demo-review/lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

FULL_O1=0
for arg in "$@"; do
  case "${arg}" in
    --full-o1) FULL_O1=1 ;;
    -h | --help)
      echo "Usage: $0 [--full-o1]  (run m6-o1-formal-report.sh — long)"
      exit 0
      ;;
  esac
done

demo_story_banner "E" "我们能扛多少（容量研究）"
ART="$(demo_artifact_dir e)"
demo_log "artifacts -> ${ART}"

demo_step 1 "方法论（对客户必读）"
demo_show_customer "$(cat <<'EOF'
这是内部容量研究方法学与 dev-host 样本，不是对外 CPS/并发 SLA
HPA 阈值在 O1 结论之后由运维填写 values
EOF
)"
head -n 45 "${REPO_ROOT}/docs/acceptance/m6-o1-measurement-report-2026-10-05.md" | tee "${ART}/o1-report-head.md"

demo_step 2 "产品路径真 socket 烟雾"
demo_require_native_runtime
demo_show_customer "as_load 打产品 ResipRuntimeListener（UDP）；短批次建立会话"
bash "${REPO_ROOT}/testbed/load/scripts/m6-product-runtime-smoke.sh" 2>&1 | tee "${ART}/m6-smoke.log"

demo_step 3 "烟雾结果摘要"
SMOKE_DIR="$(ls -td /tmp/as-m6-product-runtime-smoke-* 2>/dev/null | head -n1 || true)"
if [[ -n "${SMOKE_DIR}" && -f "${SMOKE_DIR}/summary.json" ]]; then
  cp "${SMOKE_DIR}/summary.json" "${ART}/smoke-summary.json"
  python3 -c "import json,sys; s=json.load(open(sys.argv[1])); print(json.dumps(s.get('counts',s), indent=2))" \
    "${ART}/smoke-summary.json" | tee "${ART}/smoke-summary-pretty.txt"
fi

demo_step 4 "正式 O1 批次（可选，耗时）"
if [[ "${FULL_O1}" -eq 1 ]]; then
  demo_log "running m6-o1-formal-report.sh (several minutes)..."
  bash "${REPO_ROOT}/testbed/load/scripts/m6-o1-formal-report.sh" 2>&1 | tee "${ART}/o1-formal.log"
else
  demo_log "SKIP full O1 batch (use --full-o1 to run formal report script)"
  demo_show_customer "展示已有报告 docs/acceptance/m6-o1-measurement-report-2026-10-05.md"
fi

demo_log "Story E automated checks: OK (see ${ART})"
