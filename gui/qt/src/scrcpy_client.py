"""
scrcpy 客户端模块 - 用于 Android 设备投屏

TODO: 待实现投屏功能
"""

from typing import Optional, Callable, List

import numpy as np

from gui.abstract import (
    IScreenMirrorClient,
    ConnectionState,
    DeviceInfo,
    ScreenMirrorError,
)


class ScrcpyClient(IScreenMirrorClient):
    """
    scrcpy 客户端 - 投屏功能接口
    
    TODO: 待实现
    """
    
    def __init__(self, max_size: int = 1280, bit_rate: int = 4000000, max_fps: int = 30):
        self._state = ConnectionState.DISCONNECTED
        self._device: Optional[str] = None
        self._frame_callback: Optional[Callable[[np.ndarray], None]] = None
        self._state_callback: Optional[Callable[[ConnectionState], None]] = None
        self._log_callback: Optional[Callable[[str, str], None]] = None
        
        # 设备信息
        self._device_width = 0
        self._device_height = 0
        
        # 配置
        self._max_size = max_size
        self._bit_rate = bit_rate
        self._max_fps = max_fps
    
    @property
    def state(self) -> ConnectionState:
        return self._state
    
    @property
    def device_width(self) -> int:
        return self._device_width
    
    @property
    def device_height(self) -> int:
        return self._device_height
    
    def set_frame_callback(self, callback: Callable[[np.ndarray], None]):
        self._frame_callback = callback
    
    def set_state_callback(self, callback: Callable[[ConnectionState], None]):
        self._state_callback = callback
    
    def set_log_callback(self, callback: Callable[[str, str], None]):
        self._log_callback = callback
    
    def _log(self, message: str, level: str = "INFO"):
        if self._log_callback:
            self._log_callback(message, level)
    
    def _update_state(self, state: ConnectionState):
        self._state = state
        if self._state_callback:
            self._state_callback(state)
    
    def connect(self, device: Optional[str] = None):
        raise NotImplementedError("投屏功能待实现")
    
    def disconnect(self):
        raise NotImplementedError("投屏功能待实现")
    
    def get_frame(self) -> Optional[np.ndarray]:
        raise NotImplementedError("投屏功能待实现")
    
    @staticmethod
    def list_devices() -> List[DeviceInfo]:
        raise NotImplementedError("投屏功能待实现")
