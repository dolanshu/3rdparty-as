#!/usr/bin/env bash
set -u -o pipefail

ROOT=/tmp/as-resip-two-leg-restart-recovery
REPO=/home/shudong/project/3rdparty-as
SOURCE=/tmp/as-resiprocate-userbuild/resiprocate-1.14.0
PYTHON=/home/shudong/project/3rdparty-as/.venv/bin/python
CLIENT_PORT=${CLIENT_PORT:-52641}
PEER_A_PORT=${PEER_A_PORT:-52642}
PEER_B_PORT=${PEER_B_PORT:-52643}
RUN_ID="$(date -u +%Y%m%dT%H%M%S%NZ)"
ARTIFACT_ROOT="$ROOT/runs/$RUN_ID"
LOGS="$ARTIFACT_ROOT/logs"

if [[ ! -f "$ROOT/git-status.initial" ]]; then
   printf 'Missing pre-experiment git status snapshot: %s\n' "$ROOT/git-status.initial" >&2
   exit 2
fi

mkdir -p "$LOGS"
: >"$ARTIFACT_ROOT/commands.log"
: >"$ARTIFACT_ROOT/exit-codes.txt"

OVERALL_STATUS=0

record_status() {
   printf '%s_exit_code=%s\n' "$1" "$2" >>"$ARTIFACT_ROOT/exit-codes.txt"
   if [[ "$2" -ne 0 ]]; then
      OVERALL_STATUS=1
   fi
}

record_command() {
   printf '%s\n' "$1" >>"$ARTIFACT_ROOT/commands.log"
}

run_logged() {
   local label="$1"
   shift
   local status=0
   local log_path="$LOGS/$label.log"
   local rendered
   printf -v rendered '%q ' "$@"
   record_command "$rendered > $log_path 2>&1"
   if "$@" >"$log_path" 2>&1; then
      status=0
   else
      status=$?
   fi
   printf 'EXIT_CODE[%s]=%s\n' "$label" "$status"
   record_status "$label" "$status"
   return 0
}

write_json_header() {
   printf '{\n  "run_id": "%s",\n  "artifact_root": "%s",\n  "ports": {"dum_client": %s, "peer_a": %s, "peer_b": %s}\n}\n' \
      "$RUN_ID" "$ARTIFACT_ROOT" "$CLIENT_PORT" "$PEER_A_PORT" "$PEER_B_PORT" \
      >"$ARTIFACT_ROOT/run-info.json"
}

write_json_header
cp "$ROOT/git-status.initial" "$ARTIFACT_ROOT/git-status.initial"
record_command "cp $ROOT/git-status.initial $ARTIFACT_ROOT/git-status.initial"
COPY_STATUS=$?
record_status "copy_initial_git_status" "$COPY_STATUS"
record_command "initial snapshot captured before experiment: git status --short --untracked-files=all"
record_status "initial_git_status_capture" 0

run_logged run-start-date date -u +%Y-%m-%dT%H:%M:%SZ
run_logged source-commit git -C "$SOURCE" rev-parse HEAD
run_logged source-status git -C "$SOURCE" status --short --untracked-files=all
run_logged python-version "$PYTHON" --version
run_logged python-runtime "$PYTHON" -c 'import sys; print(sys.executable); print(sys.version)'
run_logged compiler-version /usr/bin/c++ --version
run_logged shell-syntax bash -n "$ROOT/build.sh" "$ROOT/run.sh"
run_logged python-syntax "$PYTHON" -m py_compile \
   "$ROOT/dum_child.py" "$ROOT/two_leg_harness.py"

run_logged native-build \
   env BUILD_LOG="$LOGS/native-build.log" LDD_LOG="$LOGS/ldd-extension.log" \
   bash "$ROOT/build.sh"

if [[ "$OVERALL_STATUS" -eq 0 && \
   -f "$ROOT/_as_resip_two_leg.cpython-310-x86_64-linux-gnu.so" ]]; then
   run_logged extension-import \
      env PYTHONPATH="$ROOT" "$PYTHON" -c \
      'import _as_resip_two_leg; print("MODULE_IMPORT_PASS", hasattr(_as_resip_two_leg, "run_phase"))'
else
   printf 'SKIP extension-import: extension was not produced\n'
   record_status "extension_import" 125
fi

if [[ "$OVERALL_STATUS" -eq 0 ]]; then
   run_logged two-process-harness \
      timeout 45s env PYTHONDONTWRITEBYTECODE=1 "$PYTHON" \
      "$ROOT/two_leg_harness.py" \
      --client-port "$CLIENT_PORT" \
      --peer-a-port "$PEER_A_PORT" \
      --peer-b-port "$PEER_B_PORT" \
      --timeout 12 \
      --child-timeout 18 \
      --artifact-root "$ARTIFACT_ROOT"
else
   printf 'SKIP two-process-harness: an earlier build or import check failed\n'
   record_status "two_process_harness" 125
fi

record_command "git -C $REPO status --short --untracked-files=all > $ARTIFACT_ROOT/git-status.final"
if git -C "$REPO" status --short --untracked-files=all \
   >"$ARTIFACT_ROOT/git-status.final" 2>&1; then
   STATUS_CAPTURE=0
else
   STATUS_CAPTURE=$?
fi
record_status "final_git_status_capture" "$STATUS_CAPTURE"

record_command "cmp -s $ROOT/git-status.initial $ARTIFACT_ROOT/git-status.final"
if cmp -s "$ROOT/git-status.initial" "$ARTIFACT_ROOT/git-status.final"; then
   STATUS_COMPARE=0
   printf 'BYTE_FOR_BYTE_IDENTICAL\n' >"$ARTIFACT_ROOT/git-status-comparison.txt"
else
   STATUS_COMPARE=1
   printf 'DIFFERENCES_FOUND\n' >"$ARTIFACT_ROOT/git-status-comparison.txt"
   diff -u "$ROOT/git-status.initial" "$ARTIFACT_ROOT/git-status.final" \
      >"$ARTIFACT_ROOT/git-status-diff.txt" || true
fi
record_status "git_status_byte_compare" "$STATUS_COMPARE"

printf 'overall_exit_code=%s\n' "$OVERALL_STATUS" >>"$ARTIFACT_ROOT/exit-codes.txt"
printf 'ARTIFACT_ROOT=%s\n' "$ARTIFACT_ROOT"
printf 'OVERALL_EXIT_CODE=%s\n' "$OVERALL_STATUS"
if [[ -f "$ARTIFACT_ROOT/validation.txt" ]]; then
   cat "$ARTIFACT_ROOT/validation.txt"
fi
cat "$ARTIFACT_ROOT/git-status-comparison.txt"
exit "$OVERALL_STATUS"