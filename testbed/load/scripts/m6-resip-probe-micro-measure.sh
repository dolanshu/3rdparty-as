#!/usr/bin/env bash
# M6 step 3 precursor: micro measurement — as_load against resip_probe external UAS (UDP).
# Engineering evidence only. NOT O1 publication; do not treat CPS, latency, or RSS as product claims.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
DEFAULT_PROBE="${REPO_ROOT}/.cache/m2-resiprocate/probe-build/resip_probe"
_UAS_UDP_RE='\[UAS\] 监听 UDP 127\.0\.0\.1:([0-9]+)'

log() {
  echo "[m6-resip-probe-micro-measure] $*"
}

die() {
  echo "[m6-resip-probe-micro-measure] error: $*" >&2
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

probe_rss_kb() {
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
  local probe_pid="$2"
  local resources_file="${out_dir}/resources.json"
  local rss_kb=""
  rss_kb="$(probe_rss_kb "${probe_pid}" || true)"
  python3 - "${resources_file}" "${probe_pid}" "${rss_kb}" <<'PY'
import json
import sys
from datetime import datetime, timezone

path, pid_s, rss_s = sys.argv[1:4]
pid = int(pid_s)
entry = {
    "captured_utc": datetime.now(timezone.utc).isoformat(),
    "probe_pid": pid,
    "probe_rss_kb": int(rss_s) if rss_s else None,
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

  local out_dir="/tmp/as-m6-resip-probe-micro-$(date +%Y%m%d-%H%M%S)"
  mkdir -p "${out_dir}"
  log "load -> ${out_dir} (duration=5s cps=2 hold=0.5 workers=4)"

  local load_status=0
  (
    cd "${REPO_ROOT}"
    uv run python -m as_load \
      --host 127.0.0.1 \
      --port "${port}" \
      --cps 2 \
      --duration 5 \
      --hold 0.5 \
      --workers 4 \
      --timeout 5 \
      --stack resip-probe \
      --stack-version 1.14.0-632e215c \
      --out "${out_dir}"
  ) || load_status=$?

  write_resources_json "${out_dir}" "${probe_pid}"

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

  local resources_file="${out_dir}/resources.json"
  if [[ ! -f "${resources_file}" ]]; then
    cat "${probe_log}" >&2 || true
    rm -f "${probe_log}"
    die "missing resources at ${resources_file}"
  fi

  local established
  established="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["counts"]["established_sessions"])' "${summary_file}")"
  rm -f "${probe_log}"

  if [[ "${established}" -lt 1 ]]; then
    die "established_sessions=${established}; expected >= 1"
  fi

  log "micro measure passed (established_sessions=${established})"
  log "evidence: ${summary_file} ${resources_file}"
}

main "$@"
