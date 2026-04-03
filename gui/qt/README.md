# qt - Qt6 实现

## 目录说明

本目录包含基于 Qt6 的跨平台 GUI 实现，是 AAM 的主要 GUI 方案。

## 技术栈

- **Qt6 Core**: 基础功能
- **Qt6 Widgets**: 桌面 UI
- **Qt6 OpenGL**: 地图渲染
- **Qt6 Concurrent**: 异步任务

## 目录结构

```
gui/qt/
├── src/
│   ├── main_window.cpp       # 主窗口实现
│   ├── map_view.cpp          # OpenGL 地图视图
│   ├── operator_palette.cpp  # 干员面板
│   └── qt_event_bridge.cpp   # Qt 信号槽 ↔ AMA 事件桥接
├── resources/
│   ├── qml/                  # QML 组件（可选）
│   └── icons/                # 图标资源
├── tests/
└── CMakeLists.txt
```

## 主窗口

### 界面布局
```
┌─────────────────────────────────────┐
│  菜单栏  │  工具栏                    │
├─────────┴───────────────────────────┤
│  ┌─────────────┐  ┌───────────────┐ │
│  │             │  │   控制面板     │ │
│  │   地图视图   │  │  ┌─────────┐  │ │
│  │   (OpenGL)  │  │  │ 状态信息 │  │ │
│  │             │  │  └─────────┘  │ │
│  │             │  │  ┌─────────┐  │ │
│  │             │  │  │ 干员栏  │  │ │
│  │             │  │  └─────────┘  │ │
│  │             │  │  ┌─────────┐  │ │
│  │             │  │  │ 日志面板 │  │ │
│  │             │  │  └─────────┘  │ │
│  └─────────────┘  └───────────────┘ │
├─────────────────────────────────────┤
│  状态栏                              │
└─────────────────────────────────────┘
```

### 代码示例
```cpp
// src/main_window.cpp
class MainWindow : public QMainWindow, public IMainWindow {
    Q_OBJECT
    
public:
    explicit MainWindow(QWidget* parent = nullptr);
    
    // IMainWindow 实现
    void show() override { QMainWindow::show(); }
    void setTitle(const std::string& title) override;
    IMapCanvas* mapCanvas() override { return map_view_; }
    
private:
    MapView* map_view_;
    OperatorPalette* operator_palette_;
    LogPanel* log_panel_;
};
```

## 地图视图

### OpenGL 渲染
```cpp
// src/map_view.cpp
class MapView : public QOpenGLWidget, public IMapCanvas {
public:
    void renderFrame(const cv::Mat& frame) override;
    void drawDetection(const DetectionResult& det) override;
    
protected:
    void initializeGL() override;
    void paintGL() override;
    void resizeGL(int w, int h) override;
    
private:
    QOpenGLShaderProgram* shader_program_;
    GLuint frame_texture_;
};
```

## 事件桥接

```cpp
// src/qt_event_bridge.cpp
class QtEventBridge : public QObject {
    Q_OBJECT
    
public:
    void bindToCore(std::shared_ptr<aam::core::EventBus> bus);
    
private slots:
    void onFrameReceived(const cv::Mat& frame);
    void onStateChanged(const GameState& state);
    
signals:
    void operatorSelected(const QString& id);
    void tileClicked(QPoint pos);
};
```

## 构建

```bash
# 配置
cmake -B build -S gui/qt \
  -DCMAKE_PREFIX_PATH=/path/to/qt6

# 构建
cmake --build build --config Release

# 运行
./build/AAMQt
```

## 主题支持

```cpp
// 深色模式
QApplication::setStyle("Fusion");
QPalette darkPalette;
darkPalette.setColor(QPalette::Window, QColor(53, 53, 53));
// ...
QApplication::setPalette(darkPalette);
```

## 相关目录

- [gui/abstract/](../abstract/): 抽象接口
- [gui/wpf/](../wpf/): WPF 实现
