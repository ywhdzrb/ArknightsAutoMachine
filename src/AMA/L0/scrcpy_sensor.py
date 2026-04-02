"""
L0感知执行层 - Scrcpy截图传感器(ScrcpySensor)

基于scrcpy-client库实现超低延迟截图(10-30ms)：
- 使用Scrcpy的H.264视频流直接解码
- 比ADB screencap快20-50倍
- 支持高帧率(60fps+)

依赖:
- scrcpy-client (pip install scrcpy-client)
- adbutils (pip install adbutils)

性能目标:
- 单帧获取延迟 < 30ms
- 支持60fps连续采集
- CPU占用 < 10%

用法:
    from scrcpy import Client
    
    client = Client(device="127.0.0.1:5555")
    client.start()
    frame = client.last_frame  # numpy array
    client.stop()
"""

import threading
import time
import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Callable, Tuple, List, Dict, Any
from pathlib import Path
import numpy as np


logger = logging.getLogger(__name__)


# ========== Monkey Patch: 修复 scrcpy-client 的解码错误处理 ==========
# 全局错误计数器，用于触发重启
_scrcpy_error_count = 0
_scrcpy_error_lock = threading.Lock()
_scrcpy_restart_callback = None  # 重启回调函数

def _apply_scrcpy_patch():
    """应用 Monkey Patch 修复 scrcpy-client 的解码错误处理
    
    原始问题: scrcpy-client 的 __stream_loop 方法在遇到 av.error.InvalidDataError
    时会直接崩溃，导致整个视频流线程终止。
    
    修复方案: 捕获解码错误，丢弃损坏的帧，让视频流继续运行。
    如果连续错误过多，触发重启。
    """
    try:
        import scrcpy
        import av
        import cv2
        from av.codec import CodecContext
        import time
        
        # 保存原始方法
        _original_stream_loop = scrcpy.Client._Client__stream_loop
        
        def _patched_stream_loop(self):
            """修复版本：捕获解码错误，避免线程崩溃"""
            global _scrcpy_error_count, _scrcpy_restart_callback
            
            # 在方法内部创建 codec（与原始实现一致）
            codec = CodecContext.create("h264", "r")
            consecutive_errors = 0  # 连续错误计数
            max_consecutive_errors = 5  # 最大连续错误数，超过则触发重启
            
            while self.alive:
                try:
                    raw_h264 = self._Client__video_socket.recv(0x10000)
                    packets = codec.parse(raw_h264)
                    for packet in packets:
                        try:
                            frames = codec.decode(packet)
                            for frame in frames:
                                frame = frame.to_ndarray(format="bgr24")
                                if self.flip:
                                    frame = cv2.flip(frame, 1)
                                self.last_frame = frame
                                self.resolution = (frame.shape[1], frame.shape[0])
                                self._Client__send_to_listeners(scrcpy.EVENT_FRAME, frame)
                            # 成功解码，重置错误计数
                            consecutive_errors = 0
                            with _scrcpy_error_lock:
                                _scrcpy_error_count = 0
                        except av.error.InvalidDataError:
                            # 丢弃损坏的帧
                            consecutive_errors += 1
                            with _scrcpy_error_lock:
                                _scrcpy_error_count += 1
                            if consecutive_errors <= 3:
                                logger.warning(f"[ScrcpyPatch] 丢弃损坏的视频帧 (InvalidDataError), 连续错误: {consecutive_errors}")
                            
                            # 如果连续错误过多，触发重启
                            if consecutive_errors >= max_consecutive_errors:
                                logger.error(f"[ScrcpyPatch] 连续错误过多({consecutive_errors})，触发重启")
                                if _scrcpy_restart_callback:
                                    try:
                                        _scrcpy_restart_callback()
                                    except Exception as e:
                                        logger.error(f"[ScrcpyPatch] 重启回调失败: {e}")
                                break  # 退出循环
                            continue
                        except Exception as e:
                            consecutive_errors += 1
                            with _scrcpy_error_lock:
                                _scrcpy_error_count += 1
                            if consecutive_errors <= 3:
                                logger.error(f"[ScrcpyPatch] 解码异常: {e}, 连续错误: {consecutive_errors}")
                            if consecutive_errors >= max_consecutive_errors:
                                logger.error(f"[ScrcpyPatch] 连续错误过多({consecutive_errors})，触发重启")
                                if _scrcpy_restart_callback:
                                    try:
                                        _scrcpy_restart_callback()
                                    except Exception as e:
                                        logger.error(f"[ScrcpyPatch] 重启回调失败: {e}")
                                break
                            time.sleep(0.001)
                            continue
                except BlockingIOError:
                    time.sleep(0.01)
                    if not self.block_frame:
                        self._Client__send_to_listeners(scrcpy.EVENT_FRAME, None)
                except OSError as e:  # Socket Closed
                    if self.alive:
                        raise e
        
        # 替换原始方法
        scrcpy.Client._Client__stream_loop = _patched_stream_loop
        logger.info("[ScrcpyPatch] 已应用 scrcpy-client 解码错误修复")
        
    except ImportError:
        logger.debug("[ScrcpyPatch] scrcpy 或 av 未安装，跳过补丁")
    except Exception as e:
        logger.warning(f"[ScrcpyPatch] 应用补丁失败: {e}")


