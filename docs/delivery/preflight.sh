#!/usr/bin/env bash
# preflight.sh — 交付物 3.1：In-house IMS Application Server（文档暂用名）
# 部署前环境校验脚本（Helm-only 生产交付形态，ADR-0013）。
#
# 用法：
#   ./preflight.sh [-n <namespace>] [-f <values.yaml>] [--context <ctx>]
#   ./preflight.sh --dry-run          # 只检查本机工具与 chart 渲染，不连集群
#   ./preflight.sh --strict           # WARN 也算失败
#   ./preflight.sh --help
#
# 退出码：
#   0  没有 FAIL（--strict 下也没有 WARN）
#   1  存在 FAIL
#   2  用法错误（参数非法）
#   3  --strict 下存在 WARN（无 FAIL）
#
# 依赖（只用基础工具，不要求 jq / yq / python）：
#   bash, awk, grep, sed, sort, mktemp, printf, date
#   kubectl（集群类检查；--dry-run 不需要）
#   helm 3.x（chart 渲染预检）
#
# 局限（如实声明，不要越读）：
#   * 这不是容量校验工具。本脚本不发明任何资源推荐值或容量阈值：
#     deploy/helm/values.yaml 里 useCases[].resources 默认为空（无 requests），
#     容量规格取决于 O1（docs/plan.md §5.1）的维护者裁决，待 M6 真实 socket 实测
#     后由 NE datasheet 给出。resources 为空时脚本只给 WARN，不猜数字。
#   * chart 没有 kubeVersion 声明（已知缺口，见 deploy/helm/README.md 与
#     docs/product/ne-datasheet.md）。这里的版本下限是按模板实际使用的 API 推导的，
#     可用 --min-k8s 覆盖。
#   * 依赖服务只做非侵入式核对（Service / Endpoint / Pod 是否存在），不在客户
#     集群创建临时 Pod、不执行 kubectl run。真正的连通性由 AS 进程在运行时用
#     Redis PING 写入指标 as_state_store_available 确认（仅当 REDIS_URL 非空时
#     产出该序列；未配置时序列不存在，不是 0）。
#   * 绝不打��� Secret 内容、token 或证书：只查存在性与 metadata。
#   * 真实集群证据尚未取得（M8 7.2d blocked），本脚本在真实客户环境的运行结果
#     才是验收证据；本仓库内未在真实集群执行过。
#
# 权威文档：
#   Helm 参数与渲染行为 .... deploy/helm/README.md（唯一权威）
#   交付清单与命令序列 .... docs/delivery/install-guide.md
#   离线包 ................. docs/delivery/airgap-package.md
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# --- 默认值（均可用命令行覆盖）-------------------------------------------------
CHART="${REPO_ROOT}/deploy/helm"
RELEASE="as"
NAMESPACE="as-prod"
CONTEXT=""
MIN_K8S="1.23"        # 见下方"Kubernetes 版本下限依据"
TIMEOUT="20"
STRICT=0
DRY_RUN=0
SKIP_NETWORK=0
VALUES_ARGS=()

# Kubernetes 版本下限依据（来源：Kubernetes 官方 Deprecated API Migration Guide
# https://kubernetes.io/docs/reference/using-api/deprecation-guide/ 中
# "available since vX.YZ" 原文；本 chart templates 实际使用的 apiVersion 见下表）：
#   apps/v1 Deployment / StatefulSet .......... available since v1.9
#   networking.k8s.io/v1 NetworkPolicy ........ available since v1.8
#   networking.k8s.io/v1 Ingress ............... available since v1.19
#   policy/v1 PodDisruptionBudget .............. available since v1.21
#   batch/v1（batch 组 GA 条目；本 chart 用 Job）  available since v1.21
#   autoscaling/v2 HorizontalPodAutoscaler ..... available since v1.23
# 取最大值 -> 1.23。这样即使后续把 autoscaling / PDB / ingress 打开，也不会因为
# 集群太老而中途失败。默认不写进 Chart.yaml 的 kubeVersion（chart 无该声明）。
API_ALWAYS_REQUIRED="v1 apps/v1"
API_NETWORKPOLICY="networking.k8s.io/v1"   # stateStores.networkPolicy.enabled
API_INGRESS="networking.k8s.io/v1"         # services.configService.ingress.enabled
API_PDB="policy/v1"                        # podDisruptionBudget.minAvailable 非空
API_HPA="autoscaling/v2"                   # autoscaling.enabled 且阈值非空
API_JOB="batch/v1"                         # stateStores.migrateJob.enabled

PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0
SKIP_COUNT=0

TMP_DIR=""
cleanup() {
  [[ -n "${TMP_DIR}" && -d "${TMP_DIR}" ]] && rm -rf "${TMP_DIR}"
  return 0
}
trap cleanup EXIT

# --- 输出 ----------------------------------------------------------------------
record() {
  # record <PASS|FAIL|WARN|SKIP> <检查名> <证据/依据>
  local level="$1" name="$2" evidence="${3:-}"
  case "${level}" in
    PASS) PASS_COUNT=$((PASS_COUNT + 1)) ;;
    FAIL) FAIL_COUNT=$((FAIL_COUNT + 1)) ;;
    WARN) WARN_COUNT=$((WARN_COUNT + 1)) ;;
    SKIP) SKIP_COUNT=$((SKIP_COUNT + 1)) ;;
  esac
  printf '%-5s %-34s %s\n' "${level}" "${name}" "${evidence}"
  case "${level}" in
    FAIL|WARN) printf '      └ 修复指引: %s\n' "${REMEDY:-见对应交付文档}" ;;
  esac
  return 0
}

