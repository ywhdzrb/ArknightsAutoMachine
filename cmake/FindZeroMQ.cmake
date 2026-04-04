# =============================================================================
# FindZeroMQ.cmake - ZeroMQ Library Discovery Module
# =============================================================================
# 版本: v0.1.0-alpha.2
# 功能: 跨平台 ZeroMQ 库查找模块
# 输出变量:
#   ZeroMQ_FOUND          - 是否找到 ZeroMQ
#   ZeroMQ_INCLUDE_DIRS   - 头文件路径
#   ZeroMQ_LIBRARIES      - 库文件路径
#   ZeroMQ_VERSION        - 版本号
# 目标:
#   libzmq-static         - 静态库目标
#   cppzmq-static         - C++ 封装静态库目标
# =============================================================================

include(FindPackageHandleStandardArgs)

# =============================================================================
# 版本配置
# =============================================================================
set(ZeroMQ_MINIMUM_VERSION "4.3.4")

# =============================================================================
# 查找路径配置
# =============================================================================
# vcpkg 路径
if(DEFINED ENV{VCPKG_ROOT})
    list(APPEND ZeroMQ_SEARCH_PATHS
        "$ENV{VCPKG_ROOT}/installed/x64-windows"
        "$ENV{VCPKG_ROOT}/installed/x64-windows-static"
        "$ENV{VCPKG_ROOT}/installed/x64-linux"
        "$ENV{VCPKG_ROOT}/installed/x64-osx"
        "$ENV{VCPKG_ROOT}/installed/arm64-osx"
    )
endif()

# 系统默认路径
list(APPEND ZeroMQ_SEARCH_PATHS
    "${CMAKE_PREFIX_PATH}"
    "${CMAKE_INSTALL_PREFIX}"
    "/usr/local"
    "/usr"
    "/opt/local"
    "/opt"
)

# Windows 特定路径
if(WIN32)
    list(APPEND ZeroMQ_SEARCH_PATHS
        "C:/Program Files/ZeroMQ"
        "C:/Program Files (x86)/ZeroMQ"
        "C:/vcpkg/installed/x64-windows"
        "C:/vcpkg/installed/x64-windows-static"
        "${CMAKE_CURRENT_SOURCE_DIR}/third_party/zeromq"
    )
endif()

# =============================================================================
# 查找头文件
# =============================================================================
find_path(ZeroMQ_INCLUDE_DIR
    NAMES zmq.h
    PATHS ${ZeroMQ_SEARCH_PATHS}
    PATH_SUFFIXES
        include
        zeromq/include
        zmq/include
    DOC "ZeroMQ header file path"
)

# =============================================================================
# 查找库文件
# =============================================================================
if(WIN32)
    # Windows: 查找 .lib 文件
    find_library(ZeroMQ_LIBRARY_RELEASE
        NAMES libzmq-mt-s-4_3_4 libzmq-mt-4_3_4 libzmq libzmq-static zmq
        PATHS ${ZeroMQ_SEARCH_PATHS}
        PATH_SUFFIXES
            lib
            lib/x64
            zeromq/lib
        DOC "ZeroMQ release library"
    )
    
    find_library(ZeroMQ_LIBRARY_DEBUG
        NAMES libzmq-mt-sgd-4_3_4 libzmq-mt-gd-4_3_4 libzmqd libzmq-staticd zmqd
        PATHS ${ZeroMQ_SEARCH_PATHS}
        PATH_SUFFIXES
            lib
            lib/x64
            zeromq/lib
        DOC "ZeroMQ debug library"
    )
    
    # 选择库
    if(ZeroMQ_LIBRARY_RELEASE AND ZeroMQ_LIBRARY_DEBUG)
        set(ZeroMQ_LIBRARY
            optimized ${ZeroMQ_LIBRARY_RELEASE}
            debug ${ZeroMQ_LIBRARY_DEBUG}
        )
    elseif(ZeroMQ_LIBRARY_RELEASE)
        set(ZeroMQ_LIBRARY ${ZeroMQ_LIBRARY_RELEASE})
    elseif(ZeroMQ_LIBRARY_DEBUG)
        set(ZeroMQ_LIBRARY ${ZeroMQ_LIBRARY_DEBUG})
    endif()
else()
    # Linux/macOS: 查找 .a 或 .so
    find_library(ZeroMQ_LIBRARY
        NAMES zmq libzmq.a libzmq.so
        PATHS ${ZeroMQ_SEARCH_PATHS}
        PATH_SUFFIXES
            lib
            lib/x86_64-linux-gnu
            lib/aarch64-linux-gnu
        DOC "ZeroMQ library"
    )
endif()

# =============================================================================
# 查找 C++ 封装库 (cppzmq)
# =============================================================================
find_path(CPPZMQ_INCLUDE_DIR
    NAMES zmq.hpp
    PATHS ${ZeroMQ_SEARCH_PATHS}
    PATH_SUFFIXES
        include
        cppzmq/include
    DOC "cppzmq header file path"
)

