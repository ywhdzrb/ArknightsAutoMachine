# common - 共享类型定义

## 目录说明

本目录包含所有 AMA 层间通信共享的基础类型定义，被其他所有 proto 文件导入。

## 文件说明

### types.proto

定义跨层共享的基础数据结构:

#### 坐标类型
```protobuf
message Point2D {
  int32 x = 1;
  int32 y = 2;
}

message Rect2D {
  int32 x = 1;
  int32 y = 2;
  int32 width = 3;
  int32 height = 4;
}
```

#### 时间戳
```protobuf
message Timestamp {
  int64 seconds = 1;
  int32 nanos = 2;
}
```

#### 设备信息
```protobuf
message DeviceInfo {
  string device_id = 1;
  string model = 2;
  Resolution resolution = 3;
  int32 refresh_rate = 4;
}
```

#### 通用枚举
```protobuf
enum StatusCode {
  STATUS_UNSPECIFIED = 0;
  STATUS_OK = 1;
  STATUS_ERROR = 2;
  STATUS_TIMEOUT = 3;
}
```

## 导入方式

在其他 proto 文件中:

```protobuf
syntax = "proto3";

package aam.l0;

import "common/types.proto";

message FrameMetadata {
  common.Timestamp capture_time = 1;
  common.Resolution resolution = 2;
}
```

## 设计原则

1. **最小化**: 只包含真正共享的类型
2. **稳定性**: 这些类型变更影响范围最大，需格外谨慎
3. **无业务逻辑**: 纯数据结构，不包含服务定义

## 变更控制

- 任何修改需经过架构审查
- 禁止删除字段（只能标记为废弃）
- 新增字段使用新的编号