usage() {
  cat <<'EOF'
preflight.sh — 部署前环境校验（交付物 3.1，Helm-only，ADR-0013）

用法:
  preflight.sh [选项]

选项:
  -n, --namespace <ns>    目标命名空间（默认 as-prod）
  -f, --values <file>     传给 helm template 的 values 文件，可重复
      --release <name>    Helm release 名（默认 as）
      --chart <path>      chart 路径（默认 deploy/helm）
      --context <name>    指定 kubeconfig context（默认用 current-context）
      --min-k8s <x.y>     K8s 最低 minor（默认 1.23，按模板实际使用的 API 推导；
                          chart 本身没有 kubeVersion 声明）
  -t, --as <seconds>      kubectl --request-timeout（默认 20）
      --strict            WARN 也算失败
      --skip-network      跳过需要连通性的项（外部依赖服务、镜像拉取提示等）
      --dry-run           只检查本机工具与 chart 渲染，不连接集群
  -h, --help              显示本帮助

退出码:
  0 无 FAIL（--strict 下也无 WARN）   1 存在 FAIL
  2 用法错误                          3 --strict 下存在 WARN

安全: 只查 Secret 存在性与 metadata，绝不打印 Secret 内容、token 或证书。
局限: 不是容量校验工具。useCases[].resources 默认为空时只给 WARN 并指向
      O1 / NE datasheet，不发明任何推荐值。详见脚本头部注释。
EOF
}

# --- 参数 ----------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--namespace) NAMESPACE="${2:-}"; shift 2 ;;
    -f|--values)    VALUES_ARGS+=("-f" "${2:-}"); shift 2 ;;
    --release)      RELEASE="${2:-}"; shift 2 ;;
    --chart)        CHART="${2:-}"; shift 2 ;;
    --context)      CONTEXT="${2:-}"; shift 2 ;;
    --min-k8s)      MIN_K8S="${2:-}"; shift 2 ;;
    -t|--as)        TIMEOUT="${2:-}"; shift 2 ;;
    --strict)       STRICT=1; shift ;;
    --skip-network) SKIP_NETWORK=1; shift ;;
    --dry-run)      DRY_RUN=1; shift ;;
    -h|--help)      usage; exit 0 ;;
    *) printf '未知参数: %s\n\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "${NAMESPACE}" || -z "${RELEASE}" || -z "${MIN_K8S}" || -z "${TIMEOUT}" ]]; then
  printf 'ERROR: --namespace/--release/--min-k8s/--as 需要非空参数\n' >&2
  exit 2
fi

TMP_DIR="$(mktemp -d)"
RENDER_FILE="${TMP_DIR}/render.yaml"
RENDER_ERR="${TMP_DIR}/render.err"
: >"${RENDER_FILE}"
: >"${RENDER_ERR}"

# --- 基础工具解析（环境变量可覆盖，风格参考 scripts/lib/repo-toolchain.sh）--------
KUBECTL=""
HELM=""
if [[ -n "${KUBECTL_BIN:-}" && -x "${KUBECTL_BIN}" ]]; then
  KUBECTL="${KUBECTL_BIN}"
elif command -v kubectl >/dev/null 2>&1; then
  KUBECTL="$(command -v kubectl)"
fi
if [[ -n "${HELM_BIN:-}" && -x "${HELM_BIN}" ]]; then
  HELM="${HELM_BIN}"
elif command -v helm >/dev/null 2>&1; then
  HELM="$(command -v helm)"
fi

kc() {
  if [[ -n "${CONTEXT}" ]]; then
    "${KUBECTL}" --context "${CONTEXT}" --request-timeout="${TIMEOUT}s" "$@"
  else
    "${KUBECTL}" --request-timeout="${TIMEOUT}s" "$@"
  fi
}

# --- 数值工具（不依赖 jq）--------------------------------------------------------
qty_millis() {
  awk 'function millis(q){ if (q ~ /m$/) { sub(/m$/,"",q); return q+0 } if (q ~ /k$/) { sub(/k$/,"",q); return q*1000 } return q*1000 } { t+=millis($1) } END { printf "%.0f\n", t+0 }'
}
qty_bytes() {
  awk 'function b(q){ if (q ~ /Ki$/) { sub(/Ki$/,"",q); return q*1024 } if (q ~ /Mi$/) { sub(/Mi$/,"",q); return q*1048576 } if (q ~ /Gi$/) { sub(/Gi$/,"",q); return q*1073741824 } if (q ~ /Ti$/) { sub(/Ti$/,"",q); return q*1099511627776 } if (q ~ /^[0-9.]+$/) return q+0; if (q ~ /k$/) { sub(/k$/,"",q); return q*1000 } if (q ~ /M$/) { sub(/M$/,"",q); return q*1000000 } if (q ~ /G$/) { sub(/G$/,"",q); return q*1000000000 } if (q ~ /T$/) { sub(/T$/,"",q); return q*1000000000000 } return -1 } { if (b($1) < 0) bad=1; t+=b($1) } END { if (bad) printf "0\n"; else printf "%.0f\n", t+0 }'
}
fmt_millis() { awk -v m="${1:-0}" 'BEGIN{ if (m>=1000) printf "%.2f core(s) = %dm", m/1000, m; else printf "%dm", m }'; }
fmt_bytes() {
  awk -v b="${1:-0}" 'BEGIN{ if (b>=1073741824) printf "%.2f GiB", b/1073741824; else if (b>=1048576) printf "%.2f MiB", b/1048576; else printf "%.0f B", b }'
}
version_ge() {
  # version_ge <a> <b> -> 0 表示 a >= b（只比较 major.minor.patch）
  awk -v a="${1#v}" -v b="${2#v}" 'BEGIN{
    split(a, A, "."); split(b, B, ".");
    am=A[1]+0; an=(A[2]==""?0:A[2]+0); ap=(A[3]==""?0:A[3]+0);
    bm=B[1]+0; bn=(B[2]==""?0:B[2]+0); bp=(B[3]==""?0:B[3]+0);
    if (am>bm) exit 0;
    if (am==bm && an>bn) exit 0;
    if (am==bm && an==bn && ap>=bp) exit 0;
    exit 1 }'
}