def _set_scrcpy_restart_callback(callback):
    """设置 Scrcpy 重启回调函数"""
    global _scrcpy_restart_callback
    _scrcpy_restart_callback = callback


# 应用补丁
_apply_scrcpy_patch()


class ScrcpyState(Enum):
    """Scrcpy传感器运行状态"""
    STOPPED = auto()
    STARTING = auto()
    RUNNING = auto()
    PAUSED = auto()
    ERROR = auto()
    STOPPING = auto()


@dataclass(frozen=True)
class FrameMetadata:
    """帧元数据"""
    timestamp: float
    sequence_number: int
    capture_latency_ms: float
    resolution: Tuple[int, int]
    size_bytes: int


@dataclass
class ScreenshotFrame:
    """截图帧数据结构"""
    image_data: Optional[bytes] = None
    image_numpy: Optional[np.ndarray] = None
    metadata: Optional[FrameMetadata] = None


@dataclass
class ScrcpyConfig:
    """Scrcpy传感器配置"""
    target_fps: float = 60.0
    max_buffer_size: int = 3
    bitrate: int = 8000000  # 8Mbps 平衡画质和稳定性
    max_width: int = 0  # 0 means no limit
    stay_awake: bool = True
    lock_screen_orientation: int = -1  # -1 = unlocked (scrcpy-client默认)
    block_frame: bool = True  # True = 只返回非空帧，减少CPU占用


