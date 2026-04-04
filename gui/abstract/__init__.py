# -*- coding: utf-8 -*-
"""
Arknights Auto Machine (AAM) - GUI 抽象层

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

定义 GUI 层的抽象接口，实现核心与具体 GUI 框架的解耦。
"""

from typing import Optional, Callable, List, Protocol, runtime_checkable
from enum import IntEnum
from dataclasses import dataclass
from typing_extensions import TypedDict

import numpy as np
from numpy.typing import NDArray


class ConnectionState(IntEnum):
    """连接状态"""
    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2
    STREAMING = 3
    ERROR = 4


class DeviceInfoDict(TypedDict):
    """设备信息字典类型"""
    device_id: str
    model: str
    name: str


@dataclass
class DeviceInfo:
    """设备信息"""
    device_id: str
    model: str = ""
    name: str = ""

    def __str__(self) -> str:
        if self.model:
            return f"{self.device_id} ({self.model})"
        return self.device_id

    def to_dict(self) -> DeviceInfoDict:
        """转换为字典"""
        return {
            'device_id': self.device_id,
            'model': self.model,
            'name': self.name
        }


class ScreenMirrorError(Exception):
    """投屏错误"""
    pass


class IScreenMirrorClient(Protocol):
    """
    投屏客户端抽象接口

    定义设备投屏的基本操作
    """

    @property
    def state(self) -> ConnectionState:
        """获取当前连接状态"""
        ...

    @property
    def device_width(self) -> int:
        """获取设备屏幕宽度"""
        ...

    @property
    def device_height(self) -> int:
        """获取设备屏幕高度"""
        ...

    def set_frame_callback(self, callback: Callable[[NDArray], None]) -> None:
        """设置帧回调函数"""
        ...

    def set_state_callback(self, callback: Callable[[ConnectionState], None]) -> None:
        """设置状态回调函数"""
        ...

    def set_log_callback(self, callback: Callable[[str, str], None]) -> None:
        """设置日志回调函数"""
        ...

    def connect(self, device: Optional[str] = None) -> None:
        """连接设备"""
        ...

    def disconnect(self) -> None:
        """断开连接"""
        ...

    def get_frame(self) -> Optional[NDArray]:
        """获取当前帧"""
        ...

    def list_devices(self) -> List[DeviceInfo]:
        """列出所有已连接的设备"""
        ...

    def __enter__(self) -> 'IScreenMirrorClient':
        """上下文管理器入口"""
        ...

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """上下文管理器出口"""
        ...


class IScreenView(Protocol):
    """
    投屏视图抽象接口

    定义投屏显示组件的基本操作
    """

    def get_frame(self) -> Optional[NDArray]:
        """获取当前帧"""
        ...

    def get_client(self) -> IScreenMirrorClient:
        """获取客户端实例"""
        ...

    def is_connected(self) -> bool:
        """检查是否已连接"""
        ...

    def connect_device(self, device_id: str) -> None:
        """连接指定设备"""
        ...

    def disconnect(self) -> None:
        """断开连接"""
        ...

    def list_devices(self) -> List[DeviceInfo]:
        """列出所有已连接的设备"""
        ...

    @property
    def device_width(self) -> int:
        """获取设备屏幕宽度"""
        ...

    @property
    def device_height(self) -> int:
        """获取设备屏幕高度"""
        ...


class IMainWindow(Protocol):
    """
    主窗口抽象接口

    定义主窗口的基本操作
    """

    def show(self) -> None:
        """显示窗口"""
        ...

    def hide(self) -> None:
        """隐藏窗口"""
        ...

    def close(self) -> None:
        """关闭窗口"""
        ...

    def set_title(self, title: str) -> None:
        """设置窗口标题"""
        ...

    def set_status(self, message: str) -> None:
        """设置状态栏消息"""
        ...


__all__ = [
    'ConnectionState',
    'DeviceInfo',
    'DeviceInfoDict',
    'ScreenMirrorError',
    'IScreenMirrorClient',
    'IScreenView',
    'IMainWindow',
]
