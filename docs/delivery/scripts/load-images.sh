#!/usr/bin/env bash
# load-images.sh — 交付物 3.2 的离线侧脚本：校验和验证 + 镜像导入 + 离线安装前置检查
# In-house IMS Application Server（文档暂用名），Helm-only 生产交付形态（ADR-0013）。
#
# 用法:
#   ./load-images.sh --bundle ./airgap-in --verify-only
#   ./load-images.sh --bundle ./airgap-in --load --namespace as-prod --values values.yaml
#   ./load-images.sh --help
#
# 退出码:
#   0  校验与前置检查通过（--load 时表示镜像已导入）
#   1  校验不通过 / 必需项缺失 / 镜像导入失败
#   2  用法错误
#
# 依赖: bash, awk, grep, sed, sha256sum
#   sha256sum（校验和，风格沿用 deploy/kind/m5-lib.sh 的供应链守卫）
#   docker（--load 时；或按提示由客户在节点侧用 ctr / crictl 导入）
#   helm 3.x、kubectl（离线安装前置检查）
#
# 安全: 只检查 Secret 是否存在（-o name），绝不读取或打印 Secret 内容、token、
#       证书；也不在本脚本里硬编码任何 values 或凭据。打印的 helm 命令是骨架，
#       参数值一律占位符，口径见 docs/delivery/install-guide.md 与
#       deploy/helm/README.md。
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
BUNDLE_DIR="./airgap-in"
VERIFY_ONLY=0
DO_LOAD=0
NAMESPACE="as-prod"
VALUES_FILE=""
CONTEXT=""
EXPECTED_CONTEXT="${AS_TARGET_CONTEXT:-}"
RELEASE_NAME="as"
TLS_SECRET=""
POSTGRES_SECRET=""
CONFIG_RUNTIME_SECRET=""
MIGRATE_OWNER_SECRET=""
CHART_TGZ=""
DRY_RUN=0

