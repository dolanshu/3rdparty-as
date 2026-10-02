#!/bin/sh
set -u

ROOT=/tmp/as-resip-dum-two-leg-spike
PYTHON=/home/shudong/project/3rdparty-as/.venv/bin/python
PYTHON_INCLUDE=/home/shudong/.local/share/uv/python/cpython-3.10-linux-x86_64-gnu/include/python3.10
PYTHON_LIBDIR=/home/shudong/.local/share/uv/python/cpython-3.10.21-linux-x86_64-gnu/lib
UPSTREAM_SRC=/tmp/as-resiprocate-userbuild/resiprocate-1.14.0
UPSTREAM_BUILD=/tmp/as-resiprocate-userbuild/upstream-minimal-20260930
EXTENSION_SUFFIX=.cpython-310-x86_64-linux-gnu.so
OUTPUT="$ROOT/_resip_dum$EXTENSION_SUFFIX"
RPATH="$UPSTREAM_BUILD/resip/dum:$UPSTREAM_BUILD/resip/stack:$UPSTREAM_BUILD/rutil:$UPSTREAM_BUILD/rutil/dns/ares:$PYTHON_LIBDIR"
BUILD_LOG="$ROOT/logs/native-build.log"

mkdir -p "$ROOT/tmp" "$ROOT/logs"
printf 'PYTHON='; "$PYTHON" --version
printf 'PYTHON_INCLUDE=%s\nPYTHON_LIBDIR=%s\nPYTHON_LIBRARY=libpython3.10.so\n' \
   "$PYTHON_INCLUDE" "$PYTHON_LIBDIR"
printf 'OUTPUT=%s\n' "$OUTPUT"

if timeout 60s env TMPDIR="$ROOT/tmp" /usr/bin/c++ \
   -std=c++17 -O2 -g -Wall -Wextra -fPIC -shared -pthread \
   -I"$PYTHON_INCLUDE" \
   -I"$UPSTREAM_BUILD" \
   -I"$UPSTREAM_SRC" \
   -I"$UPSTREAM_SRC/rutil/dns/ares" \
   "$ROOT/dum_two_leg_module.cxx" \
   -L"$UPSTREAM_BUILD/resip/dum" \
   -L"$UPSTREAM_BUILD/resip/stack" \
   -L"$UPSTREAM_BUILD/rutil" \
   -L"$UPSTREAM_BUILD/rutil/dns/ares" \
   -L"$PYTHON_LIBDIR" \
   -Wl,-rpath,"$RPATH" \
   -ldum -lresip -lrutil -lssl -lcrypto -ldl \
   -Wl,--no-as-needed -lpython3.10 -Wl,--as-needed \
   -o "$OUTPUT" >"$BUILD_LOG" 2>&1; then
   BUILD_STATUS=0
else
   BUILD_STATUS=$?
fi
printf 'BUILD_EXIT_CODE=%s\n' "$BUILD_STATUS"
printf 'BUILD_LOG=%s\n' "$BUILD_LOG"
if [[ "$BUILD_STATUS" -ne 0 ]]; then
   tail -n 80 "$BUILD_LOG"
   exit "$BUILD_STATUS"
fi