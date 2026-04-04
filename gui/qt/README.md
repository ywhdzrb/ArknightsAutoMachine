# qt - PyQt6 实现

## 目录说明

本目录包含基于 PyQt6 的跨平台 GUI 实现，是 AAM 的主要 GUI 方案。

## 许可证兼容性说明

### PyQt6 与 AGPL-3.0

本项目采用 AGPL-3.0 许可证。PyQt6 采用 GPL 许可证，与 AGPL-3.0 兼容：

- **GPL 兼容性**: AGPL-3.0 是 GPL-3.0 的扩展版本，两者完全兼容
- **网络条款**: AGPL-3.0 额外要求通过网络提供服务时也需提供源代码
- **使用建议**: 
  - 商业使用需注意 GPL/AGPL 的传染性
  - 如需闭源商业使用，可考虑购买 Riverbank Computing 的商业许可证
  - 更多信息: https://www.riverbankcomputing.com/commercial/license-faq

## 技术栈

- **PyQt6**: Qt6 Python 绑定
- **Qt6 Widgets**: 桌面 UI
- **Qt6 Core**: 信号槽、事件循环
- **cv2 (OpenCV)**: 截屏图像处理

## 目录结构

```
gui/qt/
├── src/
│   ├── mainwindows.py        # 主窗口实现
│   ├── screen_view.py        # 投屏视图组件
│   ├── scrcpy_client.py      # scrcpy 客户端（重导出）
│   └── __init__.py           # 模块模块初始化
├── requirements.txt          # Python 依赖
└── README.md                 # 本文档
```

## 主窗口

### 界面布局
```
┌─────────────────────────────────────┐
│  菜单栏  │  工具栏                                                      │
├─────────┴───────────────────────────┤
│  ┌─────────────┐       ┌───────────────┐ │
│  │                          │       │       控制面板               │ │
│  │   地图视图               │       │      ┌─────────┐  │ │
│  │                          │       │      │     状态信息     │  │ │
│  │                          │       │      └─────────┘  │ │
│  │                          │       │      ┌─────────┐  │ │
│  │                          │       │      │     干员栏       │  │ │
│  │                          │       │      └─────────┘  │ │
│  │                          │       │      ┌─────────┐  │ │
│  │                          │       │      │     日志面板     │  │ │
│  │                          │       │      └─────────┘  │ │
│  └─────────────┘       └───────────────┘ │
├─────────────────────────────────────┤
│  状态栏                                                                  │
└─────────────────────────────────────┘
```

### 代码示例
```python
# src/mainwindows.py
from PyQt6.QtWidgets import QMainWindow
from .screen_view import ScreenView
from bridge.python.aam_bridge import ScrcpyClient

class MainWindow(QMainWindow):
    def __init__(self, screen_client=None, parent=None):
        super().__init__(parent)
        # 使用依赖注入的客户端
        self.screen_view = ScreenView(client=screen_client)
        self._setup_ui()
    
    def _setup_ui(self):
        # 设置界面布局
        pass
    
    def set_title(self, title: str):
        self.setWindowTitle(title)
    
    def set_status(self, message: str):
        self.statusBar().showMessage(message)
```

## 投屏视图

### 帧渲染
```python
# src/screen_view.py
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPixmap, QPainter, QImage
from PyQt6.QtCore import Qt, pyqtSignal
import numpy as np

class ScreenView(QWidget):
    # 使用 QImage 信号避免主线程处理 numpy 数组
    frame_ready = pyqtSignal(QImage)
    
    def __init__(self, client=None, parent=None):
        super().__init__(parent)
        self._client = client  # 依赖注入
        self._setup_ui()
    
    def _on_frame_received(self, frame: np.ndarray):
        """帧接收回调，转换为 QImage"""
        h, w, ch = frame.shape
        rgb_frame = np.ascontiguousarray(frame[:, :, ::-1])
        q_image = QImage(
            rgb_frame.data, w, h, ch * w, 
            QImage.Format.Format_RGB888
        ).copy()
        self.frame_ready.emit(q_image)
```

## 事件桥接

```python
# src/qt_event_bridge.py
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from typing import Optional
import numpy as np

class QtEventBridge(QObject):
    # 信号定义
    operator_selected = pyqtSignal(str)
    tile_clicked = pyqtSignal(int, int)  # x, y
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._event_bus = None
    
    def bind_to_core(self, event_bus):
        """绑定到 AAM 核心事件总线"""
        self._event_bus = event_bus
        # 订阅核心事件
        event_bus.subscribe('frame_received', self._on_frame_received)
        event_bus.subscribe('state_changed', self._on_state_changed)
    
    @pyqtSlot(np.ndarray)
    def _on_frame_received(self, frame: np.ndarray):
        """处理帧接收事件"""
        pass
    
    @pyqtSlot(dict)
    def _on_state_changed(self, state: dict):
        """处理状态变化事件"""
        pass
```

## 运行

```bash
# 安装依赖
pip install -r requirements.txt

# 运行
python -m gui.run_qt
```

## 主题支持

```python
# 深色模式
from PyQt6.QtWidgets import QApplication, QStyleFactory
from PyQt6.QtGui import QPalette, QColor

app = QApplication([])
app.setStyle(QStyleFactory.create("Fusion"))

dark_palette = QPalette()
dark_palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
dark_palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
dark_palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
dark_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 255))
dark_palette.setColor(QPalette.ColorRole.ToolTipText, QColor(255, 255, 255))
dark_palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
dark_palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
dark_palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
dark_palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
dark_palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))

app.setPalette(dark_palette)
```

## 架构设计

### 依赖注入

GUI 层通过依赖注入接收投屏客户端实例：

```python
from bridge.python.aam_bridge import ScrcpyClient, ScrcpyConfig
from gui.qt.src import MainWindow

# 创建配置
config = ScrcpyConfig(
    max_size=1920,
    bit_rate=8000000,
    max_fps=60
)

# 创建客户端
client = ScrcpyClient(config)

# 注入到主窗口
window = MainWindow(screen_client=client)
```

### 抽象接口

所有 GUI 组件都依赖 `gui.abstract` 中定义的抽象接口：

- `IMainWindow`: 主窗口接口
- `IScreenView`: 投屏视图接口
- `IScreenMirrorClient`: 投屏客户端接口

## 相关目录

- [gui/abstract/](../abstract/): 抽象接口
- [bridge/python/aam_bridge/](../../bridge/python/aam_bridge/): 投屏客户端实现
- [gui/wpf/](../wpf/): WPF 实现
