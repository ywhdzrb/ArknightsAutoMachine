"""
高性能窗口截图捕获器

支持多种截图方式：
- Windows Graphics Capture (WGC): Windows 10 1903+，GPU 加速，支持 HDR，自动剔除边框
- DXGI Desktop Duplication: 高性能，但需要全屏或独占模式
- BitBlt: 传统 GDI 方式，兼容性最好
- PrintWindow: 支持后台窗口截图

性能对比（1920x1080）：
- WGC: ~5-10ms，GPU 加速，推荐首选
- DXGI: ~8-15ms，需要全屏
- BitBlt: ~20-40ms
- ADB screencap: ~500-1000ms
"""

import ctypes
import ctypes.wintypes as wintypes
import logging
import numpy as np
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Callable, Tuple, List, Dict, Any
from pathlib import Path
import threading

logger = logging.getLogger(__name__)

# Windows API 常量
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040
SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000
PW_RENDERFULLCONTENT = 0x00000002

# DWM API
DWMWA_EXTENDED_FRAME_BOUNDS = 9


class CaptureError(Exception):
    """截图操作异常基类"""
    pass


class WindowNotFoundError(CaptureError):
    """找不到指定窗口"""
    pass


class CaptureMethodNotAvailable(CaptureError):
    """截图方式不可用"""
    pass


class CaptureTimeoutError(CaptureError):
    """截图超时"""
    pass


class CaptureMethod(Enum):
    """截图方式枚举"""
    AUTO = auto()           # 自动选择最佳方式
    WGC = auto()            # Windows Graphics Capture (Win10 1903+)
    DXGI = auto()           # DXGI Desktop Duplication
    BITBLT = auto()         # GDI BitBlt
    PRINTWINDOW = auto()    # PrintWindow API


@dataclass
class CaptureFrame:
    """截图帧数据结构
    
    Attributes:
        image_numpy: BGR 格式 numpy 数组 (OpenCV 标准)
        timestamp: 捕获时间戳
        latency_ms: 截图延迟
        resolution: (width, height)
        method: 使用的截图方式
    """
    image_numpy: np.ndarray
    timestamp: float
    latency_ms: float
    resolution: Tuple[int, int]
    method: CaptureMethod


@dataclass
class WindowInfo:
    """窗口信息
    
    Attributes:
        hwnd: 窗口句柄
        title: 窗口标题
        class_name: 窗口类名
        rect: (left, top, right, bottom) 窗口矩形（含边框）
        client_rect: (left, top, right, bottom) 客户区矩形（不含边框）
        is_visible: 是否可见
        is_minimized: 是否最小化
    """
    hwnd: int
    title: str
    class_name: str
    rect: Tuple[int, int, int, int]
    client_rect: Tuple[int, int, int, int]
    is_visible: bool
    is_minimized: bool


