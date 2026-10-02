#!/usr/bin/env bash
set -u

ROOT=/tmp/as-resip-dum-process-restart
REPO=/home/shudong/project/3rdparty-as
SOURCE=/tmp/as-resiprocate-userbuild/resiprocate-1.14.0
BUILD=/tmp/as-resiprocate-userbuild/upstream-minimal-20260930
PYTHON=/home/shudong/project/3rdparty-as/.venv/bin/python
PEER_PORT=39841
CLIENT_PORT=39842

mkdir -p "$ROOT/logs" "$ROOT/messages" "$ROOT/processes"
: > "$ROOT/exit-codes.txt"
: > "$ROOT/commands.log"

record_status() {
   printf '%s_exit_code=%s\n' "$1" "$2" >> "$ROOT/exit-codes.txt"
}

record_command() {
   printf '%s\n' "$1" >> "$ROOT/commands.log"
}

record_command "date -u +%Y-%m-%dT%H:%M:%SZ"
date -u +%Y-%m-%dT%H:%M:%SZ > "$ROOT/run-start-utc.txt" 2>&1
record_command "git -C $REPO status --short --untracked-files=all"
git -C "$REPO" status --short --untracked-files=all > "$ROOT/repo-status-before.txt" 2>&1
record_status "repo_status_before" "$?"
record_command "git -C $SOURCE rev-parse HEAD"
git -C "$SOURCE" rev-parse HEAD > "$ROOT/resip-source-commit.txt" 2>&1
record_status "resip_source_commit" "$?"
record_command "git -C $SOURCE status --short --untracked-files=all"
git -C "$SOURCE" status --short --untracked-files=all > "$ROOT/resip-source-status.txt" 2>&1
record_status "resip_source_status" "$?"
record_command "$PYTHON --version"
"$PYTHON" --version > "$ROOT/python-version.txt" 2>&1
record_status "python_version" "$?"
record_command "$PYTHON -c 'import sys; print(sys.executable); print(sys.version)'"
"$PYTHON" -c 'import sys; print(sys.executable); print(sys.version)' > "$ROOT/python-runtime.txt" 2>&1
record_status "python_runtime" "$?"

record_command "find $REPO -path $REPO/.git -prune -o -type f -print0 | sort -z | xargs -0 -r sha256sum"
find "$REPO" -path "$REPO/.git" -prune -o -type f -print0 | sort -z | xargs -0 -r sha256sum > "$ROOT/repo-files-before.sha256" 2> "$ROOT/logs/repo-hash-before.log"
record_status "repo_hash_before" "$?"
record_command "find $REPO -path $REPO/.git -prune -o -type l -printf '%p -> %l\\n' | sort"
find "$REPO" -path "$REPO/.git" -prune -o -type l -printf '%p -> %l\n' | sort > "$ROOT/repo-symlinks-before.txt" 2> "$ROOT/logs/repo-symlinks-before.log"
record_status "repo_symlinks_before" "$?"

COMPILE_COMMAND="c++ -std=c++17 -O0 -g -I$SOURCE -I$BUILD $ROOT/dum_phase_child.cxx -L$BUILD/resip/dum -L$BUILD/resip/stack -L$BUILD/rutil -L$BUILD/rutil/dns/ares -Wl,-rpath,$BUILD/resip/dum:$BUILD/resip/stack:$BUILD/rutil:$BUILD/rutil/dns/ares -ldum-1.14 -lresip-1.14 -lrutil-1.14 -lresipares-1.14 -pthread -o $ROOT/dum_phase_child"
record_command "$COMPILE_COMMAND"
c++ -std=c++17 -O0 -g \
   -I"$SOURCE" -I"$BUILD" \
   "$ROOT/dum_phase_child.cxx" \
   -L"$BUILD/resip/dum" -L"$BUILD/resip/stack" \
   -L"$BUILD/rutil" -L"$BUILD/rutil/dns/ares" \
   -Wl,-rpath,"$BUILD/resip/dum:$BUILD/resip/stack:$BUILD/rutil:$BUILD/rutil/dns/ares" \
   -ldum-1.14 -lresip-1.14 -lrutil-1.14 -lresipares-1.14 -pthread \
   -o "$ROOT/dum_phase_child" > "$ROOT/logs/build.log" 2>&1
build_status=$?
record_status "child_build" "$build_status"

