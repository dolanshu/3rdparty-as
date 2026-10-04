# Metrics / readiness helpers for M5 ISSU & scale-down evidence.
# shellcheck shell=bash

m5_use_case_deployment() {
  local ns="${1:?}" use_case="${2:?}" release="${3:-as}"
  kubectl -n "${ns}" get deploy -l \
    "app.kubernetes.io/instance=${release},app.kubernetes.io/use-case=${use_case}" \
    -o jsonpath='{.items[0].metadata.name}'
}

m5_pod_active_calls() {
  local ns="${1:?}" pod="${2:?}"
  kubectl -n "${ns}" exec "${pod}" -- python -c '
import urllib.request
text = urllib.request.urlopen("http://127.0.0.1:8080/metrics", timeout=5).read().decode()
for line in text.splitlines():
    if line.startswith("as_active_calls{") and not line.startswith("#"):
        print(int(float(line.split()[-1])))
        break
else:
    raise SystemExit("as_active_calls not found")
' 2>/dev/null
}

m5_pod_ready_http_code() {
  local ns="${1:?}" pod="${2:?}"
  kubectl -n "${ns}" exec "${pod}" -- python -c '
import urllib.error
import urllib.request
try:
    urllib.request.urlopen("http://127.0.0.1:8080/health/ready", timeout=3)
    print(200)
except urllib.error.HTTPError as e:
    print(e.code)
' 2>/dev/null || echo "000"
}

m5_list_use_case_pods() {
  local ns="${1:?}" use_case="${2:?}" release="${3:-as}"
  kubectl -n "${ns}" get pods -l \
    "app.kubernetes.io/instance=${release},app.kubernetes.io/use-case=${use_case}" \
    -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}'
}
