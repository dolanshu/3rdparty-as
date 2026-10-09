# Vendored CLI tools for this repo (see docs/handoff/pre-m8-demo-review-plan.md §2.4).
# shellcheck shell=bash

repo_toolchain_prepend_path() {
  local root="${1:?repo root required}"
  if [[ -d "${root}/.tools/m71-bin" ]]; then
    PATH="${root}/.tools/m71-bin:${PATH}"
    export PATH
  fi
}

# Print absolute path to helm, or return non-zero.
repo_resolve_helm() {
  local root="${1:-}"
  if [[ -n "${HELM_BIN:-}" && -x "${HELM_BIN}" ]]; then
    printf '%s\n' "${HELM_BIN}"
    return 0
  fi
  if command -v helm >/dev/null 2>&1; then
    command -v helm
    return 0
  fi
  if [[ -n "${root}" && -x "${root}/.tools/m71-bin/helm" ]]; then
    printf '%s\n' "${root}/.tools/m71-bin/helm"
    return 0
  fi
  if [[ -x /tmp/linux-amd64/helm ]]; then
    printf '%s\n' /tmp/linux-amd64/helm
    return 0
  fi
  return 1
}

repo_require_helm() {
  local root="${1:?repo root required}"
  local helm_bin
  if helm_bin="$(repo_resolve_helm "${root}")"; then
    printf '%s\n' "${helm_bin}"
    return 0
  fi
  echo "helm not found; install helm 3.x, set HELM_BIN, or place helm in ${root}/.tools/m71-bin (see pre-m8-demo-review-plan.md)" >&2
  return 1
}
