# -*- coding: utf-8 -*-
"""
Arknights Auto Machine (AAM) - scrcpy 客户端模块

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

from typing import Optional, Callable, List, Any
from dataclasses import dataclass, field
import json
from pathlib import Path
import subprocess
import time

from numpy.typing import NDArray
import numpy as np

from gui.abstract import (
    IScreenMirrorClient,
    ConnectionState,
    DeviceInfo,
    ScreenMirrorError,
)
from .device_cache import DeviceCache


@dataclass
class ScrcpyConfig:
    """
    scrcpy 客户端配置

    支持从 YAML/JSON 文件加载配置
    """

    # 视频参数
    max_size: int = 1280
    bit_rate: int = 4000000
    max_fps: int = 30

    # 连接参数
    timeout: float = 10.0
    retry_count: int = 3
    retry_delay: float = 1.0

    # 缓存参数
    device_cache_ttl: float = 5.0

    # 其他选项
    stay_awake: bool = True
    show_touches: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> 'ScrcpyConfig':
        """从字典创建配置"""
        return cls(
            max_size=data.get('max_size', 1280),
            bit_rate=data.get('bit_rate', 4000000),
            max_fps=data.get('max_fps', 30),
            timeout=data.get('timeout', 10.0),
            retry_count=data.get('retry_count', 3),
            retry_delay=data.get('retry_delay', 1.0),
            device_cache_ttl=data.get('device_cache_ttl', 5.0),
            stay_awake=data.get('stay_awake', True),
            show_touches=data.get('show_touches', False),
        )

    @classmethod
    def from_json(cls, path: Path) -> 'ScrcpyConfig':
        """从 JSON 文件加载配置"""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data.get('scrcpy', {}))

    @classmethod
    def from_yaml(cls, path: Path) -> 'ScrcpyConfig':
        """从 YAML 文件加载配置"""
        try:
            import yaml
            with open(path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            return cls.from_dict(data.get('scrcpy', {}))
        except ImportError:
            raise RuntimeError("需要安装 PyYAML: pip install pyyaml")


class ScrcpyClient(IScreenMirrorClient):
    """
    scrcpy 客户端 - 投屏功能接口

    实现基于 scrcpy 的 Android 设备投屏功能

    TODO: 待实现完整的 scrcpy 集成
    """

    def __init__(self, config: Optional[ScrcpyConfig] = None):
        """
        初始化 scrcpy 客户端

        Args:
            config: 配置对象，如果为 None 则使用默认配置
        """
        self._config = config or ScrcpyConfig()
        self._state = ConnectionState.DISCONNECTED
        self._device: Optional[str] = None
        self._frame_callback: Optional[Callable[[NDArray], None]] = None
        self._state_callback: Optional[Callable[[ConnectionState], None]] = None
        self._log_callback: Optional[Callable[[str, str], None]] = None

        # 设备信息
        self._device_width = 0
        self._device_height = 0

        # 设备缓存
        self._device_cache = DeviceCache(ttl=self._config.device_cache_ttl)

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def device_width(self) -> int:
        return self._device_width

    @property
    def device_height(self) -> int:
        return self._device_height

    def set_frame_callback(self, callback: Callable[[NDArray], None]) -> None:
        self._frame_callback = callback

    def set_state_callback(self, callback: Callable[[ConnectionState], None]) -> None:
        self._state_callback = callback

    def set_log_callback(self, callback: Callable[[str, str], None]) -> None:
        self._log_callback = callback

    def _log(self, message: str, level: str = "INFO") -> None:
        """记录日志"""
        if self._log_callback:
            self._log_callback(message, level)

    def _update_state(self, state: ConnectionState) -> None:
        """更新连接状态"""
        self._state = state
        if self._state_callback:
            self._state_callback(state)

    def _run_adb_command(self, args: List[str], timeout: float = None) -> Optional[str]:
        """
        执行 ADB 命令

        Args:
            args: 命令参数列表
            timeout: 超时时间

        Returns:
            命令输出，失败返回 None
        """
        try:
            result = subprocess.run(
                ['adb'] + args,
                capture_output=True,
                text=True,
                timeout=timeout or self._config.timeout
            )
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                self._log(f"ADB 命令失败: {result.stderr}", "ERROR")
                return None
        except subprocess.TimeoutExpired:
            self._log("ADB 命令超时", "ERROR")
            return None
        except FileNotFoundError:
            self._log("未找到 adb 命令，请确保 Android SDK 已安装", "ERROR")
            return None
        except Exception as e:
            self._log(f"ADB 命令执行错误: {e}", "ERROR")
            return None

    def connect(self, device: Optional[str] = None) -> None:
        """
        连接设备

        Args:
            device: 设备ID，如果为 None 则连接第一个可用设备

        Note:
            此方法是同步的，在 GUI 中使用时应考虑异步调用
        """
        raise NotImplementedError("投屏功能待实现")

    def disconnect(self) -> None:
        """断开连接"""
        raise NotImplementedError("投屏功能待实现")

    def get_frame(self) -> Optional[NDArray]:
        """获取当前帧"""
        raise NotImplementedError("投屏功能待实现")

    def list_devices(self) -> List[DeviceInfo]:
        """
        列出所有已连接的设备

        使用缓存机制减少 ADB 调用频率

        Returns:
            设备信息列表
        """
        # 尝试从缓存获取
        cached = self._device_cache.get_devices()
        if cached is not None:
            return cached

        # 执行 ADB 命令获取设备列表
        output = self._run_adb_command(['devices', '-l'])
        if output is None:
            return []

        devices = []
        lines = output.split('\n')
        for line in lines[1:]:  # 跳过标题行
            if not line.strip():
                continue

            parts = line.split()
            if len(parts) >= 2 and parts[1] == 'device':
                device_id = parts[0]

                # 解析设备信息
                model = ""
                name = ""
                for part in parts[2:]:
                    if part.startswith('model:'):
                        model = part[6:]
                    elif part.startswith('product:'):
                        name = part[8:]

                devices.append(DeviceInfo(
                    device_id=device_id,
                    model=model,
                    name=name
                ))

        # 更新缓存
        self._device_cache.set_devices(devices)

        return devices

    def __enter__(self) -> 'ScrcpyClient':
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """上下文管理器出口"""
        self.disconnect()