# 渲染结果解析：逐文档输出 kind / name / 是否声明 requests / cpu / memory
render_docs() {
  awk '
    function millis(q){ if (q ~ /m$/) { sub(/m$/,"",q); return q+0 } if (q ~ /k$/) { sub(/k$/,"",q); return q*1000 } return q*1000 }
    function bytes(q){ if (q ~ /Ki$/) { sub(/Ki$/,"",q); return q*1024 } if (q ~ /Mi$/) { sub(/Mi$/,"",q); return q*1048576 } if (q ~ /Gi$/) { sub(/Gi$/,"",q); return q*1073741824 } if (q ~ /Ti$/) { sub(/Ti$/,"",q); return q*1099511627776 } if (q ~ /^[0-9.]+$/) return q+0; if (q ~ /k$/) { sub(/k$/,"",q); return q*1000 } if (q ~ /M$/) { sub(/M$/,"",q); return q*1000000 } if (q ~ /G$/) { sub(/G$/,"",q); return q*1000000000 } if (q ~ /T$/) { sub(/T$/,"",q); return q*1000000000000 } return 0 }
    function flush(){ if (kind != "") printf "%s\t%s\t%s\t%.0f\t%.0f\t%s\n", kind, name, (hasreq ? "yes" : "no"), cpu, mem, uc }
    /^---$/ { flush(); kind=""; name=""; hasreq=0; cpu=0; mem=0; uc=""; inreq=0; next }
    /^kind: / { kind=$2 }
    /^  name: / { if (name == "") name=$2 }
    /app\.kubernetes\.io\/use-case: / { uc=$2 }
    /^ *requests: *$/ { inreq=1; hasreq=0; cpu=0; mem=0; next }
    inreq == 1 {
      if ($1 == "cpu:") { cpu=millis($2); hasreq=1; next }
      if ($1 == "memory:") { mem=bytes($2); hasreq=1; next }
      if ($1 == "ephemeral-storage:") { next }
      inreq=0
    }
    END { flush() }
  ' "${RENDER_FILE}"
}

render_grep() { grep -qE "$1" "${RENDER_FILE}" 2>/dev/null; }

printf '==> %s：部署前环境校验（release=%s namespace=%s chart=%s）\n' \
  "${SCRIPT_NAME}" "${RELEASE}" "${NAMESPACE}" "${CHART}"
printf '    模式: %s\n' "$([[ "${DRY_RUN}" -eq 1 ]] && echo '--dry-run（不连集群）' || echo '完整检查')"
printf -- '--------------------------------------------------------------------\n'

# =============================================================================
# 1. 本机工具
# =============================================================================
REMEDY="安装 kubectl（https://kubernetes.io/docs/tasks/tools/）；离线环境请事先放入离线介质"
if [[ -n "${KUBECTL}" ]]; then
  record PASS "kubectl 存在" "${KUBECTL} ($(${KUBECTL} version --client=true -o yaml 2>/dev/null | awk -F': ' '/gitVersion/ {print $2; exit}' || echo 'client 版本未知'))"
else
  record FAIL "kubectl 存在" "未找到 kubectl（--dry-run 也需要它做 client 版本自检）"
fi

REMEDY="安装 helm 3.x（chart apiVersion: v2 要求 helm 3）；离线环境请事先放入离线介质"
if [[ -n "${HELM}" ]]; then
  HELM_SHORT="$("${HELM}" version --short 2>/dev/null || echo "")"
  case "${HELM_SHORT}" in
    v3.*)
      record PASS "helm 存在且为 3.x" "${HELM} (${HELM_SHORT})" ;;
    "")
      record WARN "helm 版本判定" "${HELM} 存在但 \`helm version --short\` 无输出；请人工确认是 3.x" ;;
    *)
      record FAIL "helm 存在且为 3.x" "版本为 ${HELM_SHORT}，chart apiVersion: v2 需要 helm 3.x" ;;
  esac
else
  record FAIL "helm 存在" "未找到 helm（chart apiVersion: v2，需 helm 3.x；可用 HELM_BIN 指定）"
fi

# =============================================================================
# 2. kubeconfig / context
# =============================================================================
CURRENT_CONTEXT=""
if [[ "${DRY_RUN}" -eq 1 ]]; then
  record SKIP "kubeconfig 与 context" "--dry-run：不连接集群"
elif [[ -z "${KUBECTL}" ]]; then
  record SKIP "kubeconfig 与 context" "无 kubectl，跳过"
else
  REMEDY="配置 kubeconfig：kubectl config set-cluster/set-context/set-credentials；本脚本只读不改 context"
  if kc config current-context >/dev/null 2>&1; then
    CURRENT_CONTEXT="$(kc config current-context 2>/dev/null || echo "")"
    if [[ -n "${CONTEXT}" ]]; then
      if kc config get-contexts "${CONTEXT}" -o name >/dev/null 2>&1; then
        record PASS "kubeconfig 与 context" "使用 --context ${CONTEXT}（current-context=${CURRENT_CONTEXT}）"
      else
        record FAIL "kubeconfig 与 context" "--context ${CONTEXT} 不在 kubeconfig 中（现有: ${CURRENT_CONTEXT}）"
      fi
    else
      record PASS "kubeconfig 与 context" "current-context=${CURRENT_CONTEXT}"
    fi
  else
    record FAIL "kubeconfig 与 context" "没有 current-context：kubectl config current-context 失败"
  fi
fi

# =============================================================================
# chart 渲染（先做，后续多项检查依赖渲染结果；结论在第 10 项汇报）
# =============================================================================
RENDER_CODE=0
RENDER_STAGE=0
if [[ -z "${HELM}" ]]; then
  RENDER_STAGE=1
  RENDER_CODE=1
  printf 'ERROR: 未找到 helm，无法渲染 chart\n' >"${RENDER_ERR}"
elif [[ ! -d "${CHART}" ]]; then
  RENDER_STAGE=1
  RENDER_CODE=1
  printf 'ERROR: chart 路径不存在: %s\n' "${CHART}" >"${RENDER_ERR}"
