# scripts - 运维脚本

## 目录说明

本目录包含 AAM 项目的运维脚本，用于代码生成、环境设置和数据库迁移。

## 目录结构

```
scripts/
├── codegen/               # 代码生成脚本
├── setup/                 # 环境设置脚本
└── db_migrate/            # 数据库迁移脚本
```

## codegen

### protobuf_gen.py

生成 Protobuf 代码:

```bash
# 生成所有代码
python scripts/codegen/protobuf_gen.py

# 生成特定语言
python scripts/codegen/protobuf_gen.py --lang=cpp
python scripts/codegen/protobuf_gen.py --lang=python

# 生成并格式化
python scripts/codegen/protobuf_gen.py --format
```

### version_bump.py

版本号管理:

```bash
# 查看当前版本
python scripts/codegen/version_bump.py --show

# 升级补丁版本
python scripts/codegen/version_bump.py --bump=patch

# 升级次要版本
python scripts/codegen/version_bump.py --bump=minor

# 升级主要版本
python scripts/codegen/version_bump.py --bump=major
```

## setup

### install_deps_windows.ps1

Windows 依赖安装:

```powershell
# 以管理员身份运行
.\scripts\setup\install_deps_windows.ps1

# 安装内容:
# - Visual Studio 2022 Build Tools
# - CMake
# - vcpkg
# - Python 3.11
# - Poetry
```

### setup_vcpkg.sh

Linux/macOS vcpkg 设置:

```bash
# 安装 vcpkg 和依赖
./scripts/setup/setup_vcpkg.sh

# 仅安装依赖
./scripts/setup/setup_vcpkg.sh --deps-only
```

## db_migrate

### fetch_prts_data.py

从 PRTS 拉取数据:

```bash
# 拉取所有关卡数据
python scripts/db_migrate/fetch_prts_data.py --all

# 拉取特定关卡
python scripts/db_migrate/fetch_prts_data.py --level=1-7

# 增量更新
python scripts/db_migrate/fetch_prts_data.py --incremental
```

## 使用示例

### 完整环境设置

```powershell
# Windows
.\scripts\setup\install_deps_windows.ps1
.\scripts\codegen\protobuf_gen.py
.\scripts\db_migrate\fetch_prts_data.py --all

# 构建项目
cmake --preset=windows-cl-x64
cmake --build --preset=windows-cl-x64-release
```

```bash
# Linux/macOS
./scripts/setup/setup_vcpkg.sh
python scripts/codegen/protobuf_gen.py
python scripts/db_migrate/fetch_prts_data.py --all

# 构建项目
cmake --preset=linux-gcc-x64
cmake --build --preset=linux-gcc-x64-release
```

## 相关目录

- [tools/](../tools/): 开发工具
- [third_party/](../third_party/): 外部依赖
