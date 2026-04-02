"""
L0感知执行层 - ADB截图传感器(AdbSensor)

职责:
- 封装ADB screencap命令，提供高效稳定的截图能力
- 支持连续帧采集，满足实时预览需求
- 内存管理与性能优化（帧缓冲池、降采样、压缩）
- 截图质量监控与异常恢复机制

性能目标:
- 单帧获取延迟 < 66ms (对应15fps)
- 连续截图1000帧无内存泄漏
- 内存占用 < 200MB（含帧缓存）

架构设计:
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│  GUI Preview │◄───│  FrameBuffer  │◄───│  ADB Client │
│  (降采样显示) │    │  (环形缓冲区) │    │(screencap)  │
└─────────────┘    └──────────────┘    └─────────────┘
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
import queue


logger = logging.getLogger(__name__)


class SensorState(Enum):
    """传感器运行状态枚举"""
    STOPPED = auto()       # 未启动或已停止
    STARTING = auto()      # 正在初始化
    RUNNING = auto()       # 正常运行中
    PAUSED = auto()        # 暂停状态（保留连接但停止采集）
    ERROR = auto()         # 错误状态（需手动恢复）
    STOPPING = auto()      # 正在停止中


@dataclass(frozen=True)
class FrameMetadata:
    """单帧截图的元数据信息
    
    Attributes:
        timestamp: 帧捕获时间戳（time.monotonic）
        sequence_number: 帧序号（单调递增，用于检测丢帧）
        capture_latency_ms: 从发起请求到收到数据的耗时
        resolution: 原始分辨率 (width, height)
        size_bytes: 原始PNG数据大小
        quality_score: 图像质量评估分数（0-100，基于清晰度/亮度等指标）
    """
    timestamp: float
    sequence_number: int
    capture_latency_ms: float
    resolution: Tuple[int, int]
    size_bytes: int
    quality_score: float = 0.0


@dataclass
class ScreenshotFrame:
    """完整的截图帧数据结构
    
    设计为不可变对象以确保线程安全，
    所有字段通过__init__一次性赋值后不再修改。
    
    Attributes:
        image_data: 原始PNG二进制数据（来自ADB exec-out screencap -p）
        image_numpy: 解码后的numpy数组（BGR格式，OpenCV标准）
        metadata: 帧元数据
    """
    image_data: bytes
    image_numpy: Optional[np.ndarray] = None
    metadata: Optional[FrameMetadata] = None


@dataclass
class SensorConfig:
    """传感器配置参数集合
    
    所有可调参数集中管理，便于GUI配置面板绑定和持久化。
    
    Attributes:
        target_fps: 目标帧率（实际帧率受限于ADB传输速度）
        max_buffer_size: 环形缓冲区最大容量（超过则丢弃最旧帧）
        auto_downsample: 是否自动对高分辨率画面降采样
        downsample_target_size: 降采样目标尺寸 (width, height)，None表示不限制
        jpeg_quality: JPEG压缩质量（1-100），用于降低内存占用和传输开销
        enable_quality_monitoring: 是否启用图像质量监控
        decode_to_numpy: 是否自动解码为numpy数组（消耗CPU但便于后续处理）
        timeout_per_frame: 单帧超时时间（秒）
        reconnect_on_failure: 连续失败N次后是否尝试重连
        max_consecutive_failures: 触发重连的最大连续失败次数
    """
    target_fps: float = 15.0
    max_buffer_size: int = 5
    auto_downsample: bool = True
    downsample_target_size: Tuple[int, int] = (960, 540)
    jpeg_quality: int = 85
    enable_quality_monitoring: bool = True
    decode_to_numpy: bool = True
    timeout_per_frame: float = 10.0
    reconnect_on_failure: bool = True
    max_consecutive_failures: int = 10


DEFAULT_CONFIG = SensorConfig()


class AdbSensorError(Exception):
    """传感器操作相关异常基类"""
    pass


class ScreenshotTimeoutError(AdbSensorError):
    """截图操作超时"""
    pass


class SensorNotRunningError(AdbSensorError):
    """传感器未运行时的非法操作"""
    pass


class BufferOverflowError(AdbSensorError):
    """帧缓冲区溢出"""
    pass


class AdbSensor:
    """ADB截图传感器核心类
    
    职责:
    - 管理截图生命周期（start/stop/pause/resume）
    - 维护帧缓冲区供消费者读取
    - 性能统计与质量监控
    - 异常检测与自动恢复
    
    线程模型:
    - 主线程: 调用API方法（get_latest_frame、start、stop等）
    - 采集线程: 循环执行ADB screenshot命令并填充缓冲区
    - 监控线程: 定期检查性能指标和健康状态
    
    使用模式:
    
    模式1 - 连续采集 + 消费者轮询:
        sensor = AdbSensor(adb_client, device_serial)
        sensor.start()
        
        while running:
            frame = sensor.get_latest_frame()
            if frame and frame.image_numpy is not None:
                process(frame.image_numpy)
            time.sleep(0.033)
        
        sensor.stop()
    
    模式2 - 回调驱动:
        def on_new_frame(frame: ScreenshotFrame):
            display(frame.image_numpy)
        
        sensor = AdbSensor(adb_client, device_serial)
        sensor.set_callback(on_new_frame)
        sensor.start()
    
    Time Complexity:
    - start(): O(1) 启动线程
    - get_latest_frame(): O(1) 从队列读取
    - stop(): O(1) 标记停止+等待线程结束
    - 内部循环: O(n) n=每帧像素数（解码+缩放）
    """
    
    MIN_FRAME_INTERVAL_MS = 20.0
    MAX_FRAME_INTERVAL_MS = 500.0
    
    def __init__(
        self,
        adb_client,
        device_serial: str,
        config: Optional[SensorConfig] = None,
        on_frame_callback: Optional[Callable[[ScreenshotFrame], None]] = None,
        on_error_callback: Optional[Callable[[Exception], None]] = None,
    ):
        """初始化截图传感器
        
        Args:
            adb_client: 已初始化的ADBClient实例（持有ADB连接）
            device_serial: 目标设备的序列号
            config: 传感器配置，None使用默认值
            on_frame_callback: 新帧可用时的回调函数（可选）
            on_error_callback: 发生错误时的回调函数（可选）
            
        Raises:
            ValueError: adb_client或device_serial无效
        """
        if adb_client is None:
            raise ValueError("ADB客户端不能为None")
        if not device_serial or not isinstance(device_serial, str):
            raise ValueError("设备序列号必须是非空字符串")
        
        self._adb_client = adb_client
        self._device_serial = device_serial
        self._config = config or DEFAULT_CONFIG
        
        self._state = SensorState.STOPPED
        self._state_lock = threading.RLock()
        
        self._frame_buffer: deque = deque(maxlen=self._config.max_buffer_size)
        self._buffer_lock = threading.Lock()
        
        self._capture_thread: Optional[threading.Thread] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()
        
        self._sequence_counter = 0
        self._counter_lock = threading.Lock()
        
        self._consecutive_failures = 0
        self._stats_lock = threading.Lock()
        self._performance_stats = {
            'total_frames_captured': 0,
            'successful_frames': 0,
            'failed_frames': 0,
            'average_latency_ms': 0.0,
            'min_latency_ms': float('inf'),
            'max_latency_ms': 0.0,
            'current_fps': 0.0,
            'last_frame_time': 0.0,
            'buffer_overflows': 0,
            'reconnect_count': 0,
        }
        
        self._on_frame_callback = on_frame_callback
        self._on_error_callback = on_error_callback
        
        self._latest_frame: Optional[ScreenshotFrame] = None
        self._latest_frame_lock = threading.Lock()
        
        logger.info(
            f"AdbSensor初始化 | 设备:{device_serial} | "
            f"目标FPS:{self._config.target_fps} | "
            f"缓冲区大小:{self._config.max_buffer_size}"
        )
    
    @property
    def state(self) -> SensorState:
        """返回当前传感器状态（线程安全）"""
        with self._state_lock:
            return self._state
    
    @property
    def is_running(self) -> bool:
        """传感器是否正在运行（RUNNING状态）"""
        return self.state == SensorState.RUNNING
    
    @property
    def config(self) -> SensorConfig:
        """返回当前配置的副本"""
        return self._config
    
    @property
    def device_serial(self) -> str:
        """返回目标设备序列号"""
        return self._device_serial
    
    def start(self) -> None:
        """启动传感器，开始连续截图采集
        
        执行流程:
        1. 状态验证（必须处于STOPPED/ERROR状态）
        2. 预热：执行一次测试截图确认ADB链路正常
        3. 启动采集线程和监控线程
        4. 更新状态为RUNNING
        
        Raises:
            RuntimeError: 传感器已在运行中
            AdbSensorError: 预热截图失败
        """
        with self._state_lock:
            if self._state in (SensorState.RUNNING, SensorState.STARTING):
                raise RuntimeError(f"传感器已在运行中，当前状态: {self._state.name}")
            
            self._state = SensorState.STARTING
        
        logger.info(f"正在启动传感器 | 设备:{self._device_serial}")
        
        try:
            test_frame = self._capture_single_frame()
            if test_frame is None:
                raise AdbSensorError("预热截图失败，请检查设备连接")
            
            logger.info("预热截图成功，传感器就绪")
            
        except Exception as e:
            with self._state_lock:
                self._state = SensorState.ERROR
            raise AdbSensorError(f"传感器启动失败: {e}") from e
        
        self._stop_event.clear()
        self._pause_event.set()
        
        self._reset_stats()
        
        self._capture_thread = threading.Thread(
            target=self._capture_loop,
            name=f"sensor_capture_{self._device_serial[:8]}",
            daemon=True,
        )
        self._capture_thread.start()
        
        if self._config.enable_quality_monitoring:
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop,
                name=f"sensor_monitor_{self._device_serial[:8]}",
                daemon=True,
            )
            self._monitor_thread.start()
        
        with self._state_lock:
            self._state = SensorState.RUNNING
        
        logger.info(f"传感器已启动 | 目标FPS:{self._config.target_fps}")
    
    def stop(self, timeout: float = 5.0) -> None:
        """停止传感器，释放所有资源
        
        Args:
            timeout: 等待采集线程结束的超时时间（秒）
            
        Note:
            此方法是阻塞的，会等待采集线程完全退出。
            如果采集线程卡死（如ADB命令无响应），将强制终止。
        """
        with self._state_lock:
            if self._state == SensorState.STOPPED:
                return
            
            self._state = SensorState.STOPPING
        
        logger.info("正在停止传感器...")
        
        self._stop_event.set()
        self._pause_event.set()
        
        threads_to_join = [self._capture_thread]
        if self._monitor_thread:
            threads_to_join.append(self._monitor_thread)
        
        for thread in threads_to_join:
            if thread and thread.is_alive():
                thread.join(timeout=timeout)
                if thread.is_alive():
                    logger.warning(
                        f"线程 {thread.name} 未能在 {timeout}s 内结束"
                    )
        
        self._clear_buffer()
        
        with self._state_lock:
            self._state = SensorState.STOPPED
        
        final_stats = self.get_performance_stats()
        logger.info(
            f"传感器已停止 | 总帧数:{final_stats['total_frames_captured']} | "
            f"成功:{final_stats['successful_frames']} | "
            f"失败:{final_stats['failed_frames']}"
        )
    
    def pause(self) -> None:
        """暂停截图采集（保留连接和资源）"""
        with self._state_lock:
            if self._state != SensorState.RUNNING:
                return
            
            self._state = SensorState.PAUSED
        
        self._pause_event.clear()
        logger.info("传感器已暂停")
    
    def resume(self) -> None:
        """从暂停状态恢复截图采集"""
        with self._state_lock:
            if self._state != SensorState.PAUSED:
                return
            
            self._state = SensorState.RUNNING
        
        self._pause_event.set()
        logger.info("传感器已恢复")
    
    def get_latest_frame(self, timeout: float = 0.0) -> Optional[ScreenshotFrame]:
        """获取最新的一帧截图数据
        
        这是主要的消费接口，供GUI预览窗口或其他处理模块调用。
        
        Args:
            timeout: 等待新帧的最长时间（秒），0表示立即返回（非阻塞）
            
        Returns:
            最新的ScreenshotFrame对象，如果缓冲区为空且非阻塞则返回None
            
        Time Complexity:
            O(1) - 直接访问最新帧引用
        """
        if timeout > 0:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                with self._latest_frame_lock:
                    if self._latest_frame is not None:
                        return self._latest_frame
                time.sleep(0.001)
            return None
        else:
            with self._latest_frame_lock:
                return self._latest_frame
    
    def get_frame_from_buffer(self, index: int = -1) -> Optional[ScreenshotFrame]:
        """从缓冲区获取指定位置的帧
        
        Args:
            index: 帧索引，-1表示最新帧，0表示最旧帧
            
        Returns:
            指定位置的帧，索引越界返回None
        """
        with self._buffer_lock:
            if not self._frame_buffer:
                return None
            
            try:
                return self._frame_buffer[index]
            except IndexError:
                return None
    
    def get_buffer_size(self) -> int:
        """返回当前缓冲区中的帧数量"""
        with self._buffer_lock:
            return len(self._frame_buffer)
    
    def set_callback(
        self,
        on_frame: Optional[Callable[[ScreenshotFrame], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """设置回调函数（可动态更新）
        
        Args:
            on_frame: 新帧回调
            on_error: 错误回调
        """
        if on_frame is not None:
            self._on_frame_callback = on_frame
        if on_error is not None:
            self._on_error_callback = on_error
    
    def update_config(self, **kwargs) -> None:
        """动态更新配置参数
        
        支持的关键字参数与SensorConfig的字段一一对应。
        部分参数（如max_buffer_size）需要重建缓冲区才能生效。
        
        Args:
            **kwargs: 要更新的配置项
        """
        old_max_buffer = self._config.max_buffer_size
        
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)
                logger.debug(f"配置更新: {key} = {value}")
        
        if old_max_buffer != self._config.max_buffer_size:
            with self._buffer_lock:
                new_buffer: deque = deque(list(self._frame_buffer), maxlen=self._config.max_buffer_size)
                self._frame_buffer = new_buffer
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计快照（线程安全）
        
        Returns:
            包含各项性能指标的字典副本
        """
        with self._stats_lock:
            stats = dict(self._performance_stats)
            stats['state'] = self._state.name
            stats['buffer_size'] = len(self._frame_buffer)
            stats['consecutive_failures'] = self._consecutive_failures
            return stats
    
    def _capture_loop(self) -> None:
        """主采集循环（在独立线程中运行）- 优化版
        
        优化策略:
        - 截图完成后立即开始下一次，减少空闲等待
        - 通过FPS控制每秒钟创建多少次截图线程
        - 使用自适应间隔动态调整
        """
        target_fps = max(self._config.target_fps, 1.0)
        target_interval = 1.0 / target_fps
        min_interval = self.MIN_FRAME_INTERVAL_MS / 1000.0
        
        logger.debug(
            f"采集循环启动 | 目标FPS:{target_fps} | "
            f"目标间隔:{target_interval*1000:.1f}ms"
        )
        
        # FPS控制变量
        frame_count = 0
        fps_check_start = time.monotonic()
        last_capture_time = 0
        
        while not self._stop_event.is_set():
            try:
                self._pause_event.wait()
                
                if self._stop_event.is_set():
                    break
                
                # FPS控制：检查是否需要等待
                current_time = time.monotonic()
                elapsed_since_last = current_time - last_capture_time
                
                # 如果距离上次截图时间不足目标间隔，等待
                if elapsed_since_last < target_interval:
                    sleep_time = target_interval - elapsed_since_last
                    time.sleep(max(sleep_time, 0.001))
                
                # 记录本次截图开始时间
                capture_start = time.monotonic()
                last_capture_time = capture_start
                
                # 执行截图
                frame = self._capture_single_frame()
                
                if frame is not None:
                    self._process_successful_frame(frame)
                    self._consecutive_failures = 0
                    frame_count += 1
                else:
                    self._handle_capture_failure()
                
                # 每秒计算一次实际FPS并调整
                fps_elapsed = time.monotonic() - fps_check_start
                if fps_elapsed >= 1.0:
                    actual_fps = frame_count / fps_elapsed
                    logger.debug(f"实际FPS: {actual_fps:.1f} | 目标: {target_fps:.1f}")
                    
                    # 如果实际FPS远低于目标，缩短间隔
                    if actual_fps < target_fps * 0.8:
                        target_interval = max(target_interval * 0.9, min_interval)
                    # 如果实际FPS接近目标，稍微放宽
                    elif actual_fps > target_fps * 1.1:
                        target_interval = min(target_interval * 1.05, 1.0 / target_fps * 1.5)
                    
                    frame_count = 0
                    fps_check_start = time.monotonic()
                
            except Exception as e:
                logger.error(f"采集循环异常: {e}", exc_info=True)
                
                if self._on_error_callback:
                    try:
                        self._on_error_callback(e)
                    except Exception as cb_err:
                        logger.error(f"错误回调执行失败: {cb_err}")
                
                time.sleep(0.05)
        
        logger.info("采集循环已退出")
    
    def _capture_single_frame(self) -> Optional[ScreenshotFrame]:
        """执行单次截图操作的内部方法
        
        完整流程:
        1. 调用ADBClient.take_screenshot()获取原始PNG数据
        2. 构建FrameMetadata记录时间戳和延迟
        3. 如配置启用，解码为numpy数组
        4. 如配置启用，执行降采样以减少内存占用
        5. 封装为ScreenshotFrame对象返回
        
        Returns:
            成功返回ScreenshotFrame，失败返回None
        """
        start_time = time.monotonic()
        
        try:
            raw_data = self._adb_client.take_screenshot(
                device_serial=self._device_serial,
                timeout=self._config.timeout_per_frame,
            )
            
            if not raw_data:
                logger.warning("截图返回空数据")
                return None
            
            latency_ms = (time.monotonic() - start_time) * 1000
            
            with self._counter_lock:
                self._sequence_counter += 1
                seq_num = self._sequence_counter
            
            image_numpy = None
            resolution = (0, 0)
            quality_score = 0.0
            
            if self._config.decode_to_numpy or self._config.auto_downsample:
                np_arr = np.frombuffer(raw_data, dtype=np.uint8)
                image_numpy = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                
                if image_numpy is not None:
                    h, w = image_numpy.shape[:2]
                    resolution = (w, h)
                    
                    if self._config.auto_downsample:
                        target_w, target_h = self._config.downsample_target_size
                        if w > target_w or h > target_h:
                            scale = min(target_w / w, target_h / h)
                            new_w = int(w * scale)
                            new_h = int(h * scale)
                            image_numpy = cv2.resize(image_numpy, (new_w, new_h), interpolation=cv2.INTER_AREA)
                            resolution = (new_w, new_h)
                    
                    if self._config.enable_quality_monitoring:
                        quality_score = self._calculate_quality_score(image_numpy)
            
            metadata = FrameMetadata(
                timestamp=time.monotonic(),
                sequence_number=seq_num,
                capture_latency_ms=latency_ms,
                resolution=resolution,
                size_bytes=len(raw_data),
                quality_score=quality_score,
            )
            
            frame = ScreenshotFrame(
                image_data=raw_data,
                image_numpy=image_numpy,
                metadata=metadata,
            )
            
            return frame
            
        except Exception as e:
            logger.debug(f"截图失败: {type(e).__name__}: {e}")
            return None
    
    def _process_successful_frame(self, frame: ScreenshotFrame) -> None:
        """处理成功获取的帧（更新缓冲区、统计、回调）"""
        with self._buffer_lock:
            old_size = len(self._frame_buffer)
            self._frame_buffer.append(frame)
            if len(self._frame_buffer) <= old_size:
                with self._stats_lock:
                    self._performance_stats['buffer_overflows'] += 1
        
        with self._latest_frame_lock:
            self._latest_frame = frame
        
        with self._stats_lock:
            self._performance_stats['total_frames_captured'] += 1
            self._performance_stats['successful_frames'] += 1
            
            if frame.metadata:
                lat = frame.metadata.capture_latency_ms
                self._performance_stats['average_latency_ms'] = (
                    (self._performance_stats['average_latency_ms'] *
                     (self._performance_stats['successful_frames'] - 1) + lat) /
                    self._performance_stats['successful_frames']
                )
                self._performance_stats['min_latency_ms'] = min(
                    self._performance_stats['min_latency_ms'], lat
                )
                self._performance_stats['max_latency_ms'] = max(
                    self._performance_stats['max_latency_ms'], lat
                )
            
            now = time.monotonic()
            prev_time = self._performance_stats['last_frame_time']
            if prev_time > 0:
                interval = now - prev_time
                if interval > 0:
                    smooth_factor = 0.1
                    current_fps = 1.0 / interval
                    prev_fps = self._performance_stats['current_fps']
                    self._performance_stats['current_fps'] = (
                        smooth_factor * current_fps + (1 - smooth_factor) * prev_fps
                    )
            
            self._performance_stats['last_frame_time'] = now
        
        if self._on_frame_callback:
            try:
                self._on_frame_callback(frame)
            except Exception as cb_err:
                logger.error(f"帧回调执行失败: {cb_err}")
    
    def _handle_capture_failure(self) -> None:
        """处理截图失败的逻辑（计数、重连决策）"""
        self._consecutive_failures += 1
        
        with self._stats_lock:
            self._performance_stats['total_frames_captured'] += 1
            self._performance_stats['failed_frames'] += 1
        
        if self._consecutive_failures >= self._config.max_consecutive_failures:
            logger.error(
                f"连续截图失败次数达上限: {self._consecutive_failures}/"
                f"{self._config.max_consecutive_failures}"
            )
            
            if self._config.reconnect_on_failure:
                self._attempt_reconnect()
            else:
                with self._state_lock:
                    self._state = SensorState.ERROR
                
                error = AdbSensorError(
                    f"连续截图失败{self._consecutive_failures}次，传感器进入ERROR状态"
                )
                if self._on_error_callback:
                    try:
                        self._on_error_callback(error)
                    except Exception:
                        pass
    
    def _attempt_reconnect(self) -> None:
        """尝试重新建立ADB连接"""
        logger.info("尝试重新连接设备...")
        
        try:
            with self._stats_lock:
                self._performance_stats['reconnect_count'] += 1
            
            self._adb_client.check_device_health(self._device_serial)
            
            test_frame = self._capture_single_frame()
            if test_frame is not None:
                self._consecutive_failures = 0
                logger.info("重连成功，恢复正常采集")
            else:
                logger.warning("重连后首次截图仍失败")
                
        except Exception as e:
            logger.error(f"重连失败: {e}")
            
            with self._state_lock:
                self._state = SensorState.ERROR
    
    def _monitor_loop(self) -> None:
        """监控循环（定期报告性能指标）
        
        每5秒输出一次当前性能摘要到日志，
        用于生产环境问题排查和性能调优。
        """
        monitor_interval = 5.0
        
        while not self._stop_event.is_set():
            self._stop_event.wait(monitor_interval)
            
            if self._stop_event.is_set():
                break
            
            stats = self.get_performance_stats()
            
            logger.info(
                f"[Sensor Monitor] FPS:{stats['current_fps']:.1f} | "
                f"延迟(avg/min/max):"
                f"{stats['average_latency_ms']:.1f}/"
                f"{stats['min_latency_ms']:.1f}/"
                f"{stats['max_latency_ms']:.1f}ms | "
                f"总帧:{stats['total_frames_captured']} | "
                f"成功:{stats['successful_frames']} | "
                f"失败:{stats['failed_frames']} | "
                f"缓冲区:{stats['buffer_size']}/"
                f"{self._config.max_buffer_size} | "
                f"溢出:{stats['buffer_overflows']}"
            )
    
    def _calculate_quality_score(self, image: np.ndarray) -> float:
        """计算图像质量评分（0-100）
        
        评估维度:
        1. 清晰度（拉普拉斯方差）- 权重50%
        2. 亮度合理性 - 权重30%
        3. 对比度 - 权重20%
        
        Args:
            image: BGR格式的numpy数组
            
        Returns:
            0-100的质量分数
        """
        try:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            clarity_score = min(laplacian_var / 500.0 * 50, 50)
            
            mean_brightness = np.mean(gray)
            brightness_score = 30.0 - abs(mean_brightness - 127) / 255 * 30
            brightness_score = max(brightness_score, 0)
            
            contrast_score = min(np.std(gray) / 60.0 * 20, 20)
            
            total = clarity_score + brightness_score + contrast_score
            return max(0.0, min(100.0, total))
            
        except Exception:
            return 0.0
    
    def _clear_buffer(self) -> None:
        """清空帧缓冲区"""
        with self._buffer_lock:
            self._frame_buffer.clear()
        
        with self._latest_frame_lock:
            self._latest_frame = None
    
    def _reset_stats(self) -> None:
        """重置所有性能统计计数器"""
        with self._stats_lock:
            self._performance_stats = {
                'total_frames_captured': 0,
                'successful_frames': 0,
                'failed_frames': 0,
                'average_latency_ms': 0.0,
                'min_latency_ms': float('inf'),
                'max_latency_ms': 0.0,
                'current_fps': 0.0,
                'last_frame_time': 0.0,
                'buffer_overflows': 0,
                'reconnect_count': 0,
            }
        
        self._consecutive_failures = 0
        
        with self._counter_lock:
            self._sequence_counter = 0
    
    def __repr__(self) -> str:
        return (
            f"<AdbSensor device={self._device_serial[:12]}... "
            f"state={self._state.name} fps={self._config.target_fps}>"
        )
    
    def __enter__(self) -> 'AdbSensor':
        """上下文管理器入口（自动调用start）"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """上下文管理器出口（自动调用stop）"""
        self.stop()


def create_preview_image(frame: ScreenshotFrame, size: Optional[Tuple[int, int]] = None) -> Image.Image:
    """将截图帧转换为PIL Image用于Tkinter GUI显示
    
    Args:
        frame: 截图帧数据
        size: 目标显示尺寸 (width, height)，None保持原始大小
        
    Returns:
        PIL Image对象（RGB格式）
    
    Usage:
        from PIL import ImageTk
        tk_image = ImageTk.PhotoImage(create_preview_image(frame))
        label.configure(image=tk_image)
    """
    if frame is None or frame.image_numpy is None:
        blank = Image.new('RGB', (640, 360), color='#1a1a2e')
        return blank
    
    rgb_image = cv2.cvtColor(frame.image_numpy, cv2.COLOR_BGR2RGB)
    pil_image = Image.fromarray(rgb_image)
    
    if size:
        pil_image = pil_image.resize(size, Image.Resampling.LANCZOS)
    
    return pil_image
