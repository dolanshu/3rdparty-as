#!/usr/bin/env bash
# bundle-images.sh — 交付物 3.2 的联网侧脚本：镜像同步 + 校验和 + helm package
# In-house IMS Application Server（文档暂用名），Helm-only 生产交付形态（ADR-0013）。
#
# 范围（评审 G-P1-7）：只做「镜像 save + 校验和 + helm package」。本脚本
# 不产生 Helm 之外的第二套安装形态，也不做在线安装器、不走 CI 私有 registry
# 自动同步。离线侧用同目录的 load-images.sh。
#
# 用法:
#   ./bundle-images.sh --images images.txt --out ./airgap-out
#   ./bundle-images.sh --repository registry.customer.internal/as --tag-prefix rel-
#   ./bundle-images.sh --dry-run
#   ./bundle-images.sh --help
#
# 退出码:
#   0  全部成功
#   1  任一步失败（失败即中止，并指出是哪一条镜像/哪一步）
#   2  用法错误
#
# 依赖: bash, awk, grep, sed, sort, date, sha256sum
#   docker（pull/save/tag）；可用 DOCKER 环境变量覆盖二进制路径
#   helm 3.x（package）；可用 HELM 环境变量覆盖二进制路径
#     （风格参考 scripts/lib/repo-toolchain.sh 的 repo_resolve_helm）
#
# 安全: 不打印任何凭据（images.txt 里禁止写凭据，registry 认证走 docker 自己的
#       凭据配置或 --platform 之外的常规 `docker login`，由调用方在受控环境完成）。
#       本仓库与本脚本不内嵌任何真实 registry 地址或密钥；占位地址一律用
#       registry.example.com。
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

IMAGES_FILE="${SCRIPT_DIR}/images.txt"
OUT_DIR="./airgap-out"
CHART=""
DESTINATION=""
SKIP_HELM_PACKAGE=0
PUSH=0
REPOSITORY=""
TAG_PREFIX=""
PLATFORM=""
DRY_RUN=0

usage() {
  cat <<'EOF'
bundle-images.sh — 离线包制作（联网侧）：镜像同步 + SHA256SUMS + helm package

用法:
  bundle-images.sh [选项]

选项:
      --images <file>     依赖镜像清单（每行一个 repository:tag[@digest]）
                          默认: 本脚本同目录的 images.txt
      --out <dir>         输出目录（默认 ./airgap-out）
      --chart <path>      chart 路径（默认 <repo>/deploy/helm）
                          相对路径先按当前目录解析，失败再按 repo 根解析
      --repository <repo> 按客户 registry 重打标签时的目标前缀
                          例: --repository registry.customer.internal/as
      --tag-prefix <p>    重打标签时追加到 tag 之前的字符串（例: rel-）
      --push              重打标签后 docker push 到目标 registry（不加则只在本机打标签并写进 tar）
      --platform <os/arch>  传给 docker pull 的 --platform；也会写进 tar 文件名，
                          例: linux/amd64。一个 tar 只承载一个平台
      --skip-helm-package 只做镜像与校验和，不执行 helm package
      --dry-run           只解析与校验清单并打印计划，不调用 docker / helm
  -h, --help              显示本帮助

产物（写入 --out）:
  images/<image>-<tag>-<platform>.tar   docker save 的镜像归档
  <chart-name>-<version>.tgz           helm package 产物
  SHA256SUMS                           所有 tar 与 tgz 的 sha256
  MANIFEST.txt                         镜像 / tag / digest / tar / sha256 /
                                       生成时间(UTC) / 工具版本

退出码: 0 成功   1 某一步失败   2 用法错误

范围声明: 仅镜像同步 + 校验和 + helm package。不做在线安装器，不做 CI 私有
registry 自动同步，不产生 Helm 之外的安装形态（ADR-0013；评审 G-P1-7）。
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --images|--out|--chart|--repository|--tag-prefix|--platform)
      case "$1" in
        --images)    IMAGES_FILE="${2:-}" ;;
        --out)       OUT_DIR="${2:-}" ;;
        --chart)     CHART="${2:-}" ;;
        --repository) REPOSITORY="${2:-}" ;;
        --tag-prefix) TAG_PREFIX="${2:-}" ;;
        --platform)  PLATFORM="${2:-}" ;;
      esac
      shift 2 ;;
    --destination) OUT_DIR="${2:-}"; shift 2 ;;
    --push)             PUSH=1; shift ;;
    --skip-helm-package) SKIP_HELM_PACKAGE=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf '未知参数: %s\n\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -n "${IMAGES_FILE}" && -n "${OUT_DIR}" ]] || { printf 'ERROR: --images/--out 需要非空参数\n' >&2; exit 2; }

