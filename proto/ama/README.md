# ama - AMA 核心协议

## 目录说明

本目录包含 AMA（Arknights Auto Machine）架构 L0-L4 层的核心通信协议定义。

## 文件说明

### l0_frame.proto
**L0 感知层 - 帧流定义**

定义屏幕捕获的原始帧数据:
- `FrameStream`: 连续帧流
- `FrameMetadata`: 帧元数据（时间戳、分辨率、编码格式）
- `CaptureConfig`: 捕获配置（源类型、分辨率、帧率）

关键消息:
```protobuf
message Frame {
  bytes data = 1;                    // H264/YUV420p 原始数据
  FrameMetadata metadata = 2;
  common.Timestamp timestamp = 3;
}
```

### l1_perception.proto
**L1 视觉层 - 感知数据**

定义图像处理后的结构化数据:
- `DetectionResult`: 目标检测框（干员/敌人/地形）
- `OCRResult`: 文本识别结果
- `PerceptionFrame`: 完整的感知帧

关键消息:
```protobuf
message DetectionResult {
  string class_name = 1;
  common.Rect2D bbox = 2;
  float confidence = 3;
}
```

### l2_action.proto
**L2 运动层 - 操作指令**

定义抽象操作命令:
- `TapAction`: 点击操作
- `SwipeAction`: 滑动操作
- `ActionSequence`: 操作序列

关键消息:
```protobuf
message TapAction {
  common.Point2D position = 1;
  int32 duration_ms = 2;
  ActionTiming timing = 3;
}
```

### l3_tactical.proto
**L3 战术层 - 战术原语**

定义游戏战术操作:
- `DeployOperator`: 部署干员
- `UseSkill`: 释放技能
- `RetreatOperator`: 撤退干员
- `TacticalCommand`: 战术指令序列

关键消息:
```protobuf
message DeployOperator {
  string operator_id = 1;
  common.Point2D tile_position = 2;
  Direction direction = 3;
  int32 cost_threshold = 4;
}
```

### l4_state.proto
**L4 状态层 - 游戏状态**

定义完整游戏状态快照:
- `GameSnapshot`: 完整状态
- `OperatorState`: 干员状态
- `EnemyState`: 敌人状态
- `GameResources`: 资源状态（费用、生命）

关键消息:
```protobuf
message GameSnapshot {
  string snapshot_id = 1;
  common.Timestamp timestamp = 2;
  GameState state = 3;
  repeated OperatorState operators = 4;
  repeated EnemyState enemies = 5;
  GameResources resources = 6;
}
```

### l4_query.proto
**L4 状态查询接口**

定义状态查询的 gRPC 服务:
- `GetCurrentState`: 获取当前状态
- `GetStateHistory`: 获取历史状态
- `SubscribeState`: 订阅状态变更

## 层间通信模式

| 层 | 协议 | 延迟预算 | 用途 |
|---|---|---|---|
| L0→L1 | 共享内存 | < 8ms | 原始帧流传输 |
| L1→L2 | gRPC Stream | < 5ms | 感知结果推送 |
| L2→L3 | gRPC Unary | < 2ms | 操作确认 |
| L3→L4 | gRPC Unary | < 10ms | 战术执行 |
| L4→L5 | gRPC Stream | < 100ms | 状态同步 |

## 版本历史

- v1.0.0: 初始协议定义
- v1.1.0: 新增 L4 增量快照支持