else
  set +e
  "${HELM}" template "${RELEASE}" "${CHART}" \
    --namespace "${NAMESPACE}" "${VALUES_ARGS[@]+"${VALUES_ARGS[@]}"}" \
    >"${RENDER_FILE}" 2>"${RENDER_ERR}"
  RENDER_CODE=$?
  set -e
fi

# =============================================================================
# 3./4. K8s 版本与 API（需要连集群）
# =============================================================================
SERVER_VERSION=""
if [[ "${DRY_RUN}" -eq 1 ]]; then
  record SKIP "K8s 版本下限" "--dry-run：不连接集群"
  record SKIP "必需 API 可用性" "--dry-run：不连接集群"
elif [[ -z "${KUBECTL}" ]]; then
  record SKIP "K8s 版本下限" "无 kubectl"
  record SKIP "必需 API 可用性" "无 kubectl"
else
  REMEDY="升级集群到 >= ${MIN_K8S}（依据：chart 模板用到的 autoscaling/v2 自 1.23 起可用）；或与维护者确认本部署不启用该可选特性后用 --min-k8s 覆盖"
  SERVER_VERSION="$(kc version -o yaml 2>/dev/null | awk -F': ' '/gitVersion/ {print $2; exit}' || true)"
  if [[ -z "${SERVER_VERSION}" ]]; then
    SERVER_VERSION="$(kc version -o json 2>/dev/null | sed -n 's/.*"gitVersion"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1 || true)"
  fi
  if [[ -z "${SERVER_VERSION}" ]]; then
    record FAIL "K8s 版本下限" "无法读取服务端版本（kubectl version 无输出）；请检查 API Server 连通性与 --as 超时"
  elif version_ge "${SERVER_VERSION}" "${MIN_K8S}"; then
    record PASS "K8s 版本下限" "server ${SERVER_VERSION} >= ${MIN_K8S}（chart 无 kubeVersion 声明，此下限按模板实际使用的 API 推导）"
  else
    record FAIL "K8s 版本下限" "server ${SERVER_VERSION} < ${MIN_K8S}"
  fi

  # API 探测：必需项 + 由渲染结果决定的条件项
  API_VERSIONS="$(kc api-versions 2>/dev/null || true)"
  if [[ -z "${API_VERSIONS}" ]]; then
    record FAIL "必需 API 可用性" "kubectl api-versions 无输出，无法探测 API 可用性"
  else
    API_REQUIRED="${API_ALWAYS_REQUIRED}"
    if [[ "${RENDER_CODE}" -eq 0 ]]; then
      render_grep 'kind: NetworkPolicy' && API_REQUIRED="${API_REQUIRED} ${API_NETWORKPOLICY}"
      render_grep 'kind: Ingress' && API_REQUIRED="${API_REQUIRED} ${API_INGRESS}"
      render_grep 'kind: PodDisruptionBudget' && API_REQUIRED="${API_REQUIRED} ${API_PDB}"
      render_grep 'kind: HorizontalPodAutoscaler' && API_REQUIRED="${API_REQUIRED} ${API_HPA}"
      render_grep 'kind: Job' && API_REQUIRED="${API_REQUIRED} ${API_JOB}"
    else
      # 渲染 fail-closed 时按最严格集合探测（fail-closed 不代表跳过探测）
      API_REQUIRED="${API_REQUIRED} ${API_NETWORKPOLICY} ${API_PDB} ${API_HPA} ${API_JOB}"
    fi
    MISSING_APIS=""
    for api in ${API_REQUIRED}; do
      printf '%s\n' "${API_VERSIONS}" | grep -qx "${api}" || MISSING_APIS="${MISSING_APIS} ${api}"
    done
    if [[ -z "${MISSING_APIS}" ]]; then
      record PASS "必需 API 可用性" "已探测: $(printf '%s' "${API_REQUIRED}" | tr '\n' ' ')"
    else
      record FAIL "必需 API 可用性" "集群未提供:${MISSING_APIS}"
    fi
  fi
fi

# =============================================================================
# 5. 命名空间
# =============================================================================
if [[ "${DRY_RUN}" -eq 1 ]]; then
  record SKIP "命名空间" "--dry-run：不连接集群"
elif [[ -z "${KUBECTL}" ]]; then
  record SKIP "命名空间" "无 kubectl"
else
  REMEDY="helm upgrade --install 加 --create-namespace，或先 kubectl create namespace ${NAMESPACE}；命名空间是单客户单系统的边界（REQ-NF-9）"
  if kc get namespace "${NAMESPACE}" >/dev/null 2>&1; then
    NS_LABELS="$(kc get namespace "${NAMESPACE}" -o go-template='{{range $k, $v := .metadata.labels}}{{$k}}={{$v}} {{end}}' 2>/dev/null | tr -s ' ' || true)"
    NS_ANN="$(kc get namespace "${NAMESPACE}" -o go-template='{{range $k, $v := .metadata.annotations}}{{$k}} {{end}}' 2>/dev/null | tr -s ' ' || true)"
    record PASS "命名空间存在" "${NAMESPACE} 已存在；labels: ${NS_LABELS:-（无）}；annotations: ${NS_ANN:-（无）}"
  else
    if [[ "$(kc auth can-i create namespaces 2>/dev/null || echo no)" == "yes" ]]; then
      record PASS "命名空间（可创建）" "${NAMESPACE} 不存在，但当前账号有 create namespaces 权限，helm --create-namespace 可创建"
    else
      record FAIL "命名空间" "${NAMESPACE} 不存在，且当前账号无 create namespaces 权限"
    fi
  fi
fi

# =============================================================================
# 6. 节点与资源（render 基础上的 requests 之和 vs allocatable）
# =============================================================================
if [[ "${DRY_RUN}" -eq 1 ]]; then
  record SKIP "节点资源与 requests 之和" "--dry-run：不连接集群（可在联网侧单独核对渲染结果）"
elif [[ -z "${KUBECTL}" ]]; then
  record SKIP "节点资源与 requests 之和" "无 kubectl"