# chart 解析：显式路径优先；默认取 repo 内的 deploy/helm
resolve_chart() {
  local candidate="${1:-}"
  if [[ -z "${candidate}" ]]; then
    printf '%s\n' "${REPO_ROOT}/deploy/helm"
    return 0
  fi
  if [[ -d "${candidate}" ]]; then printf '%s\n' "${candidate}"; return 0; fi
  if [[ -d "${REPO_ROOT}/${candidate}" ]]; then printf '%s\n' "${REPO_ROOT}/${candidate}"; return 0; fi
  return 1
}
if ! CHART="$(resolve_chart "${CHART}")"; then
  printf 'ERROR: chart 路径不存在: %s\n' "${CHART:-<默认>}" >&2
  exit 1
fi

# 工具定位：环境变量优先（scripts/lib/repo-toolchain.sh 风格）
DOCKER_BIN=""
HELM_BIN_RESOLVED=""
if [[ -n "${DOCKER:-}" && -x "${DOCKER}" ]]; then
  DOCKER_BIN="${DOCKER}"
elif command -v docker >/dev/null 2>&1; then
  DOCKER_BIN="$(command -v docker)"
fi
if [[ -n "${HELM:-}" && -x "${HELM}" ]]; then
  HELM_BIN_RESOLVED="${HELM}"
elif command -v helm >/dev/null 2>&1; then
  HELM_BIN_RESOLVED="$(command -v helm)"
elif [[ -n "${HELM_BIN:-}" && -x "${HELM_BIN}" ]]; then
  HELM_BIN_RESOLVED="${HELM_BIN}"
fi

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[[ -f "${IMAGES_FILE}" ]] || die "镜像清单不存在: ${IMAGES_FILE}"
[[ -d "${CHART}" ]] || die "chart 路径不存在: ${CHART}"

# --- 解析镜像清单 ---------------------------------------------------------------
# 格式：每行一条 repository:tag[@sha256:...]；空行与 # 注释忽略；允许行尾注释。
ENTRIES=()
while IFS= read -r raw_line || [[ -n "${raw_line}" ]]; do
  line="${raw_line%%#*}"
  line="$(printf '%s' "${line}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
  [[ -z "${line}" ]] && continue
  ENTRIES+=("${line}")
done <"${IMAGES_FILE}"

if [[ "${#ENTRIES[@]}" -eq 0 ]]; then
  die "镜像清单里没有任何条目: ${IMAGES_FILE}"
fi

printf '==> %s（联网侧）\n' "${SCRIPT_NAME}"
printf '    清单: %s（%d 条）\n' "${IMAGES_FILE}" "${#ENTRIES[@]}"
printf '    chart: %s\n' "${CHART}"
printf '    输出: %s\n' "${OUT_DIR}"
printf '    模式: %s\n' "$([[ "${DRY_RUN}" -eq 1 ]] && echo '--dry-run（不调用 docker / helm）' || echo '实际执行')"
printf -- '--------------------------------------------------------------------\n'

sanitize() { printf '%s' "$1" | sed -e 's|/|_|g' -e 's|:|_|g' -e 's|@|_|g'; }

# 目标引用：可选地按客户 registry 重打标签。
target_ref() {
  local ref="$1"
  local repo_part tag_part digest_part name_part
  digest_part=""
  if [[ "${ref}" == *"@sha256:"* ]]; then
    digest_part="@${ref##*@}"
    ref="${ref%@*}"
  fi
  if [[ "${ref}" == *:* ]]; then
    repo_part="${ref%:*}"
    tag_part="${ref##*:}"
  else
    repo_part="${ref}"
    tag_part="latest"
  fi
  name_part="${repo_part##*/}"
  if [[ -n "${REPOSITORY}" ]]; then
    repo_part="${REPOSITORY%/}/${name_part}"
  fi
  tag_part="${TAG_PREFIX}${tag_part}"
  printf '%s:%s%s\n' "${repo_part}" "${tag_part}" "${digest_part}"
}

