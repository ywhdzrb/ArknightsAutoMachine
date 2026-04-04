# -*- coding: utf-8 -*-
"""
Arknights Auto Machine (AAM) - 设备缓存模块

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

import time
from typing import Optional, Callable, List, Dict, Any
from dataclasses import dataclass, field

from gui.abstract import DeviceInfo


@dataclass
class CacheEntry:
    """缓存条目"""
    data: Any
    timestamp: float
    ttl: float  # 生存时间（秒）


class DeviceCache:
    """
    设备列表缓存

    提供带 TTL 的缓存机制，避免频繁调用 adb 命令
    """

    def __init__(self, ttl: float = 5.0):
        """
        初始化缓存

        Args:
            ttl: 缓存生存时间（秒），默认 5 秒
        """
        self._cache: Dict[str, CacheEntry] = {}
        self._ttl = ttl
        self._device_list_key = "device_list"

    def get_devices(self) -> Optional[List[DeviceInfo]]:
        """
        获取缓存的设备列表

        Returns:
            如果缓存有效返回设备列表，否则返回 None
        """
        entry = self._cache.get(self._device_list_key)
        if entry is None:
            return None

        # 检查是否过期
        if time.time() - entry.timestamp > entry.ttl:
            return None

        return entry.data

    def set_devices(self, devices: List[DeviceInfo]) -> None:
        """
        设置设备列表缓存

        Args:
            devices: 设备列表
        """
        self._cache[self._device_list_key] = CacheEntry(
            data=devices,
            timestamp=time.time(),
            ttl=self._ttl
        )

    def invalidate(self) -> None:
        """使缓存失效"""
        self._cache.pop(self._device_list_key, None)

    def clear(self) -> None:
        """清空所有缓存"""
        self._cache.clear()