elif [[ "${RENDER_CODE}" -ne 0 ]]; then
  record SKIP "节点资源与 requests 之和" "chart 未渲染成功（第 10 项），无法提取 requests；先补齐必填项再跑本项"
else
  REMEDY="useCases[].resources 在 values.yaml 中默认为空（无 requests）——本脚本不发明推荐值；资源规格待 O1 裁决后由 docs/product/ne-datasheet.md 给出。在那之前只能人工核对容量"
  NODE_COUNT="$(kc get nodes --no-headers 2>/dev/null | grep -c . || true)"
  ALLOC_CPU_M="$(kc get nodes -o jsonpath='{range .items[*]}{.status.allocatable.cpu}{"\n"}{end}' 2>/dev/null | grep -v '^$' | qty_millis || true)"
  ALLOC_MEM_B="$(kc get nodes -o jsonpath='{range .items[*]}{.status.allocatable.memory}{"\n"}{end}' 2>/dev/null | grep -v '^$' | qty_bytes || true)"
  ALLOC_EPH_B="$(kc get nodes -o jsonpath='{range .items[*]}{.status.allocatable.ephemeral-storage}{"\n"}{end}' 2>/dev/null | grep -v '^$' | qty_bytes || true)"

  DOCS="$(render_docs)"
  SUM_CPU_M="$(printf '%s\n' "${DOCS}" | awk -F'\t' '{t+=$4} END {printf "%.0f\n", t+0}')"
  SUM_MEM_B="$(printf '%s\n' "${DOCS}" | awk -F'\t' '{t+=$5} END {printf "%.0f\n", t+0}')"
  AS_UC_NO_REQ="$(printf '%s\n' "${DOCS}" | awk -F'\t' '$1=="Deployment" && $6!="" && $3=="no" {print $2}' | tr '\n' ' ' || true)"

  record PASS "节点数量与 allocatable" "nodes=${NODE_COUNT}；allocatable cpu=$(fmt_millis "${ALLOC_CPU_M}") memory=$(fmt_bytes "${ALLOC_MEM_B}") ephemeral-storage=$(fmt_bytes "${ALLOC_EPH_B}")"

  if awk -v a="${SUM_CPU_M}" -v b="${ALLOC_CPU_M}" 'BEGIN{exit !(a>0)}'; then
    if awk -v a="${SUM_CPU_M}" -v b="${ALLOC_CPU_M}" 'BEGIN{exit !(a<=b)}'; then
      record PASS "本次部署 CPU requests 之和" "$(fmt_millis "${SUM_CPU_M}") <= allocatable $(fmt_millis "${ALLOC_CPU_M}")"
    else
      record FAIL "本次部署 CPU requests 之和" "$(fmt_millis "${SUM_CPU_M}") > allocatable $(fmt_millis "${ALLOC_CPU_M}")"
    fi
    if awk -v a="${SUM_MEM_B}" -v b="${ALLOC_MEM_B}" 'BEGIN{exit !(a<=b)}'; then
      record PASS "本次部署内存 requests 之和" "$(fmt_bytes "${SUM_MEM_B}") <= allocatable $(fmt_bytes "${ALLOC_MEM_B}")"
    else
      record FAIL "本次部署内存 requests 之和" "$(fmt_bytes "${SUM_MEM_B}") > allocatable $(fmt_bytes "${ALLOC_MEM_B}")"
    fi
  else
    record WARN "本次部署 requests 之和" "渲染结果中没有任何 resources.requests —— useCases[].resources 默认为空，未声明 resources，无法做容量前置校验；资源规格建议待 O1 裁决后由 ne-datasheet 给出（AGENT.md §2：M6 实测前不发布容量数字）"
  fi

  if [[ -n "${AS_UC_NO_REQ}" ]]; then
    record WARN "AS use-case Pod 未声明 resources" "以下 Deployment 无 requests: ${AS_UC_NO_REQ} —— 未声明 resources，无法做容量前置校验；资源规格建议待 O1 裁决后由 ne-datasheet 给出"
  else
    record PASS "AS use-case Pod 声明了 resources" "$(printf '%s\n' "${DOCS}" | awk -F'\t' '$1=="Deployment" && $6!="" {print $2"="$3}' | tr '\n' ' ')"
  fi
fi

# =============================================================================
# 7. 存储（仅当 stateStores.postgres.persistence.enabled=true）
# =============================================================================
if [[ "${RENDER_CODE}" -ne 0 ]]; then
  record SKIP "存储（PVC / StorageClass）" "chart 未渲染成功（第 10 项），无法判断是否启用持久化"
elif [[ "${DRY_RUN}" -eq 1 ]]; then
  record SKIP "存储（PVC / StorageClass）" "--dry-run：不连接集群"
elif ! render_grep 'volumeClaimTemplates'; then
  record PASS "存储（PVC / StorageClass）" "渲染结果无 volumeClaimTemplates —— 内建 PostgreSQL 用 emptyDir，生产不建议（见 docs/acceptance/m5-state-stores-runbook.md）"
