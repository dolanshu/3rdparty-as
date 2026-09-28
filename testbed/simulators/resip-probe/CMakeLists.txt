# resip_probe: 最小化 reSIProcate SIP 服务器验证探针
cmake_minimum_required(VERSION 3.21)
project(resip_probe CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_BUILD_TYPE Release)

# 指向本机已构建的 reSIProcate（Makefile/CMake 混合构建）
set(RESIP_HOME "/tmp/resiprocate" CACHE PATH "reSIProcate 源码根目录")
set(RESIP_BUILD "/tmp/resiprocate/_build" CACHE PATH "reSIProcate 构建目录")

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
