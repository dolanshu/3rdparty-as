#!/usr/bin/env bash
# M6 O1 formal measurement batch — product ResipRuntimeListener (UDP), dev host only.
# Internal research evidence. NOT public SLA / marketing capacity claims (AGENT.md §2).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
_UAS_UDP_RE='RESIP_RUNTIME_LISTENING address=127\.0\.0\.1 udp_port=([0-9]+)'
_LOAD_UAS="${REPO_ROOT}/platform/tests/fixtures/load_uas_runtime.py"

log() {
  echo "[m6-o1-formal-report] $*"
}

die() {
  echo "[m6-o1-formal-report] error: $*" >&2
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

run_one_scenario() {
  local duration="$1"
  local cps="$2"
  local batch_root="$3"
  local tag="d${duration}s-cps${cps}"
  local out_dir="${batch_root}/${tag}"
  mkdir -p "${out_dir}"

  log "scenario ${tag} -> ${out_dir}"

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
      die "load_uas_runtime exited before RESIP_RUNTIME_LISTENING (${tag})"
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
      die "timed out waiting for UAS port (${tag})"
    fi
    sleep 0.1
  done

  local workers=4
  if ((cps >= 20)); then
    workers=8
  fi

  local load_status=0
  (
    cd "${REPO_ROOT}"
    uv run python -m as_load \
      --host 127.0.0.1 \
      --port "${port}" \
      --cps "${cps}" \
      --duration "${duration}" \
      --hold 0 \
      --workers "${workers}" \
      --timeout 5 \
      --stack as-platform-resip-runtime \
      --stack-version 1.14.0-632e215c \
      --out "${out_dir}"
  ) || load_status=$?

  write_resources_json "${out_dir}" "${uas_pid}"

  kill -TERM "${uas_pid}" 2>/dev/null || true
  local wait_deadline=$((SECONDS + 15))
  while kill -0 "${uas_pid}" 2>/dev/null && ((SECONDS < wait_deadline)); do
    sleep 0.1
  done
  kill -KILL "${uas_pid}" 2>/dev/null || true
  wait "${uas_pid}" 2>/dev/null || true
  rm -f "${uas_log}"

  if [[ ${load_status} -ne 0 ]]; then
    die "as_load exited ${load_status} (${tag})"
  fi

  local summary_file="${out_dir}/summary.json"
  [[ -f "${summary_file}" ]] || die "missing summary (${tag})"

  local established
  established="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["counts"]["established_sessions"])' "${summary_file}")"
  if [[ "${established}" -lt 1 ]]; then
    die "established_sessions=${established} (${tag})"
  fi

  log "ok ${tag} established_sessions=${established}"
}

write_manifest() {
  local batch_root="$1"
  python3 - "${batch_root}" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

batch_root = Path(sys.argv[1])
scenarios = []
for child in sorted(batch_root.iterdir()):
    if not child.is_dir():
        continue
    summary_path = child / "summary.json"
    resources_path = child / "resources.json"
    if not summary_path.is_file():
        continue
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    c6 = summary.get("c6_windows", {})
    one_s = c6.get("1s", {})
    hundred_s = c6.get("100s", {})

    def peak(series: dict, metric: str) -> dict:
        block = series.get(metric, {})
        sliding = block.get("sliding_peak", {})
        return {
            "status": sliding.get("status"),
            "count": sliding.get("count"),
            "cps": sliding.get("cps"),
        }

    rss_snapshots = []
    if resources_path.is_file():
        res = json.loads(resources_path.read_text(encoding="utf-8"))
        rss_snapshots = res.get("snapshots", [])

    scenarios.append(
        {
            "tag": child.name,
            "summary_path": str(summary_path),
            "resources_path": str(resources_path) if resources_path.is_file() else None,
            "configured_cps": summary.get("rates_cps", {}).get("configured_target"),
            "injection_duration_seconds": summary.get("rates_cps", {}).get(
                "injection_duration_seconds"
            ),
            "counts": summary.get("counts"),
            "setup_latency_ms": summary.get("setup_latency_ms"),
            "c6_measurement_span_seconds": c6.get("measurement_span_seconds"),
            "c6_1s_sliding_peak": {
                "transmitted_invites": peak(one_s, "transmitted_invites"),
                "established_sessions": peak(one_s, "established_sessions"),
            },
            "c6_100s_sliding_peak": {
                "transmitted_invites": peak(hundred_s, "transmitted_invites"),
                "established_sessions": peak(hundred_s, "established_sessions"),
            },
            "uas_rss_kb_last": (
                rss_snapshots[-1].get("uas_rss_kb") if rss_snapshots else None
            ),
        }
    )

manifest = {
    "schema_version": 1,
    "purpose": "M6 O1 formal batch — internal dev-host measurement only",
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "batch_root": str(batch_root),
    "scenarios": scenarios,
}
manifest_path = batch_root / "formal_manifest.json"
manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(manifest_path)
PY
}

main() {
  require_runtime_extension
  local root="${AS_M6_OUTPUT_ROOT:-/tmp}"
  local batch_root="${root}/as-m6-o1-formal-$(date +%Y%m%d-%H%M%S)"
  mkdir -p "${batch_root}" || die "cannot write AS_M6_OUTPUT_ROOT=${root}"
  log "batch root: ${batch_root}"

  run_one_scenario 30 10 "${batch_root}"
  run_one_scenario 30 20 "${batch_root}"
  run_one_scenario 60 10 "${batch_root}"
  run_one_scenario 60 20 "${batch_root}"

  local manifest
  manifest="$(write_manifest "${batch_root}")"
  log "formal batch complete"
  log "manifest: ${manifest}"
  log "report input: ${batch_root}"
}

main "$@"
