#!/usr/bin/env bash
set -u

ROOT=/tmp/as-resip-dum-uas-restart
REPO=/home/shudong/project/3rdparty-as
SOURCE=/tmp/as-resiprocate-userbuild/resiprocate-1.14.0
BUILD=/tmp/as-resiprocate-userbuild/upstream-minimal-20260930
PYTHON=/home/shudong/project/3rdparty-as/.venv/bin/python
SERVER_PORT=47771
PEER_PORT=47772
TIMEOUT=8

mkdir -p "$ROOT/logs" "$ROOT/messages" "$ROOT/processes"
: > "$ROOT/commands.log"
: > "$ROOT/exit-codes.txt"

record_command() {
   printf '%s\n' "$1" >> "$ROOT/commands.log"
}

record_status() {
   printf '%s_exit_code=%s\n' "$1" "$2" >> "$ROOT/exit-codes.txt"
}

record_command "git -C $SOURCE rev-parse HEAD"
git -C "$SOURCE" rev-parse HEAD > "$ROOT/resip-source-commit.txt" 2>&1
source_commit_status=$?
record_status "resip_source_commit" "$source_commit_status"

record_command "$PYTHON --version"
"$PYTHON" --version > "$ROOT/python-version.txt" 2>&1
python_version_status=$?
record_status "python_version" "$python_version_status"

record_command "c++ -std=c++17 -O0 -g -I$SOURCE -I$BUILD $ROOT/uas_dum_process.cxx -L$BUILD/resip/dum -L$BUILD/resip/stack -L$BUILD/rutil -L$BUILD/rutil/dns/ares -Wl,-rpath,$BUILD/resip/dum:$BUILD/resip/stack:$BUILD/rutil:$BUILD/rutil/dns/ares -ldum-1.14 -lresip-1.14 -lrutil-1.14 -lresipares-1.14 -pthread -o $ROOT/uas_dum_process"
c++ -std=c++17 -O0 -g \
   -I"$SOURCE" -I"$BUILD" \
   "$ROOT/uas_dum_process.cxx" \
   -L"$BUILD/resip/dum" -L"$BUILD/resip/stack" \
   -L"$BUILD/rutil" -L"$BUILD/rutil/dns/ares" \
   -Wl,-rpath,"$BUILD/resip/dum:$BUILD/resip/stack:$BUILD/rutil:$BUILD/rutil/dns/ares" \
   -ldum-1.14 -lresip-1.14 -lrutil-1.14 -lresipares-1.14 -pthread \
   -o "$ROOT/uas_dum_process" > "$ROOT/logs/build.log" 2>&1
build_status=$?
record_status "native_build" "$build_status"

harness_status=125
if [[ $build_status -eq 0 ]]; then
   record_command "ldd $ROOT/uas_dum_process"
   ldd "$ROOT/uas_dum_process" > "$ROOT/logs/ldd-uas-dum-process.log" 2>&1
   ldd_status=$?
   if [[ $ldd_status -eq 0 ]] && grep -q 'not found' "$ROOT/logs/ldd-uas-dum-process.log"; then
      ldd_status=1
   fi
   record_status "native_dynamic_dependencies" "$ldd_status"

   if [[ $ldd_status -eq 0 ]]; then
      record_command "PYTHONDONTWRITEBYTECODE=1 $PYTHON $ROOT/experiment.py --server-port $SERVER_PORT --peer-port $PEER_PORT --timeout $TIMEOUT"
      PYTHONDONTWRITEBYTECODE=1 "$PYTHON" "$ROOT/experiment.py" \
         --server-port "$SERVER_PORT" --peer-port "$PEER_PORT" --timeout "$TIMEOUT" \
         > "$ROOT/logs/harness.log" 2>&1
      harness_status=$?
   else
      printf 'harness skipped: native dynamic dependencies did not validate\n' > "$ROOT/logs/harness.log"
   fi
else
   printf 'harness skipped: native build failed\n' > "$ROOT/logs/harness.log"
fi
record_status "two_phase_harness" "$harness_status"

record_command "git -C $REPO status --short"
git -C "$REPO" status --short > "$ROOT/repo-status-final.txt" 2>&1
repo_status_capture=$?
record_status "repo_status_final_capture" "$repo_status_capture"

record_command "cmp -s $ROOT/repo-status-initial.txt $ROOT/repo-status-final.txt"
if cmp -s "$ROOT/repo-status-initial.txt" "$ROOT/repo-status-final.txt"; then
   repo_status_compare=0
   printf 'IDENTICAL\n' > "$ROOT/repo-status-comparison.txt"
else
   repo_status_compare=1
   printf 'DIFFERENCES_FOUND\n' > "$ROOT/repo-status-comparison.txt"
   diff -u "$ROOT/repo-status-initial.txt" "$ROOT/repo-status-final.txt" > "$ROOT/repo-status-diff.txt" || true
fi
record_status "repo_status_compare" "$repo_status_compare"

printf 'native_build_exit=%s\n' "$build_status"
printf 'two_phase_harness_exit=%s\n' "$harness_status"
printf 'repo_status_compare_exit=%s\n' "$repo_status_compare"
cat "$ROOT/exit-codes.txt"
if [[ -f "$ROOT/validation.txt" ]]; then
   cat "$ROOT/validation.txt"
fi

if [[ $build_status -ne 0 || $harness_status -ne 0 || $repo_status_compare -ne 0 ]]; then
   exit 1
fi
exit 0
