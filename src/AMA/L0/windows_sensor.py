"""
L0感知执行层 - Windows高性能截图传感器(WindowsSensor)

职责:
- 使用 Windows Graphics Capture / BitBlt 实现超低延迟截图
- 专为模拟器优化，绕过 ADB screencap 的性能瓶颈
- 支持自动检测模拟器窗口并匹配
- 与 AdbSensor 接口兼容，可无缝替换

性能对比 (1920x1080):
- ADB screencap: 500-1000ms
- BitBlt: 20-40ms
- WGC: 5-10ms (推荐)

使用场景:
- 本地模拟器（MuMu、BlueStacks、LDPlayer等）
- 需要高帧率实时预览
- ADB 连接不稳定或速度慢

架构设计:
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│  GUI Preview │◄───│  FrameBuffer  │◄───│  WindowCapture  │
│  (降采样显示) │    │  (环形缓冲区) │    │ (WGC/BitBlt)   │
└─────────────┘    └──────────────┘    └─────────────────┘
                                              │
                                       ┌──────┴──────┐
                                       │  模拟器窗口  │
                                       │ (MuMu等)    │
                                       └─────────────┘
"""

import threading
import time
import logging
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Callable, Tuple, List, Dict, Any
from pathlib import Path
import numpy as np
import cv2
from PIL import Image, ImageTk
import ctypes

import sys
_from_path = Path(__file__).parent.parent.parent
if str(_from_path) not in sys.path:
    sys.path.insert(0, str(_from_path))
from common.capture import WindowCapture, CaptureMethod, CaptureFrame

logger = logging.getLogger(__name__)


class WindowsSensorState(Enum):
    """传感器运行状态枚举"""
    STOPPED = auto()
    STARTING = auto()
    RUNNING = auto()
    PAUSED = auto()
    ERROR = auto()
    STOPPING = auto()


@dataclass(frozen=True)
class WindowsFrameMetadata:
    """单帧截图的元数据信息"""
    timestamp: float
    sequence_number: int
    capture_latency_ms: float
    resolution: Tuple[int, int]
    method: str  # 'WGC', 'BitBlt', 'PrintWindow'


@dataclass
class WindowsScreenshotFrame:
    """完整的截图帧数据结构"""
    image_numpy: np.ndarray  # BGR 格式
    metadata: Optional[WindowsFrameMetadata] = None


@dataclass
class WindowsSensorConfig:
    """传感器配置参数集合"""
    target_fps: float = 30.0  # Windows 截图可以达到更高帧率
    max_buffer_size: int = 3  # 更小的缓冲区，因为截图很快
    auto_downsample: bool = True
    downsample_target_size: Tuple[int, int] = (960, 540)
    capture_method: CaptureMethod = CaptureMethod.AUTO
    client_only: bool = True  # 只捕获客户区（剔除边框）
    window_title_keywords: List[str] = field(default_factory=lambda: [
        "MuMu", "mumu", "模拟器", "Emulator",
        "BlueStacks", "蓝叠",
        "LDPlayer", "雷电",
        "Nox", "夜神",
        "MEmu", "逍遥",
        "SmartGaGa", "天天",
    ])
    fallback_to_adb: bool = True  # Windows 截图失败时回退到 ADB


DEFAULT_CONFIG = WindowsSensorConfig()


class WindowsSensorError(Exception):
    """传感器操作相关异常基类"""
    pass


class WindowNotFoundError(WindowsSensorError):
    """找不到模拟器窗口"""
    pass