else
  REMEDY="chart 的 volumeClaimTemplates 不指定 storageClassName，因此必须有默认 StorageClass；PVC 处于 Pending 时先查 kubectl describe pvc 与 StorageClass 的 provisioner/参数（AGENT.md §15 O1 未裁决，容量数值不得凭空给出）"
  REQ_SIZE="$(sed -n 's/^ *storage: *//p' "${RENDER_FILE}" | tr -d '"' | head -1)"
  DEFAULT_SC="$(kc get storageclass -o go-template='{{range .items}}{{.metadata.name}} {{index .metadata.annotations "storageclass.kubernetes.io/is-default-class"}}{{"\n"}}{{end}}' 2>/dev/null | awk '$2=="true" {print $1}' | head -1)"
  if [[ -z "${DEFAULT_SC}" ]]; then
    record FAIL "默认 StorageClass 存在" "stateStores.postgres.persistence.enabled=true 但集群没有默认 StorageClass（模板不指定 storageClassName）"
  else
    record PASS "默认 StorageClass 存在" "${DEFAULT_SC}；values 请求 storage=${REQ_SIZE:-（未渲染出 size）}"
  fi
  PVC_NAME="$(kc get pvc -n "${NAMESPACE}" -o name 2>/dev/null | sed 's|persistentvolumeclaim/||' | grep -E '^(data-)?postgres' | head -1 || true)"
  if [[ -n "${PVC_NAME}" ]]; then
    PVC_CAP="$(kc get pvc "${PVC_NAME}" -n "${NAMESPACE}" -o jsonpath='{.status.capacity.storage}' 2>/dev/null || echo "")"
    record PASS "已存在的 PVC 容量" "${PVC_NAME}: status.capacity.storage=${PVC_CAP:-（尚未绑定）}（对比 values 请求 ${REQ_SIZE}）"
  else
    record WARN "PVC 容量" "首次安装，尚无 PVC；实际可用容量由 StorageClass / provisioner 在绑定后决定，本脚本不做容量预测，也不发明推荐值"
  fi
fi

# =============================================================================
# 8. 依赖服务（Redis / PostgreSQL）—— 非侵入式
# =============================================================================
NETWORK_NOTE="真正的连通性由 AS 进程在运行时用 Redis PING 写入指标 as_state_store_available 确认（REDIS_URL 为空时该序列不存在，不是 0）"
if [[ "${DRY_RUN}" -eq 1 ]]; then
  record SKIP "依赖服务 Redis/PostgreSQL" "--dry-run：不连接集群"
elif [[ -z "${KUBECTL}" ]]; then
  record SKIP "依赖服务 Redis/PostgreSQL" "无 kubectl"
elif [[ "${RENDER_CODE}" -ne 0 ]]; then
  record SKIP "依赖服务 Redis/PostgreSQL" "chart 未渲染成功（第 10 项），无法确定依赖形态"
else
  REMEDY="内建状态存储由 chart 渲染（stateStores.enabled）；外部依赖请在 values 里给 postgres.host / redis.url，或用 redis.sentinel.addresses；本脚本只查存在性，不创建临时 Pod、不执行 kubectl run"
  if render_grep 'component: state-postgres'; then
    PG_SVC="$(grep -E '^  name: .*-postgres$' "${RENDER_FILE}" | head -1 | awk '{print $2}')"
    RD_SVC="$(grep -E '^  name: .*-redis$' "${RENDER_FILE}" | head -1 | awk '{print $2}')"
    PG_SVC="${PG_SVC:-<fullname>-postgres}"
    RD_SVC="${RD_SVC:-<fullname>-redis}"
    for pair in "PostgreSQL:${PG_SVC}" "Redis:${RD_SVC}"; do
      KIND_NAME="${pair%%:*}"
      SVC_NAME="${pair#*:}"
      if kc get service "${SVC_NAME}" -n "${NAMESPACE}" >/dev/null 2>&1; then
        EP_COUNT="$(kc get endpoints "${SVC_NAME}" -n "${NAMESPACE}" -o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null | grep -c . || true)"
        if [[ "${EP_COUNT}" -gt 0 ]]; then
          record PASS "内建 ${KIND_NAME} Service/Endpoint" "${SVC_NAME}: endpoints 地址数=${EP_COUNT}"
        else
          record WARN "内建 ${KIND_NAME} Service/Endpoint" "${SVC_NAME} 存在但暂无 endpoints（首次安装属正常；Pod 未就绪时 AS 会探不到）。${NETWORK_NOTE}"
        fi
      else
        record WARN "内建 ${KIND_NAME} Service" "${SVC_NAME} 尚未创建（首次安装前必然如此）。${NETWORK_NOTE}"
      fi
    done
    if render_grep 'component: state-postgres' && render_grep 'kind: StatefulSet'; then
      PG_READY="$(kc get pods -n "${NAMESPACE}" -l app.kubernetes.io/component=state-postgres --no-headers 2>/dev/null | grep -c 'Running' || true)"
      record PASS "内建 PostgreSQL Pod" "state-postgres Running 副本数=${PG_READY}（不是容量结论）"
    fi
  else
    PG_HOST="$(awk -F': ' '/^  CONFIG_DB_HOST: /{gsub(/"/,"",$2); print $2; exit}' "${RENDER_FILE}")"
    RD_URL="$(awk -F': ' '/^  REDIS_URL: /{gsub(/"/,"",$2); print $2; exit}' "${RENDER_FILE}")"
    if [[ -z "${PG_HOST:-}" ]]; then
      record WARN "外部 PostgreSQL" "渲染出的 CONFIG_DB_HOST 为空 —— values 需要 postgres.host（外部治理库，ADR-0007）"
    elif [[ "${SKIP_NETWORK}" -eq 1 ]]; then
      record SKIP "外部 PostgreSQL" "--skip-network：host=${PG_HOST}（cluster 外地址不做连通性探测）"
    elif [[ "${PG_HOST}" == *.* ]]; then
      record SKIP "外部 PostgreSQL" "host=${PG_HOST} 看起来是集群外地址；非侵入式检查到此为止。${NETWORK_NOTE}"
    elif kc get service "${PG_HOST}" -n "${NAMESPACE}" >/dev/null 2>&1; then
      EP_COUNT="$(kc get endpoints "${PG_HOST}" -n "${NAMESPACE}" -o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null | grep -c . || true)"
      record PASS "外部 PostgreSQL Service" "同命名空间存在 Service ${PG_HOST}，endpoints 地址数=${EP_COUNT}。${NETWORK_NOTE}"
    else
      record WARN "外部 PostgreSQL" "同命名空间找不到 Service ${PG_HOST}：若它由客户自建在别的命名空间，本脚本不做跨命名空间猜测。${NETWORK_NOTE}"
    fi
    if [[ -z "${RED_URL:-}" ]]; then
      record WARN "外部 Redis" "渲染出的 REDIS_URL 为空（redis.url 为空且 redis.sentinel.masters 为空）—— 运行态状态存储不可用；拓扑待 O5/D3 裁决，不要凭空填地址"
    elif [[ "${SKIP_NETWORK}" -eq 1 ]]; then
      record SKIP "外部 Redis" "--skip-network：${RED_URL%%@*}@***（凭据不回显）"
    else
      record PASS "外部 Redis 已配置" "redis.url 已设置（凭据不回显）；${NETWORK_NOTE}"
    fi
  fi
