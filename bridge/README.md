# bridge - C++ ↔ Python 桥接层

## 目录说明

本目录实现 C++ 核心与 Python 推理后端之间的通信桥接，支持多种传输协议。

## 架构设计

```
┌─────────────────────────────────────────┐
│           AAM Core (C++)                │
│  ┌─────────────────────────────────┐   │
│  │      Bridge Client              │   │
│  │  ┌─────────┐  ┌─────────┐      │   │
│  │  │  gRPC   │  │   SHM   │      │   │
│  │  │ Client  │  │ Client  │      │   │
│  │  └────┬────┘  └────┬────┘      │   │
│  └───────┼────────────┼───────────┘   │
└──────────┼────────────┼───────────────┘
           │            │
           ▼            ▼
    ┌─────────────────────────┐
    │      Transport Layer    │
    │  (gRPC / Shared Memory) │
    └─────────────────────────┘
           │            │
           ▼            ▼
┌──────────┼────────────┼───────────────┐
│          ▼            ▼               │
│  ┌─────────────────────────────────┐ │
│  │      Bridge Server (Python)     │ │
│  │  ┌─────────┐  ┌─────────┐      │ │
│  │  │  gRPC   │  │   SHM   │      │ │
│  │  │ Server  │  │ Server  │      │ │
│  │  └─────────┘  └─────────┘      │ │
│  └─────────────────────────────────┘ │
│           AAM Inference (Python)      │
└───────────────────────────────────────┘
```

## 目录结构

```
bridge/
├── include/aam_bridge/    # C++ 接口
├── src/                   # C++ 实现
├── python/aam_bridge/     # Python 封装
└── tests/                 # 桥接测试
```

## 传输协议

### gRPC（默认）
- **适用场景**: 跨进程通信、网络分布式
- **延迟**: ~5ms（本地）
- **优势**: 强类型、自动序列化、流支持

### 共享内存（SHM）
- **适用场景**: 高频数据（帧流）
- **延迟**: < 1ms
- **优势**: 零拷贝、最低延迟

### 协议选择策略
```cpp
enum class TransportType {
    SHARED_MEMORY,    // L0-L3 高频数据
    GRPC_UNARY,       // L4 状态查询
    GRPC_STREAM,      // L5 实时推理流
    WEBSOCKET         // 调试/监控
};
```

## C++ 客户端

### 使用示例
```cpp
#include "aam_bridge/ipc_client.hpp"

// 创建客户端
auto client = aam::bridge::IPCClient::create(
    TransportType::GRPC_UNARY,
    "localhost:50051"
);

// 发送请求
ama::l4::GameSnapshot state;
client->send(state);

// 接收响应
auto commands = client->receive<aam::l3::TacticalCommand>();
```

## Python 服务端

### 使用示例
```python
from aam_bridge import NativeClient

# 创建服务端
server = NativeClient(
    transport="grpc",
    port=50051
)

# 注册处理器
@server.handler("strategy")
async def handle_strategy(request):
    # LLM 推理
    response = await llm.predict(request)
    return response

# 启动
server.start()
```

## pybind11 封装

用于调试模式直接调用:

```cpp
// bridge/src/pybind_module.cpp
#include <pybind11/pybind11.h>

PYBIND11_MODULE(aam_native, m) {
    m.def("capture_frame", &capture_frame);
    m.def("execute_action", &execute_action);
}
```

```python
# 使用
import aam_native

frame = aam_native.capture_frame()
aam_native.execute_action(tap_action)
```

## 性能基准

| 传输方式 | 延迟 | 吞吐量 | 适用场景 |
|---|---|---|---|
| gRPC Unary | 5ms | 10k QPS | 状态查询 |
| gRPC Stream | 10ms | 1k msg/s | 实时流 |
| SHM | <1ms | 144fps | 帧流传输 |
| WebSocket | 20ms | 100 msg/s | 调试 |

## 故障恢复

### 重连机制
```cpp
class ResilientClient {
    void sendWithRetry(const Message& msg, int max_retries = 3);
    void onDisconnect();
    void reconnect();
};
```

### 降级策略
- Python 后端崩溃 → 启用本地规则引擎
- 网络中断 → 切换到离线模式
- 超时 → 返回默认策略

## 相关目录

- [core/](../core/): C++ 核心
- [inference/](../inference/): Python 推理后端
- [proto/](../proto/): 协议定义
