# core - C++ AMA 核心

## 目录说明

本目录包含 AAM 架构 L0-L4 层的 C++ 实现，是系统的实时核心组件。

## 架构分层

```
core/
├── include/aam/           # 公共接口层
│   ├── core/              # 核心抽象
│   ├── l0/                # 感知层接口
│   ├── l1/                # 视觉层接口
│   ├── l2/                # 运动层接口
│   ├── l3/                # 战术层接口
│   └── l4/                # 状态层接口
└── src/
    ├── l0_sensing/        # L0: 屏幕捕获
    ├── l1_perception/     # L1: 图像处理
    ├── l2_motor/          # L2: 操作执行
    ├── l3_tactical/       # L3: 战术执行
    ├── l4_state/          # L4: 状态机
    └── common/            # 基础设施
```

## 各层职责

### L0 - 感知层 (Sensing)
- **职责**: 屏幕捕获、设备通信
- **技术**: ADB、scrcpy、Win32 API、MaaFramework
- **性能目标**: 144Hz 捕获，延迟 < 16ms

### L1 - 视觉层 (Perception)
- **职责**: 图像预处理、目标检测、OCR
- **技术**: OpenCV CUDA、ONNX Runtime、PaddleOCR
- **性能目标**: 单帧处理 < 30ms

### L2 - 运动层 (Motor)
- **职责**: 操作抽象、坐标变换、人性化模拟
- **技术**: 贝塞尔曲线、正态分布抖动
- **性能目标**: 操作执行 < 50ms

### L3 - 战术层 (Tactical)
- **职责**: 战术原语、DSL 编译、费用管理
- **技术**: 自定义字节码 VM、碰撞检测
- **性能目标**: 指令编译 < 2ms

### L4 - 状态层 (State)
- **职责**: 游戏状态机、快照序列化、数据持久化
- **技术**: 分层状态机 (HFSM)、SQLite、MessagePack
- **性能目标**: 状态查询 < 1ms

## 构建系统

### 依赖管理
使用 vcpkg 管理 C++ 依赖:

```json
{
  "dependencies": [
    "opencv4[contrib,cuda]",
    "grpc",
    "protobuf",
    "boost-interprocess",
    "spdlog",
    "gtest"
  ]
}
```

### 编译选项

```cmake
# 严格标准
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# MSVC
add_compile_options(/W4 /WX /permissive- /Zc:__cplusplus)

# GCC/Clang
add_compile_options(-Wall -Wextra -Wpedantic -Werror -march=native)
```

### 构建命令

```bash
# 配置
cmake --preset=windows-cl-x64

# 构建
cmake --build --preset=windows-cl-x64-release

# 测试
ctest --preset=windows-cl-x64-release
```

## 测试覆盖

- **单元测试**: GTest，目标 > 90% 分支覆盖
- **集成测试**: 跨层流水线测试
- **性能测试**: Valgrind、Cachegrind 分析
- **模糊测试**: libFuzzer 针对协议解析器

## 性能基准

| 指标 | 目标 | 测试方法 |
|---|---|---|
| L0→L1 延迟 | < 8ms | 帧时间戳差分 |
| L2→L3 延迟 | < 2ms | 指令往返时间 |
| 内存占用 | < 150MB | Massif 分析 |
| CPU 占用 | < 15% | 持续运行测试 |

## 相关目录

- [bridge/](../bridge/): C++ ↔ Python 桥接层
- [proto/ama/](../proto/ama/): 层间通信协议
- [configs/ama/](../configs/ama/): 运行时配置
