#!/usr/bin/env bash
set -u
set -o pipefail

ROOT=/home/shudong/project/3rdparty-as
OUTPUT_DIR=/tmp/as-resip-python-bridge-spike
PYTHON_INCLUDE=/home/shudong/.local/share/uv/python/cpython-3.10-linux-x86_64-gnu/include/python3.10
PYTHON_LIBDIR=/home/shudong/.local/share/uv/python/cpython-3.10.21-linux-x86_64-gnu/lib
PYTHON_LIBRARY=python3.10
EXTENSION_SUFFIX=.cpython-310-x86_64-linux-gnu.so
EXTENSION_PATH="$OUTPUT_DIR/as_resip_bridge$EXTENSION_SUFFIX"

mkdir -p "$OUTPUT_DIR/tmp" "$OUTPUT_DIR/uv-cache"
exec 3>&1
exec > "$OUTPUT_DIR/run.log" 2>&1

finish() {
    local status=$1
    cat "$OUTPUT_DIR/run.log" >&3
    exit "$status"
}

printf 'RUNNER_COMMAND: bash %s\n' "$OUTPUT_DIR/run.sh"
printf 'REPOSITORY: %s\n' "$ROOT"
printf 'OUTPUT_DIRECTORY: %s\n' "$OUTPUT_DIR"
printf 'PYTHON_INCLUDE: %s\n' "$PYTHON_INCLUDE"
printf 'PYTHON_LIBRARY_DIRECTORY: %s\n' "$PYTHON_LIBDIR"
printf 'PYTHON_LIBRARY: lib%s.so\n' "$PYTHON_LIBRARY"
printf 'EXTENSION_SUFFIX: %s\n' "$EXTENSION_SUFFIX"

/usr/bin/c++ --version > "$OUTPUT_DIR/compiler-version.log" 2>&1
compiler_version_status=$?
printf 'COMPILER_VERSION_EXIT_CODE=%d\n' "$compiler_version_status"
cat "$OUTPUT_DIR/compiler-version.log"
if [[ "$compiler_version_status" -ne 0 ]]; then
    finish "$compiler_version_status"
fi

build_command=(
    timeout 60s
    env "TMPDIR=$OUTPUT_DIR/tmp"
    /usr/bin/c++
    -std=c++17
    -O2
    -Wall
    -Wextra
    -fPIC
    -shared
    -pthread
    "-I$PYTHON_INCLUDE"
    "$OUTPUT_DIR/bridge.cpp"
    "-L$PYTHON_LIBDIR"
    "-Wl,-rpath,$PYTHON_LIBDIR"
    "-l$PYTHON_LIBRARY"
    -o "$EXTENSION_PATH"
)
printf 'BUILD_COMMAND='
printf '%q ' "${build_command[@]}"
printf '\n'
"${build_command[@]}" > "$OUTPUT_DIR/build.log" 2>&1
build_status=$?
printf 'BUILD_EXIT_CODE=%d\n' "$build_status"
cat "$OUTPUT_DIR/build.log"
if [[ "$build_status" -ne 0 ]]; then
    finish "$build_status"
fi

timeout 10s ldd "$EXTENSION_PATH" > "$OUTPUT_DIR/extension-linkage.log" 2>&1
linkage_status=$?
printf 'LINKAGE_CHECK_EXIT_CODE=%d\n' "$linkage_status"
cat "$OUTPUT_DIR/extension-linkage.log"
if [[ "$linkage_status" -ne 0 ]]; then
    finish "$linkage_status"
fi

cd "$ROOT" || finish 99
harness_command=(
    timeout 60s
    env
    PYTHONDONTWRITEBYTECODE=1
    "UV_CACHE_DIR=$OUTPUT_DIR/uv-cache"
    UV_NO_PROGRESS=1
    UV_PYTHON_DOWNLOADS=never
    uv run --no-sync --project "$ROOT" python
    "$OUTPUT_DIR/harness.py"
    "$EXTENSION_PATH"
)
printf 'HARNESS_COMMAND='
printf '%q ' "${harness_command[@]}"
printf '\n'
"${harness_command[@]}" > "$OUTPUT_DIR/harness.log" 2>&1
harness_status=$?
printf 'HARNESS_EXIT_CODE=%d\n' "$harness_status"
cat "$OUTPUT_DIR/harness.log"
finish "$harness_status"