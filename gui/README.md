# gui - 多前端实现

## 目录说明

本目录包含 AAM 的多前端实现，支持 Qt6（跨平台）和 WPF（Windows 高级）。

## 架构设计

```
gui/
├── abstract/              # GUI 抽象层
│   ├── include/aam_gui/   # 接口定义
│   └── src/               # 抽象实现
├── qt/                    # Qt6 实现
└── wpf/                   # WPF 实现
```

## 抽象工厂模式

```cpp
// gui/abstract/include/aam_gui/gui_factory.hpp
class IGUIFactory {
public:
    virtual ~IGUIFactory() = default;
    virtual std::unique_ptr<IMainWindow> createMainWindow() = 0;
    virtual std::unique_ptr<IMapView> createMapView() = 0;
    virtual std::unique_ptr<IOperatorPanel> createOperatorPanel() = 0;
    virtual void bindEventBus(std::shared_ptr<aam::core::EventBus>) = 0;
};

// Qt 实现
class QtGUIFactory : public IGUIFactory { ... };

// WPF 桥接
class WpfBridgeFactory : public IGUIFactory { ... };
```

## 前端对比

| 特性 | Qt6 | WPF |
|---|---|---|
| 平台 | Win/Linux/macOS | Windows only |
| 性能 | 优秀 | 优秀 |
| 视觉效果 | 良好 | 优秀 |
| 开发效率 | 中等 | 高 |
| 触摸支持 | 良好 | 优秀 |
| 推荐场景 | 跨平台 | Windows 专业版 |

## 统一事件总线

```cpp
// 解耦 AMA 核心与 GUI
class EventBus {
public:
    template<typename Event>
    void subscribe(std::function<void(const Event&)> handler);
    
    template<typename Event>
    void publish(const Event& event);
};

// 事件类型
struct FrameEvent { cv::Mat frame; };
struct StateEvent { GameState state; };
struct ActionEvent { TacticalCommand command; };
```

## Qt6 实现

### 目录结构
```
gui/qt/
├── src/
│   ├── main_window.cpp       # 主窗口
│   ├── map_view.cpp          # OpenGL 地图渲染
│   ├── operator_palette.cpp  # 干员栏
│   └── qt_event_bridge.cpp   # 信号槽 ↔ 事件总线
├── resources/
│   ├── qml/                  # QML 组件
│   └── icons/                # 图标资源
└── tests/
```

### 技术栈
- Qt6 Widgets / Qt Quick
- OpenGL / Qt3D（地图渲染）
- Qt Concurrent（异步任务）

## WPF 实现

### 目录结构
```
gui/wpf/
├── AAM.WPF/                  # C# 主项目
│   ├── Views/
│   │   ├── MainWindow.xaml
│   │   └── MapOverlay.xaml   # 悬浮地图层
│   ├── ViewModels/           # MVVM 模式
│   └── App.xaml
└── AAM.Native/               # C++/CLI 桥接
    ├── include/
    └── src/
        ├── cpp_cli_bridge.cpp
        └── frame_pusher.cpp  # 零拷贝帧传递
```

### 技术栈
- .NET 8 / WPF
- C++/CLI（托管/非托管桥接）
- Windows 原生 API 集成

## 构建配置

### Qt6
```cmake
find_package(Qt6 REQUIRED COMPONENTS Core Widgets OpenGL)

add_executable(AAMQt
    src/main_window.cpp
    src/map_view.cpp
)

target_link_libraries(AAMQt
    Qt6::Core
    Qt6::Widgets
    Qt6::OpenGL
    aam_core
)
```

### WPF
```xml
<!-- AAM.WPF.csproj -->
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>WinExe</OutputType>
    <TargetFramework>net8.0-windows</TargetFramework>
    <UseWPF>true</UseWPF>
  </PropertyGroup>
</Project>
```

## 相关目录

- [gui/abstract/](abstract/): 抽象接口定义
- [core/](../core/): AMA 核心
- [configs/gui/](../configs/gui/): GUI 配置
