# l2_motor - L2 运动层实现

## 目录说明

本目录包含操作执行引擎，实现从抽象操作到物理输入的转换。

## 文件说明

### coordinate_transform.cpp
**坐标变换**

逻辑坐标与物理坐标的映射:
- 逻辑坐标: 1920x1080 虚拟分辨率
- 物理坐标: 设备实际分辨率
- 透视变换矩阵自动校准

### input_adapters/
输入适配器目录:
- **adb_input.cpp**: ADB shell input 命令
- **win32_postmessage.cpp**: Win32 PostMessage API
- **physical_arm_stub.cpp**: 物理机械臂预留接口

### trajectory_generator.cpp
**轨迹生成器**

人性化操作模拟:
- 贝塞尔曲线滑动
- 正态分布时间抖动
- 防检测随机扰动

### feedback_loop.cpp
**反馈闭环**

操作确认系统:
- 操作后截图比对
- 失败重试机制
- 误差动态补偿

## 坐标系统

```
┌─────────────────────────────────────────┐
│           逻辑坐标系 (1920x1080)          │
│  ┌─────────────────────────────────┐   │
│  │         游戏画面 (16:9)          │   │
│  │    (0,0) ─────────► (1920,0)    │   │
│  │      │                        │   │   │
│  │      ▼                        ▼   │   │
│  │  (0,1080) ───────► (1920,1080)  │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
                    │
                    ▼ 坐标变换矩阵
┌─────────────────────────────────────────┐
│           物理坐标系 (设备相关)           │
│  ┌─────────────────────────────────┐   │
│  │    实际屏幕像素坐标 (如 2400x1080)    │   │
│  │    考虑刘海、圆角、导航栏偏移         │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

## 人性化模拟

### 点击模拟
```cpp
class HumanizedTap {
    // 点击延时: N(80ms, 15ms)
    std::chrono::milliseconds getTapDelay();
    
    // 位置扰动: ±5px
    Point2D addPositionJitter(Point2D pos);
};
```

### 滑动轨迹
```cpp
class BezierSwipe {
    // 三阶贝塞尔曲线
    std::vector<Point2D> generate(
        Point2D start,
        Point2D end,
        Point2D control1,
        Point2D control2,
        int duration_ms
    );
};
```

### 时间分布
```cpp
// 韦伯-费希纳定律模拟
class WeberFechnerTiming {
    // 操作间隔符合人类感知规律
    int getNextInterval();
};
```

## 输入后端

### ADB 输入
```cpp
class ADBInput : public IInputBackend {
    void tap(Point2D pos) override;
    void swipe(Point2D start, Point2D end, int duration) override;
    void sendKey(const std::string& key) override;
};
```

### Win32 输入
```cpp
class Win32Input : public IInputBackend {
    // 使用 PostMessage 避免焦点抢占
    void tap(Point2D pos) override;
};
```

## 反馈闭环

```
发送操作指令
    │
    ▼
┌─────────────┐
│ 执行输入     │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 等待 200ms  │
└──────┬──────┘
       │
       ▼
┌─────────────┐     否
│ 截图比对     │ ──► 重试 (最多3次)
│ 确认效果     │
└──────┬──────┘
       │ 是
       ▼
   操作完成
```

## 反检测机制

1. **随机延时**: 操作间隔随机化
2. **轨迹扰动**: 滑动路径非直线
3. **焦点保护**: 不抢占游戏窗口焦点
4. **操作间隔**: 最小 120ms，避免连点检测

## 配置示例

```yaml
# configs/ama/input_profiles/rog_phone_8.yaml
input:
  backend: adb
  
humanization:
  tap_delay_mean: 80      # ms
  tap_delay_std: 15       # ms
  position_jitter: 5      # px
  min_interval: 120       # ms
  
bezier:
  control_point_variance: 0.2
```

## 相关目录

- [include/aam/l2/](../../include/aam/l2/): 接口定义
- [configs/ama/input_profiles/](../../../configs/ama/input_profiles/): 设备配置
