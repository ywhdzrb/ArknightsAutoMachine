# API 文档

## 概述

本目录包含 AAM 项目的所有接口契约文档，包括 gRPC 服务定义、REST API 规范和内部模块接口说明。

## 文档结构

### gRPC API

基于 Protocol Buffers 定义的服务接口:

| 服务 | 用途 | 协议文件 |
|---|---|---|
| ControlService | 主控制服务 | `proto/services/control_service.proto` |
| DebugService | 远程调试接口 | `proto/services/debug_service.proto` |
| L5Inference | LLM推理流 | `proto/inference/llm_stream.proto` |

### 内部接口

#### L0-L4 层间通信
- **共享内存传输**: 高频数据（屏幕帧/点击坐标）
- **gRPC Unary**: L4 状态查询
- **gRPC Stream**: L5 实时推理流

#### GUI 抽象接口
- `IMainWindow`: 主窗口接口
- `IMapView`: 地图视图接口
- `IOperatorPanel`: 干员面板接口

## 代码生成

API 文档从 proto 文件自动生成:

```bash
# 生成 C++ 代码
protoc --cpp_out=. --grpc_cpp_out=. proto/ama/*.proto

# 生成 Python 代码
protoc --python_out=. --grpc_python_out=. proto/ama/*.proto

# 生成文档
protoc --doc_out=. --doc_opt=markdown,api.md proto/**/*.proto
```

## 版本控制

- 所有 proto 文件遵循语义化版本
- Breaking Change 需升级主版本号
- CI 自动检测破坏性变更

## 相关目录

- [proto/](../../proto/): Protocol Buffers 定义文件
- [bridge/](../../bridge/): 语言桥接层实现
