#!/usr/bin/env bash
set -u -o pipefail

ROOT=/tmp/as-resip-dum-final-probes
REPO=/home/shudong/project/3rdparty-as
PYTHON=/home/shudong/project/3rdparty-as/.venv/bin/python
PYTHON_LIBDIR=/home/shudong/.local/share/uv/python/cpython-3.10.21-linux-x86_64-gnu/lib
UPSTREAM_BUILD=/tmp/as-resiprocate-userbuild/upstream-minimal-20260930
EXT="$ROOT/_resip_dum_sdp_roundtrip.cpython-310-x86_64-linux-gnu.so"
LOGS="$ROOT/logs"

: "${PROBE_A_UAS_PORT:?select an explicit free loopback Probe A UAS port}"
: "${PROBE_A_UPSTREAM_PORT:?select an explicit free loopback Probe A upstream port}"
: "${PROBE_A_DOWNSTREAM_PORT:?select an explicit free loopback Probe A downstream port}"
: "${PROBE_B_UAS_PORT:?select an explicit free loopback Probe B UAS port}"
: "${PROBE_B_UPSTREAM_PORT:?select an explicit free loopback Probe B upstream port}"
: "${PROBE_B_DOWNSTREAM_PORT:?select an explicit free loopback Probe B downstream port}"

declare -A seen_ports=()
for port in \
   "$PROBE_A_UAS_PORT" "$PROBE_A_UPSTREAM_PORT" "$PROBE_A_DOWNSTREAM_PORT" \
   "$PROBE_B_UAS_PORT" "$PROBE_B_UPSTREAM_PORT" "$PROBE_B_DOWNSTREAM_PORT"; do
   if [[ ! "$port" =~ ^[0-9]+$ ]]; then
      printf 'invalid non-numeric UDP port: %s\n' "$port" >&2
      exit 2
   fi
   port_value=$((10#$port))
   if (( port_value < 1 || port_value > 65535 )); then
      printf 'UDP port out of range: %s\n' "$port" >&2
      exit 2
   fi
   if [[ -n "${seen_ports[$port_value]:-}" ]]; then
      printf 'all six Probe A/B UDP ports must be distinct; duplicate=%s\n' \
         "$port_value" >&2
      exit 2
   fi
   seen_ports[$port_value]=1
done

mkdir -p "$LOGS"
exec >"$LOGS/run.log" 2>&1

OVERALL_STATUS=0

run_logged() {
   local label="$1"
   shift
   local log_file="$LOGS/$label.log"
   local command_status
   printf 'COMMAND[%s]=' "$label"
   printf '%q ' "$@"
   printf '\n'
   if "$@" >"$log_file" 2>&1; then
      command_status=0
   else
      command_status=$?
   fi
   printf 'EXIT_CODE[%s]=%s\n' "$label" "$command_status"
   if [[ "$command_status" -ne 0 ]]; then
      tail -n 100 "$log_file"
      OVERALL_STATUS=1
   fi
}

run_logged build timeout 75s bash "$ROOT/build.sh"
if [[ -f "$EXT" ]]; then
   run_logged ldd timeout 10s ldd "$EXT"
   DEPENDENCY_STATUS=0
   DEPENDENCY_LOG="$LOGS/dependency-check.log"
   {
      for dependency in \
         "libpython3.10.so.1.0 => $PYTHON_LIBDIR/libpython3.10.so.1.0" \
         "libdum-1.14.so => $UPSTREAM_BUILD/resip/dum/libdum-1.14.so" \
         "libresip-1.14.so => $UPSTREAM_BUILD/resip/stack/libresip-1.14.so" \
         "librutil-1.14.so => $UPSTREAM_BUILD/rutil/librutil-1.14.so" \
         "libresipares-1.14.so => $UPSTREAM_BUILD/rutil/dns/ares/libresipares-1.14.so"; do
         if grep -Fq -- "$dependency" "$LOGS/ldd.log"; then
            printf 'PASS %s\n' "$dependency"
         else
            printf 'FAIL missing %s\n' "$dependency"
            DEPENDENCY_STATUS=1
         fi
      done
      if grep -Fq 'not found' "$LOGS/ldd.log"; then
         printf 'FAIL ldd contains an unresolved library\n'
         DEPENDENCY_STATUS=1
      fi
      printf 'EXIT_CODE=%s\n' "$DEPENDENCY_STATUS"
   } >"$DEPENDENCY_LOG"
   cat "$DEPENDENCY_LOG"
   if [[ "$DEPENDENCY_STATUS" -ne 0 ]]; then
      OVERALL_STATUS=1
   fi

   run_logged probe-a timeout 45s env PYTHONDONTWRITEBYTECODE=1 \
      ROUNDTRIP_UAS_PORT="$PROBE_A_UAS_PORT" \
      ROUNDTRIP_UPSTREAM_PORT="$PROBE_A_UPSTREAM_PORT" \
      ROUNDTRIP_DOWNSTREAM_PORT="$PROBE_A_DOWNSTREAM_PORT" \
      /home/shudong/project/3rdparty-as/.venv/bin/python "$ROOT/probe_a.py"

   run_logged probe-b timeout 45s env PYTHONDONTWRITEBYTECODE=1 \
      CANCEL_UAS_PORT="$PROBE_B_UAS_PORT" \
      CANCEL_UPSTREAM_PORT="$PROBE_B_UPSTREAM_PORT" \
      CANCEL_DOWNSTREAM_PORT="$PROBE_B_DOWNSTREAM_PORT" \
      /home/shudong/project/3rdparty-as/.venv/bin/python "$ROOT/probe_b.py"
else
   printf 'SKIP ldd and probes: native extension was not produced\n'
   OVERALL_STATUS=1
fi

if git -C "$REPO" status --short --untracked-files=all \
   >"$LOGS/repo-status-current.txt" 2>&1; then
   printf 'EXIT_CODE[repo-status-all]=0\n'
else
   STATUS_COMMAND=$?
   printf 'EXIT_CODE[repo-status-all]=%s\n' "$STATUS_COMMAND"
   OVERALL_STATUS=1
fi

if diff -u "$ROOT/repo-status-baseline.txt" "$LOGS/repo-status-current.txt" \
   >"$LOGS/repo-status-diff.log" 2>&1; then
   printf 'EXIT_CODE[repo-status-all-diff]=0\n'
else
   DIFF_STATUS=$?
   printf 'EXIT_CODE[repo-status-all-diff]=%s\n' "$DIFF_STATUS"
   cat "$LOGS/repo-status-diff.log"
   OVERALL_STATUS=1
fi

if git -C "$REPO" status --short \
   >"$LOGS/repo-status-short-current.txt" 2>&1; then
   printf 'EXIT_CODE[repo-status-short]=0\n'
else
   STATUS_COMMAND=$?
   printf 'EXIT_CODE[repo-status-short]=%s\n' "$STATUS_COMMAND"
   OVERALL_STATUS=1
fi

if diff -u "$ROOT/repo-status-short-baseline.txt" \
   "$LOGS/repo-status-short-current.txt" >"$LOGS/repo-status-short-diff.log" 2>&1; then
   printf 'EXIT_CODE[repo-status-short-diff]=0\n'
else
   DIFF_STATUS=$?
   printf 'EXIT_CODE[repo-status-short-diff]=%s\n' "$DIFF_STATUS"
   cat "$LOGS/repo-status-short-diff.log"
   OVERALL_STATUS=1
fi

printf 'OVERALL_EXIT_CODE=%s\n' "$OVERALL_STATUS"
exit "$OVERALL_STATUS"