class WindowsSensor:
    """Windows 高性能截图传感器

    专为模拟器优化的截图方案，使用 Windows Graphics Capture 或 BitBlt API，
    绕过 ADB screencap 的性能瓶颈。

    性能目标:
    - 单帧获取延迟 < 20ms (BitBlt) 或 < 10ms (WGC)
    - 目标帧率: 30 FPS
    - 内存占用 < 100MB

    线程模型:
    - 主线程: API 方法调用
    - 采集线程: 循环截图并填充缓冲区

    使用示例:
        # 自动查找模拟器窗口
        sensor = WindowsSensor()
        sensor.start()

        # 或者指定窗口标题
        sensor = WindowsSensor(window_title="MuMu模拟器12")
        sensor.start()

        # 获取截图
        while running:
            frame = sensor.get_latest_frame()
            if frame:
                process(frame.image_numpy)
            time.sleep(0.033)

        sensor.stop()
    """

    MIN_FRAME_INTERVAL_MS = 10.0  # 最小帧间隔，避免过度占用 CPU
    MAX_FRAME_INTERVAL_MS = 100.0

    def __init__(
        self,
        window_title: Optional[str] = None,
        window_class: Optional[str] = None,
        hwnd: Optional[int] = None,
        config: Optional[WindowsSensorConfig] = None,
        on_frame_callback: Optional[Callable[[WindowsScreenshotFrame], None]] = None,
        on_error_callback: Optional[Callable[[Exception], None]] = None,
    ):
        """初始化 Windows 截图传感器

        Args:
            window_title: 窗口标题（支持部分匹配），None 则自动查找
            window_class: 窗口类名，None 则自动查找
            hwnd: 直接指定窗口句柄（优先级最高）
            config: 传感器配置
            on_frame_callback: 新帧回调
            on_error_callback: 错误回调
        """
        self._window_title = window_title
        self._window_class = window_class
        self._target_hwnd = hwnd
        self._config = config or DEFAULT_CONFIG
        self._on_frame_callback = on_frame_callback
        self._on_error_callback = on_error_callback

        # 捕获器
        self._capture: Optional[WindowCapture] = None

        # 状态
        self._state = WindowsSensorState.STOPPED
        self._state_lock = threading.Lock()

        # 帧缓冲区
        self._frame_buffer: deque = deque(maxlen=self._config.max_buffer_size)
        self._buffer_lock = threading.Lock()
        self._latest_frame: Optional[WindowsScreenshotFrame] = None
        self._latest_frame_lock = threading.Lock()

        # 采集线程
        self._capture_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # 统计
        self._sequence_counter = 0
        self._counter_lock = threading.Lock()
        self._performance_stats: Dict[str, Any] = {
            'total_frames': 0,
            'success_frames': 0,
            'failed_frames': 0,
            'avg_latency_ms': 0.0,
            'min_latency_ms': float('inf'),
            'max_latency_ms': 0.0,
            'buffer_overflows': 0,
            'current_fps': 0.0,
            'capture_method': 'None',
        }
        self._stats_lock = threading.Lock()

        # 帧率计算
        self._fps_frame_count = 0
        self._fps_start_time = time.monotonic()
        self._fps_lock = threading.Lock()

        logger.info(
            f"WindowsSensor初始化 | 目标窗口: {window_title or '自动检测'} | "
            f"目标FPS: {self._config.target_fps} | 方法: {self._config.capture_method.name}"
        )

    def _find_emulator_window(self) -> WindowCapture:
        """自动查找模拟器窗口"""
        # 如果指定了 hwnd 或标题，直接使用
        if self._target_hwnd or self._window_title or self._window_class:
            return WindowCapture(
                window_title=self._window_title,
                window_class=self._window_class,
                hwnd=self._target_hwnd,
                method=self._config.capture_method,
                client_only=self._config.client_only,
            )

        # 自动查找
        for keyword in self._config.window_title_keywords:
            try:
                capture = WindowCapture(
                    window_title=keyword,
                    method=self._config.capture_method,
                    client_only=self._config.client_only,
                )
                logger.info(f"自动找到模拟器窗口: {keyword}")
                return capture
            except Exception:
                continue

        raise WindowNotFoundError(
            f"找不到模拟器窗口，尝试过的关键词: {self._config.window_title_keywords}"
        )

    def start(self, timeout: float = 10.0) -> bool:
        """启动传感器

        Args:
            timeout: 启动超时时间（秒）

        Returns:
            是否成功启动
        """
        logger.info(f"WindowsSensor.start() 被调用 | 目标窗口:{self._window_title or '自动检测'}")

        with self._state_lock:
            if self._state in (WindowsSensorState.RUNNING, WindowsSensorState.STARTING):
                logger.warning("传感器已在运行中")
                return True

            self._state = WindowsSensorState.STARTING

        try:
            # 创建捕获器
            logger.info("查找模拟器窗口...")
            self._capture = self._find_emulator_window()
            logger.info(f"找到窗口，开始启动捕获器...")

            logger.info("启动窗口捕获器...")
            self._capture.start()
            logger.info("窗口捕获器启动完成")

            # 获取实际使用的截图方式
            stats = self._capture.get_statistics()
            method = stats.get('method', 'Unknown')
            with self._stats_lock:
                self._performance_stats['capture_method'] = method

            logger.info(f"窗口捕获器已启动 | 方法: {method}")

            # 重置统计
            self._reset_statistics()

            # 启动采集线程
            self._stop_event.clear()
            self._capture_thread = threading.Thread(
                target=self._capture_loop,
                name="WindowsCaptureThread",
                daemon=True,
            )
            self._capture_thread.start()

            # 等待启动完成
            start_time = time.monotonic()
            while time.monotonic() - start_time < timeout:
                with self._state_lock:
                    if self._state == WindowsSensorState.RUNNING:
                        return True
                    elif self._state == WindowsSensorState.ERROR:
                        raise WindowsSensorError("采集线程启动失败")
                time.sleep(0.1)

            raise TimeoutError("传感器启动超时")

        except Exception as e:
            with self._state_lock:
                self._state = WindowsSensorState.ERROR
            logger.error(f"传感器启动失败: {e}")
            self._cleanup()
            raise

    def stop(self, timeout: float = 5.0) -> bool:
        """停止传感器

        Args:
            timeout: 停止超时时间（秒）

        Returns:
            是否成功停止
        """
        with self._state_lock:
            if self._state in (WindowsSensorState.STOPPED, WindowsSensorState.STOPPING):
                return True
            self._state = WindowsSensorState.STOPPING

        logger.info("正在停止Windows传感器...")
        self._stop_event.set()

        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=timeout)
            if self._capture_thread.is_alive():
                logger.warning("采集线程未在超时内结束")

        self._cleanup()

        with self._state_lock:
            self._state = WindowsSensorState.STOPPED

        logger.info("Windows传感器已停止")
        return True

    def _cleanup(self) -> None:
        """清理资源"""
        if self._capture:
            try:
                self._capture.stop()
            except Exception as e:
                logger.debug(f"清理捕获器失败: {e}")
            finally:
                self._capture = None

        with self._buffer_lock:
            self._frame_buffer.clear()

        with self._latest_frame_lock:
            self._latest_frame = None

    def _is_window_minimized(self) -> bool:
        """检测目标窗口是否最小化"""
        if not self._capture:
            return False

        try:
            hwnd = self._capture._hwnd
            if hwnd and hwnd != 0:
                # 使用 Windows API 检测窗口是否最小化
                user32 = ctypes.windll.user32
                return bool(user32.IsIconic(hwnd))
        except Exception:
            pass
        return False

    def _capture_loop(self) -> None:
        """采集线程主循环"""
        logger.info("采集线程已启动")

        with self._state_lock:
            self._state = WindowsSensorState.RUNNING

        target_interval = 1.0 / self._config.target_fps
        consecutive_failures = 0
        max_failures = 10
        was_minimized = False

        while not self._stop_event.is_set():
            loop_start = time.monotonic()

            try:
                # 检测窗口是否最小化
                is_minimized = self._is_window_minimized()

                if is_minimized:
                    if not was_minimized:
                        logger.warning("窗口已最小化，暂停截图")
                        was_minimized = True
                    # 窗口最小化时跳过截图，但保持循环
                    time.sleep(0.1)  # 100ms 检查一次
                    continue
                else:
                    if was_minimized:
                        logger.info("窗口已恢复，继续截图")
                        was_minimized = False

                # 执行截图
                frame = self._capture.capture(timeout_ms=1000.0)

                if frame:
                    self._process_successful_frame(frame)
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    if consecutive_failures >= max_failures:
                        logger.error(f"连续 {max_failures} 次截图失败，停止采集")
                        break

            except Exception as e:
                logger.error(f"截图异常: {e}")
                consecutive_failures += 1
                if self._on_error_callback:
                    try:
                        self._on_error_callback(e)
                    except Exception as cb_err:
                        logger.error(f"错误回调执行失败: {cb_err}")

                if consecutive_failures >= max_failures:
                    break

            # 控制帧率
            elapsed = time.monotonic() - loop_start
            sleep_time = target_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        with self._state_lock:
            if self._state != WindowsSensorState.STOPPING:
                self._state = WindowsSensorState.ERROR

        logger.info("采集线程已退出")

    def _process_successful_frame(self, frame: CaptureFrame) -> None:
        """处理成功获取的帧"""
        with self._counter_lock:
            self._sequence_counter += 1
            seq_num = self._sequence_counter

        # 降采样（如果需要）
        image = frame.image_numpy
        if self._config.auto_downsample:
            h, w = image.shape[:2]
            target_w, target_h = self._config.downsample_target_size
            if w > target_w or h > target_h:
                scale = min(target_w / w, target_h / h)
                new_w = int(w * scale)
                new_h = int(h * scale)
                image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)

        # 创建帧对象
        metadata = WindowsFrameMetadata(
            timestamp=frame.timestamp,
            sequence_number=seq_num,
            capture_latency_ms=frame.latency_ms,
            resolution=frame.resolution,
            method=frame.method.name,
        )

        screenshot_frame = WindowsScreenshotFrame(
            image_numpy=image,
            metadata=metadata,
        )

        # 更新缓冲区
        with self._buffer_lock:
            old_size = len(self._frame_buffer)
            self._frame_buffer.append(screenshot_frame)
            if len(self._frame_buffer) <= old_size:
                with self._stats_lock:
                    self._performance_stats['buffer_overflows'] += 1

        # 更新最新帧
        with self._latest_frame_lock:
            self._latest_frame = screenshot_frame

        # 更新统计
        self._update_statistics(frame.latency_ms)

        # 回调
        if self._on_frame_callback:
            try:
                self._on_frame_callback(screenshot_frame)
            except Exception as e:
                logger.error(f"帧回调执行失败: {e}")

    def _update_statistics(self, latency_ms: float) -> None:
        """更新性能统计"""
        with self._stats_lock:
            self._performance_stats['total_frames'] += 1
            self._performance_stats['success_frames'] += 1

            # 更新延迟统计
            stats = self._performance_stats
            stats['avg_latency_ms'] = 0.9 * stats['avg_latency_ms'] + 0.1 * latency_ms
            stats['min_latency_ms'] = min(stats['min_latency_ms'], latency_ms)
            stats['max_latency_ms'] = max(stats['max_latency_ms'], latency_ms)

        # 计算 FPS
        with self._fps_lock:
            self._fps_frame_count += 1
            elapsed = time.monotonic() - self._fps_start_time
            if elapsed >= 1.0:
                fps = self._fps_frame_count / elapsed
                with self._stats_lock:
                    self._performance_stats['current_fps'] = fps
                self._fps_frame_count = 0
                self._fps_start_time = time.monotonic()

    def _reset_statistics(self) -> None:
        """重置统计信息"""
        with self._stats_lock:
            self._performance_stats = {
                'total_frames': 0,
                'success_frames': 0,
                'failed_frames': 0,
                'avg_latency_ms': 0.0,
                'min_latency_ms': float('inf'),
                'max_latency_ms': 0.0,
                'buffer_overflows': 0,
                'current_fps': 0.0,
                'capture_method': self._performance_stats.get('capture_method', 'Unknown'),
            }

    def get_latest_frame(self, timeout: float = 0.0) -> Optional[WindowsScreenshotFrame]:
        """获取最新帧

        Args:
            timeout: 等待新帧的超时时间（秒），0 表示不等待

        Returns:
            最新帧，如果没有则返回 None
        """
        with self._latest_frame_lock:
            return self._latest_frame

    def get_frame_from_buffer(self) -> Optional[WindowsScreenshotFrame]:
        """从缓冲区获取一帧（FIFO）"""
        with self._buffer_lock:
            if self._frame_buffer:
                return self._frame_buffer.popleft()
            return None

    def get_statistics(self) -> Dict[str, Any]:
        """获取性能统计信息"""
        with self._stats_lock:
            return self._performance_stats.copy()

    def get_state(self) -> WindowsSensorState:
        """获取当前状态"""
        with self._state_lock:
            return self._state

    def is_running(self) -> bool:
        """检查是否运行中"""
        return self.get_state() == WindowsSensorState.RUNNING

    def get_window_info(self) -> Optional[Dict[str, Any]]:
        """获取窗口信息"""
        if self._capture:
            try:
                info = self._capture.get_window_info()
                return {
                    'hwnd': info.hwnd,
                    'title': info.title,
                    'class_name': info.class_name,
                    'rect': info.rect,
                    'client_rect': info.client_rect,
                    'is_visible': info.is_visible,
                    'is_minimized': info.is_minimized,
                }
            except Exception as e:
                logger.debug(f"获取窗口信息失败: {e}")
        return None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False
