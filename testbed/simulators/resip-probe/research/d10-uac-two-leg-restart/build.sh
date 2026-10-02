#!/usr/bin/env bash
set -u -o pipefail

ROOT=/tmp/as-resip-two-leg-restart-recovery
SOURCE=/tmp/as-resiprocate-userbuild/resiprocate-1.14.0
BUILD=/tmp/as-resiprocate-userbuild/upstream-minimal-20260930
PYTHON_INCLUDE=/home/shudong/.local/share/uv/python/cpython-3.10-linux-x86_64-gnu/include/python3.10
PYTHON_LIBDIR=/home/shudong/.local/share/uv/python/cpython-3.10.21-linux-x86_64-gnu/lib
OUTPUT="$ROOT/_as_resip_two_leg.cpython-310-x86_64-linux-gnu.so"
BUILD_LOG=${BUILD_LOG:-"$ROOT/native-build-final.log"}
LDD_LOG=${LDD_LOG:-"$ROOT/ldd-extension-final.log"}
DEPENDENCY_LOG="$(dirname "$LDD_LOG")/dependency-check.txt"
RPATH="$BUILD/resip/dum:$BUILD/resip/stack:$BUILD/rutil:$BUILD/rutil/dns/ares:$PYTHON_LIBDIR"

mkdir -p "$(dirname "$BUILD_LOG")" "$(dirname "$LDD_LOG")"

COMPILE=(
   /usr/bin/c++
   -std=c++17
   -O0
   -g
   -Wall
   -Wextra
   -fPIC
   -shared
   -pthread
   "-I$PYTHON_INCLUDE"
   "-I$BUILD"
   "-I$SOURCE"
   "-I$SOURCE/rutil/dns/ares"
   "$ROOT/two_leg_dum_module.cxx"
   "-L$BUILD/resip/dum"
   "-L$BUILD/resip/stack"
   "-L$BUILD/rutil"
   "-L$BUILD/rutil/dns/ares"
   "-L$PYTHON_LIBDIR"
   "-Wl,-rpath,$RPATH"
   -ldum-1.14
   -lresip-1.14
   -lrutil-1.14
   -lresipares-1.14
   -lssl
   -lcrypto
   -ldl
   -Wl,--no-as-needed
   -lpython3.10
   -Wl,--as-needed
   -o
   "$OUTPUT"
)

printf 'COMMAND[build]='
printf '%q ' "${COMPILE[@]}"
printf '\n'
if "${COMPILE[@]}" >"$BUILD_LOG" 2>&1; then
   BUILD_STATUS=0
else
   BUILD_STATUS=$?
fi
printf 'BUILD_EXIT_CODE=%s\nBUILD_LOG=%s\n' "$BUILD_STATUS" "$BUILD_LOG"
if [[ "$BUILD_STATUS" -ne 0 ]]; then
   tail -n 100 "$BUILD_LOG"
   exit "$BUILD_STATUS"
fi

printf 'COMMAND[ldd]=ldd %q\n' "$OUTPUT"
if ldd "$OUTPUT" >"$LDD_LOG" 2>&1; then
   LDD_STATUS=0
else
   LDD_STATUS=$?
fi
if [[ "$LDD_STATUS" -eq 0 ]] && grep -Fq 'not found' "$LDD_LOG"; then
   LDD_STATUS=1
fi

DEPENDENCY_STATUS=0
{
   for library in \
      libdum-1.14.so \
      libresip-1.14.so \
      librutil-1.14.so \
      libresipares-1.14.so \
      libpython3.10.so.1.0; do
      if grep -Fq "$library =>" "$LDD_LOG"; then
         printf 'PASS %s\n' "$library"
      else
         printf 'FAIL missing resolved dependency %s\n' "$library"
         DEPENDENCY_STATUS=1
      fi
   done
   if grep -Fq 'not found' "$LDD_LOG"; then
      printf 'FAIL ldd reports an unresolved dependency\n'
      DEPENDENCY_STATUS=1
   fi
   printf 'LDD_COMMAND_EXIT_CODE=%s\nDEPENDENCY_CHECK_EXIT_CODE=%s\n' \
      "$LDD_STATUS" "$DEPENDENCY_STATUS"
} >"$DEPENDENCY_LOG"

cat "$DEPENDENCY_LOG"
if [[ "$LDD_STATUS" -ne 0 || "$DEPENDENCY_STATUS" -ne 0 ]]; then
   exit 1
fi
exit 0