fi

# =============================================================================
# 9. RBAC（本 chart 不创建 Role/RoleBinding）
# =============================================================================
RBAC_RESOURCES="serviceaccounts deployments configmaps secrets services statefulsets jobs networkpolicies persistentvolumeclaims poddisruptionbudgets horizontalpodautoscalers"
if [[ "${DRY_RUN}" -eq 1 ]]; then
  record SKIP "RBAC 权限" "--dry-run：不连接集群"
elif [[ -z "${KUBECTL}" ]]; then
  record SKIP "RBAC 权限" "无 kubectl"
else
  REMEDY="本 chart 不渲染 Role/RoleBinding，安装账号必须自带这些权限；请客户 K8s 管理员按 deploy/helm/templates 实际渲染的 kind 列表授予（缺失时 helm install 会在创建对象时被 API Server 拒绝）"
  # 只检查本次渲染真正会用到的资源类型；渲染失败时按最严格集合检查。
  MISSING_RBAC=""
  for res in ${RBAC_RESOURCES}; do
    # 渲染成功时只检查本次真正会渲染的资源；渲染失败（fail-closed）时按最严格集合检查。
    case "${res}" in
      networkpolicies)         NEEDED_KIND='kind: NetworkPolicy' ;;
      persistentvolumeclaims)  NEEDED_KIND='volumeClaimTemplates' ;;
      poddisruptionbudgets)    NEEDED_KIND='kind: PodDisruptionBudget' ;;
      horizontalpodautoscalers) NEEDED_KIND='kind: HorizontalPodAutoscaler' ;;
      statefulsets)            NEEDED_KIND='kind: StatefulSet' ;;
      jobs)                    NEEDED_KIND='kind: Job' ;;
      *)                       NEEDED_KIND='' ;;
    esac
    if [[ -n "${NEEDED_KIND}" && "${RENDER_CODE}" -eq 0 ]]; then
      if render_grep "${NEEDED_KIND}"; then
        :
      else
        continue
      fi
    fi
    if [[ "$(kc auth can-i create "${res}" -n "${NAMESPACE}" 2>/dev/null || echo no)" != "yes" ]]; then
      MISSING_RBAC="${MISSING_RBAC} create/${res}"
    fi
  done
  if render_grep 'kind: Ingress'; then
    [[ "$(kc auth can-i create ingresses -n "${NAMESPACE}" 2>/dev/null || echo no)" == "yes" ]] || MISSING_RBAC="${MISSING_RBAC} create/ingresses"
  fi
  if [[ "$(kc auth can-i create namespaces 2>/dev/null || echo no)" != "yes" ]]; then
    MISSING_RBAC="${MISSING_RBAC} create/namespaces(cluster)"
  fi
  if [[ -z "${MISSING_RBAC}" ]]; then
    record PASS "RBAC 权限" "渲染涉及的 create 权限均具备（namespace=${NAMESPACE}）"
  else
    record FAIL "RBAC 权限" "缺少:${MISSING_RBAC}"
  fi
fi

# =============================================================================
# 10. Chart 渲染预检（fail-closed 识别为 PASS）
# =============================================================================
REMEDY="按提示补齐必填项：tls.secretName（客户 PKI Secret，ADR-0016）、sip.peerAllowlist（S-SBC CIDR，ADR-0016）、stateStores 场景的 postgres.secretName（ADR-0026）；参数口径见 deploy/helm/README.md"
if [[ "${RENDER_STAGE}" -eq 1 ]]; then
  record FAIL "chart 渲染预检" "$(head -1 "${RENDER_ERR}" 2>/dev/null || echo "无法渲染 chart")（chart=${CHART}）"
elif [[ "${RENDER_CODE}" -eq 0 ]]; then
  KIND_COUNT="$(grep -c '^kind:' "${RENDER_FILE}" || true)"
  record PASS "chart 渲染预检" "渲染成功：${KIND_COUNT} 个对象；必填项（tls.secretName / sip.peerAllowlist / postgres.secretName）已给齐"
  record PASS "chart fail-closed 守卫" "未触发 fail-closed 分支（templates/validate-install.yaml 三条守卫：tls.secretName / sip.peerAllowlist / postgres.secretName 均未命中）"
elif grep -q 'tls.secretName' "${RENDER_ERR}"; then
  record PASS "chart 渲染预检（预期 fail-closed）" "渲染按预期失败：tls.enabled=true 但 tls.secretName 为空 —— fail-closed 生效（ADR-0016），安装会被 chart 拒绝而不是带着空证书上线"
  record SKIP "chart 其余渲染相关检查" "fail-closed 触发，渲染无产物可供解析"
elif grep -q 'peerAllowlist' "${RENDER_ERR}"; then
  record PASS "chart 渲染预检（预期 fail-closed）" "渲染按预期失败：sip.peerAllowlist 为空 —— fail-closed 生效（ADR-0016）"
  record SKIP "chart 其余渲染相关检查" "fail-closed 触发，渲染无产物可供解析"
elif grep -q 'postgres.secretName' "${RENDER_ERR}"; then
  record PASS "chart 渲染预检（预期 fail-closed）" "渲染按预期失败：stateStores.enabled 且未给 postgres.secretName —— fail-closed 生效（ADR-0026）"
  record SKIP "chart 其余渲染相关检查" "fail-closed 触发，渲染无产物可供解析"
else
  record FAIL "chart 渲染预检" "渲染失败且不是已知的 fail-closed 守卫，前 3 行错误: $(head -3 "${RENDER_ERR}" | tr '\n' ' ')"