class WindowCapture:
    """高性能窗口截图捕获器
    
    自动选择最佳截图方式，支持模拟器窗口实时采集。
    
    使用示例:
        capture = WindowCapture("MuMu模拟器12")
        
        # 开始捕获
        capture.start()
        
        # 获取截图
        frame = capture.capture()
        if frame:
            print(f"截图延迟: {frame.latency_ms:.1f}ms")
            cv2.imshow("Capture", frame.image_numpy)
        
        # 停止捕获
        capture.stop()
    
    性能优化:
    - WGC 方式使用 GPU 加速，延迟最低
    - 自动剔除窗口边框，只捕获客户区
    - 支持连续捕获模式，复用资源
    """
    
    def __init__(
        self,
        window_title: Optional[str] = None,
        window_class: Optional[str] = None,
        hwnd: Optional[int] = None,
        method: CaptureMethod = CaptureMethod.AUTO,
        client_only: bool = True,
        on_error: Optional[Callable[[Exception], None]] = None,
    ):
        """初始化窗口捕获器
        
        Args:
            window_title: 窗口标题（支持部分匹配）
            window_class: 窗口类名（精确匹配）
            hwnd: 直接指定窗口句柄（优先级最高）
            method: 截图方式，AUTO 自动选择
            client_only: 是否只捕获客户区（剔除边框）
            on_error: 错误回调函数
        """
        self._window_title = window_title
        self._window_class = window_class
        self._target_hwnd = hwnd
        self._method = method
        self._client_only = client_only
        self._on_error = on_error
        
        self._hwnd: Optional[int] = None
        self._current_method: CaptureMethod = method
        self._capture_impl: Optional[Any] = None
        
        # 状态
        self._running = False
        self._lock = threading.Lock()
        
        # 统计
        self._stats = {
            'total_captures': 0,
            'failed_captures': 0,
            'avg_latency_ms': 0.0,
        }
        
        # 初始化 Windows API
        self._init_winapi()
        
        # 查找窗口
        self._find_window()
    
    def _init_winapi(self) -> None:
        """初始化 Windows API 函数"""
        # User32
        self._user32 = ctypes.windll.user32
        self._gdi32 = ctypes.windll.gdi32
        self._dwmapi = ctypes.windll.dwmapi
        
        # 设置函数原型
        self._user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        self._user32.FindWindowW.restype = wintypes.HWND
        
        self._user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
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
        
        self._user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        self._user32.SetWindowPos.restype = wintypes.BOOL
        
        self._user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        self._user32.SetForegroundWindow.restype = wintypes.BOOL
        
        self._user32.GetDC.argtypes = [wintypes.HWND]
        self._user32.GetDC.restype = wintypes.HDC
        
        self._user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        self._user32.ReleaseDC.restype = ctypes.c_int
        
        # GDI32
        self._gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
        self._gdi32.CreateCompatibleDC.restype = wintypes.HDC
        
        self._gdi32.DeleteDC.argtypes = [wintypes.HDC]
        self._gdi32.DeleteDC.restype = wintypes.BOOL
        
        self._gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
        self._gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
        
        self._gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        self._gdi32.DeleteObject.restype = wintypes.BOOL
        
        self._gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
        self._gdi32.SelectObject.restype = wintypes.HGDIOBJ
        
        self._gdi32.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
        self._gdi32.BitBlt.restype = wintypes.BOOL
        
        self._gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
        self._gdi32.GetDIBits.restype = ctypes.c_int
        
        # DWM API
        self._dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
        self._dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long
    
    def _find_window(self) -> None:
        """查找目标窗口"""
        if self._target_hwnd:
            # 直接使用指定句柄
            if self._user32.IsWindow(self._target_hwnd):
                self._hwnd = self._target_hwnd
                logger.info(f"使用指定窗口句柄: {self._hwnd}")
                return
            else:
                raise WindowNotFoundError(f"无效的窗口句柄: {self._target_hwnd}")
        
        # 通过类名查找
        if self._window_class:
            hwnd = self._user32.FindWindowW(self._window_class, None)
            if hwnd:
                self._hwnd = hwnd
                logger.info(f"通过类名找到窗口: {self._window_class}, hwnd={hwnd}")
                return
        
        # 通过标题查找
        if self._window_title:
            hwnd = self._find_window_by_title(self._window_title)
            if hwnd:
                self._hwnd = hwnd
                title = self._get_window_title(hwnd)
                logger.info(f"通过标题找到窗口: '{title}', hwnd={hwnd}")
                return
        
        raise WindowNotFoundError(
            f"找不到窗口: title='{self._window_title}', class='{self._window_class}'"
        )
    
    def _find_window_by_title(self, title: str) -> Optional[int]:
        """通过标题查找窗口（支持部分匹配）"""
        found_hwnd = None
        
        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def enum_callback(hwnd, lparam):
            nonlocal found_hwnd
            
            if not self._user32.IsWindowVisible(hwnd):
                return True
            
            window_title = self._get_window_title(hwnd)
            if title.lower() in window_title.lower():
                found_hwnd = hwnd
                return False  # 停止枚举
            
            return True
        
        self._user32.EnumWindows(enum_callback, 0)
        return found_hwnd
    
    def _get_window_title(self, hwnd: int) -> str:
        """获取窗口标题"""
        buffer = ctypes.create_unicode_buffer(256)
        self._user32.GetWindowTextW(hwnd, buffer, 256)
        return buffer.value
    
    def _get_window_class(self, hwnd: int) -> str:
        """获取窗口类名"""
        buffer = ctypes.create_unicode_buffer(256)
        self._user32.GetClassNameW(hwnd, buffer, 256)
        return buffer.value
    
    def _get_window_rect(self, hwnd: int) -> Tuple[int, int, int, int]:
        """获取窗口矩形（含边框）"""
        rect = wintypes.RECT()
        self._user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return (rect.left, rect.top, rect.right, rect.bottom)
    
    def _get_client_rect(self, hwnd: int) -> Tuple[int, int, int, int]:
        """获取客户区矩形（不含边框）"""
        # 获取客户区大小
        client = wintypes.RECT()
        self._user32.GetClientRect(hwnd, ctypes.byref(client))
        
        # 转换到屏幕坐标
        pt = wintypes.POINT()
        pt.x = client.left
        pt.y = client.top
        self._user32.ClientToScreen(hwnd, ctypes.byref(pt))
        
        left, top = pt.x, pt.y
        right = left + (client.right - client.left)
        bottom = top + (client.bottom - client.top)
        
        return (left, top, right, bottom)
    
    def _get_extended_frame_bounds(self, hwnd: int) -> Tuple[int, int, int, int]:
        """获取扩展框架边界（DWM 边框）"""
        rect = wintypes.RECT()
        result = self._dwmapi.DwmGetWindowAttribute(
            hwnd,
            DWMWA_EXTENDED_FRAME_BOUNDS,
            ctypes.byref(rect),
            ctypes.sizeof(rect)
        )
        
        if result == 0:  # S_OK
            return (rect.left, rect.top, rect.right, rect.bottom)
        else:
            # 回退到普通窗口矩形
            return self._get_window_rect(hwnd)
    
    def get_window_info(self) -> WindowInfo:
        """获取窗口详细信息"""
        if not self._hwnd or not self._user32.IsWindow(self._hwnd):
            raise WindowNotFoundError("窗口已关闭或无效")
        
        return WindowInfo(
            hwnd=self._hwnd,
            title=self._get_window_title(self._hwnd),
            class_name=self._get_window_class(self._hwnd),
            rect=self._get_window_rect(self._hwnd),
            client_rect=self._get_client_rect(self._hwnd),
            is_visible=self._user32.IsWindowVisible(self._hwnd),
            is_minimized=self._user32.IsIconic(self._hwnd),
        )
    
    def start(self) -> None:
        """启动捕获器，初始化截图方式"""
        logger.info(f"WindowCapture.start() 被调用 | hwnd={self._hwnd}")

        with self._lock:
            if self._running:
                logger.info("捕获器已在运行中")
                return

            # 验证窗口
            if not self._hwnd or not self._user32.IsWindow(self._hwnd):
                logger.info("查找窗口...")
                self._find_window()
                logger.info(f"找到窗口 | hwnd={self._hwnd}")

            # 选择并初始化截图方式
            logger.info("选择截图方式...")
            self._select_and_init_method()

            self._running = True
            logger.info(f"窗口捕获器已启动 | 方法: {self._current_method.name} | 窗口: {self._get_window_title(self._hwnd)}")
    
    def _select_and_init_method(self) -> None:
        """选择并初始化最佳截图方式"""
        methods_to_try = []
        
        if self._method == CaptureMethod.AUTO:
            # 自动选择：BitBlt > WGC（BitBlt更稳定，WGC可能卡住）
            methods_to_try = [CaptureMethod.BITBLT, CaptureMethod.WGC]
        else:
            methods_to_try = [self._method]
        
        for method in methods_to_try:
            try:
                self._init_capture_method(method)
                self._current_method = method
                return
            except Exception as e:
                logger.debug(f"{method.name} 初始化失败: {e}")
                continue
        
        raise CaptureMethodNotAvailable("没有可用的截图方式")
    
    def _init_capture_method(self, method: CaptureMethod) -> None:
        """初始化指定截图方式"""
        if method == CaptureMethod.WGC:
            from .wgc_capture import WGCCapture
            self._capture_impl = WGCCapture(self._hwnd, self._client_only)
        elif method == CaptureMethod.BITBLT:
            self._capture_impl = BitBltCapture(self, self._hwnd, self._client_only)
        elif method == CaptureMethod.PRINTWINDOW:
            self._capture_impl = PrintWindowCapture(self, self._hwnd, self._client_only)
        else:
            raise CaptureMethodNotAvailable(f"不支持的截图方式: {method}")
    
    def stop(self) -> None:
        """停止捕获器"""
        with self._lock:
            if not self._running:
                return
            
            self._running = False
            
            if self._capture_impl:
                try:
                    self._capture_impl.cleanup()
                except Exception as e:
                    logger.debug(f"清理截图方式失败: {e}")
                finally:
                    self._capture_impl = None
            
            logger.info("窗口捕获器已停止")
    
    def capture(self, timeout_ms: float = 1000.0) -> Optional[CaptureFrame]:
        """执行截图
        
        Args:
            timeout_ms: 超时时间（毫秒）
            
        Returns:
            CaptureFrame 对象，失败返回 None
        """
        if not self._running:
            raise CaptureError("捕获器未启动，请先调用 start()")
        
        with self._lock:
            start_time = time.monotonic()
            
            try:
                # 检查窗口是否有效
                if not self._hwnd or not self._user32.IsWindow(self._hwnd):
                    logger.warning("窗口已关闭，尝试重新查找")
                    self._find_window()
                    if self._capture_impl:
                        self._capture_impl.update_hwnd(self._hwnd)
                
                # 执行截图
                result = self._capture_impl.capture()
                
                if result is not None:
                    latency_ms = (time.monotonic() - start_time) * 1000
                    h, w = result.shape[:2]
                    
                    frame = CaptureFrame(
                        image_numpy=result,
                        timestamp=start_time,
                        latency_ms=latency_ms,
                        resolution=(w, h),
                        method=self._current_method,
                    )
                    
                    # 更新统计
                    self._stats['total_captures'] += 1
                    self._update_avg_latency(latency_ms)
                    
                    return frame
                else:
                    self._stats['failed_captures'] += 1
                    return None
                    
            except Exception as e:
                self._stats['failed_captures'] += 1
                if self._on_error:
                    self._on_error(e)
                raise
    
    def _update_avg_latency(self, latency_ms: float) -> None:
        """更新平均延迟（指数移动平均）"""
        alpha = 0.1
        self._stats['avg_latency_ms'] = (
            alpha * latency_ms + (1 - alpha) * self._stats['avg_latency_ms']
        )
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'method': self._current_method.name if self._running else 'STOPPED',
            'window_title': self._get_window_title(self._hwnd) if self._hwnd else None,
            'total_captures': self._stats['total_captures'],
            'failed_captures': self._stats['failed_captures'],
            'avg_latency_ms': round(self._stats['avg_latency_ms'], 2),
        }
    
    def is_running(self) -> bool:
        """检查捕获器是否运行中"""
        return self._running


