#!/usr/bin/env bash
# M6: micro measurement — as_load against product ResipRuntimeListener (UDP).
# Engineering evidence only. NOT O1 publication; do not treat CPS, latency, or RSS as product claims.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
_UAS_UDP_RE='RESIP_RUNTIME_LISTENING address=127\.0\.0\.1 udp_port=([0-9]+)'
_LOAD_UAS="${REPO_ROOT}/platform/tests/fixtures/load_uas_runtime.py"

log() {
  echo "[m6-product-runtime-micro-measure] $*"
}

die() {
  echo "[m6-product-runtime-micro-measure] error: $*" >&2
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

uas_rss_kb() {
  local pid="$1"
  local rss=""
  if [[ -r "/proc/${pid}/status" ]]; then
    rss="$(awk '/^VmRSS:/ {print $2}' "/proc/${pid}/status" 2>/dev/null || true)"
    if [[ -n "${rss}" ]]; then
      echo "${rss}"
      return 0
    fi
  fi
  rss="$(ps -o rss= -p "${pid}" 2>/dev/null | tr -d ' ' || true)"
  if [[ -n "${rss}" ]]; then
    echo "${rss}"
    return 0
  fi
  return 1
}

write_resources_json() {
  local out_dir="$1"
  local uas_pid="$2"
  local resources_file="${out_dir}/resources.json"
  local rss_kb=""
  rss_kb="$(uas_rss_kb "${uas_pid}" || true)"
  python3 - "${resources_file}" "${uas_pid}" "${rss_kb}" <<'PY'
import json
import sys
from datetime import datetime, timezone

path, pid_s, rss_s = sys.argv[1:4]
pid = int(pid_s)
entry = {
    "captured_utc": datetime.now(timezone.utc).isoformat(),
    "uas_pid": pid,
    "uas_rss_kb": int(rss_s) if rss_s else None,
    "rss_source": (
        f"/proc/{pid}/status VmRSS" if rss_s else "unavailable"
    ),
}
existing: list = []
try:
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    if isinstance(payload, dict) and isinstance(payload.get("snapshots"), list):
        existing = payload["snapshots"]
    elif isinstance(payload, list):
        existing = payload
except FileNotFoundError:
    pass
existing.append(entry)
with open(path, "w", encoding="utf-8") as fh:
    json.dump({"snapshots": existing}, fh, indent=2, sort_keys=True)
    fh.write("\n")
PY
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

  local out_dir="/tmp/as-m6-product-runtime-micro-$(date +%Y%m%d-%H%M%S)"
  mkdir -p "${out_dir}"
  log "load -> ${out_dir} (duration=3s cps=2 hold=0 workers=2)"

  local load_status=0
  (
    cd "${REPO_ROOT}"
    uv run python -m as_load \
      --host 127.0.0.1 \
      --port "${port}" \
      --cps 2 \
      --duration 3 \
      --hold 0 \
      --workers 2 \
      --timeout 5 \
      --stack as-platform-resip-runtime \
      --stack-version 1.14.0-632e215c \
      --out "${out_dir}"
  ) || load_status=$?

  write_resources_json "${out_dir}" "${uas_pid}"

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

  local resources_file="${out_dir}/resources.json"
  if [[ ! -f "${resources_file}" ]]; then
    cat "${uas_log}" >&2 || true
    rm -f "${uas_log}"
    die "missing resources at ${resources_file}"
  fi

  local established
  established="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["counts"]["established_sessions"])' "${summary_file}")"
  rm -f "${uas_log}"

  if [[ "${established}" -lt 1 ]]; then
    die "established_sessions=${established}; expected >= 1"
  fi

  log "micro measure passed (established_sessions=${established})"
  log "evidence: ${summary_file} ${resources_file}"
}

main "$@"