fi

# =============================================================================
# 11. 镜像来源（提示级；绝不尝试拉取）
# =============================================================================
REMEDY="把 image.repository / image.tag 指向客户内网 registry 的真实镜像；占位符 registry.example.com 不可拉取。离线安装包制作见 docs/delivery/airgap-package.md"
if [[ "${RENDER_CODE}" -ne 0 ]]; then
  record SKIP "镜像来源提示" "chart 未渲染成功（第 10 项），无法提取镜像引用"
else
  IMAGES="$(grep -E '^ *image: ' "${RENDER_FILE}" | sed 's/^ *image: //' | tr -d '"' | sort -u || true)"
  if [[ -z "${IMAGES}" ]]; then
    record WARN "镜像来源提示" "渲染结果里没有 image 字段"
  fi
  while IFS= read -r img; do
    [[ -z "${img}" ]] && continue
    case "${img}" in
      *registry.example.com*)
        record WARN "镜像占位符 ${img}" "仍是 registry.example.com 占位地址（values.yaml 默认值），必须改为客户内网 registry；tag 需与交付版本一致" ;;
      *:0.0.0|*:0.0.0-*)
        record WARN "镜像 tag ${img}" "tag 落到 Chart.appVersion=0.0.0（values.image.tag 为空时的回退）。根 VERSION 与 Chart.appVersion 不同步是已知缺口，不要用 0.0.0 当交付版本" ;;
      *)
        record PASS "镜像引用 ${img}" "已解析到具体引用（仅提示级检查，本脚本不拉取镜像）" ;;
    esac
  done <<<"${IMAGES}"
  if [[ "${SKIP_NETWORK}" -eq 1 ]]; then
    record SKIP "镜像可拉取性" "--skip-network：按提示级处理，不做任何拉取尝试"
  else
    record PASS "镜像可拉取性" "未执行任何拉取（客户网络内不做试探性 pull）；离线环境请先 load 镜像再安装，见 docs/delivery/airgap-package.md"
  fi
fi

# =============================================================================
# 12. 端口占用 / 冲突提示
# =============================================================================
REMEDY="NodePort/hostNetwork 场景下端口冲突由客户 K8s 管理员决策；SIP 5060/5061 与健康 8080、控制台 8000 是协议/约定端口（deploy/helm/values.yaml），不是容量数字"
if [[ "${DRY_RUN}" -eq 1 || -z "${KUBECTL}" ]]; then
  record SKIP "端口占用提示" "--dry-run 或无 kubectl：不连接集群"
elif [[ "${RENDER_CODE}" -ne 0 ]]; then
  record SKIP "端口占用提示" "chart 未渲染成功（第 10 项），无法提取端口"
else
  MY_PORTS="$(grep -E '^ *containerPort: ' "${RENDER_FILE}" | sed 's/^ *containerPort: //' | sort -u | tr '\n' ' ' || true)"
  SIP_P="$(awk -F': ' '/^  SIP_LISTEN_PORT: /{gsub(/"/,"",$2); print $2; exit}' "${RENDER_FILE}")"
  SIPTLS_P="$(awk -F': ' '/^  SIP_TLS_LISTEN_PORT: /{gsub(/"/,"",$2); print $2; exit}' "${RENDER_FILE}")"
  HEALTH_P="$(awk -F': ' '/^  AS_HEALTH_PORT: /{gsub(/"/,"",$2); print $2; exit}' "${RENDER_FILE}")"
  CFG_P="$(awk -F': ' '/^ *- name: http$/{p=1} p && /^ *port: /{gsub(/"/,"",$2); print $2; exit}' "${RENDER_FILE}")"
  record PASS "本部署使用的容器端口" "SIP=${SIP_P:-?} TLS=${SIPTLS_P:-?} 健康=${HEALTH_P:-?} 控制台=${CFG_P:-?}；容器端口集合: ${MY_PORTS:-（无）}"
  CONFLICTS="$(kc get svc -A -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.spec.type}{"\t"}{range .spec.ports[*]}{.port}{","}{end}{"\n"}{end}' 2>/dev/null \
    | awk -F'\t' -v ports="${MY_PORTS}" '
        BEGIN { n=split(ports, P, " "); for (i=1;i<=n;i++) if (P[i] != "") want[P[i]]=1 }
        ($3=="NodePort" || $3=="LoadBalancer") {
          m=split($4, L, ",");
          for (j=1;j<=m;j++) if (L[j] != "" && want[L[j]]) print $1"/"$2"(" $3 ", port " L[j] ")"
        }' || true)"
  if [[ -n "${CONFLICTS}" ]]; then
    record WARN "NodePort/LoadBalancer 端口占用" "以下既有 Service 已占用相同端口号: ${CONFLICTS} —— 请与客户确认（若为本 release 自身对象可忽略）"
  else
    record PASS "NodePort/LoadBalancer 端口占用" "未发现与本部署容器端口冲突的 NodePort/LoadBalancer Service"
  fi
fi

# =============================================================================
# 汇总
# =============================================================================
printf -- '--------------------------------------------------------------------\n'
printf '汇总: PASS=%d FAIL=%d WARN=%d SKIP=%d\n' "${PASS_COUNT}" "${FAIL_COUNT}" "${WARN_COUNT}" "${SKIP_COUNT}"
if [[ "${FAIL_COUNT}" -gt 0 ]]; then
  printf '结论: 存在 FAIL 项 —— 不要继续安装。修复后重跑本脚本。\n'
  printf '退出码: 1\n'
  exit 1
fi
if [[ "${STRICT}" -eq 1 && "${WARN_COUNT}" -gt 0 ]]; then
  printf '结论: --strict 模式，WARN 视为失败。\n'
  printf '退出码: 3\n'
  exit 3
fi
printf '结论: 无 FAIL 项。%s\n' "$([[ "${WARN_COUNT}" -gt 0 ]] && echo '存在 WARN，请逐条确认后再安装。' || echo '')"
printf '退出码: 0\n'
exit 0