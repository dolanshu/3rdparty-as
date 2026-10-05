#!/usr/bin/env bash
# M6 step 2: real-socket smoke cascade — as_load against resip_probe external UAS (UDP).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
DEFAULT_PROBE="${REPO_ROOT}/.cache/m2-resiprocate/probe-build/resip_probe"
_UAS_UDP_RE='\[UAS\] 监听 UDP 127\.0\.0\.1:([0-9]+)'

log() {
  echo "[m6-resip-probe-smoke] $*"
}

die() {
  echo "[m6-resip-probe-smoke] error: $*" >&2
  exit 1
}

resolve_probe_bin() {
  local candidate="${AS_RESIP_PROBE_BIN:-${DEFAULT_PROBE}}"
  if [[ ! -x "${candidate}" ]]; then
    die "resip_probe not found at ${candidate}; run: make m2-native-build (or set AS_RESIP_PROBE_BIN)"
  fi
  echo "${candidate}"
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
  local probe_bin
  probe_bin="$(resolve_probe_bin)"
  log "probe: ${probe_bin} --external S1"

  local probe_log
  probe_log="$(mktemp)"
  "${probe_bin}" --external S1 >"${probe_log}" 2>&1 &
  local probe_pid=$!

  local port=""
  local deadline=$((SECONDS + 60))
  while [[ -z "${port}" ]]; do
    if ! kill -0 "${probe_pid}" 2>/dev/null; then
      cat "${probe_log}" >&2 || true
      rm -f "${probe_log}"
      die "resip_probe exited before UAS UDP listen line appeared"
    fi
    if port="$(extract_uas_port "${probe_log}" 2>/dev/null || true)" && [[ -n "${port}" ]]; then
      break
    fi
    port=""
    if ((SECONDS >= deadline)); then
      kill -INT "${probe_pid}" 2>/dev/null || true
      wait "${probe_pid}" 2>/dev/null || true
      cat "${probe_log}" >&2 || true
      rm -f "${probe_log}"
      die "timed out waiting for UAS UDP listen line"
    fi
    sleep 0.1
  done
  log "UAS UDP port: ${port}"

  local out_dir="/tmp/as-m6-resip-probe-smoke-$(date +%Y%m%d)"
  mkdir -p "${out_dir}"
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
      --stack resip-probe \
      --stack-version 1.14.0-632e215c \
      --out "${out_dir}"
  ) || load_status=$?

  kill -INT "${probe_pid}" 2>/dev/null || true
  wait "${probe_pid}" 2>/dev/null || true

  if [[ ${load_status} -ne 0 ]]; then
    cat "${probe_log}" >&2 || true
    rm -f "${probe_log}"
    die "as_load exited ${load_status}"
  fi

  local summary_file="${out_dir}/summary.json"
  if [[ ! -f "${summary_file}" ]]; then
    cat "${probe_log}" >&2 || true
    rm -f "${probe_log}"
    die "missing summary at ${summary_file}"
  fi

  local established
  established="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["counts"]["established_sessions"])' "${summary_file}")"
  rm -f "${probe_log}"

  if [[ "${established}" -lt 1 ]]; then
    die "established_sessions=${established}; expected >= 1"
  fi

  log "smoke passed (established_sessions=${established})"
}

main "$@"