if [[ $build_status -eq 0 ]]; then
   record_command "ldd $ROOT/dum_phase_child"
   ldd "$ROOT/dum_phase_child" > "$ROOT/logs/ldd-child.log" 2>&1
   ldd_status=$?
   if [[ $ldd_status -eq 0 ]] && grep -q 'not found' "$ROOT/logs/ldd-child.log"; then
      ldd_status=1
   fi
   record_status "child_ldd" "$ldd_status"
   if [[ $ldd_status -eq 0 ]]; then
      record_command "PYTHONDONTWRITEBYTECODE=1 $PYTHON $ROOT/process_restart.py --peer-port $PEER_PORT --client-port $CLIENT_PORT --timeout 12"
      PYTHONDONTWRITEBYTECODE=1 "$PYTHON" "$ROOT/process_restart.py" \
         --peer-port "$PEER_PORT" --client-port "$CLIENT_PORT" --timeout 12 \
         > "$ROOT/logs/harness.log" 2>&1
      harness_status=$?
      record_status "process_restart_harness" "$harness_status"
   else
      printf 'harness skipped: child dynamic dependencies did not validate\n' > "$ROOT/logs/harness.log"
      record_status "process_restart_harness" 125
   fi
else
   printf 'harness skipped: child compile failed\n' > "$ROOT/logs/harness.log"
   record_status "child_ldd" 125
   record_status "process_restart_harness" 125
fi

record_command "git -C $REPO status --short --untracked-files=all"
git -C "$REPO" status --short --untracked-files=all > "$ROOT/repo-status-after.txt" 2>&1
record_status "repo_status_after" "$?"
record_command "find $REPO -path $REPO/.git -prune -o -type f -print0 | sort -z | xargs -0 -r sha256sum"
find "$REPO" -path "$REPO/.git" -prune -o -type f -print0 | sort -z | xargs -0 -r sha256sum > "$ROOT/repo-files-after.sha256" 2> "$ROOT/logs/repo-hash-after.log"
record_status "repo_hash_after" "$?"
record_command "cmp -s $ROOT/repo-files-before.sha256 $ROOT/repo-files-after.sha256"
if cmp -s "$ROOT/repo-files-before.sha256" "$ROOT/repo-files-after.sha256"; then
   hash_compare_status=0
   printf 'BYTE_FOR_BYTE_IDENTICAL\n' > "$ROOT/repo-byte-for-byte-comparison.txt"
else
   hash_compare_status=1
   printf 'DIFFERENCES_FOUND\n' > "$ROOT/repo-byte-for-byte-comparison.txt"
   diff -u "$ROOT/repo-files-before.sha256" "$ROOT/repo-files-after.sha256" > "$ROOT/repo-hash-diff.txt" || true
fi
record_status "repo_byte_for_byte_compare" "$hash_compare_status"
record_command "find $REPO -path $REPO/.git -prune -o -type l -printf '%p -> %l\\n' | sort"
find "$REPO" -path "$REPO/.git" -prune -o -type l -printf '%p -> %l\n' | sort > "$ROOT/repo-symlinks-after.txt" 2> "$ROOT/logs/repo-symlinks-after.log"
record_status "repo_symlinks_after" "$?"
record_command "cmp -s $ROOT/repo-symlinks-before.txt $ROOT/repo-symlinks-after.txt"
if cmp -s "$ROOT/repo-symlinks-before.txt" "$ROOT/repo-symlinks-after.txt"; then
   symlink_compare_status=0
else
   symlink_compare_status=1
   diff -u "$ROOT/repo-symlinks-before.txt" "$ROOT/repo-symlinks-after.txt" > "$ROOT/repo-symlink-diff.txt" || true
fi
record_status "repo_symlink_compare" "$symlink_compare_status"

printf 'child_build_exit=%s\n' "$build_status"
printf 'repository_byte_for_byte_compare_exit=%s\n' "$hash_compare_status"
printf 'repository_symlink_compare_exit=%s\n' "$symlink_compare_status"
if [[ -f "$ROOT/exit-codes.txt" ]]; then
   cat "$ROOT/exit-codes.txt"
fi
if [[ -f "$ROOT/validation.txt" ]]; then
   cat "$ROOT/validation.txt"
fi
if [[ $build_status -ne 0 || $hash_compare_status -ne 0 || $symlink_compare_status -ne 0 ]]; then
   exit 1
fi
if [[ -f "$ROOT/exit-codes.txt" ]] && grep -q '^process_restart_harness_exit_code=0$' "$ROOT/exit-codes.txt"; then
   exit 0
fi
exit 1
