"""
L0感知执行层 - 通信桥接接口(L0Bridge)

职责:
- 封装AdbSensor和AdbMotor的联合操作
- 提供L0层对外的统一API（供上层L1-L5调用）
- 管理传感器和控制器的生命周期同步
- 实现状态聚合与健康报告

设计模式:
- Facade模式: 将Sensor+Motor组合为统一接口
- Observer模式: 支持多监听器订阅帧数据和操作事件
- Singleton倾向: 每个设备对应一个Bridge实例
"""

import threading
import time
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Callable, Dict, List, Any, Tuple
from .sensor import AdbSensor, ScreenshotFrame, SensorState, SensorConfig
from .motor import AdbMotor, MotorConfig, InputAction


logger = logging.getLogger(__name__)


class BridgeState(Enum):
    """桥接器整体状态枚举"""
    UNINITIALIZED = auto()   # 未初始化
    INITIALIZING = auto()    # 正在初始化
    READY = auto()           # 就绪（已连接但未开始采集）
    RUNNING = auto()         # 运行中（采集+控制均激活）
    PAUSED = auto()          # 已暂停
    ERROR = auto()           # 错误状态
    SHUTDOWN = auto()        # 已关闭


@dataclass
class BridgeHealthReport:
    """健康检查报告数据类
    
    Attributes:
        timestamp: 报告生成时间
        bridge_state: 当前桥接器状态
        sensor_state: 传感器状态
        sensor_fps: 传感器当前帧率
        sensor_latency_ms: 平均截图延迟
        motor_queue_size: 控制器待处理队列长度
        motor_total_ops: 控制器总操作数
        device_connected: 设备是否在线
        uptime_seconds: 本次运行时长(秒)
        error_count: 自启动以来的错误计数
        warnings: 警告信息列表
    """
    timestamp: float = field(default_factory=time.time)
    bridge_state: BridgeState = BridgeState.UNINITIALIZED
    sensor_state: SensorState = SensorState.STOPPED
    sensor_fps: float = 0.0
    sensor_latency_ms: float = 0.0
    motor_queue_size: int = 0
    motor_total_ops: int = 0
    device_connected: bool = False
    uptime_seconds: float = 0.0
    error_count: int = 0
    warnings: List[str] = field(default_factory=list)


@dataclass
class BridgeConfig:
    """桥接器配置集合
    
    Attributes:
        sensor_config: 截图传感器配置
        motor_config: 输入控制器配置
        auto_start_sensor: 连接后是否自动启动传感器
        auto_start_health_monitor: 是否启用自动健康监控
        health_check_interval: 健康检查间隔(秒)
        enable_frame_callback: 是否启用帧回调转发
        max_startup_retries: 启动最大重试次数
    """
    sensor_config: SensorConfig = field(default_factory=SensorConfig)
    motor_config: MotorConfig = field(default_factory=MotorConfig)
    auto_start_sensor: bool = False
    auto_start_health_monitor: bool = True
    health_check_interval: float = 10.0
    enable_frame_callback: bool = True
    max_startup_retries: int = 3


DEFAULT_BRIDGE_CONFIG = BridgeConfig()


class L0BridgeError(Exception):
    """桥接器异常基类"""
    pass


class BridgeNotReadyError(L0BridgeError):
    """桥接器未就绪时的非法操作"""
    pass


