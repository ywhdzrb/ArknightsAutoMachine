"""
投屏视图组件 - 显示 Android 设备屏幕

TODO: 待实现投屏功能
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QSizePolicy
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPainter, QFont

import numpy as np
from typing import Optional, List

from gui.abstract import (
    IScreenView,
    IScreenMirrorClient,
    ConnectionState,
    DeviceInfo,
)

from .scrcpy_client import ScrcpyClient


class ScreenView(QWidget, IScreenView):
    """
    设备投屏视图
    
    显示 Android 设备的实时屏幕画面
    提供接口供外部获取帧数据
    
    TODO: 待实现投屏功能
    """
    
    # 信号定义
    connection_changed = pyqtSignal(int)
    log_message = pyqtSignal(str, str)
    frame_ready = pyqtSignal(np.ndarray)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._client = ScrcpyClient()
        self._client.set_state_callback(self._on_state_changed)
        self._client.set_log_callback(self._on_log)
        
        self._setup_ui()
        
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(480, 320)
    
    def _on_log(self, message: str, level: str):
        self.log_message.emit(message, level)
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.display_widget = ScreenDisplayWidget()
        layout.addWidget(self.display_widget, 1)
    
    def _on_state_changed(self, state: ConnectionState):
        self.connection_changed.emit(int(state))
    
    # ========== IScreenView 接口实现 ==========
    
    def get_frame(self) -> Optional[np.ndarray]:
        raise NotImplementedError("投屏功能待实现")
    
    def get_client(self) -> IScreenMirrorClient:
        return self._client
    
    def is_connected(self) -> bool:
        return self._client.state in (ConnectionState.CONNECTED, ConnectionState.STREAMING)
    
    def connect_device(self, device_id: str):
        raise NotImplementedError("投屏功能待实现")
    
    def disconnect(self):
        raise NotImplementedError("投屏功能待实现")
    
    @staticmethod
    def list_devices() -> List[DeviceInfo]:
        raise NotImplementedError("投屏功能待实现")
    
    @property
    def device_width(self) -> int:
        return self._client.device_width
    
    @property
    def device_height(self) -> int:
        return self._client.device_height


class ScreenDisplayWidget(QWidget):
    """屏幕显示组件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), Qt.GlobalColor.black)
        self.setPalette(palette)
        
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(320, 240)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(Qt.GlobalColor.gray)
        painter.setFont(QFont("Arial", 16))
        painter.drawText(
            self.rect(),
            Qt.AlignmentFlag.AlignCenter,
            "投屏功能待实现\n\nTODO: Screen Mirroring"
        )