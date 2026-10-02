#!/usr/bin/env bash
set -u -o pipefail

ROOT=/tmp/as-resip-dum-two-leg-spike
REPO=/home/shudong/project/3rdparty-as
PYTHON=/home/shudong/project/3rdparty-as/.venv/bin/python
PYTHON_LIBDIR=/home/shudong/.local/share/uv/python/cpython-3.10.21-linux-x86_64-gnu/lib
UPSTREAM_BUILD=/tmp/as-resiprocate-userbuild/upstream-minimal-20260930
EXT="$ROOT/_resip_dum.cpython-310-x86_64-linux-gnu.so"
LOGS="$ROOT/logs"
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
      tail -n 80 "$log_file"
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
   run_logged integration timeout 45s env PYTHONDONTWRITEBYTECODE=1 \
      "$PYTHON" "$ROOT/run_integration.py"
else
   printf 'SKIP ldd and integration: extension was not produced\n'
   OVERALL_STATUS=1
fi

CURRENT_STATUS="$LOGS/repo-status-current.txt"
git -C "$REPO" -c core.quotePath=false status --short >"$CURRENT_STATUS" 2>&1
STATUS_COMMAND=$?
printf 'COMMAND[repo-status]=git -C %q -c core.quotePath=false status --short\n' "$REPO"
printf 'EXIT_CODE[repo-status]=%s\n' "$STATUS_COMMAND"
if [[ "$STATUS_COMMAND" -ne 0 ]]; then
   OVERALL_STATUS=1
fi

if diff -u "$ROOT/repo-status-baseline.txt" "$CURRENT_STATUS" \
   >"$LOGS/repo-status-diff.log" 2>&1; then
   DIFF_STATUS=0
else
   DIFF_STATUS=$?
fi
printf 'COMMAND[repo-status-diff]=diff -u %q %q\n' \
   "$ROOT/repo-status-baseline.txt" "$CURRENT_STATUS"
printf 'EXIT_CODE[repo-status-diff]=%s\n' "$DIFF_STATUS"
if [[ "$DIFF_STATUS" -ne 0 ]]; then
   cat "$LOGS/repo-status-diff.log"
   OVERALL_STATUS=1
fi

printf 'OVERALL_EXIT_CODE=%s\n' "$OVERALL_STATUS"
exit "$OVERALL_STATUS"