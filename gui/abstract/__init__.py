"""
Arknights Auto Machine - GUI 抽象层

定义 GUI 层的抽象接口，实现核心与具体 GUI 框架的解耦。
"""

from typing import Optional, Callable, List
from enum import IntEnum
from dataclasses import dataclass

import numpy as np


class ConnectionState(IntEnum):
    """连接状态"""
    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2
    STREAMING = 3
    ERROR = 4


@dataclass
class DeviceInfo:
    """设备信息"""
    device_id: str
    model: str = ""
    name: str = ""
    
    def __str__(self):
        if self.model:
            return f"{self.device_id} ({self.model})"
        return self.device_id


class ScreenMirrorError(Exception):
    """投屏错误"""
    pass


class IScreenMirrorClient:
    """
    投屏客户端抽象接口
    
    定义设备投屏的基本操作
    """
    
    @property
    def state(self) -> ConnectionState:
        """获取当前连接状态"""
        raise NotImplementedError
    
    @property
    def device_width(self) -> int:
        """获取设备屏幕宽度"""
        raise NotImplementedError
    
    @property
    def device_height(self) -> int:
        """获取设备屏幕高度"""
        raise NotImplementedError
    
    def set_frame_callback(self, callback: Callable[[np.ndarray], None]):
        """设置帧回调函数"""
        raise NotImplementedError
    
    def set_state_callback(self, callback: Callable[[ConnectionState], None]):
        """设置状态回调函数"""
        raise NotImplementedError
    
    def set_log_callback(self, callback: Callable[[str, str], None]):
        """设置日志回调函数"""
        raise NotImplementedError
    
    def connect(self, device: Optional[str] = None):
        """连接设备"""
        raise NotImplementedError
    
    def disconnect(self):
        """断开连接"""
        raise NotImplementedError
    
    def get_frame(self) -> Optional[np.ndarray]:
        """获取当前帧"""
        raise NotImplementedError
    
    @staticmethod
    def list_devices() -> List[DeviceInfo]:
        """列出所有已连接的设备"""
        raise NotImplementedError


class IScreenView:
    """
    投屏视图抽象接口
    
    定义投屏显示组件的基本操作
    """
    
    def get_frame(self) -> Optional[np.ndarray]:
        """获取当前帧"""
        raise NotImplementedError
    
    def get_client(self) -> IScreenMirrorClient:
        """获取客户端实例"""
        raise NotImplementedError
    
    def is_connected(self) -> bool:
        """检查是否已连接"""
        raise NotImplementedError
    
    def connect_device(self, device_id: str):
        """连接指定设备"""
        raise NotImplementedError
    
    def disconnect(self):
        """断开连接"""
        raise NotImplementedError
    
    @staticmethod
    def list_devices() -> List[DeviceInfo]:
        """列出所有已连接的设备"""
        raise NotImplementedError
    
    @property
    def device_width(self) -> int:
        """获取设备屏幕宽度"""
        raise NotImplementedError
    
    @property
    def device_height(self) -> int:
        """获取设备屏幕高度"""
        raise NotImplementedError


class IMainWindow:
    """
    主窗口抽象接口
    
    定义主窗口的基本操作
    """
    
    def show(self):
        """显示窗口"""
        raise NotImplementedError
    
    def hide(self):
        """隐藏窗口"""
        raise NotImplementedError
    
    def close(self):
        """关闭窗口"""
        raise NotImplementedError


__all__ = [
    'ConnectionState',
    'DeviceInfo',
    'ScreenMirrorError',
    'IScreenMirrorClient',
    'IScreenView',
    'IMainWindow',
]