# M7 product-path RecoveryTU extension (D10 engineering slice).
cmake_minimum_required(VERSION 3.21)
project(as_platform_resip_recovery CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

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
    "RESIP_HOME and RESIP_BUILD must be set. Use: make m7-platform-recovery-build")
endif()

find_package(Python3 REQUIRED COMPONENTS Interpreter Development.Module)

python3_add_library(_resip_recovery MODULE WITH_SOABI recovery_module.cxx)

target_include_directories(_resip_recovery PRIVATE
  ${RESIP_HOME}
  ${RESIP_HOME}/rutil
  ${RESIP_BUILD}
  ${Python3_INCLUDE_DIRS}
)

target_link_directories(_resip_recovery PRIVATE
  ${RESIP_BUILD}/rutil
  ${RESIP_BUILD}/resip/stack
  ${RESIP_BUILD}/resip/dum
)

target_link_libraries(_resip_recovery PRIVATE
  Python3::Module
  dum
  resip
  rutil
  ssl
  crypto
  pthread
  dl
)

set(_resip_recovery_rpath
  "${RESIP_BUILD}/rutil"
  "${RESIP_BUILD}/resip/stack"
  "${RESIP_BUILD}/resip/dum"
)

set_target_properties(_resip_recovery PROPERTIES
  PREFIX ""
  OUTPUT_NAME "_resip_recovery"
  BUILD_RPATH "${_resip_recovery_rpath}"
  INSTALL_RPATH "${_resip_recovery_rpath}"
)
