#!/usr/bin/env bash
# Auto-build reSIProcate for resip-probe.
# Usage: ./build-req.sh
# Output: /tmp/resiprocate/_build/ (same as CMakeLists.txt expects)

set -euo pipefail

RESIP_VERSION="resiprocate-1.14.0"
RESIP_HOME="${RESIP_HOME:-/tmp/resiprocate}"
RESIP_BUILD="${RESIP_BUILD:-${RESIP_HOME}/_build}"

# Dev dependencies (popping up on systems without apt sudo: build from source)
# If apt-get is available with sudo, use it. Otherwise try apt-get without sudo (works in some CI).
have_cmd() { command -v "$1" &>/dev/null; }

if have_cmd apt-get; then
  echo "[build-req] Checking system deps..."
  DEBS=(libpopt-dev libc-ares-dev)
  for deb in "${DEBS[@]}"; do
    if ! dpkg -l "$deb" &>/dev/null 2>&1; then
      echo "[build-req] Installing $deb..."
      if have_cmd sudo; then
        sudo apt-get install -y "$deb"
      else
        apt-get install -y "$deb"
      fi
    fi
  done
fi

# Clone if not present
if [ ! -d "$RESIP_HOME/.git" ]; then
  echo "[build-req] Cloning reSIProcate $RESIP_VERSION..."
  git clone --branch "$RESIP_VERSION" --depth 1 https://github.com/resiprocate/resiprocate.git "$RESIP_HOME"
else
  echo "[build-req] reSIProcate already at $RESIP_HOME"
fi

# Build if not present
if [ ! -f "${RESIP_BUILD}/librutil.a" ] && [ ! -f "${RESIP_BUILD}/librutil-1.14.so" ]; then
  echo "[build-req] Configuring..."
  cd "$RESIP_HOME"
  rm -rf _build && mkdir _build && cd _build
  PKG_CONFIG_PATH="${RESIP_HOME}/contrib/popt/build:${PKG_CONFIG_PATH:-}" \
  cmake .. \
    -DCMAKE_BUILD_TYPE=Release \
    -DUSE_CONTRIB=OFF \
    -DBUILD_PYTHON=OFF \
    -DUSE_MAXMIND_GEOIP=OFF \
    -DBUILD_TFM=OFF \
    -DBUILD_REPRO=OFF \
    -DBUILD_RETURN=OFF \
    -DBUILD_RECON=OFF \
    -DBUILD_REND=OFF \
    -DBUILD_MEDIA=OFF \
    -DBUILD_REFLOW=OFF \
    -DBUILD_TESTING=OFF \
    -DRESIP_HAVE_RADCLI=OFF \
    -DUSE_NETSNMP=OFF \
    -DUSE_GSTREAMER=OFF \
    -DBUILD_QPID_PROTON=OFF
  echo "[build-req] Building..."
  make -j$(nproc)
else
  echo "[build-req] reSIProcate already built at $RESIP_BUILD"
fi

echo "[build-req] Done. Probe CMakeLists.txt can use -DRESIP_HOME=$RESIP_HOME -DRESIP_BUILD=$RESIP_BUILD"
