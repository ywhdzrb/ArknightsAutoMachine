# -*- coding: utf-8 -*-
"""
Arknights Auto Machine (AAM) - 主窗口 (PyQt6 实现)

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

import sys
import os
from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QGroupBox,
    QLabel,
    QTextEdit,
    QStatusBar
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from gui.abstract import IMainWindow, IScreenMirrorClient
from .screen_view import ScreenView


def is_tiling_window_manager() -> bool:
    """
    检测当前是否运行在平铺窗口管理器环境下

    通过检查多个环境变量来判断：
    - XDG_CURRENT_DESKTOP: 当前桌面环境
    - DESKTOP_SESSION: 当前桌面会话
    - I3SOCK: i3wm 的 socket 路径
    - HYPRLAND_INSTANCE_SIGNATURE: Hyprland 实例签名
    - SWAYSOCK: Sway 的 socket 路径

    Returns:
        bool: 如果检测到平铺窗口管理器返回 True
    """
    if not sys.platform.startswith("linux"):
        return False

    # 平铺窗口管理器特征列表
    tiling_wm_signatures = ["i3", "Hyprland", "sway", "bspwm", "dwm", "awesome", "xmonad"]

    # 归一化环境变量值进行检测
    def normalize_env(value: Optional[str]) -> str:
        return (value or "").lower().strip()

    # 检查 XDG_CURRENT_DESKTOP
    xdg_current_desktop = normalize_env(os.environ.get("XDG_CURRENT_DESKTOP", ""))
    for signature in tiling_wm_signatures:
        if signature.lower() in xdg_current_desktop:
            return True

    # 检查 DESKTOP_SESSION
    desktop_session = normalize_env(os.environ.get("DESKTOP_SESSION", ""))
    for signature in tiling_wm_signatures:
        if signature.lower() in desktop_session:
            return True

    # 检查特定窗口管理器的环境变量
    # i3wm
    if os.environ.get("I3SOCK"):
        return True
    # Hyprland
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return True
    # Sway
    if os.environ.get("SWAYSOCK"):
        return True

    return False


class MainWindow(QMainWindow, IMainWindow):
    """主窗口"""

    def __init__(self, screen_client: Optional[IScreenMirrorClient] = None):
        """
        初始化主窗口

        Args:
            screen_client: 可选的投屏客户端实例（依赖注入）
        """
        super().__init__()
        self._screen_client = screen_client
        self._init_ui()

    def _init_ui(self):
        """初始化UI"""
        self.setWindowTitle('Arknights Auto Machine')
        self.resize(1000, 600)

        # 平铺窗口管理器检测
        if is_tiling_window_manager():
            # 使用 setMinimumSize + resize 代替 setFixedSize
            # 允许用户在需要时调整窗口大小
            self.setMinimumSize(800, 500)

        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # 创建分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：投屏视图
        left_panel = self._create_left_panel()
        splitter.addWidget(left_panel)

        # 右侧：控制面板
        right_panel = self._create_right_panel()
        splitter.addWidget(right_panel)

        # 设置分割比例
        splitter.setSizes([800, 400])

        main_layout.addWidget(splitter)

        # 创建状态栏
        self._create_status_bar()

        # 设置样式
        self._apply_style()

    def _create_left_panel(self) -> QWidget:
        """创建左侧投屏面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        # 使用依赖注入的客户端或创建默认客户端
        self.screen_view = ScreenView(client=self._screen_client)
        layout.addWidget(self.screen_view)

        return panel

    def _create_right_panel(self) -> QWidget:
        """创建右侧控制面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 状态信息组
        status_group = QGroupBox("状态信息")
        status_layout = QVBoxLayout(status_group)

        self.status_label = QLabel("投屏功能待实现")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold;")

        status_layout.addWidget(self.status_label)

        layout.addWidget(status_group)

        # 日志面板组
        log_group = QGroupBox("日志")
        log_layout = QVBoxLayout(log_group)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 10))

        log_layout.addWidget(self.log_text)

        layout.addWidget(log_group, 1)

        return panel

    def _create_status_bar(self):
        """创建状态栏"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")

    def _apply_style(self):
        """应用深色主题样式"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2b2b2b;
            }
            QWidget {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QGroupBox {
                border: 1px solid #555;
                border-radius: 4px;
                margin-top: 12px;
                padding-top: 8px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QPushButton {
                background-color: #404040;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 6px 12px;
                min-height: 20px;
            }
            QPushButton:hover {
                background-color: #505050;
            }
            QPushButton:pressed {
                background-color: #606060;
            }
            QPushButton:disabled {
                background-color: #333;
                color: #666;
            }
            QTextEdit {
                background-color: #1e1e1e;
                border: 1px solid #555;
                border-radius: 4px;
            }
            QLabel {
                background-color: transparent;
            }
            QStatusBar {
                background-color: #333;
                border-top: 1px solid #555;
            }
        """)

    def _log(self, message: str, level: str = "INFO"):
        """
        添加日志消息

        Args:
            message: 日志消息
            level: 日志级别 (INFO/WARNING/ERROR/SUCCESS)
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        color_map = {
            "INFO": "#4fc3f7",
            "WARNING": "#ffb74d",
            "ERROR": "#e57373",
            "SUCCESS": "#81c784"
        }
        color = color_map.get(level, "#ffffff")
        self.log_text.append(
            f'<span style="color: #888;">[{timestamp}]</span> '
            f'<span style="color: {color};">[{level}]</span> {message}'
        )
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    # ========== IMainWindow 接口实现 ==========

    def show(self):
        """显示窗口"""
        super().show()

    def hide(self):
        """隐藏窗口"""
        super().hide()

    def close(self):
        """关闭窗口"""
        super().close()

    def set_title(self, title: str) -> None:
        """设置窗口标题"""
        self.setWindowTitle(title)

    def set_status(self, message: str) -> None:
        """设置状态栏消息"""
        self.status_bar.showMessage(message)

    def closeEvent(self, event):
        """窗口关闭事件"""
        # 清理资源
        if hasattr(self, 'screen_view'):
            self.screen_view.cleanup()
        event.accept()
