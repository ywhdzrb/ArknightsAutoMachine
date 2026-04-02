"""
窗口工具函数 - 用于检测和枚举系统窗口

提供功能:
- 枚举所有可见窗口
- 获取窗口信息（标题、类名、PID、矩形）
- 查找模拟器窗口
- 窗口匹配和筛选
"""

import ctypes
import ctypes.wintypes as wintypes
import logging
from dataclasses import dataclass
from typing import List, Optional, Callable, Tuple

logger = logging.getLogger(__name__)


@dataclass
class WindowInfo:
    """窗口信息数据类"""
    hwnd: int
    title: str
    class_name: str
    pid: int
    rect: Tuple[int, int, int, int]  # left, top, right, bottom
    client_rect: Tuple[int, int, int, int]
    is_visible: bool
    is_minimized: bool
    width: int
    height: int


class WindowEnumerator:
    """窗口枚举器"""
    
    # 常见模拟器窗口类名
    EMULATOR_CLASS_NAMES = [
        "Qt5QWindowIcon",           # MuMu 模拟器
        "Qt6QWindowIcon",           # MuMu 模拟器新版
        "NoxPlayer",                # 夜神模拟器
        "LDPlayerMainFrame",        # 雷电模拟器
        "BlueStacksApp",            # 蓝叠模拟器
        "MEmuPlayer",               # 逍遥模拟器
        "SmartGaGa",                # 天天模拟器
        "TPlayer",                  # 腾讯手游助手
        "WindowIcon",               # 通用 Qt 窗口
    ]
    
    # 常见模拟器标题关键词
    EMULATOR_TITLE_KEYWORDS = [
        "MuMu", "mumu", "网易MuMu", "MuMu模拟器",
        "BlueStacks", "蓝叠", "蓝叠模拟器",
        "Nox", "夜神", "夜神模拟器",
        "LDPlayer", "雷电", "雷电模拟器",
        "MEmu", "逍遥", "逍遥模拟器",
        "SmartGaGa", "天天", "天天模拟器",
        "腾讯手游助手", "GameLoop",
        "Android Emulator", "模拟器",
    ]
    
    def __init__(self):
        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32
        self._setup_api()
    
    def _setup_api(self) -> None:
        """设置 API 函数原型"""
        # User32
        self._user32.EnumWindows.argtypes = [
            ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM),
            wintypes.LPARAM
        ]
        self._user32.EnumWindows.restype = wintypes.BOOL
        
        self._user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self._user32.GetWindowTextW.restype = ctypes.c_int
        
        self._user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self._user32.GetClassNameW.restype = ctypes.c_int
        
        self._user32.IsWindow.argtypes = [wintypes.HWND]
        self._user32.IsWindow.restype = wintypes.BOOL
        
        self._user32.IsWindowVisible.argtypes = [wintypes.HWND]
        self._user32.IsWindowVisible.restype = wintypes.BOOL
        
        self._user32.IsIconic.argtypes = [wintypes.HWND]
        self._user32.IsIconic.restype = wintypes.BOOL
        
        self._user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self._user32.GetWindowRect.restype = wintypes.BOOL
        
        self._user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self._user32.GetClientRect.restype = wintypes.BOOL
        
        self._user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        self._user32.ClientToScreen.restype = wintypes.BOOL
        
        self._user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self._user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    
    def _get_window_title(self, hwnd: int) -> str:
        """获取窗口标题"""
        buffer = ctypes.create_unicode_buffer(256)
        length = self._user32.GetWindowTextW(hwnd, buffer, 256)
        return buffer.value if length > 0 else ""
    
    def _get_window_class(self, hwnd: int) -> str:
        """获取窗口类名"""
        buffer = ctypes.create_unicode_buffer(256)
        length = self._user32.GetClassNameW(hwnd, buffer, 256)
        return buffer.value if length > 0 else ""
    
    def _get_window_pid(self, hwnd: int) -> int:
        """获取窗口进程 ID"""
        pid = wintypes.DWORD()
        self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value
    
    def _get_window_rect(self, hwnd: int) -> Tuple[int, int, int, int]:
        """获取窗口矩形"""
        rect = wintypes.RECT()
        if self._user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return (rect.left, rect.top, rect.right, rect.bottom)
        return (0, 0, 0, 0)
    
    def _get_client_rect(self, hwnd: int) -> Tuple[int, int, int, int]:
        """获取客户区矩形"""
        client = wintypes.RECT()
        if not self._user32.GetClientRect(hwnd, ctypes.byref(client)):
            return (0, 0, 0, 0)
        
        # 转换到屏幕坐标
        pt = wintypes.POINT()
        pt.x = client.left
        pt.y = client.top
        self._user32.ClientToScreen(hwnd, ctypes.byref(pt))
        
        left, top = pt.x, pt.y
        right = left + (client.right - client.left)
        bottom = top + (client.bottom - client.top)
        
        return (left, top, right, bottom)
    
    def enumerate_windows(
        self,
        visible_only: bool = True,
        filter_func: Optional[Callable[[int], bool]] = None
    ) -> List[WindowInfo]:
        """枚举所有窗口
        
        Args:
            visible_only: 是否只枚举可见窗口
            filter_func: 自定义过滤函数，接收 hwnd 返回 bool
            
        Returns:
            WindowInfo 列表
        """
        windows = []
        
        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def enum_callback(hwnd, lparam):
            # 检查窗口是否有效
            if not self._user32.IsWindow(hwnd):
                return True
            
            # 检查可见性
            if visible_only and not self._user32.IsWindowVisible(hwnd):
                return True
            
            # 应用自定义过滤
            if filter_func and not filter_func(hwnd):
                return True
            
            # 获取窗口信息
            title = self._get_window_title(hwnd)
            class_name = self._get_window_class(hwnd)
            
            # 获取PID用于调试
            pid = self._get_window_pid(hwnd)

            # 跳过无标题窗口（通常是系统窗口）
            if not title and not class_name:
                logger.debug(f"跳过无标题窗口: hwnd={hwnd}, pid={pid}")
                return True
            rect = self._get_window_rect(hwnd)
            client_rect = self._get_client_rect(hwnd)
            is_minimized = self._user32.IsIconic(hwnd)
            
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]
            
            # 记录小窗口但不过滤（可能是最小化的模拟器窗口）
            if width < 100 or height < 100:
                logger.debug(f"小窗口: {title[:30] if title else '无标题'} hwnd={hwnd} pid={pid} size={width}x{height} minimized={is_minimized}")
                # 不再跳过，让最小化窗口也显示在列表中
            
            info = WindowInfo(
                hwnd=hwnd,
                title=title,
                class_name=class_name,
                pid=pid,
                rect=rect,
                client_rect=client_rect,
                is_visible=self._user32.IsWindowVisible(hwnd),
                is_minimized=is_minimized,
                width=width,
                height=height
            )
            
            windows.append(info)
            return True
        
        self._user32.EnumWindows(enum_callback, 0)
        return windows
    
    def find_emulator_windows(self) -> List[WindowInfo]:
        """查找模拟器窗口
        
        Returns:
            模拟器窗口信息列表
        """
        all_windows = self.enumerate_windows(visible_only=True)
        emulator_windows = []
        
        for window in all_windows:
            # 检查类名
            if any(name.lower() in window.class_name.lower() for name in self.EMULATOR_CLASS_NAMES):
                emulator_windows.append(window)
                continue
            
            # 检查标题关键词
            if any(keyword.lower() in window.title.lower() for keyword in self.EMULATOR_TITLE_KEYWORDS):
                emulator_windows.append(window)
                continue
        
        return emulator_windows
    
    def find_window_by_title(self, title_keyword: str) -> Optional[WindowInfo]:
        """通过标题关键词查找窗口
        
        Args:
            title_keyword: 标题关键词（部分匹配）
            
        Returns:
            WindowInfo 或 None
        """
        windows = self.enumerate_windows(visible_only=True)
        
        for window in windows:
            if title_keyword.lower() in window.title.lower():
                return window
        
        return None
    
    def find_window_by_hwnd(self, hwnd: int) -> Optional[WindowInfo]:
        """通过句柄查找窗口
        
        Args:
            hwnd: 窗口句柄
            
        Returns:
            WindowInfo 或 None
        """
        if not self._user32.IsWindow(hwnd):
            return None
        
        title = self._get_window_title(hwnd)
        class_name = self._get_window_class(hwnd)
        pid = self._get_window_pid(hwnd)
        rect = self._get_window_rect(hwnd)
        client_rect = self._get_client_rect(hwnd)
        
        return WindowInfo(
            hwnd=hwnd,
            title=title,
            class_name=class_name,
            pid=pid,
            rect=rect,
            client_rect=client_rect,
            is_visible=self._user32.IsWindowVisible(hwnd),
            is_minimized=self._user32.IsIconic(hwnd),
            width=rect[2] - rect[0],
            height=rect[3] - rect[1]
        )
    
    def get_window_display_name(self, window: WindowInfo) -> str:
        """获取窗口显示名称（用于下拉框）

        Args:
            window: 窗口信息

        Returns:
            格式化后的显示名称
        """
        title = window.title if window.title else "无标题"
        # 截断过长的标题
        if len(title) > 40:
            title = title[:37] + "..."

        # 标注最小化状态
        status = " [最小化]" if window.is_minimized else ""
        return f"{title}{status} (PID: {window.pid}, {window.width}x{window.height})"


# 全局枚举器实例
_window_enumerator: Optional[WindowEnumerator] = None


def get_window_enumerator() -> WindowEnumerator:
    """获取全局窗口枚举器实例"""
    global _window_enumerator
    if _window_enumerator is None:
        _window_enumerator = WindowEnumerator()
    return _window_enumerator


def enumerate_windows(visible_only: bool = True) -> List[WindowInfo]:
    """便捷函数：枚举所有窗口"""
    return get_window_enumerator().enumerate_windows(visible_only=visible_only)


def find_emulator_windows() -> List[WindowInfo]:
    """便捷函数：查找模拟器窗口"""
    return get_window_enumerator().find_emulator_windows()


def find_window_by_title(title_keyword: str) -> Optional[WindowInfo]:
    """便捷函数：通过标题查找窗口"""
    return get_window_enumerator().find_window_by_title(title_keyword)
