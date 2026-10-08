#!/usr/bin/env bash
# Story C - Operate the platform (Helm / kind / metrics / draining / alerts)
set -euo pipefail
# shellcheck source=scripts/demo-review/lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

STRICT_KIND=0
for arg in "$@"; do
  case "${arg}" in
    --require-kind) STRICT_KIND=1 ;;
    -h | --help)
      echo "Usage: $0 [--require-kind]  (fail if kind-as-m71 missing)"
      exit 0
      ;;
  esac
done

demo_story_banner "C" "平台能运维（L1 机制演示）"
demo_show_customer "$(cat <<'EOF'
范围说明：本场演示 Helm 契约、指标/draining 单测与告警模板形态。
集群镜头是 kind as-m71，不是客户 K8s，也不是 M5 全链签收。
不得声称告警生效、缩容 actuator、生产 Helm 已独立评审签收。
详见 docs/reviews/m5-full-chain-review-2026-10-05.md 与 callload 评审 F10 对账。
EOF
)"
ART="$(demo_artifact_dir c)"
demo_log "artifacts -> ${ART}"

demo_step 1 "Helm chart 契约"
demo_show_customer "交付物：Kubernetes Helm chart（translation / anti-fraud / config-service 模板）"
make -C "${REPO_ROOT}" chart-check 2>&1 | tee "${ART}/chart-check.log"

demo_step 2 "集群镜头（kind as-m71）"
demo_show_customer "$(cat <<'EOF'
镜头是 kind as-m71，不是 kind as-m5，也不是客户 K8s。
ims-sim：S-CSCF、北向 S-SBC、南向 S-SBC、被叫、call-load。
as-sut：翻译进程、Redis、config-service。反诈进程没起，因为会和翻译抢 5060。
F1/F2 在翻译进程上是内核阻止，响应 603。
这仍是 L1：不说 M5 全链已验收，不说生产告警或缩容已闭环。
测试页不是产品控制台。7.2d 的 Ingress 登录仍在原来的 M5 集群，不在这里。
EOF
)"
if demo_m71_present; then
  {
    echo "== ims-sim =="
    demo_m71_kubectl -n ims-sim get deploy
    echo "== as-sut =="
    demo_m71_kubectl -n as-sut get deploy
  } | tee "${ART}/as-m71-deploys.txt"
  for name in scscf ssbc-north ssbc-south uas call-load; do
    ready="$(demo_m71_kubectl -n ims-sim get deploy "${name}" -o jsonpath='{.status.readyReplicas}')"
    [[ "${ready}" -ge 1 ]] || demo_die "ims-sim/${name} is not ready"
  done
  for name in as-sut-translation as-sut-redis as-sut-config-service; do
    ready="$(demo_m71_kubectl -n as-sut get deploy "${name}" -o jsonpath='{.status.readyReplicas}')"
    [[ "${ready}" -ge 1 ]] || demo_die "as-sut/${name} is not ready"
  done
  if demo_m71_kubectl -n as-sut get deploy as-sut-anti-fraud >/dev/null 2>&1; then
    demo_die "anti-fraud deployment is present; first edition keeps it off so it does not bind SIP 5060"
  fi
else
  if [[ "${STRICT_KIND}" -eq 1 ]]; then
    demo_die "kind context kind-as-m71 missing; run: bash testbed/sim-platform/kind-up.sh"
  fi
  demo_log "SKIP kind: no kind-as-m71 context"
  demo_show_customer "（本场跳过集群实拍；可展示 docs/acceptance/m71-sim-platform-evidence.md）"
  head -n 20 "${REPO_ROOT}/docs/acceptance/m71-sim-platform-evidence.md" | tee "${ART}/m71-evidence-head.txt"
fi

demo_step 3 "Ingress HTTPS 登录（仍是 kind as-m5，可选）"
demo_show_customer "$(cat <<'EOF'
这一步仍看原来的 kind as-m5：Ingress 强制 HTTPS 和控制台登录（7.2d）。
不搬到 as-m71。测试页不是这个登录。没有密码或没有 as-m5 就跳过，不当成这场已签 REQ-S-4。
EOF
)"
if [[ -n "${M5_7_2D_E2E_PASSWORD:-}" ]] && demo_kind_context; then
  make -C "${REPO_ROOT}" m5-7.2d-evidence 2>&1 | tee "${ART}/m5-7.2d-evidence.log" || demo_log "WARN: m5-7.2d-evidence failed"
else
  demo_log "SKIP m5-7.2d-evidence (stays on kind-as-m5; set M5_7_2D_E2E_PASSWORD)"
  demo_log "  see docs/acceptance/m5-7.2d-ingress-runbook.md"
fi

demo_step 4 "指标与 draining 语义"
demo_show_customer "/metrics 含 as_active_calls；draining 时 /health/ready → 503"
uv run pytest platform/tests/test_health_server.py platform/tests/test_metrics.py -q \
  2>&1 | tee "${ART}/health-metrics-unit.log"
if demo_m71_present; then
  demo_m71_kubectl -n as-sut exec deploy/as-sut-translation -- python -c \
    'import urllib.request
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
text = opener.open("http://127.0.0.1:8080/metrics", timeout=5).read().decode()
lines = [line for line in text.splitlines() if line.startswith("as_active_calls")]
if not lines:
    raise SystemExit("as_active_calls missing")
print("\n".join(lines))' \
    | tee "${ART}/pod-metrics-sample.txt"
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