class ScrcpySensor:
    """Scrcpy截图传感器
    
    基于scrcpy-client库实现超低延迟截图。
    使用回调方式接收视频帧，避免轮询开销。
    
    使用方式:
        sensor = ScrcpySensor(device_serial="127.0.0.1:5555")
        sensor.start()
        frame = sensor.get_latest_frame()
        sensor.stop()
    """
    
    # 类级别的错误计数器，用于检测是否需要重启
    _error_counter: Dict[str, int] = {}
    _error_counter_lock = threading.Lock()
    
    def __init__(
        self,
        device_serial: str,
        config: Optional[ScrcpyConfig] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ):
        self._device_serial = device_serial
        self._config = config or ScrcpyConfig()
        self._on_error = on_error
        
        # scrcpy-client 客户端
        self._client: Optional[Any] = None
        
        # 状态
        self._state = ScrcpyState.STOPPED
        self._state_lock = threading.RLock()
        
        # 帧缓冲
        self._frame_buffer: List[ScreenshotFrame] = []
        self._buffer_lock = threading.Lock()
        self._sequence_number = 0
        
        # 最新帧（用于快速访问）
        self._latest_frame: Optional[ScreenshotFrame] = None
        self._frame_event = threading.Event()
        
        # 统计
        self._stats = {
            'total_frames': 0,
            'successful_frames': 0,
            'failed_frames': 0,
            'buffer_overflows': 0,
            'start_time': 0.0,
        }
        self._stats_lock = threading.Lock()
        
        # 设备信息
        self._device_resolution: Tuple[int, int] = (0, 0)
        
        # 重启相关
        self._restart_attempts = 0
        self._max_restart_attempts = 3
        self._restart_lock = threading.Lock()
        
        logger.info(f"ScrcpySensor初始化 | 设备:{device_serial} | 目标FPS:{self._config.target_fps}")
    
    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        with self._state_lock:
            return self._state == ScrcpyState.RUNNING
    
    @property
    def state(self) -> ScrcpyState:
        """当前状态"""
        with self._state_lock:
            return self._state
    
    def _set_state(self, new_state: ScrcpyState) -> None:
        """设置状态"""
        with self._state_lock:
            old_state = self._state
            self._state = new_state
            if old_state != new_state:
                logger.info(f"ScrcpySensor状态: {old_state.name} -> {new_state.name}")
    
    def _on_frame(self, frame: np.ndarray) -> None:
        """视频帧回调
        
        由scrcpy-client库调用，每收到一帧视频数据时触发。
        
        Args:
            frame: numpy数组 (H, W, 3) BGR格式，可能为None
        """
        # 检查空帧
        if frame is None:
            # 空帧不记录日志，避免日志刷屏
            return
        
        # 每60帧记录一次日志（约每秒一次，如果60fps）
        if self._sequence_number % 60 == 0:
            logger.debug(f"收到第{self._sequence_number}帧 | 分辨率:{frame.shape}")
        
        try:
            timestamp = time.monotonic()
            
            self._sequence_number += 1
            
            # 计算延迟（从帧生成到接收的时间）
            # scrcpy-client不直接提供pts，我们使用当前时间作为参考
            capture_latency_ms = 0.0
            
            # 更新分辨率
            if self._device_resolution == (0, 0):
                self._device_resolution = (frame.shape[1], frame.shape[0])
            
            metadata = FrameMetadata(
                timestamp=timestamp,
                sequence_number=self._sequence_number,
                capture_latency_ms=capture_latency_ms,
                resolution=(frame.shape[1], frame.shape[0]),
                size_bytes=frame.nbytes,
            )
            
            screenshot_frame = ScreenshotFrame(
                image_numpy=frame.copy(),  # 复制避免被覆盖
                metadata=metadata,
            )
            
            # 更新最新帧
            self._latest_frame = screenshot_frame
            self._frame_event.set()
            
            # 添加到缓冲区
            with self._buffer_lock:
                self._frame_buffer.append(screenshot_frame)
                
                # 限制缓冲区大小
                while len(self._frame_buffer) > self._config.max_buffer_size:
                    self._frame_buffer.pop(0)
                    with self._stats_lock:
                        self._stats['buffer_overflows'] += 1
            
            with self._stats_lock:
                self._stats['total_frames'] += 1
                self._stats['successful_frames'] += 1
                
        except Exception as e:
            logger.error(f"帧回调处理失败: {e}")
            with self._stats_lock:
                self._stats['failed_frames'] += 1
    
    def _on_stream_error(self) -> None:
        """视频流错误回调（由 Monkey Patch 调用）
        
        当检测到连续解码错误时，尝试自动重启 Scrcpy。
        """
        with self._restart_lock:
            if self._restart_attempts >= self._max_restart_attempts:
                logger.error(f"Scrcpy 重启次数已达上限({self._max_restart_attempts})，停止重试")
                if self._on_error:
                    self._on_error("视频流错误，自动重启失败，请手动重新连接")
                return
            
            self._restart_attempts += 1
            logger.warning(f"Scrcpy 视频流错误，尝试第 {self._restart_attempts} 次重启...")
        
        try:
            # 停止当前连接
            self.stop()
            time.sleep(1.0)  # 等待资源释放
            
            # 重新启动
            self.start()
            
            # 重置重启计数
            with self._restart_lock:
                self._restart_attempts = 0
            
            logger.info("Scrcpy 自动重启成功")
            
        except Exception as e:
            logger.error(f"Scrcpy 自动重启失败: {e}")
            if self._on_error:
                self._on_error(f"视频流错误，自动重启失败: {e}")
    
    def start(self) -> None:
        """启动Scrcpy传感器"""
        if self._state != ScrcpyState.STOPPED:
            raise RuntimeError(f"无法启动，当前状态: {self._state.name}")
        
        self._set_state(ScrcpyState.STARTING)
        
        try:
            # 注册重启回调
            _set_scrcpy_restart_callback(self._on_stream_error)
            
            # 导入scrcpy-client
            from scrcpy import Client
            
            # 构建配置 (参数名必须与scrcpy-client的Client.__init__匹配)
            client_config = {
                'device': self._device_serial,
                'max_fps': int(self._config.target_fps),
                'bitrate': self._config.bitrate,
                'max_width': self._config.max_width,
                'stay_awake': self._config.stay_awake,
                'lock_screen_orientation': self._config.lock_screen_orientation,
                'block_frame': self._config.block_frame,  # 只返回非空帧
            }
            
            logger.debug(f"ScrcpyClient配置: {client_config}")
            
            # 创建客户端
            self._client = Client(**client_config)
            
            # 添加帧监听器
            self._client.add_listener('frame', self._on_frame)
            
            # 添加初始化监听器
            def on_init():
                logger.info(f"ScrcpyClient初始化完成 | 设备名:{self._client.device_name} | 分辨率:{self._client.resolution}")
            self._client.add_listener('init', on_init)
            
            # 启动客户端 (使用threaded=True在后台线程运行，避免阻塞)
            logger.info("启动ScrcpyClient...")
            self._client.start(threaded=True)
            
            # 等待第一帧
            logger.info("等待ScrcpyClient第一帧...")
            if not self._frame_event.wait(timeout=10.0):
                # 检查客户端状态
                logger.error(f"等待超时 | alive={self._client.alive} | last_frame={self._client.last_frame is not None}")
                raise RuntimeError("等待第一帧超时，请检查设备连接和Scrcpy权限")
            
            # 获取分辨率
            if self._client.resolution:
                self._device_resolution = self._client.resolution
            elif self._latest_frame and self._latest_frame.image_numpy is not None:
                h, w = self._latest_frame.image_numpy.shape[:2]
                self._device_resolution = (w, h)
            
            with self._stats_lock:
                self._stats['start_time'] = time.monotonic()
            
            self._set_state(ScrcpyState.RUNNING)
            logger.info(f"ScrcpySensor已启动 | 分辨率:{self._device_resolution}")
            
        except Exception as e:
            import traceback
            self._set_state(ScrcpyState.ERROR)
            logger.error(f"启动ScrcpySensor失败: {e}")
            logger.debug(f"ScrcpySensor启动错误堆栈:\n{traceback.format_exc()}")
            self._cleanup()
            raise
    
    def get_latest_frame(self, timeout: float = 0.0) -> Optional[ScreenshotFrame]:
        """获取最新帧
        
        Args:
            timeout: 等待超时时间（秒），0表示不等待
            
        Returns:
            最新帧数据，如果没有则返回None
        """
        if timeout > 0:
            if self._frame_event.wait(timeout=timeout):
                self._frame_event.clear()
        
        # 优先使用缓存的最新帧（由回调更新）
        if self._latest_frame is not None:
            return self._latest_frame
        
        # 否则从客户端获取
        if self._client and self._client.last_frame is not None:
            frame = self._client.last_frame
            timestamp = time.monotonic()
            self._sequence_number += 1
            
            metadata = FrameMetadata(
                timestamp=timestamp,
                sequence_number=self._sequence_number,
                capture_latency_ms=0.0,
                resolution=(frame.shape[1], frame.shape[0]),
                size_bytes=frame.nbytes,
            )
            
            return ScreenshotFrame(
                image_numpy=frame,
                metadata=metadata,
            )
        
        # 否则返回缓冲区的最新帧
        with self._buffer_lock:
            if self._frame_buffer:
                return self._frame_buffer[-1]
        
        return None
    
    def stop(self) -> None:
        """停止传感器"""
        if self._state == ScrcpyState.STOPPED:
            return
        
        self._set_state(ScrcpyState.STOPPING)
        
        try:
            self._cleanup()
        finally:
            self._set_state(ScrcpyState.STOPPED)
            logger.info("ScrcpySensor已停止")
    
    def _cleanup(self) -> None:
        """清理资源"""
        logger.debug("开始清理ScrcpySensor资源...")
        
        # 先停止客户端（这会在内部停止线程）
        if self._client:
            try:
                logger.debug("停止ScrcpyClient...")
                self._client.stop()
                logger.debug("ScrcpyClient已停止")
            except Exception as e:
                logger.warning(f"停止ScrcpyClient时出错: {e}")
            finally:
                self._client = None
        
        # 清除事件和帧数据
        self._frame_event.clear()
        self._latest_frame = None
        
        # 清空缓冲区
        with self._buffer_lock:
            self._frame_buffer.clear()
        
        logger.debug("ScrcpySensor资源清理完成")
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._stats_lock:
            stats = self._stats.copy()
        
        elapsed = time.monotonic() - stats['start_time'] if stats['start_time'] > 0 else 0
        fps = stats['total_frames'] / elapsed if elapsed > 0 else 0
        
        return {
            **stats,
            'fps': fps,
            'state': self._state.name,
            'buffer_size': len(self._frame_buffer),
            'resolution': self._device_resolution,
        }
