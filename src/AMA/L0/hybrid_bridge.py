"""
L0感知执行层 - 混合桥接器(HybridL0Bridge)

职责:
- 智能选择最佳截图方案：Windows 截图（模拟器）或 ADB 截图（物理设备）
- 自动检测设备类型并选择最优方案
- 保持与 L0Bridge 相同的接口，可无缝替换

截图方案选择策略:
1. 如果是本地模拟器（127.0.0.1）→ 使用 Windows 截图（WGC/BitBlt）
2. 如果是无线调试或物理设备 → 使用 ADB 截图
3. 如果 Windows 截图失败 → 自动回退到 ADB 截图

性能对比:
- Windows 截图: 5-40ms（推荐用于模拟器）
- ADB 截图: 500-1000ms（用于物理设备）

使用示例:
    # 自动检测并选择最佳方案
    bridge = HybridL0Bridge(adb_client, device_serial)
    bridge.initialize()
    
    # 获取截图（自动使用最优方案）
    frame = bridge.get_latest_frame()
    
    # 输入控制（统一使用 ADB）
    bridge.tap(x, y)
"""

import threading
import time
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Callable, Dict, List, Any, Tuple, Union

from .bridge import L0Bridge, BridgeState, BridgeConfig, BridgeHealthReport, L0BridgeError, BridgeNotReadyError
from .sensor import AdbSensor, ScreenshotFrame, SensorState
from .windows_sensor import WindowsSensor, WindowsScreenshotFrame, WindowsSensorState, WindowsSensorConfig
from .scrcpy_sensor import ScrcpySensor, ScrcpyConfig
from .motor import AdbMotor, MotorConfig

import sys
from pathlib import Path
_src_path = Path(__file__).parent.parent.parent
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))
from common.capture import CaptureMethod


logger = logging.getLogger(__name__)


class CaptureBackend(Enum):
    """截图后端类型"""
    AUTO = auto()       # 自动选择
    WINDOWS = auto()    # Windows 截图（模拟器）
    ADB = auto()        # ADB 截图（物理设备）
    SCRCPY = auto()     # Scrcpy截图（超低延迟）


@dataclass
class HybridBridgeConfig:
    """混合桥接器配置

    Attributes:
        bridge_config: 基础桥接器配置
        preferred_backend: 首选截图后端
        auto_detect_emulator: 是否自动检测模拟器
        emulator_window_title: 模拟器窗口标题（可选）
        fallback_on_failure: Windows 截图失败时是否回退到 ADB
        windows_priority: Windows 截图优先级（高/中/低）
        windows_specific_method: Windows截图特定方式（auto/wgc/bitblt/printwindow）
    """
    bridge_config: BridgeConfig = field(default_factory=BridgeConfig)
    preferred_backend: CaptureBackend = CaptureBackend.AUTO
    auto_detect_emulator: bool = True
    emulator_window_title: Optional[str] = None
    fallback_on_failure: bool = True
    windows_priority: str = "high"  # high, medium, low
    windows_specific_method: str = "auto"  # auto, wgc, bitblt, printwindow


