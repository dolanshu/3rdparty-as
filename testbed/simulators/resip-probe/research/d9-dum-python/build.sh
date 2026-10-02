#!/bin/sh
set -eu

ROOT=/tmp/as-resip-dum-python-slice
UPSTREAM_SRC=/tmp/as-resiprocate-userbuild/resiprocate-1.14.0
UPSTREAM_BUILD=/tmp/as-resiprocate-userbuild/upstream-minimal-20260930
PYTHON=/home/shudong/project/3rdparty-as/.venv/bin/python
CXX=/usr/bin/c++

PYTHON_INCLUDE=$($PYTHON -c 'import sysconfig; print(sysconfig.get_path("include"))')
PYTHON_LIBDIR=$($PYTHON -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR"))')
PYTHON_LIBRARY=$($PYTHON -c 'import sysconfig; library = sysconfig.get_config_var("LDLIBRARY"); print(library[3:].split(".so", 1)[0])')
PYTHON_SUFFIX=$($PYTHON -c 'import sysconfig; print(sysconfig.get_config_var("EXT_SUFFIX"))')

mkdir -p "$ROOT/build"
OUTPUT="$ROOT/build/_resip_dum$PYTHON_SUFFIX"
RPATH="$UPSTREAM_BUILD/resip/dum:$UPSTREAM_BUILD/resip/stack:$UPSTREAM_BUILD/rutil:$UPSTREAM_BUILD/rutil/dns/ares:$PYTHON_LIBDIR"

printf 'Python: '
"$PYTHON" --version
printf 'Python include: %s\nPython libdir: %s\nPython library: %s\n' \
   "$PYTHON_INCLUDE" "$PYTHON_LIBDIR" "$PYTHON_LIBRARY"
printf 'Output: %s\n' "$OUTPUT"

"$CXX" -O2 -g -std=c++17 -fPIC -pthread -shared \
   -I"$PYTHON_INCLUDE" \
   -I"$UPSTREAM_BUILD" \
   -I"$UPSTREAM_SRC" \
   -I"$UPSTREAM_SRC/rutil/dns/ares" \
   "$ROOT/dum_module.cxx" \
   -L"$UPSTREAM_BUILD/resip/dum" \
   -L"$UPSTREAM_BUILD/resip/stack" \
   -L"$UPSTREAM_BUILD/rutil" \
   -L"$UPSTREAM_BUILD/rutil/dns/ares" \
   -L"$PYTHON_LIBDIR" \
   -Wl,-rpath,"$RPATH" \
   -ldum -lresip -lrutil -lssl -lcrypto -ldl \
   -Wl,--no-as-needed -l"$PYTHON_LIBRARY" -Wl,--as-needed \
   -o "$OUTPUT"

printf 'Built: %s\n' "$OUTPUT"