class L0Bridge:
    """L0层对外通信桥接器
    
    作为AMA架构中感知执行层(L0)的唯一对外出口，
    统一管理截图(AdbSensor)和输入(AdbMotor)两大核心能力。
    
    核心能力:
    - 设备连接管理与状态监控
    - 高频截图采集 + 低延迟触控输出
    - 操作日志记录与性能统计
    - 异常检测与自动恢复
    
    上层调用示例 (L1反射层):
    
        bridge = L0Bridge(adb_client, device_serial)
        bridge.initialize()
        
        frame = bridge.get_latest_frame()
        if frame and bridge.detect_enemy(frame.image_numpy):
            bridge.tap(enemy_x, enemy_y)
        
        stats = bridge.get_health_report()
    
    Time Complexity:
    - initialize(): O(1) 创建子组件
    - get_latest_frame(): O(1) 直接代理到sensor
    - tap()/swipe(): O(1) 直接代理到motor
    - shutdown(): O(1) 清理资源
    """
    
    def __init__(
        self,
        adb_client,
        device_serial: str,
        config: Optional[BridgeConfig] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_state_change: Optional[Callable[[BridgeState], None]] = None,
    ):
        """初始化L0桥接器
        
        Args:
            adb_client: ADBClient实例
            device_serial: 目标设备序列号
            config: 桥接器配置
            on_error: 全局错误回调
            on_state_change: 状态变更回调
            
        Raises:
            ValueError: 参数无效
        """
        if adb_client is None:
            raise ValueError("ADB客户端不能为None")
        if not device_serial:
            raise ValueError("设备序列号不能为空")
        
        self._adb_client = adb_client
        self._device_serial = device_serial
        self._config = config or DEFAULT_BRIDGE_CONFIG
        
        self._state = BridgeState.UNINITIALIZED
        self._state_lock = threading.RLock()
        
        self._sensor: Optional[AdbSensor] = None
        self._motor: Optional[AdbMotor] = None
        
        self._start_time: float = 0.0
        self._error_count: int = 0
        self._error_lock = threading.Lock()
        
        self._on_error = on_error
        self._on_state_change = on_state_change
        
        self._frame_listeners: List[Callable[[ScreenshotFrame], None]] = []
        self._listeners_lock = threading.Lock()
        
        logger.info(f"L0Bridge创建 | 设备:{device_serial}")
    
    @property
    def state(self) -> BridgeState:
        """返回当前桥接器状态"""
        with self._state_lock:
            return self._state
    
    @property
    def is_ready(self) -> bool:
        """桥接器是否就绪可使用"""
        return self._state in (BridgeState.READY, BridgeState.RUNNING)
    
    @property
    def is_running(self) -> bool:
        """桥接器是否正在运行"""
        return self._state == BridgeState.RUNNING
    
    @property
    def device_serial(self) -> str:
        """返回目标设备序列号"""
        return self._device_serial
    
    @property
    def sensor(self) -> Optional[AdbSensor]:
        """访问底层传感器实例（高级用法）"""
        return self._sensor
    
    @property
    def motor(self) -> Optional[AdbMotor]:
        """访问底层控制器实例（高级用法）"""
        return self._motor
    
    def _set_state(self, new_state: BridgeState) -> None:
        """更新内部状态并通知观察者"""
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
    
    def initialize(self) -> bool:
        """初始化桥接器（创建Sensor和Motor实例）
        
        执行流程:
        1. 验证设备连接可用性
        2. 获取屏幕分辨率
        3. 创建AdbSensor和AdbMotor实例
        4. 注册内部回调用于状态联动
        5. 更新状态为READY
        
        Returns:
            初始化是否成功
            
        Raises:
            L0BridgeError: 初始化过程中发生不可恢复的错误
        """
        self._set_state(BridgeState.INITIALIZING)
        
        logger.info(f"正在初始化L0Bridge | 设备:{self._device_serial}")
        
        for attempt in range(self._config.max_startup_retries):
            try:
                health_ok = self._adb_client.check_device_health(self._device_serial)
                
                if not health_ok:
                    logger.warning(
                        f"设备健康检查失败 (尝试 {attempt + 1}/"
                        f"{self._config.max_startup_retries})"
                    )
                    time.sleep(1.0)
                    continue
                
                resolution = self._adb_client.get_screen_resolution(
                    self._device_serial,
                    force_refresh=True,
                )
                
                if resolution == (0, 0):
                    resolution = (1920, 1080)
                    logger.warning(f"无法获取分辨率，使用默认值:{resolution}")
                
                self._sensor = AdbSensor(
                    adb_client=self._adb_client,
                    device_serial=self._device_serial,
                    config=self._config.sensor_config,
                    on_frame_callback=self._on_sensor_frame,
                    on_error_callback=self._on_sensor_error,
                )
                
                self._motor = AdbMotor(
                    adb_client=self._adb_client,
                    device_serial=self._device_serial,
                    screen_resolution=resolution,
                    config=self._config.motor_config,
                    on_operation_complete=self._on_motor_operation_complete,
                )
                
                self._start_time = time.monotonic()
                self._error_count = 0
                
                self._set_state(BridgeState.READY)
                
                logger.info(
                    f"L0Bridge初始化完成 | 分辨率:{resolution} | "
                    f"传感器FPS目标:{self._config.sensor_config.target_fps}"
                )
                
                if self._config.auto_start_sensor:
                    self.start()
                
                return True
                
            except Exception as e:
                logger.error(
                    f"初始化失败 (尝试 {attempt + 1}/"
                    f"{self._config.max_startup_retries}): {e}",
                    exc_info=True,
                )
                self._record_error(e)
                
                if attempt < self._config.max_startup_retries - 1:
                    time.sleep(2.0 ** attempt)
        
        self._set_state(BridgeState.ERROR)
        raise L0BridgeError(
            f"初始化失败，已耗尽{self._config.max_startup_retries}次重试"
        )
    
    def start(self) -> None:
        """启动传感器采集（进入RUNNING状态）"""
        if not self.is_ready:
            raise BridgeNotReadyError(
                f"桥接器未就绪，当前状态: {self._state.name}"
            )
        
        if self._sensor:
            self._sensor.start()
        
        self._set_state(BridgeState.RUNNING)
        logger.info("L0Bridge已启动（传感器采集中）")
    
    def stop(self) -> None:
        """停止传感器采集（回到READY状态）"""
        if self._sensor:
            self._sensor.stop()
        
        self._set_state(BridgeState.READY)
        logger.info("L0Bridge已停止")
    
    def pause(self) -> None:
        """暂停所有活动"""
        if self._sensor:
            self._sensor.pause()
        self._set_state(BridgeState.PAUSED)
    
    def resume(self) -> None:
        """从暂停恢复"""
        if self._sensor:
            self._sensor.resume()
        if self._state == BridgeState.PAUSED:
            self._set_state(BridgeState.RUNNING)
    
    def shutdown(self) -> None:
        """完全关闭桥接器，释放所有资源
        
        清理顺序:
        1. 停止传感器采集线程
        2. 停止控制器异步队列
        3. 清空监听器列表
        4. 更新状态为SHUTDOWN
        """
        logger.info("正在关闭L0Bridge...")
        
        try:
            if self._sensor:
                self._sensor.stop(timeout=3.0)
                self._sensor = None
            
            if self._motor:
                self._motor.stop_async_mode(timeout=3.0)
                self._motor = None
            
            with self._listeners_lock:
                self._frame_listeners.clear()
            
        except Exception as e:
            logger.error(f"关闭过程异常: {e}", exc_info=True)
        
        self._set_state(BridgeState.SHUTDOWN)
        logger.info("L0Bridge已完全关闭")
    
    def get_latest_frame(self, timeout: float = 0.0) -> Optional[ScreenshotFrame]:
        """获取最新截图帧（代理到sensor）
        
        Args:
            timeout: 等待超时（秒），0表示非阻塞
            
        Returns:
            最新的ScreenshotFrame对象
        """
        if self._sensor is None:
            return None
        return self._sensor.get_latest_frame(timeout=timeout)
    
    def add_frame_listener(self, listener: Callable[[ScreenshotFrame], None]) -> None:
        """注册帧数据监听器
        
        Args:
            listener: 回调函数，接收ScreenshotFrame参数
        """
        with self._listeners_lock:
            self._frame_listeners.append(listener)
        logger.debug(f"帧监听器已注册 | 总数:{len(self._frame_listeners)}")
    
    def remove_frame_listener(self, listener: Callable[[ScreenshotFrame], None]) -> None:
        """移除帧数据监听器"""
        with self._listeners_lock:
            try:
                self._frame_listeners.remove(listener)
            except ValueError:
                pass
    
    def tap(self, x: int, y: int, **kwargs) -> bool:
        """点击屏幕坐标（代理到motor）"""
        if self._motor is None:
            raise BridgeNotReadyError("控制器未初始化")
        return self._motor.tap(x, y, **kwargs)
    
    def swipe(self, x1: int, y1: int, x2: int, y2: int, **kwargs) -> bool:
        """滑动操作（代理到motor）"""
        if self._motor is None:
            raise BridgeNotReadyError("控制器未初始化")
        return self._motor.swipe(x1, y1, x2, y2, **kwargs)
    
    def drag(self, x1: int, y1: int, x2: int, y2: int, **kwargs) -> bool:
        """拖拽操作（代理到motor）"""
        if self._motor is None:
            raise BridgeNotReadyError("控制器未初始化")
        return self._motor.drag(x1, y1, x2, y2, **kwargs)
    
    def long_press(self, x: int, y: int, **kwargs) -> bool:
        """长按操作（代理到motor）"""
        if self._motor is None:
            raise BridgeNotReadyError("控制器未初始化")
        return self._motor.long_press(x, y, **kwargs)
    
    def text_input(self, text: str, **kwargs) -> bool:
        """文本输入（代理到motor）"""
        if self._motor is None:
            raise BridgeNotReadyError("控制器未初始化")
        return self._motor.text_input(text, **kwargs)
    
    def key_event(self, keycode: str, **kwargs) -> bool:
        """按键事件（代理到motor）"""
        if self._motor is None:
            raise BridgeNotReadyError("控制器未初始化")
        return self._motor.key_event(keycode, **kwargs)
    
    def press_back(self, **kwargs) -> bool:
        """快捷方法：按下返回键"""
        return self.key_event("KEYCODE_BACK", **kwargs)
    
    def press_home(self, **kwargs) -> bool:
        """快捷方法：按下Home键"""
        return self.key_event("KEYCODE_HOME", **kwargs)
    
    def get_health_report(self) -> BridgeHealthReport:
        """生成完整的健康检查报告
        
        Returns:
            BridgeHealthReport对象，包含各组件的状态快照
        """
        report = BridgeHealthReport(
            timestamp=time.monotonic(),
            bridge_state=self._state,
            device_connected=False,
        )
        
        if self._sensor:
            stats = self._sensor.get_performance_stats()
            report.sensor_state = self._sensor.state
            report.sensor_fps = stats.get('current_fps', 0.0)
            report.sensor_latency_ms = stats.get('average_latency_ms', 0.0)
        
        if self._motor:
            motor_stats = self._motor.get_statistics()
            report.motor_queue_size = motor_stats.get('queue_size', 0)
            report.motor_total_ops = motor_stats.get('total_operations', 0)
        
        try:
            report.device_connected = self._adb_client.check_device_health(
                self._device_serial
            )
        except Exception:
            report.device_connected = False
        
        if self._start_time > 0:
            report.uptime_seconds = time.monotonic() - self._start_time
        
        with self._error_lock:
            report.error_count = self._error_count
        
        if report.sensor_fps < 5.0 and self.is_running:
            report.warnings.append(
                f"传感器帧率过低: {report.sensor_fps:.1f}fps"
            )
        
        if report.sensor_latency_ms > 200.0:
            report.warnings.append(
                f"截图延迟过高: {report.sensor_latency_ms:.1f}ms"
            )
        
        if not report.device_connected:
            report.warnings.append("设备可能离线或无响应")
        
        return report
    
    def update_sensor_config(self, **kwargs) -> None:
        """动态更新传感器配置"""
        if self._sensor:
            self._sensor.update_config(**kwargs)
    
    def update_motor_config(self, **kwargs) -> None:
        """动态更新控制器配置"""
        if self._motor:
            current = self._motor.config
            for key, value in kwargs.items():
                if hasattr(current, key):
                    setattr(current, key, value)
    
    def _on_sensor_frame(self, frame: ScreenshotFrame) -> None:
        """传感器新帧回调（内部中转）"""
        if self._config.enable_frame_callback:
            with self._listeners_lock:
                listeners_copy = list(self._frame_listeners)
            
            for listener in listeners_copy:
                try:
                    listener(frame)
                except Exception as e:
                    logger.error(f"帧监听器执行异常: {e}")
    
    def _on_sensor_error(self, error: Exception) -> None:
        """传感器错误回调（内部处理）"""
        self._record_error(error)
        
        if self._on_error:
            try:
                self._on_error(error)
            except Exception as cb_err:
                logger.error(f"错误回调执行失败: {cb_err}")
    
    def _on_motor_operation_complete(
        self,
        action: InputAction,
        success: bool,
    ) -> None:
        """控制器操作完成回调（内部记录）"""
        if not success:
            logger.debug(f"操作失败: {action.id}")
    
    def _record_error(self, error: Exception) -> None:
        """记录错误（线程安全计数）"""
        with self._error_lock:
            self._error_count += 1
    
    def __enter__(self) -> 'L0Bridge':
        """上下文管理器入口"""
        self.initialize()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """上下文管理器出口"""
        self.shutdown()
    
    def __repr__(self) -> str:
        return (
            f"<L0Bridge device={self._device_serial[:12]}... "
            f"state={self._state.name}>"
        )
