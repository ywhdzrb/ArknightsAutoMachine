# cmake - CMake 工具模块

## 目录说明

本目录包含 CMake 构建系统的工具模块和配置文件。

## 文件说明

### FindZeroMQ.cmake
查找 ZeroMQ 库的 CMake 模块:

```cmake
find_package(ZeroMQ REQUIRED)
target_link_libraries(target ZeroMQ::ZeroMQ)
```

### FindCUDA.cmake
CUDA 工具包查找模块:

```cmake
find_package(CUDA REQUIRED)
enable_language(CUDA)
```

### utils.cmake
通用 CMake 函数:

```cmake
# 添加测试
aam_add_test(test_name SOURCES ...)

# 添加库
aam_add_library(lib_name TYPE SHARED SOURCES ...)

# 设置编译选项
aam_set_compile_options(target)
```

### compiler_flags.cmake
跨平台编译选项:

```cmake
# MSVC
add_compile_options(/W4 /WX /permissive-)

# GCC/Clang
add_compile_options(-Wall -Wextra -Wpedantic -Werror)
```

## 使用方式

### 根 CMakeLists.txt

```cmake
cmake_minimum_required(VERSION 3.25)
project(AAMCore CXX)

# 添加工具模块路径
list(APPEND CMAKE_MODULE_PATH ${CMAKE_SOURCE_DIR}/cmake)

# 包含通用配置
include(compiler_flags)
include(utils)

# 查找依赖
find_package(ZeroMQ REQUIRED)
```

## 编译选项

### 调试构建
```cmake
set(CMAKE_BUILD_TYPE Debug)
add_compile_options(-O0 -g3)
```

### 发布构建
```cmake
set(CMAKE_BUILD_TYPE Release)
add_compile_options(-O3 -DNDEBUG)
add_link_options(-flto)
```

### 带调试信息的发布
```cmake
set(CMAKE_BUILD_TYPE RelWithDebInfo)
add_compile_options(-O2 -g)
```

## 预设配置

### CMakePresets.json

```json
{
  "version": 3,
  "configurePresets": [
    {
      "name": "windows-cl-x64",
      "generator": "Visual Studio 17 2022",
      "architecture": "x64",
      "toolset": "v143"
    },
    {
      "name": "linux-gcc-x64",
      "generator": "Ninja",
      "cacheVariables": {
        "CMAKE_C_COMPILER": "gcc",
        "CMAKE_CXX_COMPILER": "g++"
      }
    }
  ]
}
```

## 相关目录

- [core/CMakeLists.txt](../core/CMakeLists.txt): 核心模块构建配置
- [gui/qt/CMakeLists.txt](../gui/qt/CMakeLists.txt): Qt GUI 构建配置
