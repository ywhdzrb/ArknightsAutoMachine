# abstract - GUI 抽象层

## 目录说明

本目录定义 GUI 层的抽象接口，实现 AMA 核心与具体 GUI 框架的解耦。

## 设计原则

### 依赖倒置
AMA 核心依赖抽象接口，而非具体实现:

```cpp
// 好：依赖抽象
class AAMCore {
    std::unique_ptr<IMainWindow> gui_;
};

// 避免：依赖具体类
class AAMCore {
    QtMainWindow gui_;  // 错误！
};
```

### 接口隔离
每个接口职责单一:
- `IMainWindow`: 主窗口生命周期
- `IMapCanvas`: 地图渲染
- `IOperatorPanel`: 干员面板
- `ILogView`: 日志显示

## 接口定义

### IMainWindow
```cpp
class IMainWindow {
public:
    virtual ~IMainWindow() = default;
    
    virtual void show() = 0;
    virtual void hide() = 0;
    virtual void close() = 0;
    
    virtual void setTitle(const std::string& title) = 0;
    virtual void showStatus(const std::string& status) = 0;
    
    // 子组件访问
    virtual IMapCanvas* mapCanvas() = 0;
    virtual IOperatorPanel* operatorPanel() = 0;
};
```

### IMapCanvas
```cpp
class IMapCanvas {
public:
    virtual ~IMapCanvas() = default;
    
    // 帧渲染
    virtual void renderFrame(const cv::Mat& frame) = 0;
    
    // 叠加层
    virtual void drawDetection(const DetectionResult& det) = 0;
    virtual void drawGrid(const MapGrid& grid) = 0;
    virtual void drawPath(const std::vector<Point2D>& path) = 0;
    
    // 交互
    virtual void setInteractive(bool enabled) = 0;
    virtual Signal<Point2D> onTileClicked() = 0;
};
```

### IOperatorPanel
```cpp
class IOperatorPanel {
public:
    virtual ~IOperatorPanel() = default;
    
    // 干员列表
    virtual void setOperators(const std::vector<OperatorInfo>& ops) = 0;
    virtual void updateOperatorState(const std::string& id, 
                                      const OperatorState& state) = 0;
    
    // 交互
    virtual Signal<std::string> onOperatorSelected() = 0;
    virtual Signal<std::string> onSkillActivated() = 0;
};
```

## 事件桥接

```cpp
// gui/abstract/src/event_dispatcher.cpp
class GUIEventDispatcher {
public:
    void bindToCore(std::shared_ptr<aam::core::EventBus> core_bus);
    void bindToGUI(std::shared_ptr<GUIEventBus> gui_bus);
    
private:
    void forwardToGUI(const FrameEvent& e);
    void forwardToCore(const UserActionEvent& e);
};
```

## 工厂模式

```cpp
// 运行时选择 GUI 实现
std::unique_ptr<IGUIFactory> createGUIFactory(GUIType type) {
    switch (type) {
        case GUIType::QT:
            return std::make_unique<QtGUIFactory>();
        case GUIType::WPF:
            return std::make_unique<WpfBridgeFactory>();
        default:
            throw std::invalid_argument("Unknown GUI type");
    }
}
```

## 相关目录

- [gui/qt/](../qt/): Qt6 实现
- [gui/wpf/](../wpf/): WPF 实现
