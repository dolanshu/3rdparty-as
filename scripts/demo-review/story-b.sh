#!/usr/bin/env bash
# Story B - Block fraudulent-number ranges (603 + anti-fraud decision)
set -euo pipefail
# shellcheck source=scripts/demo-review/lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

demo_story_banner "B" "拦截诈骗号段（US-2 / REQ-F-7）"
ART="$(demo_artifact_dir b)"
demo_log "artifacts -> ${ART}"

demo_step 1 "本场阻止号段（实验室规则，不是控制台下发）"
demo_show_customer "$(cat <<'EOF'
产品路径上 F2 被叫前缀 +15550003 → 603。不说成 608。
规则在实验室 values 的 AS_RULESET_JSON。控制台下发还没接到这个集群。
EOF
)"

demo_step 2 "测试页：UDP / TCP / TLS 打到产品 AS"
demo_show_customer "$(cat <<'EOF'
同一条路径看 T5 200、T4 404、F2 603、T1 200（被叫改成 013800138000）。
接通的对话 BYE 2xx，出腿也拆。这是短跑，不是容量场。
EOF
)"
demo_m71_signal udp "${ART}"
demo_m71_signal tcp "${ART}"
demo_m71_signal tls "${ART}"

demo_step 3 "主叫取消 → 487（契约形状，不是本场呼叫类型）"
demo_require_uv
demo_require_native_runtime
demo_show_customer "第一版呼叫类型没有主叫取消。下面只对契约形状，不在 as-m71 现场演示。"
uv run pytest platform/tests/test_e1_contract_resip_runtime_full.py::test_e1_s4_caller_cancel_returns_487 -m contract -v \
  2>&1 | tee "${ART}/sip-487.log"

demo_step 4 "反诈进程的 608（这条网上没有起）"
demo_show_customer "608 属于单独的反诈进程。它会和翻译抢 5060，本场没有起。下面是判决单测，不是现场 SIP。"
uv run pytest apps/anti-fraud/tests/test_decision.py -q 2>&1 | tee "${ART}/anti-fraud-decision.log"

demo_log "Story B automated checks: OK (see ${ART})"
