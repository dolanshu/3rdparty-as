#!/usr/bin/env bash
set -u -o pipefail

ROOT=/tmp/as-resip-dum-python-slice
REPO=/home/shudong/project/3rdparty-as
PYTHON=/home/shudong/project/3rdparty-as/.venv/bin/python
PYTHON_LIBDIR=/home/shudong/.local/share/uv/python/cpython-3.10.21-linux-x86_64-gnu/lib
UPSTREAM_BUILD=/tmp/as-resiprocate-userbuild/upstream-minimal-20260930
EXT="$ROOT/build/_resip_dum.cpython-310-x86_64-linux-gnu.so"
LOGS="$ROOT/logs"

mkdir -p "$LOGS"

run_logged() {
   local label="$1"
   shift
   local log_file="$LOGS/$label.log"
   local command_status

   {
      printf 'COMMAND:'
      printf ' %q' "$@"
      printf '\n'
   } > "$log_file"
   "$@" >> "$log_file" 2>&1
   command_status=$?
   printf 'EXIT_CODE: %s\n' "$command_status" >> "$log_file"
   cat "$log_file"
   return "$command_status"
}

overall_status=0
printf 'VALIDATION_COMMAND: bash %s/validate.sh\n' "$ROOT" > "$LOGS/summary.log"

run_logged build sh "$ROOT/build.sh"
build_status=$?
if [[ $build_status -ne 0 ]]; then
   overall_status=1
fi

if [[ $build_status -eq 0 ]]; then
   run_logged ldd ldd "$EXT"
   ldd_status=$?
   if [[ $ldd_status -ne 0 ]]; then
      overall_status=1
   fi

   dependency_log="$LOGS/dependency-check.log"
   dependency_status=0
   {
      printf 'COMMAND: assert exact libpython and reSIProcate paths from ldd.log\n'
      for dependency in \
         "libpython3.10.so.1.0 => $PYTHON_LIBDIR/libpython3.10.so.1.0" \
         "libdum-1.14.so => $UPSTREAM_BUILD/resip/dum/libdum-1.14.so" \
         "libresip-1.14.so => $UPSTREAM_BUILD/resip/stack/libresip-1.14.so" \
         "librutil-1.14.so => $UPSTREAM_BUILD/rutil/librutil-1.14.so" \
         "libresipares-1.14.so => $UPSTREAM_BUILD/rutil/dns/ares/libresipares-1.14.so"; do
         if grep -Fq -- "$dependency" "$LOGS/ldd.log"; then
            printf 'PASS: %s\n' "$dependency"
         else
            printf 'FAIL: %s\n' "$dependency"
            dependency_status=1
         fi
      done
      if grep -Fq 'not found' "$LOGS/ldd.log"; then
         printf 'FAIL: ldd reported an unresolved library\n'
         dependency_status=1
      fi
      printf 'EXIT_CODE: %s\n' "$dependency_status"
   } > "$dependency_log"
   cat "$dependency_log"
   if [[ $dependency_status -ne 0 ]]; then
      overall_status=1
   fi

   run_logged integration env PYTHONDONTWRITEBYTECODE=1 "$PYTHON" "$ROOT/run_integration.py"
   integration_status=$?
   if [[ $integration_status -ne 0 ]]; then
      overall_status=1
   fi
else
   printf 'SKIPPED: ldd and integration require a successful extension build\n' \
      > "$LOGS/post-build-checks.log"
   printf 'EXIT_CODE: 125\n' >> "$LOGS/post-build-checks.log"
   cat "$LOGS/post-build-checks.log"
   overall_status=1
fi

status_file="$LOGS/repo-status.current"
git -C "$REPO" -c core.quotePath=false status --short --untracked-files=all \
   > "$status_file" 2>&1
status_command_status=$?
{
   printf 'COMMAND: git -C %s -c core.quotePath=false status --short --untracked-files=all\n' "$REPO"
   cat "$status_file"
   printf 'EXIT_CODE: %s\n' "$status_command_status"
} > "$LOGS/repo-status.log"
cat "$LOGS/repo-status.log"
if [[ $status_command_status -ne 0 ]]; then
   overall_status=1
fi

run_logged baseline-compare diff -u \
   <(cat "$ROOT/repo-status-baseline.txt"; printf '\n') "$status_file"
baseline_status=$?
if [[ $baseline_status -ne 0 ]]; then
   overall_status=1
fi

printf 'OVERALL_EXIT_CODE: %s\n' "$overall_status" >> "$LOGS/summary.log"
cat "$LOGS/summary.log"
exit "$overall_status"