usage() {
  cat <<'EOF'
load-images.sh — 离线包安装（离线侧）：校验和验证 + 镜像导入 + 前置检查

用法:
  load-images.sh --bundle <dir> [--verify-only | --load] [选项]

选项:
      --bundle <dir>         离线包目录（默认 ./airgap-in）
      --verify-only          只做校验和与前置检查，不导入镜像（默认行为）
      --load                 把 images/*.tar 导入本机 docker（需要 docker）
      --namespace <ns>       目标命名空间（默认 as-prod）
      --values <file>        客户值文件（用于推断必需的 Secret 名；不在此硬编码）
      --context <name>       期望的 kubeconfig context；与当前 context 不一致即失败
      --release <name>       Helm release 名（默认 as）
      --chart-tgz <file>     指定 chart 包（默认取 bundle 目录下唯一 .tgz）
      --tls-secret <name>    TLS Secret 名（证书由客户 PKI 提供，ADR-0016）
      --postgres-secret <n>  PostgreSQL 凭据 Secret 名（键: CONFIG_DB_USER 等）
      --config-runtime-secret <n>  config-service 运行时 Secret 名
                              （键: AS_CONFIG_DSN / AS_AUDIT_RESOURCE_HMAC_KEY_B64）
      --migrate-owner-secret <n>    migrate Job 用的 owner DSN Secret 名
                              （键: AS_CONFIG_OWNER_DSN）
      --dry-run              只打印将要执行的命令
  -h, --help                 显示本帮助

执行顺序（顺序本身就是安全要求）:
  1) 校验 SHA256SUMS —— 不匹配立即中止，绝不继续导入
  2) --load 时导入镜像（无 docker 则打印节点侧 ctr / crictl 指令，不代跑）
  3) 前置检查：chart tgz 存在、helm 3.x、kubectl context、必需 Secret 存在性
  4) 打印 helm upgrade --install 命令骨架（占位符）

退出码: 0 通过   1 校验/前置检查失败   2 用法错误

范围声明: 只做镜像导入与安装前置检查，不产生 Helm 之外的第二套安装形态
（ADR-0013；评审 G-P1-7）。真正的安装命令由客户按 deploy/helm/README.md 执行。
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bundle)                BUNDLE_DIR="${2:-}"; shift 2 ;;
    --namespace)             NAMESPACE="${2:-}"; shift 2 ;;
    --values)                VALUES_FILE="${2:-}"; shift 2 ;;
    --context)               CONTEXT="${2:-}"; shift 2 ;;
    --release)               RELEASE_NAME="${2:-}"; shift 2 ;;
    --chart-tgz)             CHART_TGZ="${2:-}"; shift 2 ;;
    --tls-secret)            TLS_SECRET="${2:-}"; shift 2 ;;
    --postgres-secret)       POSTGRES_SECRET="${2:-}"; shift 2 ;;
    --config-runtime-secret) CONFIG_RUNTIME_SECRET="${2:-}"; shift 2 ;;
    --migrate-owner-secret)  MIGRATE_OWNER_SECRET="${2:-}"; shift 2 ;;
    --verify-only)           VERIFY_ONLY=1; DO_LOAD=0; shift ;;
    --load)                  DO_LOAD=1; VERIFY_ONLY=0; shift ;;
    --dry-run)               DRY_RUN=1; shift ;;
    -h|--help)               usage; exit 0 ;;
    *) printf '未知参数: %s\n\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -n "${BUNDLE_DIR}" && -n "${NAMESPACE}" && -n "${RELEASE_NAME}" ]] || {
  printf 'ERROR: --bundle/--namespace/--release 需要非空参数\n' >&2
  exit 2
}

PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0
SKIP_COUNT=0
pass() { PASS_COUNT=$((PASS_COUNT + 1)); printf 'PASS  %-30s %s\n' "$1" "${2:-}"; }
fail() { FAIL_COUNT=$((FAIL_COUNT + 1)); printf 'FAIL  %-30s %s\n' "$1" "${2:-}"; }
warn() { WARN_COUNT=$((WARN_COUNT + 1)); printf 'WARN  %-30s %s\n' "$1" "${2:-}"; }
skip() { SKIP_COUNT=$((SKIP_COUNT + 1)); printf 'SKIP  %-30s %s\n' "$1" "${2:-}"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

printf '==> %s（离线侧）\n' "${SCRIPT_NAME}"
printf '    离线包: %s\n' "${BUNDLE_DIR}"
printf '    模式: %s\n' "$([[ "${VERIFY_ONLY}" -eq 1 ]] && echo '--verify-only（不导入镜像）' || echo '--load（导入镜像）')"
printf -- '--------------------------------------------------------------------\n'

# =============================================================================
# 1) 校验和 —— 第一道门，不匹配必须中止
# =============================================================================
[[ -d "${BUNDLE_DIR}" ]] || die "离线包目录不存在: ${BUNDLE_DIR}"
SUMS_FILE="${BUNDLE_DIR}/SHA256SUMS"
if [[ ! -f "${SUMS_FILE}" ]]; then
  die "缺少 SHA256SUMS（${SUMS_FILE}）—— 离线包不完整，拒绝继续。请在联网侧用 docs/delivery/scripts/bundle-images.sh 重新生成，并核对传输介质上的 MANIFEST.txt。"
fi
pass "SHA256SUMS 存在" "${SUMS_FILE}（$(grep -c . "${SUMS_FILE}" || true) 条）"

if [[ "${DRY_RUN}" -eq 1 ]]; then
  skip "校验和比对" "--dry-run：未执行 sha256sum -c"
else
  set +e
  ( cd "${BUNDLE_DIR}" && sha256sum -c SHA256SUMS )
  SUM_CODE=$?
  set -e
  if [[ "${SUM_CODE}" -ne 0 ]]; then
    die "SHA256SUMS 校验失败（exit ${SUM_CODE}）—— 镜像或 chart 包在传输中损坏/被替换，拒绝导入。处置：重新传输整个 ${BUNDLE_DIR}，并按 MANIFEST.txt 核对 sha256；不要跳过本步。"
  fi
  pass "校验和比对" "sha256sum -c 全部通过"
fi

# =============================================================================
# 2) 镜像导入
# =============================================================================
mapfile -t TARS < <(cd "${BUNDLE_DIR}" && ls -1 images/*.tar 2>/dev/null | sort || true)
if [[ "${#TARS[@]}" -eq 0 ]]; then
  skip "镜像归档" "${BUNDLE_DIR}/images/ 下没有 *.tar（若本次交付不使用内建状态存储，确认清单是否本就为空）"
else
  printf '    镜像归档 %d 个:\n' "${#TARS[@]}"
  for t in "${TARS[@]}"; do printf '      - %s\n' "${t}"; done
fi

if [[ "${DO_LOAD}" -eq 1 ]]; then
  DOCKER_BIN=""
  if [[ -n "${DOCKER:-}" && -x "${DOCKER}" ]]; then
    DOCKER_BIN="${DOCKER}"
  elif command -v docker >/dev/null 2>&1; then
    DOCKER_BIN="$(command -v docker)"
  fi
  if [[ "${#TARS[@]}" -eq 0 ]]; then
    fail "镜像导入" "没有可导入的 images/*.tar"
  elif [[ -z "${DOCKER_BIN}" ]]; then
    printf 'ERROR: 本机没有 docker，无法执行 --load。\n' >&2
    printf '       请由客户在每个 K8s 节点上导入（一个 tar 只承载一个平台）：\n' >&2
    for t in "${TARS[@]}"; do
      printf '         # 节点侧（containerd）：\n' >&2
      printf '         sudo ctr -n k8s.io images import %s/images/%s\n' "${BUNDLE_DIR}" "${t}" >&2
      printf '         # 或（CRI-O / 旧节点）：\n' >&2
      printf '         sudo crictl images import %s/images/%s\n' "${BUNDLE_DIR}" "${t}" >&2
    done
    printf '       导入后确认 imagePullPolicy=IfNotPresent 与镜像 tag 与 values 一致，再执行 helm upgrade --install。\n' >&2
    exit 1
  elif [[ "${DRY_RUN}" -eq 1 ]]; then
    for t in "${TARS[@]}"; do printf '[dry-run] %s load -i %s/images/%s\n' "${DOCKER_BIN}" "${BUNDLE_DIR}" "${t}"; done
    skip "镜像导入" "--dry-run：未实际导入"
  else
    for t in "${TARS[@]}"; do
      printf '    docker load -i %s/images/%s\n' "${BUNDLE_DIR}" "${t}"
      if ! "${DOCKER_BIN}" load -i "${BUNDLE_DIR}/images/${t}"; then
        die "docker load 失败: images/${t} —— 逐个确认后重跑；不要跳过校验和步骤"
      fi
    done
    pass "镜像导入" "已导入 ${#TARS[@]} 个归档（本机 docker）"
    printf '    注意: 多节点集群需要把同样的 tar 导入每个会调度 AS Pod 的节点（或推到客户内网 registry）。\n'
  fi
else
  skip "镜像导入" "--verify-only：未导入镜像"
fi

# =============================================================================
# 3) 离线安装前置检查
# =============================================================================
# 3.1 chart 包
if [[ -z "${CHART_TGZ}" ]]; then
  mapfile -t TGZS < <(cd "${BUNDLE_DIR}" && ls -1 ./*.tgz 2>/dev/null | sed 's|^\./||' | sort || true)
  if [[ "${#TGZS[@]}" -eq 1 ]]; then
    CHART_TGZ="${BUNDLE_DIR}/${TGZS[0]}"
  elif [[ "${#TGZS[@]}" -gt 1 ]]; then
    CHART_TGZ="${BUNDLE_DIR}/${TGZS[0]}"
    warn "chart 包不唯一" "发现 ${#TGZS[@]} 个 .tgz，默认取 ${CHART_TGZ}；用 --chart-tgz 显式指定"
  fi
fi
if [[ -n "${CHART_TGZ}" && -f "${CHART_TGZ}" ]]; then
  pass "chart 包存在" "${CHART_TGZ}"
else
  fail "chart 包存在" "${BUNDLE_DIR} 下没有 .tgz（Helm 是唯一生产形态，ADR-0013：没有 chart 就没有安装形态）"
fi

# 3.2 helm
HELM_BIN_RESOLVED=""
if [[ -n "${HELM:-}" && -x "${HELM}" ]]; then
  HELM_BIN_RESOLVED="${HELM}"
elif command -v helm >/dev/null 2>&1; then
  HELM_BIN_RESOLVED="$(command -v helm)"
elif [[ -n "${HELM_BIN:-}" && -x "${HELM_BIN}" ]]; then
  HELM_BIN_RESOLVED="${HELM_BIN}"
fi
if [[ -z "${HELM_BIN_RESOLVED}" ]]; then
  fail "helm 可用" "未找到 helm 3.x（离线机必须自带 helm；可用 HELM=/path/to/helm 指定）"
else
  HELM_SHORT="$("${HELM_BIN_RESOLVED}" version --short 2>/dev/null || echo "")"
  case "${HELM_SHORT}" in
    v3.*) pass "helm 可用" "${HELM_BIN_RESOLVED} (${HELM_SHORT})" ;;
    "")   warn "helm 版本判定" "${HELM_BIN_RESOLVED} 无版本输出，请人工确认是 3.x" ;;
    *)    fail "helm 可用" "版本为 ${HELM_SHORT}，chart apiVersion: v2 需要 helm 3.x" ;;
  esac
fi

# 3.3 kubectl + context
KUBECTL_BIN=""
if [[ -n "${KUBECTL:-}" && -x "${KUBECTL}" ]]; then
  KUBECTL_BIN="${KUBECTL}"
elif command -v kubectl >/dev/null 2>&1; then
  KUBECTL_BIN="$(command -v kubectl)"
fi
SECRET_CHECKED=0
if [[ -z "${KUBECTL_BIN}" ]]; then
  warn "kubectl 可用" "未找到 kubectl：无法核对 context 与 Secret 存在性（安装前请在有 kubectl 的运维跳板机上执行本脚本）"
else
  pass "kubectl 可用" "${KUBECTL_BIN}"
  CUR_CTX="$("${KUBECTL_BIN}" config current-context 2>/dev/null || echo "")"
  if [[ -z "${CUR_CTX}" ]]; then
    fail "kubectl context" "没有 current-context（离线机 kubeconfig 未配置或已过期）"
  else
    TARGET_CTX="${CONTEXT:-${EXPECTED_CONTEXT}}"
    if [[ -z "${TARGET_CTX}" ]]; then
      warn "kubectl context" "当前 context=${CUR_CTX}；未提供期望 context，无法判断是否指向客户集群（可用 --context 指定）"
    elif [[ "${CUR_CTX}" == "${TARGET_CTX}" ]]; then
      pass "kubectl context" "current-context=${CUR_CTX} 与期望一致"
    else
      fail "kubectl context" "当前 context=${CUR_CTX}，期望 ${TARGET_CTX} —— 装错集群会污染客户环境；先 kubectl config use-context ${TARGET_CTX}"
    fi
  fi

  # 3.4 必需 Secret：只查存在性，绝不读取内容（-o name）
  check_secret() {
    local label="$1" name="$2"
    [[ -z "${name}" ]] && { skip "${label}" "未提供名称（可用对应 --*-secret 参数或 --values 推断）"; return 0; }
    SECRET_CHECKED=1
    if "${KUBECTL_BIN}" get secret "${name}" -n "${NAMESPACE}" -o name >/dev/null 2>&1; then
      pass "${label}" "Secret ${name} 存在于 namespace ${NAMESPACE}（只查存在性，不读取内容）"
    else
      fail "${label}" "Secret ${name} 不在 namespace ${NAMESPACE}；chart 只引用不创建客户 Secret（deploy/helm/README.md）"
    fi
  }
  check_secret "TLS Secret" "${TLS_SECRET}"
  check_secret "PostgreSQL 凭据 Secret" "${POSTGRES_SECRET}"
  check_secret "config-service 运行时 Secret" "${CONFIG_RUNTIME_SECRET}"
  if [[ -n "${MIGRATE_OWNER_SECRET}" ]]; then
    check_secret "migrate owner DSN Secret" "${MIGRATE_OWNER_SECRET}"
  else
    skip "migrate owner DSN Secret" "未提供名称；只有在启用 stateStores.migrateJob 时才需要（键: AS_CONFIG_OWNER_DSN）"
  fi
  if [[ "${SECRET_CHECKED}" -eq 0 ]]; then
    warn "Secret 前置检查" "没有提供任何 Secret 名：TLS / PostgreSQL / config-service 运行时 Secret 由客户 PKI 与 DBA 提供，必须先创建（见 deploy/helm/README.md 与 docs/delivery/install-guide.md）"
  fi
  if [[ -n "${VALUES_FILE}" && ! -f "${VALUES_FILE}" ]]; then
    warn "values 文件" "${VALUES_FILE} 不存在（不影响本次校验结论）"
  fi
fi

# =============================================================================
# 4) 打印 helm 命令骨架（占位符；不在脚本里硬编码 values）
# =============================================================================
CHART_ARG="${CHART_TGZ:-<bundle 目录下的 chart .tgz>}"
printf -- '--------------------------------------------------------------------\n'
printf '接下来在离线机上执行（骨架，参数值请按客户实际替换；口径见\n'
printf '  docs/delivery/install-guide.md  与  deploy/helm/README.md）：\n\n'
cat <<EOF
  # 1) 先跑部署前环境校验（交付物 3.1）
  ./preflight.sh -n ${NAMESPACE} -f <customer-values.yaml>

  # 2) 安装（Helm-only，ADR-0013；chart 是唯一生产形态）
  helm upgrade --install ${RELEASE_NAME} "${CHART_ARG}" \\
    --namespace ${NAMESPACE} --create-namespace \\
    -f <customer-values.yaml> \\
    --set image.repository=<customer-registry>/3rdparty-as \\
    --set image.tag=<release-tag> \\
    --set tls.secretName=<tls-secret> \\
    --set sip.peerAllowlist=<s-sbc-cidrs>

  # 3) config-service 启用时（需要外部运行时 Secret + 预置 NOLOGIN 角色）
  #    --set services.configService.enabled=true \\
  #    --set services.configService.image.repository=<customer-registry>/3rdparty-as-config-service \\
  #    --set services.configService.image.tag=<release-tag> \\
  #    --set services.configService.secretName=<config-runtime-secret> \\
  #    --set services.configService.runtimeRole=<runtime-role>

  # 4) 内建状态存储时（ADR-0026）：migrate Job 用 owner DSN，运行时用 as_config_web
  #    --set stateStores.enabled=true \\
  #    --set stateStores.migrateJob.enabled=true \\
  #    --set stateStores.migrateJob.ownerSecretName=<migrate-owner-secret> \\
  #    --set postgres.secretName=<postgres-secret>
  # 迁移命令序列见 docs/acceptance/m5-state-stores-runbook.md（owner DSN 不进 runtime Pod）
EOF
printf -- '--------------------------------------------------------------------\n'
printf '汇总: PASS=%d FAIL=%d WARN=%d SKIP=%d\n' "${PASS_COUNT}" "${FAIL_COUNT}" "${WARN_COUNT}" "${SKIP_COUNT}"

if [[ "${FAIL_COUNT}" -gt 0 ]]; then
  printf '结论: 存在 FAIL 项 —— 先修复再安装。\n'
  exit 1
fi
printf '结论: 无 FAIL 项。%s\n' "$([[ "${WARN_COUNT}" -gt 0 ]] && echo '存在 WARN，请逐条确认。' || echo '')"
exit 0