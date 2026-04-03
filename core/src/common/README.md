# common - 基础设施

## 目录说明

本目录包含 AAM Core 各层共享的基础设施代码，包括日志、计时、内存管理等。

## 文件说明

### logger.cpp
**日志系统**

基于 spdlog 的封装:
- 多级别日志（Trace/Debug/Info/Warning/Error/Fatal）
- 异步日志队列
- 结构化日志输出（JSON 格式）
- 日志轮转和压缩

### timer.cpp
**高精度计时**

跨平台高精度计时器:
- Windows: QueryPerformanceCounter
- Linux: clock_gettime(CLOCK_MONOTONIC_RAW)
- macOS: mach_absolute_time

### memory_pool.cpp
**内存池**

定长对象内存池:
- 避免频繁堆分配
- 减少内存碎片
- 线程安全设计

## 日志系统

### 使用示例
```cpp
#include "aam/core/logger.hpp"

// 初始化
aam::core::Logger::init("aam.log", aam::core::LogLevel::Debug);

// 记录日志
LOG_INFO("System initialized");
LOG_DEBUG("Frame captured: {}", frame_id);
LOG_ERROR("Capture failed: {}", error_msg);

// 结构化日志
LOG_JSON({
    {"event", "operator_deployed"},
    {"operator_id", "char_002_amiya"},
    {"position", {"x", 3, "y", 4}}
});
```

### 配置
```yaml
logging:
  level: debug
  async: true
  queue_size: 8192
  file:
    path: logs/aam.log
    max_size: 100MB
    max_files: 10
  console:
    enabled: true
    color: true
```

## 计时器

### 高精度计时
```cpp
#include "aam/core/timer.hpp"

aam::core::Timer timer;
timer.start();

// ... 执行操作

auto elapsed = timer.elapsed_micros();
LOG_INFO("Operation took {} us", elapsed);
```

### 性能剖析
```cpp
#include "aam/core/profiler.hpp"

void processFrame() {
    PROFILE_SCOPE("processFrame");  // 自动计时
    
    PROFILE_BLOCK("capture");
    auto frame = capture();
    PROFILE_END();
    
    PROFILE_BLOCK("detect");
    auto results = detect(frame);
    PROFILE_END();
}
```

## 内存池

### 使用方式
```cpp
#include "aam/core/memory_pool.hpp"

// 创建内存池（对象大小: 64字节，预分配: 1024个）
aam::core::MemoryPool<64> pool(1024);

// 分配
void* ptr = pool.allocate();

// 释放
pool.deallocate(ptr);
```

### 性能对比
| 操作 | std::malloc | MemoryPool | 提升 |
|---|---|---|---|
| 分配 | 120ns | 15ns | 8x |
| 释放 | 80ns | 10ns | 8x |

## 线程池

```cpp
#include "aam/core/thread_pool.hpp"

// 创建线程池（默认: 硬件并发数）
aam::core::ThreadPool pool;

// 提交任务
auto future = pool.submit([]() {
    return heavyComputation();
});

// 获取结果
auto result = future.get();
```

## 事件总线

```cpp
#include "aam/core/event_bus.hpp"

// 创建事件总线
aam::core::EventBus bus;

// 订阅事件
bus.subscribe<FrameEvent>([](const FrameEvent& e) {
    processFrame(e.frame);
});

// 发布事件
bus.publish(FrameEvent{frame});
```

## 相关目录

- [include/aam/core/](../../include/aam/core/): 接口定义
