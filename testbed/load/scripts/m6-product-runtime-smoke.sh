#!/usr/bin/env bash
# M6: real-socket smoke — as_load against product ResipRuntimeListener (UDP).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
_UAS_UDP_RE='RESIP_RUNTIME_LISTENING address=127\.0\.0\.1 udp_port=([0-9]+)'
_LOAD_UAS="${REPO_ROOT}/platform/tests/fixtures/load_uas_runtime.py"

log() {
  echo "[m6-product-runtime-smoke] $*"
}

die() {
  echo "[m6-product-runtime-smoke] error: $*" >&2
  exit 1
}

require_runtime_extension() {
  local build_dir="${AS_RESIP_RUNTIME_BUILD:-${REPO_ROOT}/platform/native/resip_runtime/build}"
  if compgen -G "${build_dir}/_resip_runtime"*.so >/dev/null; then
    return 0
  fi
  die "platform _resip_runtime not built; run: make m2-platform-resip-build"
}

extract_uas_port() {
  local log_file="$1"
  local port=""
  port="$(sed -nE "s/.*${_UAS_UDP_RE}.*/\1/p" "${log_file}" | head -n1)"
  if [[ -z "${port}" ]]; then
    return 1
  fi
  echo "${port}"
}

main() {
  require_runtime_extension
  log "UAS: uv run python ${_LOAD_UAS}"

  local uas_log
  uas_log="$(mktemp)"
  (
    cd "${REPO_ROOT}"
    exec uv run python "${_LOAD_UAS}"
  ) >"${uas_log}" 2>&1 &
  local uas_pid=$!

  local port=""
  local deadline=$((SECONDS + 60))
  while [[ -z "${port}" ]]; do
    if ! kill -0 "${uas_pid}" 2>/dev/null; then
      cat "${uas_log}" >&2 || true
      rm -f "${uas_log}"
      die "load_uas_runtime exited before RESIP_RUNTIME_LISTENING line appeared"
    fi
    if port="$(extract_uas_port "${uas_log}" 2>/dev/null || true)" && [[ -n "${port}" ]]; then
      break
    fi
    port=""
    if ((SECONDS >= deadline)); then
      kill -INT "${uas_pid}" 2>/dev/null || true
      wait "${uas_pid}" 2>/dev/null || true
      cat "${uas_log}" >&2 || true
      rm -f "${uas_log}"
      die "timed out waiting for RESIP_RUNTIME_LISTENING udp_port"
    fi
    sleep 0.1
  done
  log "UAS UDP port: ${port}"

  local root="${AS_M6_OUTPUT_ROOT:-/tmp}"
  local out_dir="${root}/as-m6-product-runtime-smoke-$(date +%Y%m%d)"
  mkdir -p "${out_dir}" || die "cannot write AS_M6_OUTPUT_ROOT=${root}"
  log "load -> ${out_dir}"

  local load_status=0
  (
    cd "${REPO_ROOT}"
    uv run python -m as_load \
      --host 127.0.0.1 \
      --port "${port}" \
      --cps 1 \
      --duration 0.2 \
      --hold 0 \
      --workers 1 \
      --timeout 5 \
      --stack as-platform-resip-runtime \
      --stack-version 1.14.0-632e215c \
      --out "${out_dir}"
  ) || load_status=$?

  kill -TERM "${uas_pid}" 2>/dev/null || true
  local wait_deadline=$((SECONDS + 10))
  while kill -0 "${uas_pid}" 2>/dev/null && ((SECONDS < wait_deadline)); do
    sleep 0.1
  done
  kill -KILL "${uas_pid}" 2>/dev/null || true
  wait "${uas_pid}" 2>/dev/null || true

  if [[ ${load_status} -ne 0 ]]; then
    cat "${uas_log}" >&2 || true
    rm -f "${uas_log}"
    die "as_load exited ${load_status}"
  fi

  local summary_file="${out_dir}/summary.json"
  if [[ ! -f "${summary_file}" ]]; then
    cat "${uas_log}" >&2 || true
    rm -f "${uas_log}"
    die "missing summary at ${summary_file}"
  fi

  local established
  established="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["counts"]["established_sessions"])' "${summary_file}")"
  rm -f "${uas_log}"

  if [[ "${established}" -lt 1 ]]; then
    die "established_sessions=${established}; expected >= 1"
  fi

  log "smoke passed (established_sessions=${established})"
}

main "$@"