class BitBltCapture:
    """BitBlt GDI 截图实现"""
    
    def __init__(self, parent: WindowCapture, hwnd: int, client_only: bool):
        self._parent = parent
        self._hwnd = hwnd
        self._client_only = client_only
        
        # 缓存 DC 和位图
        self._mem_dc = None
        self._bitmap = None
        self._bitmap_info = None
        self._width = 0
        self._height = 0
    
    def update_hwnd(self, hwnd: int) -> None:
        """更新窗口句柄"""
        self._hwnd = hwnd
        self._cleanup_resources()
    
    def _cleanup_resources(self) -> None:
        """清理 GDI 资源"""
        if self._bitmap:
            self._parent._gdi32.DeleteObject(self._bitmap)
            self._bitmap = None
        if self._mem_dc:
            self._parent._gdi32.DeleteDC(self._mem_dc)
            self._mem_dc = None
        self._width = 0
        self._height = 0
    
    def cleanup(self) -> None:
        """清理资源"""
        self._cleanup_resources()
    
    def capture(self) -> Optional[np.ndarray]:
        """执行 BitBlt 截图"""
        # 获取窗口矩形
        if self._client_only:
            left, top, right, bottom = self._parent._get_client_rect(self._hwnd)
        else:
            left, top, right, bottom = self._parent._get_window_rect(self._hwnd)
        
        width = right - left
        height = bottom - top
        
        if width <= 0 or height <= 0:
            logger.warning(f"无效的窗口大小: {width}x{height}")
            return None
        
        # 检查是否需要重新创建资源
        if width != self._width or height != self._height:
            self._cleanup_resources()
            self._width = width
            self._height = height
        
        # 获取窗口 DC
        window_dc = self._parent._user32.GetDC(self._hwnd if self._client_only else 0)
        if not window_dc:
            logger.warning("获取窗口 DC 失败")
            return None
        
        try:
            # 创建兼容 DC
            if not self._mem_dc:
                self._mem_dc = self._parent._gdi32.CreateCompatibleDC(window_dc)
                if not self._mem_dc:
                    logger.warning("创建兼容 DC 失败")
                    return None
            
            # 创建兼容位图
            if not self._bitmap:
                self._bitmap = self._parent._gdi32.CreateCompatibleBitmap(window_dc, width, height)
                if not self._bitmap:
                    logger.warning("创建兼容位图失败")
                    return None
                
                # 选入位图
                self._parent._gdi32.SelectObject(self._mem_dc, self._bitmap)
                
                # 准备 BITMAPINFO
                class BITMAPINFOHEADER(ctypes.Structure):
                    _fields_ = [
                        ("biSize", ctypes.c_uint32),
                        ("biWidth", ctypes.c_long),
                        ("biHeight", ctypes.c_long),
                        ("biPlanes", ctypes.c_uint16),
                        ("biBitCount", ctypes.c_uint16),
                        ("biCompression", ctypes.c_uint32),
                        ("biSizeImage", ctypes.c_uint32),
                        ("biXPelsPerMeter", ctypes.c_long),
                        ("biYPelsPerMeter", ctypes.c_long),
                        ("biClrUsed", ctypes.c_uint32),
                        ("biClrImportant", ctypes.c_uint32),
                    ]
                
                class BITMAPINFO(ctypes.Structure):
                    _fields_ = [
                        ("bmiHeader", BITMAPINFOHEADER),
                        ("bmiColors", ctypes.c_uint32 * 3),
                    ]
                
                self._bitmap_info = BITMAPINFO()
                self._bitmap_info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                self._bitmap_info.bmiHeader.biWidth = width
                self._bitmap_info.bmiHeader.biHeight = -height  # 顶-down
                self._bitmap_info.bmiHeader.biPlanes = 1
                self._bitmap_info.bmiHeader.biBitCount = 24
                self._bitmap_info.bmiHeader.biCompression = 0
            
            # 执行 BitBlt
            src_x = 0 if self._client_only else left
            src_y = 0 if self._client_only else top
            
            result = self._parent._gdi32.BitBlt(
                self._mem_dc, 0, 0, width, height,
                window_dc, src_x, src_y, SRCCOPY | CAPTUREBLT
            )
            
            if not result:
                logger.debug("BitBlt 失败")
                return None
            
            # 读取像素数据
            buffer_size = width * height * 3
            buffer = ctypes.create_string_buffer(buffer_size)
            
            result = self._parent._gdi32.GetDIBits(
                self._mem_dc, self._bitmap, 0, height,
                buffer, ctypes.byref(self._bitmap_info), 0
            )
            
            if result == 0:
                logger.warning("GetDIBits 失败")
                return None
            
            # 转换为 numpy 数组 (BGR)
            image = np.frombuffer(buffer, dtype=np.uint8).reshape((height, width, 3))
            
            return image
            
        finally:
            self._parent._user32.ReleaseDC(self._hwnd if self._client_only else 0, window_dc)


