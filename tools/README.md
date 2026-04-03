# tools - 开发工具链

## 目录说明

本目录包含 AAM 项目的开发工具，用于代码生成、数据迁移和性能测试。

## 目录结构

```
tools/
├── protobuf_codegen/       # Protobuf 代码生成
├── db_migration/          # 数据库迁移
└── benchmark/             # 性能测试套件
```

## protobuf_codegen

### 功能
从 proto 文件生成 C++ 和 Python 代码:

```bash
# 生成所有代码
python tools/protobuf_codegen/generate.py

# 生成特定模块
python tools/protobuf_codegen/generate.py --module=ama

# 生成并格式化
python tools/protobuf_codegen/generate.py --format
```

### 生成内容
- C++ headers/impl (`grpc_cpp_plugin`)
- Python stubs (`grpc_python_plugin` + `mypy_protobuf`)
- TypeScript 定义（用于 Web 调试界面）

## db_migration

### 功能
关卡数据库迁移和更新:

```bash
# 从 PRTS 拉取最新数据
python tools/db_migration/fetch_prts_data.py

# 更新本地数据库
python tools/db_migration/update_database.py

# 验证数据完整性
python tools/db_migration/validate.py
```

### 数据流程
```
PRTS Wiki
    ↓
爬取/解析
    ↓
JSON 文件
    ↓
验证/转换
    ↓
SQLite 数据库
```

## benchmark

### 功能
性能测试套件:

```bash
# 运行所有基准测试
./tools/benchmark/run_all.sh

# 特定测试
./tools/benchmark/benchmark_capture --duration=60

# 生成报告
./tools/benchmark/generate_report.py --output=report.html
```

### 测试项目
- 捕获延迟
- 图像处理吞吐量
- 操作执行延迟
- 状态机性能
- 端到端延迟

## 使用示例

### 代码生成
```python
# tools/protobuf_codegen/generate.py
import subprocess
import pathlib

def generate_cpp(proto_dir: pathlib.Path, output_dir: pathlib.Path):
    for proto_file in proto_dir.glob("**/*.proto"):
        subprocess.run([
            "protoc",
            f"--cpp_out={output_dir}",
            f"--grpc_cpp_out={output_dir}",
            f"--plugin=protoc-gen-grpc_cpp={GRPC_CPP_PLUGIN}",
            proto_file
        ], check=True)
```

### 数据库迁移
```python
# tools/db_migration/fetch_prts_data.py
import requests
import json

def fetch_level_data(level_id: str) -> dict:
    url = f"https://prts.wiki/w/{level_id}"
    # 解析关卡数据
    return parsed_data

def update_database(data: dict):
    # 更新 SQLite
    pass
```

## 相关目录

- [proto/](../proto/): 协议定义（代码生成源）
- [core/src/l4_state/](../core/src/l4_state/): 数据消费者
