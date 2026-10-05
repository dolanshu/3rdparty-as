#!/usr/bin/env bash
# Story C — 平台能运维（Helm / kind / metrics / draining / 告警）
set -euo pipefail
# shellcheck source=scripts/demo-review/lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

STRICT_KIND=0
for arg in "$@"; do
  case "${arg}" in
    --require-kind) STRICT_KIND=1 ;;
    -h | --help)
      echo "Usage: $0 [--require-kind]  (fail if kind-as-m5 missing)"
      exit 0
      ;;
  esac
done

demo_story_banner "C" "平台能运维（L1 机制演示）"
demo_show_customer "$(cat <<'EOF'
范围说明：本场演示 Helm 契约、指标/draining 单测与告警模板形态。
不得对客户声称 M5 全链（告警生效、缩容 actuator、生产 Helm）已独立评审签收；
详见 docs/reviews/m5-full-chain-review-2026-10-05.md 与 callload 评审 F10 对账。
EOF
)"
ART="$(demo_artifact_dir c)"
demo_log "artifacts -> ${ART}"

demo_step 1 "Helm chart 契约"
demo_show_customer "交付物：Kubernetes Helm chart（translation / anti-fraud / config-service 模板）"
make -C "${REPO_ROOT}" chart-check 2>&1 | tee "${ART}/chart-check.log"

demo_step 2 "集群 Pod 健康（kind as-m5）"
demo_show_customer "translation / anti-fraud / config-service Pod Running；与客户 on-prem 形态一致"
if demo_kind_context; then
  bash "${REPO_ROOT}/deploy/kind/m5-verify.sh" 2>&1 | tee "${ART}/m5-verify.log"
else
  if [[ "${STRICT_KIND}" -eq 1 ]]; then
    demo_die "kind context missing; run: make m5-cluster-evidence (see m5-evidence-summary.md)"
  fi
  demo_log "SKIP kind: no kind-as-m5 context"
  demo_show_customer "（本场跳过集群实拍；可展示 m5-evidence-summary.md 与 artifacts/m5 日志）"
  head -n 35 "${REPO_ROOT}/docs/acceptance/m5-evidence-summary.md" | tee "${ART}/m5-evidence-summary-head.txt"
fi

demo_step 3 "Ingress HTTPS 登录（可选，需密码）"
demo_show_customer "生产同源：Ingress 强制 HTTPS + 控制台登录（7.2d 证据）"
if [[ -n "${M5_7_2D_E2E_PASSWORD:-}" ]] && demo_kind_context; then
  make -C "${REPO_ROOT}" m5-7.2d-evidence 2>&1 | tee "${ART}/m5-7.2d-evidence.log" || demo_log "WARN: m5-7.2d-evidence failed"
else
  demo_log "SKIP m5-7.2d-evidence (set M5_7_2D_E2E_PASSWORD and kind cluster)"
  demo_log "  see docs/acceptance/m5-7.2d-ingress-runbook.md"
fi

demo_step 4 "指标与 draining 语义"
demo_show_customer "/metrics 含 as_active_calls；draining 时 /health/ready → 503"
uv run pytest platform/tests/test_health_server.py platform/tests/test_metrics.py -q \
  2>&1 | tee "${ART}/health-metrics-unit.log"
if demo_kind_context; then
  NS="${K8S_NAMESPACE:-as-m5}"
  TR_POD="$(kubectl -n "${NS}" get pod -l app.kubernetes.io/use-case=translation -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
  if [[ -n "${TR_POD}" ]]; then
    kubectl -n "${NS}" exec "${TR_POD}" -- python -c \
      "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/metrics').read().decode()[:800])" \
      2>&1 | tee "${ART}/pod-metrics-sample.txt" || true
  fi
fi

demo_step 5 "缩容保护与 ISSU runbook"
demo_show_customer "缩容前 plan_scale_down 判据；ISSU = draining（见 m5-downscale-runbook.md）"
uv run pytest platform/tests/test_downscale_guard.py -q 2>&1 | tee "${ART}/downscale-guard.log"
head -n 40 "${REPO_ROOT}/docs/acceptance/m5-downscale-runbook.md" | tee "${ART}/downscale-runbook-head.txt"

demo_step 6 "告警规则模板（无 CPS 绝对值）"
demo_show_customer "开箱 Prometheus/Grafana 规则：比例与状态类，容量阈值待 O1 后填写"
head -n 50 "${REPO_ROOT}/deploy/alerts/as-alerts.yaml" | tee "${ART}/alerts-head.yaml"
wc -l "${REPO_ROOT}/deploy/alerts/as-alerts.yaml" | tee "${ART}/alerts-wc.txt"

demo_log "Story C automated checks: OK (see ${ART})"