class PrintWindowCapture:
    """PrintWindow API 截图实现（支持后台窗口）"""
    
    PW_CLIENTONLY = 0x00000001
    PW_RENDERFULLCONTENT = 0x00000002
    
    def __init__(self, parent: WindowCapture, hwnd: int, client_only: bool):
        self._parent = parent
        self._hwnd = hwnd
        self._client_only = client_only
        
        # 设置 PrintWindow 原型
        self._user32 = parent._user32
        self._user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.c_uint]
        self._user32.PrintWindow.restype = wintypes.BOOL
        
        # 缓存
        self._mem_dc = None
        self._bitmap = None
        self._width = 0
        self._height = 0
    
    def update_hwnd(self, hwnd: int) -> None:
        self._hwnd = hwnd
        self._cleanup_resources()
    
    def _cleanup_resources(self) -> None:
        if self._bitmap:
            self._parent._gdi32.DeleteObject(self._bitmap)
            self._bitmap = None
        if self._mem_dc:
            self._parent._gdi32.DeleteDC(self._mem_dc)
            self._mem_dc = None
    
    def cleanup(self) -> None:
        self._cleanup_resources()
    
    def capture(self) -> Optional[np.ndarray]:
        """执行 PrintWindow 截图"""
        # 获取窗口大小
        if self._client_only:
            left, top, right, bottom = self._parent._get_client_rect(self._hwnd)
        else:
            left, top, right, bottom = self._parent._get_window_rect(self._hwnd)
        
        width = right - left
        height = bottom - top
        
        if width <= 0 or height <= 0:
            return None
        
        # 检查是否需要重新创建资源
        if width != self._width or height != self._height:
            self._cleanup_resources()
            self._width = width
            self._height = height
        
        # 创建 DC 和位图
        screen_dc = self._user32.GetDC(0)
        if not screen_dc:
            return None
        
        try:
            if not self._mem_dc:
                self._mem_dc = self._parent._gdi32.CreateCompatibleDC(screen_dc)
                self._bitmap = self._parent._gdi32.CreateCompatibleBitmap(screen_dc, width, height)
                self._parent._gdi32.SelectObject(self._mem_dc, self._bitmap)
            
            # 执行 PrintWindow
            flags = self.PW_RENDERFULLCONTENT
            if self._client_only:
                flags |= self.PW_CLIENTONLY
            
            result = self._user32.PrintWindow(self._hwnd, self._mem_dc, flags)
            
            if not result:
                logger.debug("PrintWindow 失败")
                return None
            
            # 读取位图数据
            # 简化实现：使用 BitBlt 方式读取
            return self._read_bitmap_data(width, height)
            
        finally:
            self._user32.ReleaseDC(0, screen_dc)
    
    def _read_bitmap_data(self, width: int, height: int) -> Optional[np.ndarray]:
        """读取位图数据为 numpy 数组"""
        # 准备 BITMAPINFO
        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", ctypes.c_uint32),
                ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long),
                ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16),
                ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32),
                ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long),
                ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32),
            ]
        
        class BITMAPINFO(ctypes.Structure):
            _fields_ = [
                ("bmiHeader", BITMAPINFOHEADER),
                ("bmiColors", ctypes.c_uint32 * 3),
            ]
        
        bitmap_info = BITMAPINFO()
        bitmap_info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bitmap_info.bmiHeader.biWidth = width
        bitmap_info.bmiHeader.biHeight = -height
        bitmap_info.bmiHeader.biPlanes = 1
        bitmap_info.bmiHeader.biBitCount = 24
        bitmap_info.bmiHeader.biCompression = 0
        
        buffer_size = width * height * 3
        buffer = ctypes.create_string_buffer(buffer_size)
        
        result = self._parent._gdi32.GetDIBits(
            self._mem_dc, self._bitmap, 0, height,
            buffer, ctypes.byref(bitmap_info), 0
        )
        
        if result == 0:
            return None
        
        image = np.frombuffer(buffer, dtype=np.uint8).reshape((height, width, 3))
        return image