MANIFEST_ROWS=""
record_manifest_row() {
  # record_manifest_row <原清单条目> <实际引用> <tar 名> <sha256 或 ->
  MANIFEST_ROWS="${MANIFEST_ROWS}$1	$2	$3	$4
"
}

# --- 校验清单格式 ---------------------------------------------------------------
BAD=0
for entry in "${ENTRIES[@]}"; do
  if [[ "${entry}" != *:* ]]; then
    printf '清单格式错误: %s —— 必须写 repository:tag（tag 缺省按 latest 处理，但请显式写）\n' "${entry}" >&2
    BAD=1
    continue
  fi
  if [[ "${entry}" == *"@sha256:"* && "${entry}" != *"@sha256:"*:* ]]; then
    printf '清单格式错误: %s —— digest 必须跟在 tag 之后（repo:tag@sha256:...）\n' "${entry}" >&2
    BAD=1
  fi
done
[[ "${BAD}" -eq 0 ]] || die "镜像清单有格式错误，先修 ${IMAGES_FILE}（模板见该文件头部注释）"

if [[ "${DRY_RUN}" -eq 0 && -z "${DOCKER_BIN}" ]]; then
  printf 'ERROR: 未找到 docker。请安装 Docker（或设置 DOCKER=/path/to/docker）。\n' >&2
  printf '       镜像构建方式见 deploy/docker/Dockerfile 与 deploy/docker/config-service.Dockerfile。\n' >&2
  exit 1
fi
if [[ "${DRY_RUN}" -eq 0 && "${SKIP_HELM_PACKAGE}" -eq 0 && -z "${HELM_BIN_RESOLVED}" ]]; then
  printf 'ERROR: 未找到 helm 3.x。请安装 helm（或设置 HELM=/path/to/helm），或加 --skip-helm-package。\n' >&2
  exit 1
fi

# --- 镜像拉取 + 保存 + 校验和 ---------------------------------------------------
if [[ "${DRY_RUN}" -eq 0 ]]; then
  mkdir -p "${OUT_DIR}/images"
fi