# =============================================================================
# 提取版本信息
# =============================================================================
if(ZeroMQ_INCLUDE_DIR AND EXISTS "${ZeroMQ_INCLUDE_DIR}/zmq.h")
    file(STRINGS "${ZeroMQ_INCLUDE_DIR}/zmq.h" ZMQ_VERSION_MAJOR_LINE
        REGEX "^#define ZMQ_VERSION_MAJOR [0-9]+$")
    file(STRINGS "${ZeroMQ_INCLUDE_DIR}/zmq.h" ZMQ_VERSION_MINOR_LINE
        REGEX "^#define ZMQ_VERSION_MINOR [0-9]+$")
    file(STRINGS "${ZeroMQ_INCLUDE_DIR}/zmq.h" ZMQ_VERSION_PATCH_LINE
        REGEX "^#define ZMQ_VERSION_PATCH [0-9]+$")
    
    string(REGEX REPLACE "^#define ZMQ_VERSION_MAJOR ([0-9]+)$" "\\1"
        ZMQ_VERSION_MAJOR "${ZMQ_VERSION_MAJOR_LINE}")
    string(REGEX REPLACE "^#define ZMQ_VERSION_MINOR ([0-9]+)$" "\\1"
        ZMQ_VERSION_MINOR "${ZMQ_VERSION_MINOR_LINE}")
    string(REGEX REPLACE "^#define ZMQ_VERSION_PATCH ([0-9]+)$" "\\1"
        ZMQ_VERSION_PATCH "${ZMQ_VERSION_PATCH_LINE}")
    
    set(ZeroMQ_VERSION "${ZMQ_VERSION_MAJOR}.${ZMQ_VERSION_MINOR}.${ZMQ_VERSION_PATCH}")
else()
    set(ZeroMQ_VERSION "0.0.0")
endif()

# =============================================================================
# 标准查找处理
# =============================================================================
find_package_handle_standard_args(ZeroMQ
    REQUIRED_VARS
        ZeroMQ_LIBRARY
        ZeroMQ_INCLUDE_DIR
    VERSION_VAR ZeroMQ_VERSION
    HANDLE_VERSION_RANGE
)

# =============================================================================
# 创建导入目标
# =============================================================================
if(ZeroMQ_FOUND AND NOT TARGET libzmq-static)
    add_library(libzmq-static STATIC IMPORTED GLOBAL)
    
    set_target_properties(libzmq-static PROPERTIES
        IMPORTED_LOCATION "${ZeroMQ_LIBRARY}"
        INTERFACE_INCLUDE_DIRECTORIES "${ZeroMQ_INCLUDE_DIR}"
        INTERFACE_COMPILE_DEFINITIONS "ZMQ_STATIC"
    )
    
    # Windows 特定链接依赖
    if(WIN32)
        set_property(TARGET libzmq-static APPEND PROPERTY
            INTERFACE_LINK_LIBRARIES
                ws2_32
                iphlpapi
                rpcrt4
        )
    else()
        # Linux/macOS 可能需要 pthread
        find_package(Threads REQUIRED)
        set_property(TARGET libzmq-static APPEND PROPERTY
            INTERFACE_LINK_LIBRARIES
                Threads::Threads
        )
    endif()
    
    # 区分 Debug/Release
    if(WIN32 AND ZeroMQ_LIBRARY_RELEASE AND ZeroMQ_LIBRARY_DEBUG)
        set_target_properties(libzmq-static PROPERTIES
            IMPORTED_LOCATION_RELEASE "${ZeroMQ_LIBRARY_RELEASE}"
            IMPORTED_LOCATION_DEBUG "${ZeroMQ_LIBRARY_DEBUG}"
        )
    endif()
endif()

# cppzmq 目标
if(CPPZMQ_INCLUDE_DIR AND NOT TARGET cppzmq-static)
    add_library(cppzmq-static INTERFACE IMPORTED GLOBAL)
    set_target_properties(cppzmq-static PROPERTIES
        INTERFACE_INCLUDE_DIRECTORIES "${CPPZMQ_INCLUDE_DIR}"
        INTERFACE_LINK_LIBRARIES libzmq-static
    )
endif()

# =============================================================================
# 设置输出变量
# =============================================================================
if(ZeroMQ_FOUND)
    set(ZeroMQ_INCLUDE_DIRS ${ZeroMQ_INCLUDE_DIR})
    if(CPPZMQ_INCLUDE_DIR)
        list(APPEND ZeroMQ_INCLUDE_DIRS ${CPPZMQ_INCLUDE_DIR})
    endif()
    list(REMOVE_DUPLICATES ZeroMQ_INCLUDE_DIRS)
    
    set(ZeroMQ_LIBRARIES ${ZeroMQ_LIBRARY})
endif()

# =============================================================================
# 标记高级变量
# =============================================================================
mark_as_advanced(
    ZeroMQ_INCLUDE_DIR
    ZeroMQ_LIBRARY
    ZeroMQ_LIBRARY_RELEASE
    ZeroMQ_LIBRARY_DEBUG
    CPPZMQ_INCLUDE_DIR
)

# =============================================================================
# 诊断输出
# =============================================================================
if(ZeroMQ_FOUND AND NOT ZeroMQ_FIND_QUIETLY)
    message(STATUS "ZeroMQ found:")
    message(STATUS "  Version: ${ZeroMQ_VERSION}")
    message(STATUS "  Includes: ${ZeroMQ_INCLUDE_DIRS}")
    message(STATUS "  Libraries: ${ZeroMQ_LIBRARIES}")
    if(CPPZMQ_INCLUDE_DIR)
        message(STATUS "  cppzmq: Found at ${CPPZMQ_INCLUDE_DIR}")
    else()
        message(WARNING "  cppzmq: Not found (header-only C++ binding)")
    endif()
endif()
