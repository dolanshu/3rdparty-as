#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
readonly RESIP_HOME="${RESIP_HOME:-/tmp/as-resiprocate-userbuild/resiprocate-1.14.0}"
readonly RESIP_BUILD="${RESIP_BUILD:-/tmp/as-resiprocate-userbuild/upstream-minimal-20260930}"
readonly CXX="${CXX:-g++}"
readonly RUN_DIR="$(mktemp -d "${TMPDIR:-/tmp}/as-d10-recovery.XXXXXXXX")"

if [[ -n "${PYTHON:-}" ]]; then
  readonly PYTHON_BIN="$PYTHON"
elif [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
  readonly PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
else
  readonly PYTHON_BIN="$(command -v python3 || true)"
fi

export AS_REPO="$REPO_ROOT"
export D10_RUN_DIR="$RUN_DIR"
export PYTHONDONTWRITEBYTECODE=1
export RESIP_HOME
export RESIP_BUILD
export LD_LIBRARY_PATH="$RESIP_BUILD/resip/dum:$RESIP_BUILD/resip/stack:$RESIP_BUILD/rutil:$RESIP_BUILD/rutil/dns/ares${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

compile_status=not-run
link_status=not-run
ldd_status=not-run
python_syntax_status=not-run
integration_status=not-run

finish() {
  local runner_status=$?
  trap - EXIT
  printf 'D10_RUN_DIR=%s\n' "$RUN_DIR"
  printf 'D10_CXX_COMPILE_EXIT_STATUS=%s\n' "$compile_status"
  printf 'D10_CXX_LINK_EXIT_STATUS=%s\n' "$link_status"
  printf 'D10_LDD_EXIT_STATUS=%s\n' "$ldd_status"
  printf 'D10_PYTHON_SYNTAX_EXIT_STATUS=%s\n' "$python_syntax_status"
  printf 'D10_LOOPBACK_REAL_REDIS_EXIT_STATUS=%s\n' "$integration_status"
  if [[ "$runner_status" -eq 0 ]]; then
    printf 'D10_FINAL_RESULT=PASS\n'
  else
    printf 'D10_FINAL_RESULT=FAIL\n'
  fi
  printf 'D10_RUNNER_EXIT_STATUS=%s\n' "$runner_status"
  exit "$runner_status"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

run_logged() {
  local label="$1"
  local log_path="$2"
  shift 2
  local command_status=0
  printf '%s_COMMAND=' "$label"
  printf '%q ' "$@"
  printf '\n'
  if "$@" >"$log_path" 2>&1; then
    command_status=0
  else
    command_status=$?
  fi
  printf '%s_EXIT_STATUS=%s\n' "$label" "$command_status"
  if [[ "$command_status" -ne 0 ]]; then
    sed -n '1,160p' "$log_path"
    return "$command_status"
  fi
}

printf 'D10_SCOPE=testbed-only; no product adapter or D10 acceptance\n'
printf 'D10_RUN_DIR=%s\n' "$RUN_DIR"
printf 'RESIP_HOME=%s\n' "$RESIP_HOME"
printf 'RESIP_BUILD=%s\n' "$RESIP_BUILD"

if [[ -z "$PYTHON_BIN" ]]; then
  printf 'BLOCKER=python3 is unavailable\n'
  exit 20
fi
if [[ ! -d "$RESIP_HOME" || ! -d "$RESIP_BUILD" ]]; then
  printf 'BLOCKER=reSIProcate source/build directory is missing\n'
  exit 21
fi
if ! command -v "$CXX" >/dev/null 2>&1; then
  printf 'BLOCKER=C++ compiler is unavailable: %s\n' "$CXX"
  exit 22
fi

if run_logged PYTHON_SYNTAX "$RUN_DIR/python-syntax.log" \
  "$PYTHON_BIN" -c 'import ast,sys; ast.parse(open(sys.argv[1], encoding="utf-8").read(), filename=sys.argv[1])' \
  "$SCRIPT_DIR/orchestrate.py"; then
  python_syntax_status=0
else
  python_syntax_status=$?
  exit 23
fi

if run_logged CXX_COMPILE "$RUN_DIR/cxx-compile.log" \
  "$CXX" -std=c++17 -O0 -g \
  -I"$RESIP_HOME" \
  -I"$RESIP_BUILD" \
  -c "$SCRIPT_DIR/d10_recovery.cxx" \
  -o "$RUN_DIR/d10_recovery.o"; then
  compile_status=0
else
  compile_status=$?
  exit 24
fi

if run_logged CXX_LINK "$RUN_DIR/cxx-link.log" \
  "$CXX" -o "$RUN_DIR/d10_recovery" "$RUN_DIR/d10_recovery.o" \
  -L"$RESIP_BUILD/resip/dum" \
  -L"$RESIP_BUILD/resip/stack" \
  -L"$RESIP_BUILD/rutil" \
  -L"$RESIP_BUILD/rutil/dns/ares" \
  -Wl,-rpath,"$RESIP_BUILD/resip/dum:$RESIP_BUILD/resip/stack:$RESIP_BUILD/rutil:$RESIP_BUILD/rutil/dns/ares" \
  -ldum-1.14 -lresip-1.14 -lrutil-1.14 -lresipares-1.14 -pthread; then
  link_status=0
else
  link_status=$?
  exit 25
fi

if run_logged NATIVE_LDD "$RUN_DIR/ldd.log" ldd "$RUN_DIR/d10_recovery"; then
  ldd_status=0
else
  ldd_status=$?
  exit 26
fi
if grep -q 'not found' "$RUN_DIR/ldd.log"; then
  ldd_status=1
  printf 'BLOCKER=linked native probe has unresolved shared libraries; see %s/ldd.log\n' "$RUN_DIR"
  exit 27
fi
ldd_status=0

printf 'LOOPBACK_REAL_REDIS_COMMAND='
printf '%q ' "$PYTHON_BIN" "$SCRIPT_DIR/orchestrate.py" --run-dir "$RUN_DIR" --binary "$RUN_DIR/d10_recovery"
printf '\n'
if "$PYTHON_BIN" "$SCRIPT_DIR/orchestrate.py" --run-dir "$RUN_DIR" --binary "$RUN_DIR/d10_recovery" 2>&1 \
  | tee "$RUN_DIR/orchestrate.stdout.log"; then
  integration_status=0
else
  integration_status=$?
  exit 28
fi