SUMS=()
FAILED_ENTRY=""
for entry in "${ENTRIES[@]}"; do
  ref="$(target_ref "${entry}")"
  platform_suffix="unspecified"
  if [[ -n "${PLATFORM}" ]]; then
    platform_suffix="$(printf '%s' "${PLATFORM}" | sed 's|/|_|g')"
  fi
  tar_name="images/$(sanitize "${ref}")-${platform_suffix}.tar"

  printf -- '==> %s\n' "${entry}"
  RETAGGED=0
  if [[ "${ref}" != "${entry}" ]]; then
    RETAGGED=1
    printf '    重打标签 -> %s\n' "${ref}"
  fi

  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf '    [dry-run] docker pull %s%s\n' "${PLATFORM:+--platform ${PLATFORM} }" "${entry}"
    if [[ "${RETAGGED}" -eq 1 ]]; then
      printf '    [dry-run] docker tag %s %s\n' "${entry}" "${ref}"
      [[ "${PUSH}" -eq 1 ]] && printf '    [dry-run] docker push %s\n' "${ref}"
    fi
    printf '    [dry-run] docker save -o %s %s\n' "${tar_name}" "${ref}"
    printf '    [dry-run] sha256sum %s >> SHA256SUMS\n' "${tar_name}"
    record_manifest_row "${entry}" "${ref}" "${tar_name}" "-"
    continue
  fi

  # 先拉原始引用；重打标签时用 docker tag 在本地产生目标引用（不要求客户
  # registry 里已经有这个 tag —— 那是 --push 的事）。
  set +e
  if [[ -n "${PLATFORM}" ]]; then
    "${DOCKER_BIN}" pull --platform "${PLATFORM}" "${entry}"
  else
    "${DOCKER_BIN}" pull "${entry}"
  fi
  PULL_CODE=$?
  set -e
  if [[ "${PULL_CODE}" -ne 0 ]]; then
    FAILED_ENTRY="${entry}"
    printf 'ERROR: docker pull 失败（exit %d）: %s\n' "${PULL_CODE}" "${entry}" >&2
    printf '       失败即中止：请修正该条镜像引用/版本后重跑；已生成的文件不会被当成有效离线包（缺 SHA256SUMS 条目）。\n' >&2
    exit 1
  fi

  if [[ "${RETAGGED}" -eq 1 ]]; then
    set +e
    "${DOCKER_BIN}" tag "${entry}" "${ref}"
    TAG_CODE=$?
    set -e
    if [[ "${TAG_CODE}" -ne 0 ]]; then
      printf 'ERROR: docker tag 失败（exit %d）: %s -> %s\n' "${TAG_CODE}" "${entry}" "${ref}" >&2
      exit 1
    fi
    if [[ "${PUSH}" -eq 1 ]]; then
      set +e
      "${DOCKER_BIN}" push "${ref}"
      PUSH_CODE=$?
      set -e
      if [[ "${PUSH_CODE}" -ne 0 ]]; then
        printf 'ERROR: docker push 失败（exit %d）: %s\n' "${PUSH_CODE}" "${ref}" >&2
        printf '       凭据由调用方的 docker 凭据配置提供；本脚本不读取也不打印任何凭据。\n' >&2
        exit 1
      fi
    else
      printf '    目标标签只存在于本机 docker（未加 --push，不推 registry）；它会被写进 tar。\n'
    fi
  fi

  DIGEST="$("${DOCKER_BIN}" inspect --format '{{if .RepoDigests}}{{index .RepoDigests 0}}{{else}}<无 RepoDigest>{{end}}' "${ref}" 2>/dev/null || echo '<inspect 失败>')"
  printf '    digest: %s\n' "${DIGEST}"

  set +e
  "${DOCKER_BIN}" save -o "${OUT_DIR}/${tar_name}" "${ref}"
  SAVE_CODE=$?
  set -e
  if [[ "${SAVE_CODE}" -ne 0 ]]; then
    FAILED_ENTRY="${entry}"
    printf 'ERROR: docker save 失败（exit %d）: %s\n' "${SAVE_CODE}" "${entry}" >&2
    exit 1
  fi

  SHA="$(cd "${OUT_DIR}" && sha256sum "${tar_name}" | awk '{print $1}')"
  SUMS+=("${SHA}  ${tar_name}")
  printf '    saved: %s  sha256=%s\n' "${tar_name}" "${SHA}"
  record_manifest_row "${entry}" "${ref} (${DIGEST})" "${tar_name}" "${SHA}"
done

# --- helm package ---------------------------------------------------------------
CHART_TGZ=""
if [[ "${SKIP_HELM_PACKAGE}" -eq 0 ]]; then
  CHART_VERSION="$(awk -F': *' '/^version:/{gsub(/"/,"",$2); print $2; exit}' "${CHART}/Chart.yaml" 2>/dev/null || true)"
  CHART_NAME="$(awk -F': *' '/^name:/{gsub(/"/,"",$2); print $2; exit}' "${CHART}/Chart.yaml" 2>/dev/null || true)"
  CHART_APP_VERSION="$(awk -F': *' '/^appVersion:/{gsub(/"/,"",$2); print $2; exit}' "${CHART}/Chart.yaml" 2>/dev/null || true)"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf -- '==> helm package %s -d %s\n' "${CHART}" "${OUT_DIR}"
    printf '    [dry-run] chart=%s version=%s appVersion=%s\n' "${CHART_NAME:-?}" "${CHART_VERSION:-?}" "${CHART_APP_VERSION:-?}"
  else
    printf -- '==> helm package %s\n' "${CHART}"
    set +e
    "${HELM_BIN_RESOLVED}" package "${CHART}" --destination "${OUT_DIR}"
    PKG_CODE=$?
    set -e
    if [[ "${PKG_CODE}" -ne 0 ]]; then
      printf 'ERROR: helm package 失败（exit %d）。chart 必须能通过 helm lint；先跑 make chart-check。\n' "${PKG_CODE}" >&2
      exit 1
    fi
    CHART_TGZ="$(cd "${OUT_DIR}" && ls -1t ./*.tgz 2>/dev/null | head -1 | sed 's|^\./||')"
    if [[ -z "${CHART_TGZ}" ]]; then
      printf 'ERROR: helm package 未产出 .tgz 文件\n' >&2
      exit 1
    fi
    CHART_SHA="$(cd "${OUT_DIR}" && sha256sum "${CHART_TGZ}" | awk '{print $1}')"
    SUMS+=("${CHART_SHA}  ${CHART_TGZ}")
    printf '    chart tgz: %s  sha256=%s\n' "${CHART_TGZ}" "${CHART_SHA}"
    printf '    注意: Chart version=%s appVersion=%s；根 VERSION 与 Chart.appVersion 不同步是已知缺口，\n' "${CHART_VERSION:-?}" "${CHART_APP_VERSION:-?}"
    printf '          交付版本以根 VERSION 为准（AGENT.md §8），打包前请人工确认两者是否需要对齐。\n'
  fi
