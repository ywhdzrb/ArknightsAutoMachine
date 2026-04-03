# aam_bridge - Python 桥接模块

## 目录说明

本目录包含 Python 侧的桥接实现，用于与 C++ 核心通信。

## 文件说明

### __init__.py
模块初始化，导出公共接口。

### native_client.py
原生客户端封装:
- 加载 C++ 共享库
- 提供 Pythonic API
- 异步支持

## 使用示例

```python
from aam_bridge import NativeClient

# 创建客户端
client = NativeClient(
    transport="grpc",
    endpoint="localhost:50051"
)

# 连接到核心
client.connect()

# 发送状态
client.send_state(game_snapshot)

# 接收命令
command = client.receive_command()
```

## 相关目录

- [bridge/src/](../../src/): C++ 实现
- [inference/services/](../../../inference/services/): Python 服务端
