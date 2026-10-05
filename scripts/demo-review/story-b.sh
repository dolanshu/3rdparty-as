#!/usr/bin/env bash
# Story B — 拦截诈骗号段（603 + 反诈判决）
set -euo pipefail
# shellcheck source=scripts/demo-review/lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

demo_story_banner "B" "拦截诈骗号段（US-2 / REQ-F-7）"
ART="$(demo_artifact_dir b)"
demo_log "artifacts -> ${ART}"

demo_step 1 "控制台策略（人工或 bundle 样例）"
cp "${FIXTURES_DIR}/bundle-block-86168.json" "${ART}/bundle-block-86168.json"
demo_show_customer "$(cat <<'EOF'
被叫 +86168* → 策略拒绝（603 Decline）
控制台路径同故事 A；本场用预置 bundle JSON 代表激活结果
EOF
)"
cat "${ART}/bundle-block-86168.json"

demo_step 2 "产品 SIP：命中阻止 → 603"
demo_require_uv
demo_require_native_runtime
demo_show_customer "对端 INVITE 被叫命中 +86168… → 603（S3 契约形状）"
uv run pytest platform/tests/test_e1_contract_resip_runtime_full.py::test_e1_s3_block_rule_from_contract_shape -m contract -v \
  2>&1 | tee "${ART}/sip-603.log"

demo_step 3 "对比：无匹配 404 / 基本接通 200"
demo_show_customer "同一栈：无规则 404；accept-all harness 下 S1 → 200（与翻译双腿对比）"
uv run pytest \
  platform/tests/test_e1_contract_resip_runtime_full.py::test_e1_s2_no_match_from_contract_shape \
  platform/tests/test_e1_contract_resip_runtime_full.py::test_e1_s1_accept_all_from_contract_invite \
  -m contract -v 2>&1 | tee "${ART}/sip-404-200.log"

demo_step 4 "主叫取消 → 487（S4 契约）"
demo_show_customer "早 CANCEL 场景：UAS 487 Request Terminated（E1 S4 形状）"
uv run pytest platform/tests/test_e1_contract_resip_runtime_full.py::test_e1_s4_caller_cancel_returns_487 -m contract -v \
  2>&1 | tee "${ART}/sip-487.log"

demo_step 5 "反诈 AS：单腿判决（608 语义在 adapter）"
demo_show_customer "反诈用例：主叫甄别，DECLINE/BLOCK 判决；608 由信令 adapter 应答（非双腿 B2BUA）"
uv run pytest apps/anti-fraud/tests/test_decision.py -q 2>&1 | tee "${ART}/anti-fraud-decision.log"

demo_log "Story B automated checks: OK (see ${ART})"
