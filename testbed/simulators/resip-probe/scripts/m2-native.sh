#!/usr/bin/env bash
# Reproducible M2 P0: vendor restore, native reSIProcate build, resip_probe link, UDP S1 smoke.
# Uses checked-in archives under vendor/; no network git clone.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROBE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENDOR_DIR="${PROBE_ROOT}/vendor"
REPO_ROOT="$(cd "${PROBE_ROOT}/../../.." && pwd)"

AS_RESIP_CACHE_ROOT="${AS_RESIP_CACHE_ROOT:-${REPO_ROOT}/.cache/m2-resiprocate}"
AS_RESIP_HOME="${AS_RESIP_HOME:-${AS_RESIP_CACHE_ROOT}/source}"
AS_RESIP_BUILD="${AS_RESIP_BUILD:-${AS_RESIP_CACHE_ROOT}/build}"
AS_RESIP_PROBE_BUILD="${AS_RESIP_PROBE_BUILD:-${AS_RESIP_CACHE_ROOT}/probe-build}"
PLATFORM_RESIP_RUNTIME_BUILD="${AS_RESIP_RUNTIME_BUILD:-${REPO_ROOT}/platform/native/resip_runtime/build}"
PLATFORM_RESIP_TWO_LEG_BUILD="${AS_RESIP_TWO_LEG_BUILD:-${REPO_ROOT}/platform/native/resip_two_leg/build}"
PLATFORM_RESIP_RECOVERY_BUILD="${AS_RESIP_RECOVERY_BUILD:-${REPO_ROOT}/platform/native/resip_recovery/build}"

SOURCE_TARBALL="resiprocate-1.14.0-632e215c-source.tar.gz"
PREBUILT_TARBALL="resiprocate-m2-ubuntu20.04-x86_64-prebuilt-20261004.tar.gz"
PREBUILT_BUILD_DIRNAME="as-resiprocate-m2-build-20261004"
PREBUILT_PROBE_DIRNAME="as-resiprocate-m2-probe-build-20261004"

log() {
  echo "[m2-native] $*"
}

die() {
  echo "[m2-native] error: $*" >&2
  exit 1
}

usage() {
  cat <<EOF
Usage: $(basename "$0") <command>

Commands:
  restore       Verify vendor SHA256SUMS and extract source into AS_RESIP_HOME.
                If AS_RESIP_USE_PREBUILT=1, also extract the prebuilt build trees
                into AS_RESIP_BUILD / AS_RESIP_PROBE_BUILD (optional fast path).
  build-resip   CMake configure and build reSIProcate from AS_RESIP_HOME.
  build-probe   CMake build resip_probe against AS_RESIP_HOME / AS_RESIP_BUILD.
  build-platform-resip  CMake build platform _resip_runtime Python extension.
  build-platform-two-leg  CMake build platform _resip_two_leg Python extension (M7 slice).
  build-platform-recovery  CMake build platform _resip_recovery Python extension (M7 slice).
  smoke         Run ./resip_probe S1 (UDP) and assert success markers.
  smoke-tcp     Run ./resip_probe --tcp S1 (TCP loopback) and assert success markers.
  smoke-tcp-runtime  Run platform TCP resip_runtime integration pytest.
  smoke-tls-runtime  Run platform TLS resip_runtime integration tests (pytest).

Environment (defaults shown):
  AS_RESIP_CACHE_ROOT=${AS_RESIP_CACHE_ROOT}
  AS_RESIP_HOME=\$AS_RESIP_CACHE_ROOT/source
  AS_RESIP_BUILD=\$AS_RESIP_CACHE_ROOT/build
  AS_RESIP_PROBE_BUILD=\$AS_RESIP_CACHE_ROOT/probe-build
  AS_RESIP_USE_PREBUILT=0   set to 1 in restore to unpack prebuilt libraries

Repo root resolved as: ${REPO_ROOT}
EOF
}

require_cmake() {
  if ! command -v cmake &>/dev/null; then
    die "cmake not found (required >= 3.21). Install CMake or use a Kitware package."
  fi
  local ver
  ver="$(cmake --version | head -n1 | awk '{print $3}')"
  if ! printf '%s\n%s\n' "3.21" "${ver}" | sort -CV; then
    die "cmake ${ver} is older than 3.21 (probe CMakeLists requires >= 3.21)"
  fi
}

