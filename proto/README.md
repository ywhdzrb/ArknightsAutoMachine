# Protocol Buffers 定义

## 目录说明

本目录是 AAM 项目的**唯一真相源（Single Source of Truth）**，包含所有层间通信的协议定义。

## 目录结构

```
proto/
├── common/
│   └── types.proto              # 共享类型定义
├── ama/
│   ├── l0_frame.proto           # L0: 帧流定义
│   ├── l1_perception.proto      # L1: 感知数据
│   ├── l2_action.proto          # L2: 操作指令
│   ├── l3_tactical.proto        # L3: 战术原语
│   ├── l4_state.proto           # L4: 游戏状态
│   └── l4_query.proto           # L4: 状态查询
├── inference/
│   ├── l5_strategy.proto        # L5: 策略输入/输出
│   └── llm_stream.proto         # L5: 流式推理
└── services/
    ├── control_service.proto    # 主控制服务
    └── debug_service.proto      # 调试服务
```

## 协议版本策略

### 版本号规则
- **v1.0.0**: 初始稳定版本
- **v1.x.0**: 新增字段（向后兼容）
- **v2.0.0**: Breaking Change（字段删除/类型变更）

### Breaking Change 检测
CI 自动检查:
```yaml
- name: Check Breaking Changes
  uses: bufbuild/buf-action@v1
  with:
    breaking_against: 'https://github.com/org/repo.git#branch=main'
```

## 代码生成

### C++
```bash
protoc --cpp_out=../core/src --grpc_cpp_out=../core/src \
  --plugin=protoc-gen-grpc_cpp=$(which grpc_cpp_plugin) \
  ama/*.proto
```

### Python
```bash
protoc --python_out=../inference/src --grpc_python_out=../inference/src \
  --plugin=protoc-gen-grpc_python=$(which grpc_python_plugin) \
  --mypy_out=../inference/src \
  inference/*.proto
```

## 命名规范

### 消息命名
- 使用 PascalCase
- 后缀表示用途: `Request`, `Response`, `Event`, `Config`
- 示例: `FrameCaptureRequest`, `GameStateSnapshot`

### 字段命名
- 使用 snake_case
- 避免保留字: `hash`, `class`, `import`
- 时间戳字段后缀: `_at`, `_time`

### 枚举命名
- 类型名: PascalCase + 后缀 `Type`
- 值名: UPPER_SNAKE_CASE
- 包含 `UNSPECIFIED = 0` 作为默认值

## 性能优化

### 字段编号
- 1-15: 高频字段（单字节编码）
- 16-2047: 常规字段
- 避免频繁变更字段编号

### 重复字段
- 使用 `packed = true` 优化数值数组
- 大数据块考虑使用 `bytes` 类型

## 相关工具

- [Buf](https://buf.build/): Protobuf 构建系统和 linter
- [protoc-gen-doc](https://github.com/pseudomuto/protoc-gen-doc): 文档生成
- [protoc-gen-validate](https://github.com/bufbuild/protoc-gen-validate): 字段验证
