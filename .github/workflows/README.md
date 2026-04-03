# GitHub Actions Workflows

## 工作流说明

本目录包含所有 CI/CD 自动化工作流配置。

## 工作流文件

### ci.yml
**用途**: 持续集成主工作流
**触发条件**: 
- Push 到 main/develop 分支
- Pull Request 创建/更新

**构建矩阵**:
| OS | 编译器 | 构建类型 | GUI |
|---|---|---|---|
| windows-2022 | MSVC 17.8 | Debug/Release/RelWithDebInfo | Qt/WPF |
| ubuntu-22.04 | GCC 13 | Debug/Release | Qt |
| macos-14 | Clang 17 | Debug/Release | Qt |

**执行步骤**:
1. 检出代码（含子模块）
2. 安装依赖（vcpkg、Poetry）
3. CMake 配置与构建
4. 运行 C++ 单元测试（GTest）
5. 运行 Python 测试（Pytest）
6. 代码覆盖率上报
7. 静态分析（Clang-Tidy）

### release.yml
**用途**: 自动化发版
**触发条件**: 标签推送（v*）

**制品输出**:
- Windows: MSI 安装包（WPF）、AppImage（Qt）
- Linux: AppImage、DEB 包
- macOS: DMG、Homebrew Formula
- Docker: 多架构镜像（amd64/arm64）

### codeql.yml
**用途**: 安全扫描
**扫描范围**:
- C++ 代码（缓冲区溢出、内存泄漏）
- Python 代码（注入漏洞、不安全反序列化）
- 依赖项漏洞（Dependabot）

## 环境变量

```yaml
VCPKG_BINARY_SOURCES: "clear;x-gha,readwrite"
POETRY_VIRTUALENVS_IN_PROJECT: "true"
CMAKE_BUILD_PARALLEL_LEVEL: "4"
```

## 维护指南

- 修改工作流后需在 PR 中验证
- 定期检查 Actions 运行时长，优化缓存策略
- 每月审查安全扫描结果
