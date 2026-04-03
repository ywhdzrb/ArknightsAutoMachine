# l0_sensing - L0 感知层实现

## 目录说明

本目录包含屏幕捕获引擎的实现，支持多种捕获后端。

## 文件说明

### adb_capture.cpp
**ADB 屏幕捕获**

通过 ADB 协议捕获 Android 设备屏幕:
- 使用 `adb shell screenrecord --output-format=h264`
- 硬解码: Windows (MediaFoundation), Linux (VAAPI), macOS (VideoToolbox)
- 支持 144Hz 高刷设备

### maa_adapter.cpp
**MaaFramework 适配器**

适配 MaaFramework 作为捕获后端:
- 复用 Maa 的图像识别能力
- 统一接口 `ICaptureBackend`

### win32_window_capture.cpp
**Win32 窗口捕获**

捕获模拟器窗口:
- 使用 `PrintWindow` 或 `BitBlt`
- 支持后台捕获（不抢占焦点）

### shm_transport.cpp
**共享内存传输**

零拷贝帧数据传输:
- 基于 `boost::interprocess`
- 环形缓冲区设计（1GB 双缓冲）
- 无锁队列（Lock-free SPSC）

### tests/test_frame_sync.cpp
**帧同步测试**

验证时间戳同步和乱序检测。

## 架构设计

```
┌─────────────────────────────────────────┐
│         CaptureEngine (协调器)           │
├─────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌─────────┐ │
│  │ ADB      │ │ Maa      │ │ Win32   │ │
│  │ Backend  │ │ Adapter  │ │ Backend │ │
│  └────┬─────┘ └────┬─────┘ └────┬────┘ │
│       └─────────────┴─────────────┘     │
│                    │                    │
│              ┌─────┴─────┐              │
│              │  Frame    │              │
│              │  Buffer   │              │
│              └─────┬─────┘              │
│                    │                    │
│              ┌─────┴─────┐              │
│              │   SHM     │              │
│              │ Transport │              │
│              └───────────┘              │
└─────────────────────────────────────────┘
```

## 性能优化

### 零拷贝设计
- 捕获缓冲区直接映射到共享内存
- 避免内核态到用户态的拷贝

### 多后端支持
```cpp
enum class CaptureBackendType {
    ADB,        // 默认，通用
    MAA,        // 高精度识别
    WIN32,      // 模拟器专用
    SCRCPY      // 低延迟投屏
};
```

### 帧率自适应
```cpp
class AdaptiveFrameRate {
    void adjust(int current_fps);
    // 根据设备性能动态调整目标帧率
};
```

## 配置示例

```yaml
# configs/ama/capture.yaml
capture:
  backend: adb
  resolution: [1920, 1080]
  target_fps: 60
  
adb:
  device_id: "auto"  # 自动检测
  bit_rate: 8000000
  
shm:
  buffer_size: "1GB"
  num_buffers: 2
```

## 测试

```bash
# 单元测试
./test_frame_sync

# 性能测试
./benchmark_capture_latency --duration=60

# 集成测试
./test_l0_to_l2_pipeline
```

## 相关目录

- [include/aam/l0/](../../include/aam/l0/): 接口定义
- [src/l1_perception/](../l1_perception/): 下游消费者
