# resip_probe: 最小化 reSIProcate SIP 服务器验证探针
cmake_minimum_required(VERSION 3.21)
project(resip_probe CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_BUILD_TYPE Release)

# Point at a built reSIProcate tree. Prefer passing -DRESIP_HOME / -DRESIP_BUILD from
# scripts/m2-native.sh; when unset, honor AS_RESIP_* environment variables.
if(DEFINED ENV{AS_RESIP_HOME})
  set(_resip_home_default "$ENV{AS_RESIP_HOME}")
elseif(DEFINED ENV{AS_RESIP_CACHE_ROOT})
  set(_resip_home_default "$ENV{AS_RESIP_CACHE_ROOT}/source")
else()
  set(_resip_home_default "")
endif()

if(DEFINED ENV{AS_RESIP_BUILD})
  set(_resip_build_default "$ENV{AS_RESIP_BUILD}")
elseif(DEFINED ENV{AS_RESIP_CACHE_ROOT})
  set(_resip_build_default "$ENV{AS_RESIP_CACHE_ROOT}/build")
else()
  set(_resip_build_default "")
endif()

set(RESIP_HOME "${_resip_home_default}" CACHE PATH "reSIProcate source root (required)")
set(RESIP_BUILD "${_resip_build_default}" CACHE PATH "reSIProcate out-of-tree build dir (required)")

if(NOT RESIP_HOME OR NOT RESIP_BUILD)
  message(FATAL_ERROR
    "RESIP_HOME and RESIP_BUILD must be set (cmake -D or AS_RESIP_HOME / AS_RESIP_BUILD). "
    "Use testbed/simulators/resip-probe/scripts/m2-native.sh build-probe.")
endif()

add_executable(resip_probe resip_probe.cxx)

target_include_directories(resip_probe PRIVATE
    ${RESIP_HOME}            # resip/stack/SipStack.hxx, resip/dum/*
    ${RESIP_HOME}/rutil      # rutil/Log.hxx 等
    ${RESIP_BUILD}           # 生成的 version.h / config.h
)

# 库在子目录里
target_link_directories(resip_probe PRIVATE
    ${RESIP_BUILD}/rutil
    ${RESIP_BUILD}/resip/stack
    ${RESIP_BUILD}/resip/dum
)

target_link_libraries(resip_probe PRIVATE
    dum
    resip
    rutil
    ssl
    crypto
    pthread
    dl
)

# Run from the probe build dir without /tmp handoff RUNPATH (m2-native.sh sets cache paths).
set(_resip_probe_rpath
    "${RESIP_BUILD}/rutil"
    "${RESIP_BUILD}/resip/stack"
    "${RESIP_BUILD}/resip/dum"
)
set_target_properties(resip_probe PROPERTIES
    BUILD_RPATH "${_resip_probe_rpath}"
    INSTALL_RPATH "${_resip_probe_rpath}"
)
