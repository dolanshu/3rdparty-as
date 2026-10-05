#!/usr/bin/env bash
# Story A — 开通翻译号段（控制面 + 信令桥接）
set -euo pipefail
# shellcheck source=scripts/demo-review/lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

WITH_COMPOSE=0
SKIP_PG=0
for arg in "$@"; do
  case "${arg}" in
    --with-compose) WITH_COMPOSE=1 ;;
    --skip-pg) SKIP_PG=1 ;;
    -h | --help)
      echo "Usage: $0 [--with-compose] [--skip-pg]"
      echo "  --with-compose  run deploy/compose smoke-https when .env+certs exist"
      echo "  --skip-pg       skip PostgreSQL pipeline integration (browser-only control plane)"
      exit 0
      ;;
  esac
done

demo_story_banner "A" "开通翻译号段（US-1 / US-4）"
ART="$(demo_artifact_dir a)"
demo_log "artifacts -> ${ART}"

demo_step 1 "控制台与角色（人工）"
demo_show_customer "$(cat <<'EOF'
浏览器打开 https://localhost:8443/（自签证书）
管理员登录 → 用户管理创建审批员账号
界面：被叫+前缀规则、变更单队列、审批、Operations 分发
EOF
)"
if [[ "${WITH_COMPOSE}" -eq 1 ]]; then
  if demo_compose_ready; then
    demo_log "compose: smoke-https"
    (cd "${REPO_ROOT}/deploy/compose" && ./scripts/smoke-https.sh) | tee "${ART}/compose-smoke.log"
  else
    demo_log "SKIP compose: missing deploy/compose/.env or certs (see deploy/compose/README.md)"
  fi
else
  demo_log "hint: re-run with --with-compose after compose quick-start"
fi

demo_step 2 "规则治理闭环（自动化替身：PG 管道集成测）"
demo_show_customer "$(cat <<'EOF'
等价演示：一条被叫+前缀规则经 提案→审批→分发→激活，产出可编译的 ConfigBundle
EOF
)"
if [[ "${SKIP_PG}" -eq 1 ]]; then
  demo_log "SKIP: --skip-pg"
else
  if demo_pg_reachable; then
    demo_log "running test_postgres_managed_rule_pipeline_integration.py"
    AS_PG_TEST_DSN="${AS_PG_TEST_DSN:-postgresql://postgres:postgres@127.0.0.1:55432/as_config}" \
      uv run pytest \
      services/config-service/tests/test_postgres_managed_rule_pipeline_integration.py::test_managed_rule_proposal_submit_approve_distribute_and_activate_compiled_bundle \
      -m integration -v 2>&1 | tee "${ART}/pipeline-integration.log"
  else
    demo_log "SKIP PG integration (start compose postgres or set AS_PG_TEST_DSN)"
    demo_log "  cd deploy/compose && docker compose up -d postgres && ./scripts/migrate.sh"
  fi
fi

demo_step 3 "规则编译（runtime_bundle）"
demo_show_customer "展示：控制台规则如何变成运行时可消费的 JSON（ADR-0025）"
uv run pytest services/config-service/tests/test_runtime_bundle.py -m unit -q 2>&1 | tee "${ART}/runtime-bundle-unit.log"
cp "${FIXTURES_DIR}/bundle-forward-86755.json" "${ART}/bundle-forward-86755.json"
demo_log "sample bundle written: ${ART}/bundle-forward-86755.json"
head -n 20 "${ART}/bundle-forward-86755.json"

demo_step 4 "信令桥接（ConfigBundle 注入）"
demo_show_customer "$(cat <<'EOF'
说明：生产由运维分发通道推送 bundle；本场用 AS_CONFIG_BUNDLE_PATH 注入翻译进程
可选人工： AS_ENABLE_SIP_RUNTIME=1 AS_USE_CASE=translation AS_CONFIG_BUNDLE_PATH=<bundle> uv run python -m as_platform
EOF
)"

demo_step 5 "SIP 形状验证（无匹配 404 + 产品栈）"
demo_require_uv
demo_require_native_runtime
demo_show_customer "未命中规则 → 404；命中 block/forward 见故事 B / FORWARD 集成测"
uv run pytest platform/tests/test_e1_contract_resip_runtime_full.py::test_e1_s2_no_match_from_contract_shape -m contract -v \
  2>&1 | tee "${ART}/sip-404.log"
uv run pytest platform/tests/test_m7_forward_two_leg_integration.py -m integration -v \
  2>&1 | tee "${ART}/sip-forward-486.log"

demo_log "Story A automated checks: OK (see ${ART})"
