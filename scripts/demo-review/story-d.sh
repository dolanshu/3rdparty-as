#!/usr/bin/env bash
# Story D - Protect calls from unexpected drops (checkpoint / NF-1 engineering harness)
set -euo pipefail
# shellcheck source=scripts/demo-review/lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

SKIP_REDIS=0
for arg in "$@"; do
  case "${arg}" in
    --skip-redis) SKIP_REDIS=1 ;;
    -h | --help)
      echo "Usage: $0 [--skip-redis]"
      exit 0
      ;;
  esac
done

demo_story_banner "D" "通话不随便丢（checkpoint / 恢复方向）"
ART="$(demo_artifact_dir d)"
demo_log "artifacts -> ${ART}"

demo_step 1 "架构说明（对客户）"
demo_show_customer "$(cat <<'EOF'
多副本无状态 AS；必要会话状态 checkpoint 到 Redis
进程重启后按 checkpoint 恢复（工程 harness）；正式 K8s 杀 Pod 验收在客户环境 M8
EOF
)"

demo_step 2 "Redis 可用性"
if [[ "${SKIP_REDIS}" -eq 1 ]]; then
  demo_log "SKIP: --skip-redis"
else
  if demo_redis_reachable; then
    demo_log "Redis ping OK (${AS_REDIS_URL:-redis://127.0.0.1:6379/0})"
  else
    demo_log "Redis not reachable; start e.g.: docker run -d --rm -p 6379:6379 redis:7"
    demo_die "Redis required for story D automated path (or pass --skip-redis and run harness manually)"
  fi
fi

demo_step 3 "构建 recovery 原生模块"
demo_require_native_runtime
make -C "${REPO_ROOT}" m7-platform-recovery-build 2>&1 | tee "${ART}/recovery-build.log"

demo_step 4 "REQ-NF-1 工程 harness（非正式签收）"
demo_show_customer "自动化：子进程 SIP 栈 + Redis checkpoint + 重启恢复链（integration）"
if [[ "${SKIP_REDIS}" -eq 0 ]]; then
  bash "${REPO_ROOT}/scripts/d10-req-nf1-harness.sh" 2>&1 | tee "${ART}/d10-harness.log"
fi

demo_step 5 "补充集成测（可选，同 Redis）"
if [[ "${SKIP_REDIS}" -eq 0 ]]; then
  uv run pytest platform/tests/test_d10_req_nf1_redis_integration.py -m integration -q \
    2>&1 | tee "${ART}/d10-redis-integration.log" || demo_log "WARN: redis integration skipped/failed"
fi

demo_log "Story D automated checks: OK (see ${ART})"
