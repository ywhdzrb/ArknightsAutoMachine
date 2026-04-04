# -*- coding: utf-8 -*-
"""
Arknights Auto Machine (AAM) - 投屏视图组件

Copyright (C) 2026 AAM Contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

from typing import Optional, List

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal, QMutex, QMutexLocker
from PyQt6.QtGui import QPainter, QFont, QImage, QColor, QPen

import numpy as np
from numpy.typing import NDArray

from gui.abstract import (
    IScreenView,
    IScreenMirrorClient,
    ConnectionState,
    DeviceInfo,
)


class ScreenView(QWidget, IScreenView):
    """
    设备投屏视图

    显示 Android 设备的实时屏幕画面
    提供接口供外部获取帧数据

    TODO: 待实现投屏功能
    """

    # 信号定义 - 使用 QImage 避免在主线程处理 numpy 数组
    connection_changed = pyqtSignal(int)
    log_message = pyqtSignal(str, str)
    frame_ready = pyqtSignal(QImage)

    def __init__(self, client: Optional[IScreenMirrorClient] = None, parent=None):
        """
        初始化投屏视图

        Args:
            client: 投屏客户端实例（依赖注入），如果为 None 则延迟设置
            parent: 父组件
        """
        super().__init__(parent)

        self._client: Optional[IScreenMirrorClient] = client
        self._current_frame: Optional[QImage] = None
        self._frame_mutex = QMutex()  # 保护帧数据的互斥锁

        if self._client:
            self._setup_client_callbacks()

        self._setup_ui()

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(480, 320)

    def _setup_client_callbacks(self):
        """设置客户端回调"""
        if self._client:
            self._client.set_state_callback(self._on_state_changed)
            self._client.set_log_callback(self._on_log)

    def _on_log(self, message: str, level: str):
        """日志回调"""
        self.log_message.emit(message, level)

    def _setup_ui(self):
        """设置UI布局"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.display_widget = ScreenDisplayWidget()
        layout.addWidget(self.display_widget, 1)

    def _on_state_changed(self, state: ConnectionState):
        """状态变化回调"""
        self.connection_changed.emit(int(state))

    def _on_frame_received(self, frame: NDArray):
        """
        帧接收回调

        将 numpy 数组转换为 QImage（零拷贝或浅拷贝）
        """
        try:
            # 假设 frame 是 BGR 格式（OpenCV 默认）
            h, w, ch = frame.shape

            # 转换 BGR -> RGB
            rgb_frame = np.ascontiguousarray(frame[:, :, ::-1])

            # 创建 QImage（浅拷贝，共享内存）
            q_image = QImage(
                rgb_frame.data,
                w,
                h,
                ch * w,
                QImage.Format.Format_RGB888
            ).copy()  # 必须复制，因为 numpy 数组可能被释放

            with QMutexLocker(self._frame_mutex):
                self._current_frame = q_image

            # 发送信号
            self.frame_ready.emit(q_image)

            # 触发重绘
            self.display_widget.update()

        except Exception as e:
            self._on_log(f"帧处理错误: {e}", "ERROR")

    def cleanup(self):
        """清理资源，断开连接"""
        if self._client:
            try:
                self._client.disconnect()
            except Exception as e:
                self._on_log(f"断开连接时出错: {e}", "WARNING")

    def closeEvent(self, event):
        """窗口关闭事件"""
        self.cleanup()
        event.accept()

    # ========== IScreenView 接口实现 ==========

    def get_frame(self) -> Optional[NDArray]:
        """获取当前帧"""
        raise NotImplementedError("投屏功能待实现")

    def get_client(self) -> IScreenMirrorClient:
        """获取客户端实例"""
        if self._client is None:
            raise RuntimeError("投屏客户端未设置")
        return self._client

    def is_connected(self) -> bool:
        """检查是否已连接"""
        if self._client is None:
            return False
        return self._client.state in (ConnectionState.CONNECTED, ConnectionState.STREAMING)

    def connect_device(self, device_id: str):
        """连接指定设备"""
        raise NotImplementedError("投屏功能待实现")

    def disconnect(self):
        """断开连接"""
        raise NotImplementedError("投屏功能待实现")

    def list_devices(self) -> List[DeviceInfo]:
        """列出所有已连接的设备"""
        raise NotImplementedError("投屏功能待实现")

    @property
    def device_width(self) -> int:
        """获取设备屏幕宽度"""
        if self._client is None:
            return 0
        return self._client.device_width

    @property
    def device_height(self) -> int:
        """获取设备屏幕高度"""
        if self._client is None:
            return 0
        return self._client.device_height


class ScreenDisplayWidget(QWidget):
    """
    屏幕显示组件

    使用双缓冲绘制，避免闪烁
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), QColor(0, 0, 0))
        self.setPalette(palette)

        # 启用双缓冲
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(320, 240)

        # 当前显示的图像
        self._display_image: Optional[QImage] = None

    def set_image(self, image: QImage):
        """设置要显示的图像"""
        self._display_image = image
        self.update()

    def paintEvent(self, event):
        """
        绘制事件 - 使用双缓冲避免闪烁

        绘制流程：
        1. 如果有帧数据，缩放并居中绘制
        2. 否则显示占位文本
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # 填充背景
        painter.fillRect(self.rect(), QColor(0, 0, 0))

        if self._display_image and not self._display_image.isNull():
            # 计算缩放后的尺寸（保持宽高比）
            scaled_size = self._display_image.size()
            scaled_size.scale(self.size(), Qt.AspectRatioMode.KeepAspectRatio)

            # 计算居中位置
            x = (self.width() - scaled_size.width()) // 2
            y = (self.height() - scaled_size.height()) // 2

            # 绘制图像
            scaled_image = self._display_image.scaled(
                scaled_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            painter.drawImage(x, y, scaled_image)
        else:
            # 显示占位文本
            painter.setPen(QPen(QColor(128, 128, 128)))
            painter.setFont(QFont("Arial", 16))

            # 绘制边框
            pen = QPen(QColor(64, 64, 64))
            pen.setWidth(2)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(self.rect().adjusted(1, 1, -1, -1))

            # 绘制文本
            painter.setPen(QPen(QColor(128, 128, 128)))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "投屏功能待实现\n\nTODO: Screen Mirroring"
            )

        painter.end()