class HybridL0Bridge:
    """混合 L0 桥接器
    
    智能选择最佳截图方案：
    - 本地模拟器 → Windows 截图（超低延迟）
    - 物理设备/远程 → ADB 截图（通用兼容）
    
    特点:
    - 自动检测设备类型
    - 无缝切换截图方案
    - 统一的输入控制接口
    - 保持与 L0Bridge 兼容的 API
    """
    
    def __init__(
        self,
        adb_client,
        device_serial: str,
        config: Optional[HybridBridgeConfig] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_state_change: Optional[Callable[[BridgeState], None]] = None,
    ):
        """初始化混合桥接器
        
        Args:
            adb_client: ADBClient 实例
            device_serial: 设备序列号
            config: 混合桥接器配置
            on_error: 错误回调
            on_state_change: 状态变更回调
        """
        self._adb_client = adb_client
        self._device_serial = device_serial
        self._config = config or HybridBridgeConfig()
        self._on_error = on_error
        self._on_state_change = on_state_change
        
        # 当前使用的后端
        self._backend: CaptureBackend = CaptureBackend.AUTO
        self._backend_lock = threading.Lock()
        
        # 传感器（根据后端类型动态选择）
        self._adb_sensor: Optional[AdbSensor] = None
        self._windows_sensor: Optional[WindowsSensor] = None
        self._scrcpy_sensor: Optional[ScrcpySensor] = None
        self._sensor_lock = threading.Lock()
        
        # 控制器（始终使用 ADB）
        self._motor: Optional[AdbMotor] = None
        
        # 状态
        self._state = BridgeState.UNINITIALIZED
        self._state_lock = threading.RLock()
        
        # 帧监听器
        self._frame_listeners: List[Callable[[ScreenshotFrame], None]] = []
        self._listeners_lock = threading.Lock()
        
        # 统计
        self._start_time: float = 0.0
        self._error_count: int = 0
        self._error_lock = threading.Lock()
        
        logger.info(f"HybridL0Bridge创建 | 设备:{device_serial} | 自动检测模拟器:{self._config.auto_detect_emulator}")
    
    def _is_local_emulator(self) -> bool:
        """检测是否为本地模拟器"""
        # 检查设备序列号模式
        if ":" in self._device_serial:
            # 可能是 IP:PORT 格式
            parts = self._device_serial.split(":")
            if len(parts) == 2:
                ip = parts[0]
                # 本地地址
                if ip in ("127.0.0.1", "localhost", "::1"):
                    return True
                # 检查是否为本地网络
                if ip.startswith("192.168.") or ip.startswith("10."):
                    # 可能是局域网设备，进一步检查
                    pass
        
        # 检查设备属性
        try:
            model = self._adb_client.get_device_model(self._device_serial)
            # 常见模拟器特征
            emulator_keywords = ["emulator", "sdk", "google", "generic"]
            if any(kw in model.lower() for kw in emulator_keywords):
                return True
        except Exception:
            pass
        
        return False
    
    def _select_backend(self) -> CaptureBackend:
        """选择最佳截图后端"""
        if self._config.preferred_backend != CaptureBackend.AUTO:
            return self._config.preferred_backend
        
        if self._config.auto_detect_emulator:
            if self._is_local_emulator():
                logger.info("检测到本地模拟器，使用 Windows 截图")
                return CaptureBackend.WINDOWS
        
        logger.info("使用 ADB 截图")
        return CaptureBackend.ADB
    
    def initialize(self) -> bool:
        """初始化混合桥接器
        
        Returns:
            初始化是否成功
        """
        self._set_state(BridgeState.INITIALIZING)
        
        try:
            # 选择后端
            with self._backend_lock:
                self._backend = self._select_backend()
            
            # 初始化控制器（始终使用 ADB）
            resolution = self._adb_client.get_screen_resolution(
                self._device_serial,
                force_refresh=True,
            )
            if resolution == (0, 0):
                resolution = (1920, 1080)
                logger.warning(f"无法获取分辨率，使用默认值:{resolution}")
            
            self._motor = AdbMotor(
                adb_client=self._adb_client,
                device_serial=self._device_serial,
                screen_resolution=resolution,
                config=self._config.bridge_config.motor_config,
            )
            
            # 根据后端初始化传感器
            if self._backend == CaptureBackend.SCRCPY:
                success = self._init_scrcpy_sensor()
                if not success and self._config.fallback_on_failure:
                    logger.warning("Scrcpy 传感器初始化失败，回退到 ADB")
                    self._backend = CaptureBackend.ADB
                    self._init_adb_sensor()
            elif self._backend == CaptureBackend.WINDOWS:
                success = self._init_windows_sensor()
                if not success and self._config.fallback_on_failure:
                    logger.warning("Windows 传感器初始化失败，回退到 ADB")
                    self._backend = CaptureBackend.ADB
                    self._init_adb_sensor()
            else:
                self._init_adb_sensor()
            
            self._start_time = time.monotonic()
            self._set_state(BridgeState.READY)
            
            logger.info(f"HybridL0Bridge初始化完成 | 后端:{self._backend.name} | 分辨率:{resolution}")
            
            if self._config.bridge_config.auto_start_sensor:
                self.start()
            
            return True
            
        except Exception as e:
            logger.error(f"初始化失败: {e}", exc_info=True)
            self._set_state(BridgeState.ERROR)
            raise L0BridgeError(f"初始化失败: {e}")
    
    def _init_windows_sensor(self) -> bool:
        """初始化 Windows 传感器"""
        try:
            # 根据 windows_specific_method 设置转换 CaptureMethod
            method_map = {
                "auto": CaptureMethod.AUTO,
                "wgc": CaptureMethod.WGC,
                "bitblt": CaptureMethod.BITBLT,
                "printwindow": CaptureMethod.PRINTWINDOW,
            }
            capture_method = method_map.get(
                self._config.windows_specific_method,
                CaptureMethod.AUTO
            )

            logger.info(f"初始化 Windows 传感器 | 指定方式: {self._config.windows_specific_method} → {capture_method.name}")

            self._windows_sensor = WindowsSensor(
                window_title=self._config.emulator_window_title,
                config=WindowsSensorConfig(
                    capture_method=capture_method,
                    client_only=True,
                ),
                on_frame_callback=self._on_windows_frame,
                on_error_callback=self._on_sensor_error,
            )
            return True
        except Exception as e:
            logger.warning(f"Windows 传感器初始化失败: {e}")
            return False
    
    def _init_scrcpy_sensor(self) -> bool:
        """初始化 Scrcpy 传感器"""
        try:
            logger.info("初始化 Scrcpy 传感器 | 超低延迟模式")
            
            # 获取裁剪设置 - 使用绝对导入避免相对导入问题
            import sys
            from pathlib import Path
            src_path = Path(__file__).parent.parent.parent
            if str(src_path) not in sys.path:
                sys.path.insert(0, str(src_path))
            from utils.config import get_config
            config = get_config()
            crop_settings = config.get('preview.crop', {})
            crop_top = crop_settings.get('top', 0)
            crop_bottom = crop_settings.get('bottom', 0)
            crop_left = crop_settings.get('left', 0)
            crop_right = crop_settings.get('right', 0)
            
            # 构建Scrcpy配置
            # Scrcpy支持高帧率，使用60fps或从设置读取
            try:
                from utils.config import get_config
                config = get_config()
                target_fps = config.get('ui.preview_fps', 60)
            except Exception:
                target_fps = 60
            
            scrcpy_config = ScrcpyConfig(
                target_fps=target_fps,
                max_buffer_size=self._config.bridge_config.sensor_config.max_buffer_size,
                bitrate=4000000,  # 4Mbps 降低比特率以减少解码错误
            )
            
            # 如果有裁剪设置，传递给Scrcpy
            if crop_top > 0 or crop_bottom > 0 or crop_left > 0 or crop_right > 0:
                # Scrcpy裁剪格式: width:height:x:y
                # 注意: Scrcpy裁剪是在设备端进行的
                pass  # 暂时不实现，后续可以添加
            
            self._scrcpy_sensor = ScrcpySensor(
                device_serial=self._device_serial,
                config=scrcpy_config,
                on_error=self._on_sensor_error,
            )
            
            logger.info("Scrcpy 传感器初始化成功")
            return True
            
        except Exception as e:
            import traceback
            logger.warning(f"Scrcpy 传感器初始化失败: {e}")
            logger.debug(f"Scrcpy 初始化错误堆栈:\n{traceback.format_exc()}")
            return False
    
    def _init_adb_sensor(self) -> None:
        """初始化 ADB 传感器"""
        self._adb_sensor = AdbSensor(
            adb_client=self._adb_client,
            device_serial=self._device_serial,
            config=self._config.bridge_config.sensor_config,
            on_frame_callback=self._on_adb_frame,
            on_error_callback=self._on_sensor_error,
        )
    
    def _convert_windows_frame(self, frame: WindowsScreenshotFrame) -> ScreenshotFrame:
        """将 Windows 帧转换为 ADB 帧格式"""
        # 创建兼容的 ScreenshotFrame
        from .sensor import FrameMetadata
        
        metadata = FrameMetadata(
            timestamp=frame.metadata.timestamp if frame.metadata else time.monotonic(),
            sequence_number=frame.metadata.sequence_number if frame.metadata else 0,
            capture_latency_ms=frame.metadata.capture_latency_ms if frame.metadata else 0.0,
            resolution=frame.metadata.resolution if frame.metadata else (0, 0),
            size_bytes=frame.image_numpy.size if frame.image_numpy is not None else 0,
            quality_score=0.0,
        )
        
        return ScreenshotFrame(
            image_data=b'',  # Windows 截图没有原始 PNG 数据
            image_numpy=frame.image_numpy,
            metadata=metadata,
        )
    
    def _on_windows_frame(self, frame: WindowsScreenshotFrame) -> None:
        """Windows 传感器帧回调"""
        # 转换为标准格式并转发
        converted = self._convert_windows_frame(frame)
        self._forward_frame(converted)
    
    def _on_adb_frame(self, frame: ScreenshotFrame) -> None:
        """ADB 传感器帧回调"""
        self._forward_frame(frame)
    
    def _forward_frame(self, frame: ScreenshotFrame) -> None:
        """转发帧到所有监听器"""
        with self._listeners_lock:
            listeners_copy = list(self._frame_listeners)
        
        for listener in listeners_copy:
            try:
                listener(frame)
            except Exception as e:
                logger.error(f"帧监听器执行异常: {e}")
    
    def _on_sensor_error(self, error: Exception) -> None:
        """传感器错误回调"""
        self._record_error(error)
        
        if self._on_error:
            try:
                self._on_error(error)
            except Exception as e:
                logger.error(f"错误回调执行失败: {e}")
    
    def _record_error(self, error: Exception) -> None:
        """记录错误"""
        with self._error_lock:
            self._error_count += 1
    
    def _set_state(self, new_state: BridgeState) -> None:
        """更新状态"""
        with self._state_lock:
            old_state = self._state
            self._state = new_state
        
        if old_state != new_state:
            logger.info(f"状态变更: {old_state.name} → {new_state.name}")
            if self._on_state_change:
                try:
                    self._on_state_change(new_state)
                except Exception as e:
                    logger.error(f"状态变更回调失败: {e}")
    
    def start(self) -> None:
        """启动传感器"""
        logger.info(f"HybridL0Bridge.start() 被调用 | 当前状态:{self._state.name} | 后端:{self._backend.name}")

        if self._state not in (BridgeState.READY, BridgeState.PAUSED):
            raise BridgeNotReadyError(f"桥接器未就绪，当前状态: {self._state.name}")

        # 先获取传感器引用（在锁内），然后在锁外启动（避免死锁）
        sensor_to_start = None
        with self._sensor_lock:
            if self._backend == CaptureBackend.SCRCPY:
                logger.debug(f"Scrcpy后端 | _scrcpy_sensor={self._scrcpy_sensor is not None}")
                if self._scrcpy_sensor:
                    sensor_to_start = ('scrcpy', self._scrcpy_sensor)
                else:
                    logger.error("Scrcpy传感器为None")
                    raise BridgeNotReadyError("Scrcpy传感器未初始化")
            elif self._backend == CaptureBackend.WINDOWS:
                logger.debug(f"Windows后端 | _windows_sensor={self._windows_sensor is not None}")
                if self._windows_sensor:
                    sensor_to_start = ('windows', self._windows_sensor)
                else:
                    logger.error("Windows传感器为None")
                    raise BridgeNotReadyError("Windows传感器未初始化")
            elif self._adb_sensor:
                sensor_to_start = ('adb', self._adb_sensor)
            else:
                logger.error("没有可用的传感器")
                raise BridgeNotReadyError("没有可用的传感器")

        # 在锁外启动传感器，避免阻塞其他操作（如 get_latest_frame）
        if sensor_to_start:
            sensor_type, sensor = sensor_to_start
            logger.info(f"启动{sensor_type.upper()}传感器...")
            sensor.start()
            logger.info(f"{sensor_type.upper()}传感器启动完成")
            
            # 如果是 Scrcpy 传感器，启动后同步分辨率到 motor
            if sensor_type == 'scrcpy' and self._motor:
                try:
                    # 等待传感器获取到第一帧，获取实际分辨率
                    import time
                    max_wait = 5.0  # 最多等待5秒
                    wait_start = time.time()
                    scrcpy_resolution = None
                    
                    while time.time() - wait_start < max_wait:
                        if hasattr(sensor, '_client') and sensor._client:
                            scrcpy_resolution = sensor._client.resolution
                            if scrcpy_resolution and scrcpy_resolution[0] > 0:
                                break
                        time.sleep(0.1)
                    
                    if scrcpy_resolution and scrcpy_resolution[0] > 0:
                        # 更新 motor 的分辨率，使其与 Scrcpy 采集的分辨率一致
                        old_resolution = self._motor.screen_resolution
                        self._motor.screen_resolution = scrcpy_resolution
                        logger.info(f"分辨率已同步: ADB={old_resolution} -> Scrcpy={scrcpy_resolution}")
                    else:
                        logger.warning("无法获取 Scrcpy 实际分辨率，使用 ADB 分辨率")
                        
                except Exception as e:
                    logger.warning(f"同步分辨率失败: {e}")

        self._set_state(BridgeState.RUNNING)
        logger.info(f"HybridL0Bridge已启动 | 后端:{self._backend.name}")
    
    def stop(self) -> None:
        """停止传感器"""
        with self._sensor_lock:
            if self._scrcpy_sensor:
                self._scrcpy_sensor.stop()
            if self._windows_sensor:
                self._windows_sensor.stop()
            if self._adb_sensor:
                self._adb_sensor.stop()
        
        self._set_state(BridgeState.READY)
        logger.info("HybridL0Bridge已停止")
    
    def pause(self) -> None:
        """暂停"""
        with self._sensor_lock:
            if self._scrcpy_sensor:
                self._scrcpy_sensor.stop()  # Scrcpy不支持暂停，直接停止
            if self._windows_sensor:
                self._windows_sensor.pause()
            if self._adb_sensor:
                self._adb_sensor.pause()
        self._set_state(BridgeState.PAUSED)
    
    def resume(self) -> None:
        """恢复"""
        with self._sensor_lock:
            if self._scrcpy_sensor:
                self._scrcpy_sensor.start()  # Scrcpy需要重新启动
            if self._windows_sensor:
                self._windows_sensor.resume()
            if self._adb_sensor:
                self._adb_sensor.resume()
        if self._state == BridgeState.PAUSED:
            self._set_state(BridgeState.RUNNING)
    
    def shutdown(self) -> None:
        """关闭桥接器"""
        logger.info("正在关闭 HybridL0Bridge...")
        
        try:
            with self._sensor_lock:
                if self._scrcpy_sensor:
                    self._scrcpy_sensor.stop()
                    self._scrcpy_sensor = None
                if self._windows_sensor:
                    self._windows_sensor.stop()
                    self._windows_sensor = None
                if self._adb_sensor:
                    self._adb_sensor.stop()
                    self._adb_sensor = None
            
            if self._motor:
                self._motor.stop_async_mode()
                self._motor = None
            
            with self._listeners_lock:
                self._frame_listeners.clear()
                
        except Exception as e:
            logger.error(f"关闭过程异常: {e}", exc_info=True)
        
        self._set_state(BridgeState.SHUTDOWN)
        logger.info("HybridL0Bridge已完全关闭")
    
    def get_latest_frame(self, timeout: float = 0.0) -> Optional[ScreenshotFrame]:
        """获取最新帧"""
        with self._sensor_lock:
            if self._backend == CaptureBackend.SCRCPY and self._scrcpy_sensor:
                scrcpy_frame = self._scrcpy_sensor.get_latest_frame(timeout)
                if scrcpy_frame:
                    # Scrcpy帧已经是ScreenshotFrame格式
                    return scrcpy_frame
            elif self._backend == CaptureBackend.WINDOWS and self._windows_sensor:
                frame = self._windows_sensor.get_latest_frame(timeout)
                if frame:
                    return self._convert_windows_frame(frame)
            elif self._adb_sensor:
                return self._adb_sensor.get_latest_frame(timeout)
        
        return None
    
    def add_frame_listener(self, listener: Callable[[ScreenshotFrame], None]) -> None:
        """添加帧监听器"""
        with self._listeners_lock:
            self._frame_listeners.append(listener)
    
    def remove_frame_listener(self, listener: Callable[[ScreenshotFrame], None]) -> None:
        """移除帧监听器"""
        with self._listeners_lock:
            try:
                self._frame_listeners.remove(listener)
            except ValueError:
                pass
    
    # 输入控制方法（代理到 motor）
    def tap(self, x: int, y: int, **kwargs) -> bool:
        if self._motor is None:
            raise BridgeNotReadyError("控制器未初始化")
        return self._motor.tap(x, y, **kwargs)
    
    def swipe(self, x1: int, y1: int, x2: int, y2: int, **kwargs) -> bool:
        if self._motor is None:
            raise BridgeNotReadyError("控制器未初始化")
        return self._motor.swipe(x1, y1, x2, y2, **kwargs)
    
    def drag(self, x1: int, y1: int, x2: int, y2: int, **kwargs) -> bool:
        if self._motor is None:
            raise BridgeNotReadyError("控制器未初始化")
        return self._motor.drag(x1, y1, x2, y2, **kwargs)
    
    def long_press(self, x: int, y: int, **kwargs) -> bool:
        if self._motor is None:
            raise BridgeNotReadyError("控制器未初始化")
        return self._motor.long_press(x, y, **kwargs)
    
    def text_input(self, text: str, **kwargs) -> bool:
        if self._motor is None:
            raise BridgeNotReadyError("控制器未初始化")
        return self._motor.text_input(text, **kwargs)
    
    def key_event(self, keycode: str, **kwargs) -> bool:
        if self._motor is None:
            raise BridgeNotReadyError("控制器未初始化")
        return self._motor.key_event(keycode, **kwargs)
    
    def press_back(self, **kwargs) -> bool:
        return self.key_event("KEYCODE_BACK", **kwargs)
    
    def press_home(self, **kwargs) -> bool:
        return self.key_event("KEYCODE_HOME", **kwargs)
    
    def get_sensor_resolution(self) -> Tuple[int, int]:
        """获取传感器的实际分辨率（用于坐标映射）
        
        Returns:
            (width, height) 元组
        """
        with self._sensor_lock:
            if self._backend == CaptureBackend.SCRCPY and self._scrcpy_sensor:
                # 优先使用 Scrcpy 传感器的分辨率
                if hasattr(self._scrcpy_sensor, '_client') and self._scrcpy_sensor._client:
                    res = self._scrcpy_sensor._client.resolution
                    if res and res[0] > 0:
                        return res
                # 回退：使用 motor 的分辨率（已经同步过）
                if self._motor:
                    return self._motor.screen_resolution
            elif self._backend == CaptureBackend.WINDOWS and self._windows_sensor:
                # Windows 传感器使用 motor 的分辨率
                if self._motor:
                    return self._motor.screen_resolution
            elif self._adb_sensor:
                return self._adb_sensor.resolution
        
        # 默认回退
        return (1920, 1080)
    
    def is_window_minimized(self) -> bool:
        """检测Windows截图窗口是否最小化

        Returns:
            True如果窗口最小化，False如果未最小化或非Windows模式
        """
        if self._backend != CaptureBackend.WINDOWS:
            return False

        # 使用非阻塞方式获取锁，避免卡死主线程
        if self._sensor_lock.acquire(blocking=False):
            try:
                if self._windows_sensor:
                    return self._windows_sensor._is_window_minimized()
            finally:
                self._sensor_lock.release()
        return False

    def get_health_report(self) -> BridgeHealthReport:
        """获取健康报告"""
        report = BridgeHealthReport(
            timestamp=time.monotonic(),
            bridge_state=self._state,
            device_connected=False,
        )
        
        # 获取传感器统计
        with self._sensor_lock:
            if self._backend == CaptureBackend.WINDOWS and self._windows_sensor:
                stats = self._windows_sensor.get_statistics()
                report.sensor_state = SensorState.RUNNING if self._windows_sensor.is_running() else SensorState.STOPPED
                report.sensor_fps = stats.get('current_fps', 0.0)
                report.sensor_latency_ms = stats.get('avg_latency_ms', 0.0)
            elif self._adb_sensor:
                stats = self._adb_sensor.get_performance_stats()
                report.sensor_state = self._adb_sensor.state
                report.sensor_fps = stats.get('current_fps', 0.0)
                report.sensor_latency_ms = stats.get('average_latency_ms', 0.0)
        
        # 获取控制器统计
        if self._motor:
            motor_stats = self._motor.get_statistics()
            report.motor_queue_size = motor_stats.get('queue_size', 0)
            report.motor_total_ops = motor_stats.get('total_operations', 0)
        
        # 检查设备连接
        try:
            report.device_connected = self._adb_client.check_device_health(self._device_serial)
        except Exception:
            report.device_connected = False
        
        # 运行时间
        if self._start_time > 0:
            report.uptime_seconds = time.monotonic() - self._start_time
        
        # 错误计数
        with self._error_lock:
            report.error_count = self._error_count
        
        # 警告
        if report.sensor_fps < 5.0 and self.is_running:
            report.warnings.append(f"传感器帧率过低: {report.sensor_fps:.1f}fps")
        if report.sensor_latency_ms > 200.0:
            report.warnings.append(f"截图延迟过高: {report.sensor_latency_ms:.1f}ms")
        
        return report
    
    # 属性
    @property
    def state(self) -> BridgeState:
        return self._state
    
    @property
    def is_ready(self) -> bool:
        return self._state in (BridgeState.READY, BridgeState.RUNNING)
    
    @property
    def is_running(self) -> bool:
        return self._state == BridgeState.RUNNING
    
    @property
    def device_serial(self) -> str:
        return self._device_serial
    
    @property
    def backend(self) -> CaptureBackend:
        return self._backend
    
    @property
    def motor(self) -> Optional[AdbMotor]:
        return self._motor