check_native_build_deps() {
  local missing=()
  if command -v pkg-config &>/dev/null; then
    pkg-config --exists popt 2>/dev/null || missing+=("libpopt-dev")
    pkg-config --exists libcares 2>/dev/null || missing+=("libc-ares-dev")
    if ! pkg-config --exists openssl 2>/dev/null; then
      missing+=("libssl-dev")
    fi
  else
    log "pkg-config not found; skipping dev-package probe (build may still fail)"
  fi
  if ((${#missing[@]} > 0)); then
    die "missing development packages (install via apt): ${missing[*]}"
  fi
  if ! command -v g++ &>/dev/null && ! command -v c++ &>/dev/null; then
    die "no C++ compiler found (install build-essential)"
  fi
}

cmd_restore() {
  if [[ ! -f "${VENDOR_DIR}/SHA256SUMS" ]]; then
    die "missing ${VENDOR_DIR}/SHA256SUMS"
  fi
  log "verifying vendor checksums in ${VENDOR_DIR}"
  (cd "${VENDOR_DIR}" && sha256sum -c SHA256SUMS)

  if [[ ! -f "${VENDOR_DIR}/${SOURCE_TARBALL}" ]]; then
    die "missing source archive ${VENDOR_DIR}/${SOURCE_TARBALL}"
  fi

  mkdir -p "${AS_RESIP_HOME}"
  if [[ -f "${AS_RESIP_HOME}/CMakeLists.txt" ]]; then
    log "source already present at ${AS_RESIP_HOME} (skipping extract)"
  else
    log "extracting ${SOURCE_TARBALL} -> ${AS_RESIP_HOME}"
    tar -xzf "${VENDOR_DIR}/${SOURCE_TARBALL}" --strip-components=1 -C "${AS_RESIP_HOME}"
  fi

  if [[ "${AS_RESIP_USE_PREBUILT:-0}" == "1" ]]; then
    if [[ ! -f "${VENDOR_DIR}/${PREBUILT_TARBALL}" ]]; then
      die "AS_RESIP_USE_PREBUILT=1 but ${PREBUILT_TARBALL} is missing"
    fi
    local staging="${AS_RESIP_CACHE_ROOT}/.prebuilt-staging"
    rm -rf "${staging}"
    mkdir -p "${staging}"
    log "extracting prebuilt archive (staging ${staging})"
    tar -xzf "${VENDOR_DIR}/${PREBUILT_TARBALL}" -C "${staging}"
    mkdir -p "${AS_RESIP_BUILD}" "${AS_RESIP_PROBE_BUILD}"
    rm -rf "${AS_RESIP_BUILD}" "${AS_RESIP_PROBE_BUILD}"
    mv "${staging}/${PREBUILT_BUILD_DIRNAME}" "${AS_RESIP_BUILD}"
    mv "${staging}/${PREBUILT_PROBE_DIRNAME}" "${AS_RESIP_PROBE_BUILD}"
    rmdir "${staging}" 2>/dev/null || rm -rf "${staging}"
    log "prebuilt trees installed under cache (probe may still need rebuild-resip for RPATH)"
  else
    log "AS_RESIP_USE_PREBUILT not set; source only (use build-resip to compile libraries)"
  fi
}

resip_libraries_built() {
  [[ -f "${AS_RESIP_BUILD}/rutil/librutil-1.14.so" ]] \
    || [[ -f "${AS_RESIP_BUILD}/rutil/librutil.so" ]]
}

cmd_build_resip() {
  require_cmake
  check_native_build_deps
  if [[ ! -f "${AS_RESIP_HOME}/CMakeLists.txt" ]]; then
    die "reSIProcate source not found at ${AS_RESIP_HOME}; run: $(basename "$0") restore"
  fi
  if resip_libraries_built; then
    log "reSIProcate libraries already present under ${AS_RESIP_BUILD} (skipping cmake build)"
    return 0
  fi
  mkdir -p "${AS_RESIP_BUILD}"
  log "cmake configure reSIProcate -> ${AS_RESIP_BUILD}"
  cmake -S "${AS_RESIP_HOME}" -B "${AS_RESIP_BUILD}" \
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
  log "cmake build reSIProcate (parallel)"
  cmake --build "${AS_RESIP_BUILD}" --parallel "$(nproc)"
  if ! resip_libraries_built; then
    die "reSIProcate build finished but expected shared libraries were not found under ${AS_RESIP_BUILD}/rutil"
  fi
  log "reSIProcate build OK: ${AS_RESIP_BUILD}"
}

cmd_build_probe() {
  require_cmake
  if ! resip_libraries_built; then
    die "reSIProcate libraries missing; run: $(basename "$0") build-resip"
  fi
  mkdir -p "${AS_RESIP_PROBE_BUILD}"
  local rpath="${AS_RESIP_BUILD}/rutil:${AS_RESIP_BUILD}/resip/stack:${AS_RESIP_BUILD}/resip/dum"
  log "cmake configure resip_probe -> ${AS_RESIP_PROBE_BUILD}"
  cmake -S "${PROBE_ROOT}" -B "${AS_RESIP_PROBE_BUILD}" \
    -DRESIP_HOME="${AS_RESIP_HOME}" \
    -DRESIP_BUILD="${AS_RESIP_BUILD}" \
    -DCMAKE_BUILD_RPATH="${rpath}" \
    -DCMAKE_INSTALL_RPATH="${rpath}"
  log "cmake build resip_probe"
  cmake --build "${AS_RESIP_PROBE_BUILD}" --parallel "$(nproc)"
  if [[ ! -x "${AS_RESIP_PROBE_BUILD}/resip_probe" ]]; then
    die "probe binary not found at ${AS_RESIP_PROBE_BUILD}/resip_probe"
  fi
  export AS_RESIP_PROBE_BIN="${AS_RESIP_PROBE_BUILD}/resip_probe"
  log "resip_probe OK: ${AS_RESIP_PROBE_BIN}"
  log "for tests: export AS_RESIP_PROBE_BIN=${AS_RESIP_PROBE_BIN}"
}

cmd_build_platform_resip() {
  if ! resip_libraries_built; then
    die "reSIProcate libraries missing; run: $(basename "$0") build-resip"
  fi
  mkdir -p "${PLATFORM_RESIP_RUNTIME_BUILD}"
  local rpath="${AS_RESIP_BUILD}/rutil:${AS_RESIP_BUILD}/resip/stack:${AS_RESIP_BUILD}/resip/dum"
  local python_bin="${REPO_ROOT}/.venv/bin/python3"
  if [[ ! -x "${python_bin}" ]]; then
    python_bin="$(command -v python3)"
  fi
  log "cmake configure platform resip_runtime -> ${PLATFORM_RESIP_RUNTIME_BUILD}"
  cmake -S "${REPO_ROOT}/platform/native/resip_runtime" -B "${PLATFORM_RESIP_RUNTIME_BUILD}" \
    -DRESIP_HOME="${AS_RESIP_HOME}" \
    -DRESIP_BUILD="${AS_RESIP_BUILD}" \
    -DPython3_EXECUTABLE="${python_bin}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_RPATH="${rpath}" \
    -DCMAKE_BUILD_RPATH="${rpath}"
  log "cmake build platform _resip_runtime"
  cmake --build "${PLATFORM_RESIP_RUNTIME_BUILD}" --parallel "$(nproc)"
  local suffix
  suffix="$("${python_bin}" -c 'import sysconfig; print(sysconfig.get_config_var("EXT_SUFFIX"))')"
  local module_path="${PLATFORM_RESIP_RUNTIME_BUILD}/_resip_runtime${suffix}"
  if [[ ! -f "${module_path}" ]]; then
    module_path="${PLATFORM_RESIP_RUNTIME_BUILD}/_resip_runtime.so"
  fi
  if [[ ! -f "${module_path}" ]]; then
    die "extension not found under ${PLATFORM_RESIP_RUNTIME_BUILD} (_resip_runtime${suffix} or _resip_runtime.so)"
  fi
  log "platform _resip_runtime OK: ${module_path}"
}

cmd_build_platform_recovery() {
  if ! resip_libraries_built; then
    die "reSIProcate libraries missing; run: $(basename "$0") build-resip"
  fi
  mkdir -p "${PLATFORM_RESIP_RECOVERY_BUILD}"
  local rpath="${AS_RESIP_BUILD}/rutil:${AS_RESIP_BUILD}/resip/stack:${AS_RESIP_BUILD}/resip/dum"
  local python_bin="${REPO_ROOT}/.venv/bin/python3"
  if [[ ! -x "${python_bin}" ]]; then
    python_bin="$(command -v python3)"
  fi
  log "cmake configure platform resip_recovery -> ${PLATFORM_RESIP_RECOVERY_BUILD}"
  cmake -S "${REPO_ROOT}/platform/native/resip_recovery" -B "${PLATFORM_RESIP_RECOVERY_BUILD}" \
    -DRESIP_HOME="${AS_RESIP_HOME}" \
    -DRESIP_BUILD="${AS_RESIP_BUILD}" \
    -DPython3_EXECUTABLE="${python_bin}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_RPATH="${rpath}" \
    -DCMAKE_BUILD_RPATH="${rpath}"
  log "cmake build platform _resip_recovery"
  cmake --build "${PLATFORM_RESIP_RECOVERY_BUILD}" --parallel "$(nproc)"
  local suffix
  suffix="$("${python_bin}" -c 'import sysconfig; print(sysconfig.get_config_var("EXT_SUFFIX"))')"
  local module_path="${PLATFORM_RESIP_RECOVERY_BUILD}/_resip_recovery${suffix}"
  if [[ ! -f "${module_path}" ]]; then
    module_path="${PLATFORM_RESIP_RECOVERY_BUILD}/_resip_recovery.so"
  fi
  if [[ ! -f "${module_path}" ]]; then
    die "extension not found under ${PLATFORM_RESIP_RECOVERY_BUILD}"
  fi
  log "platform _resip_recovery OK: ${module_path}"
}

cmd_build_platform_two_leg() {
  if ! resip_libraries_built; then
    die "reSIProcate libraries missing; run: $(basename "$0") build-resip"
  fi
  mkdir -p "${PLATFORM_RESIP_TWO_LEG_BUILD}"
  local rpath="${AS_RESIP_BUILD}/rutil:${AS_RESIP_BUILD}/resip/stack:${AS_RESIP_BUILD}/resip/dum"
  local python_bin="${REPO_ROOT}/.venv/bin/python3"
  if [[ ! -x "${python_bin}" ]]; then
    python_bin="$(command -v python3)"
  fi
  log "cmake configure platform resip_two_leg -> ${PLATFORM_RESIP_TWO_LEG_BUILD}"
  cmake -S "${REPO_ROOT}/platform/native/resip_two_leg" -B "${PLATFORM_RESIP_TWO_LEG_BUILD}" \
    -DRESIP_HOME="${AS_RESIP_HOME}" \
    -DRESIP_BUILD="${AS_RESIP_BUILD}" \
    -DPython3_EXECUTABLE="${python_bin}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_RPATH="${rpath}" \
    -DCMAKE_BUILD_RPATH="${rpath}"
  log "cmake build platform _resip_two_leg"
  cmake --build "${PLATFORM_RESIP_TWO_LEG_BUILD}" --parallel "$(nproc)"
  local suffix
  suffix="$("${python_bin}" -c 'import sysconfig; print(sysconfig.get_config_var("EXT_SUFFIX"))')"
  local module_path="${PLATFORM_RESIP_TWO_LEG_BUILD}/_resip_two_leg${suffix}"
  if [[ ! -f "${module_path}" ]]; then
    module_path="${PLATFORM_RESIP_TWO_LEG_BUILD}/_resip_two_leg.so"
  fi
  if [[ ! -f "${module_path}" ]]; then
    die "extension not found under ${PLATFORM_RESIP_TWO_LEG_BUILD}"
  fi
  log "platform _resip_two_leg OK: ${module_path}"
}

probe_success_marker() {
  local output="$1"
  if grep -qE 'probe 退出 OK|probe exit OK|=== probe.*OK ===' <<<"${output}"; then
    return 0
  fi
  return 1
}

run_smoke_s1() {
  local label="$1"
  shift
  local probe_bin="${AS_RESIP_PROBE_BIN:-${AS_RESIP_PROBE_BUILD}/resip_probe}"
  export AS_RESIP_PROBE_BIN="${probe_bin}"
  if [[ ! -x "${probe_bin}" ]]; then
    die "resip_probe not executable at ${probe_bin}; run: $(basename "$0") build-probe"
  fi
  log "smoke: ${probe_bin} $* (${label})"
  # resip_probe self-test runs until SIGINT/SIGTERM; stop after S1 BYE completes.
  local log_file
  log_file="$(mktemp)"
  "${probe_bin}" "$@" >"${log_file}" 2>&1 &
  local probe_pid=$!
  local deadline=$((SECONDS + 120))
  while kill -0 "${probe_pid}" 2>/dev/null; do
    if grep -q 'reason=RemoteBye' "${log_file}" 2>/dev/null; then
      kill -INT "${probe_pid}" 2>/dev/null || true
      break
    fi
    if ((SECONDS >= deadline)); then
      kill -INT "${probe_pid}" 2>/dev/null || true
      wait "${probe_pid}" 2>/dev/null || true
      cat "${log_file}"
      rm -f "${log_file}"
      die "smoke timed out waiting for S1 BYE completion (${label})"
    fi
    sleep 0.1
  done
  local status=0
  wait "${probe_pid}" || status=$?
  local output
  output="$(cat "${log_file}")"
  rm -f "${log_file}"
  if [[ ${status} -ne 0 ]]; then
    echo "${output}"
    die "resip_probe S1 exited ${status} (${label})"
  fi
  if ! probe_success_marker "${output}"; then
    echo "${output}"
    die "resip_probe S1 ran but success marker not found in output (${label})"
  fi
  echo "${output}"
  log "smoke passed (${label})"
}

cmd_smoke() {
  run_smoke_s1 "S1 UDP" S1
}

cmd_smoke_tcp() {
  run_smoke_s1 "S1 TCP" --tcp S1
}

cmd_smoke_tcp_runtime() {
  local python_bin="${REPO_ROOT}/.venv/bin/python"
  if [[ ! -x "${python_bin}" ]]; then
    python_bin="$(command -v python3)"
  fi
  if ! resip_libraries_built; then
    die "reSIProcate libraries missing; run: $(basename "$0") build-resip"
  fi
  cmd_build_platform_resip
  log "smoke: platform TCP resip_runtime integration (pytest)"
  (cd "${REPO_ROOT}" && "${python_bin}" -m pytest \
    platform/tests/test_resip_runtime_tcp_integration.py -m integration -q)
  log "smoke passed (TCP resip_runtime integration)"
}

cmd_smoke_tls_runtime() {
  local python_bin="${REPO_ROOT}/.venv/bin/python"
  if [[ ! -x "${python_bin}" ]]; then
    python_bin="$(command -v python3)"
  fi
  if ! resip_libraries_built; then
    die "reSIProcate libraries missing; run: $(basename "$0") build-resip"
  fi
  cmd_build_platform_resip
  log "smoke: platform TLS resip_runtime integration (pytest)"
  (cd "${REPO_ROOT}" && "${python_bin}" -m pytest \
    platform/tests/test_resip_runtime_tls_integration.py -m integration -q)
  log "smoke passed (TLS resip_runtime integration)"
}

main() {
  local cmd="${1:-}"
  case "${cmd}" in
    restore) cmd_restore ;;
    build-resip) cmd_build_resip ;;
    build-probe) cmd_build_probe ;;
    build-platform-resip) cmd_build_platform_resip ;;
    build-platform-two-leg) cmd_build_platform_two_leg ;;
    build-platform-recovery) cmd_build_platform_recovery ;;
    smoke) cmd_smoke ;;
    smoke-tcp) cmd_smoke_tcp ;;
    smoke-tcp-runtime) cmd_smoke_tcp_runtime ;;
    smoke-tls-runtime) cmd_smoke_tls_runtime ;;
    -h | --help | help | "") usage ;;
    *)
      die "unknown command: ${cmd} (try --help)"
      ;;
  esac
}

main "$@"
