# M7 minimal product-path two-leg reSIProcate DUM extension (486 mapping slice).
cmake_minimum_required(VERSION 3.21)
project(as_platform_resip_two_leg CXX)

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
    "RESIP_HOME and RESIP_BUILD must be set. Use: make m7-platform-two-leg-build")
endif()

find_package(Python3 REQUIRED COMPONENTS Interpreter Development.Module)

python3_add_library(_resip_two_leg MODULE WITH_SOABI two_leg_module.cxx)

target_include_directories(_resip_two_leg PRIVATE
  ${RESIP_HOME}
  ${RESIP_HOME}/rutil
  ${RESIP_BUILD}
  ${Python3_INCLUDE_DIRS}
)

target_link_directories(_resip_two_leg PRIVATE
  ${RESIP_BUILD}/rutil
  ${RESIP_BUILD}/resip/stack
  ${RESIP_BUILD}/resip/dum
)

target_link_libraries(_resip_two_leg PRIVATE
  Python3::Module
  dum
  resip
  rutil
  ssl
  crypto
  pthread
  dl
)

set(_resip_two_leg_rpath
  "${RESIP_BUILD}/rutil"
  "${RESIP_BUILD}/resip/stack"
  "${RESIP_BUILD}/resip/dum"
)

set_target_properties(_resip_two_leg PROPERTIES
  PREFIX ""
  OUTPUT_NAME "_resip_two_leg"
  BUILD_RPATH "${_resip_two_leg_rpath}"
  INSTALL_RPATH "${_resip_two_leg_rpath}"
)
