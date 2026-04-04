"""
Arknights Auto Machine - 主窗口 (PyQt5 实现)
"""

from PyQt5.QtWidgets import (
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
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

import sys
import os
from datetime import datetime

from gui.abstract import IMainWindow

from .screen_view import ScreenView


class MainWindow(QMainWindow, IMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        self.initUI()
    
    def initUI(self):
        self.setWindowTitle('Arknights Auto Machine')
        self.resize(1000, 600)
        
        # 判断系统是否为 Linux 平铺窗口管理器
        if sys.platform.startswith("linux"):
            wm_list = ["i3", "Hyprland", "sway", "bspwm"]
            is_tiling_wm = False
            for wm in wm_list:
                if wm in os.environ.get("XDG_CURRENT_DESKTOP", ""):
                    is_tiling_wm = True
                    break
            if is_tiling_wm:
                self.setFixedSize(self.width(), self.height())
        
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
        
        self.show()
    
    def _create_left_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.screen_view = ScreenView()
        layout.addWidget(self.screen_view)
        
        return panel
    
    def _create_right_panel(self) -> QWidget:
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
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")
    
    def _apply_style(self):
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
        super().show()
    
    def hide(self):
        super().hide()
    
    def close(self):
        super().close()
    
    def closeEvent(self, event):
        event.accept()