else
  printf -- '==> 跳过 helm package（--skip-helm-package）\n'
  CHART_NAME=""; CHART_VERSION=""; CHART_APP_VERSION=""
fi

# --- SHA256SUMS + MANIFEST ------------------------------------------------------
if [[ "${DRY_RUN}" -eq 0 ]]; then
  printf '%s\n' "${SUMS[@]}" >"${OUT_DIR}/SHA256SUMS"
  GENERATED_UTC="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  DOCKER_VERSION="$("${DOCKER_BIN}" version --format '{{.Client.Version}}' 2>/dev/null || echo '<unknown>')"
  HELM_VERSION="$("${HELM_BIN_RESOLVED}" version --short 2>/dev/null || echo '<unknown>')"
  {
    printf '# MANIFEST —— In-house IMS Application Server（文档暂用名）离线包\n'
    printf '# 生成时间(UTC): %s\n' "${GENERATED_UTC}"
    printf '# 生成方式: docs/delivery/scripts/bundle-images.sh（Helm-only，ADR-0013）\n'
    printf '# 镜像清单: %s\n' "${IMAGES_FILE}"
    printf '# chart: %s version=%s appVersion=%s\n' "${CHART}" "${CHART_VERSION:-<未打包>}" "${CHART_APP_VERSION:-<未打包>}"
    printf '# docker: %s   helm: %s\n' "${DOCKER_VERSION}" "${HELM_VERSION}"
    printf '# 平台: %s\n' "${PLATFORM:-未指定（一个 tar 只承载 docker 本地已有的那个平台）}"
    printf '#\n'
    printf '# 字段: 清单条目 <TAB> 实际引用(可能含 digest) <TAB> tar 路径 <TAB> sha256\n'
    printf '%s' "${MANIFEST_ROWS}"
    printf '#\n# 校验: cd %s && sha256sum -c SHA256SUMS\n' "${OUT_DIR}"
    printf '# 本文件不含任何凭据；镜像的 registry 认证由客户侧 docker 凭据配置负责。\n'
  } >"${OUT_DIR}/MANIFEST.txt"
  printf -- '--------------------------------------------------------------------\n'
  printf '产物目录: %s\n' "${OUT_DIR}"
  printf '  images/*.tar   镜像归档\n'
  [[ -n "${CHART_TGZ}" ]] && printf '  %s   chart 包\n' "${CHART_TGZ}"
  printf '  SHA256SUMS     校验和（离线侧 load-images.sh 会先校验，不匹配即中止）\n'
  printf '  MANIFEST.txt   镜像/tag/digest/tar/sha256/工具版本\n'
  printf '下一步: 把整个 %s 目录带到客户机房，按 docs/delivery/airgap-package.md §4 执行离线安装。\n' "${OUT_DIR}"
else
  printf -- '--------------------------------------------------------------------\n'
  printf '[dry-run] 未写入任何文件。去掉 --dry-run 即在 %s 生成产物。\n' "${OUT_DIR}"
fi

exit 0