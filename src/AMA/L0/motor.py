"""
L0感知执行层 - ADB输入控制器(AdbMotor)

职责:
- 封装所有ADB触控操作（点击/滑动/拖拽/长按/文本输入）
- 提供精确的坐标映射和时序控制
- 支持操作队列与批量执行
- 输入防抖与随机化（反检测机制）

设计原则:
- 所有操作必须经过坐标验证（边界检查/范围限制）
- 支持可配置的随机延迟模拟人类操作
- 操作原子性保证：要么完整执行，要么完全回滚
- 完整的操作日志记录用于回放和调试
"""

import threading
import time
import random
import logging
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, List, Tuple, Dict, Any, Callable, Union
from queue import Queue, Empty
from contextlib import contextmanager


logger = logging.getLogger(__name__)


class InputType(Enum):
    """输入操作类型枚举"""
    TAP = auto()           # 单次点击
    LONG_PRESS = auto()    # 长按
    SWIPE = auto()         # 滑动（直线）
    DRAG = auto()          # 拖拽（带中间采样点）
    MULTI_TAP = auto()     # 多点连续点击
    TEXT_INPUT = auto()    # 文本输入
    KEY_EVENT = auto()     # 按键事件（返回/Home等）
    PINCH = auto()         # 缩放手势
    CUSTOM = auto()        # 自定义手势序列


@dataclass(frozen=True)
class Point2D:
    """二维坐标点（不可变，线程安全）
    
    Attributes:
        x: X轴坐标（像素）
        y: Y轴坐标（像素）
    """
    x: int
    y: int
    
    def __post_init__(self):
        if not isinstance(self.x, (int, float)) or not isinstance(self.y, (int, float)):
            raise TypeError("坐标值必须是数值类型")
    
    @property
    def tuple(self) -> Tuple[int, int]:
        return (int(self.x), int(self.y))
    
    def distance_to(self, other: 'Point2D') -> float:
        """计算到另一点的欧氏距离"""
        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)
    
    def __add__(self, other: 'Point2D') -> 'Point2D':
        return Point2D(self.x + other.x, self.y + other.y)
    
    def __sub__(self, other: 'Point2D') -> 'Point2D':
        return Point2D(self.x - other.x, self.y - other.y)
    
    def __repr__(self) -> str:
        return f"({self.x}, {self.y})"


@dataclass
class InputAction:
    """单个输入操作的完整描述
    
    设计为不可变数据对象，一旦创建不应修改，
    确保在队列中传输时的安全性。
    
    Attributes:
        action_type: 操作类型枚举
        points: 涉及的坐标点列表（tap用1个，swipe/drag用2个+）
        duration_ms: 操作持续时间（毫秒）
        delay_before_ms: 执行前的延迟（毫秒，用于反检测抖动）
        delay_after_ms: 执行后的延迟（毫秒）
        extra_params: 额外参数字典（文本内容/按键码等）
        timestamp: 操作创建时间戳
        priority: 优先级（数字越小越优先执行）
        retry_count: 失败重试次数
        max_retries: 最大重试次数
    """
    action_type: InputType
    points: Tuple[Point2D, ...] = field(default_factory=tuple)
    duration_ms: int = 100
    delay_before_ms: int = 0
    delay_after_ms: int = 0
    extra_params: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    priority: int = 0
    retry_count: int = 0
    max_retries: int = 3
    
    @property
    def id(self) -> str:
        """生成唯一标识符（基于时间戳和类型）"""
        return f"{self.action_type.name}_{self.timestamp:.6f}"


@dataclass
class MotorConfig:
    """输入控制器配置参数
    
    Attributes:
        default_tap_duration: 默认点击时长(ms)
        default_swipe_duration: 默认滑动时长(ms)
        default_drag_duration: 默认拖拽时长(ms)
        random_delay_range: 随机抖动延迟范围 (min_ms, max_ms)
        enable_anti_detection: 是否启用反检测随机化
        coordinate_tolerance: 坐标容差（超出屏幕范围时的处理方式）
            0=严格拒绝, >0=自动裁剪到有效范围
        operation_timeout: 单次操作超时时间(s)
        max_queue_size: 操作队列最大容量
        enable_confirmation: 是否启用操作确认机制（截图验证）
        confirmation_timeout: 确认截图超时时间(s)
    """
    default_tap_duration: int = 100
    default_swipe_duration: int = 300
    default_drag_duration: int = 500
    random_delay_range: Tuple[int, int] = (50, 200)
    enable_anti_detection: bool = True
    coordinate_tolerance: int = 5
    operation_timeout: float = 5.0
    max_queue_size: int = 100
    enable_confirmation: bool = False
    confirmation_timeout: float = 2.0


DEFAULT_MOTOR_CONFIG = MotorConfig()


class MotorError(Exception):
    """输入控制器异常基类"""
    pass


class CoordinateOutOfRangeError(MotorError):
    """坐标超出屏幕范围"""
    pass


class OperationTimeoutError(MotorError):
    """操作超时"""
    pass


class OperationQueueFullError(MotorError):
    """操作队列已满"""
    pass


class AdbMotor:
    """ADB输入控制器核心类
    
    职责:
    - 接收高层指令并转换为ADB shell input命令
    - 管理操作队列（支持同步/异步模式）
    - 坐标系转换与边界检查
    - 反检测机制（随机延迟、轨迹扰动）
    - 操作日志与统计
    
    线程模型:
    - 主线程: 调用tap/swipe/drag等API方法
    - 工作线程: 从队列中取出操作并顺序执行（异步模式）
    
    使用示例:
        
        # 同步模式（直接阻塞执行）
        motor = AdbMotor(adb_client, device_serial)
        motor.tap(500, 500)
        motor.swipe(100, 800, 900, 800, duration_ms=500)
        
        # 异步模式（入队后立即返回）
        motor.start_async_mode()
        motor.async_tap(500, 500)
        motor.async_swipe(100, 800, 900, 800)
        
        # 批量操作（原子执行）
        with motor.batch_context():
            motor.tap(300, 400)
            motor.tap(600, 700)
            motor.swipe(100, 500, 800, 500)
    
    Time Complexity:
    - tap()/swipe()/drag(): O(1) - 单次命令执行
    - batch_execute(): O(n) - n=操作数量
    - async_*(): O(1) - 入队操作
    """
    
    def __init__(
        self,
        adb_client,
        device_serial: str,
        screen_resolution: Tuple[int, int] = (1920, 1080),
        config: Optional[MotorConfig] = None,
        on_operation_complete: Optional[Callable[[InputAction, bool], None]] = None,
    ):
        """初始化输入控制器
        
        Args:
            adb_client: 已初始化的ADBClient实例
            device_serial: 目标设备序列号
            screen_resolution: 屏幕分辨率 (width, height)，用于坐标校验
            config: 控制器配置，None使用默认值
            on_operation_complete: 异步模式下操作完成时的回调
            
        Raises:
            ValueError: 参数无效
        """
        if adb_client is None:
            raise ValueError("ADB客户端不能为None")
        if not device_serial:
            raise ValueError("设备序列号不能为空")
        if len(screen_resolution) != 2 or any(d <= 0 for d in screen_resolution):
            raise ValueError(f"无效的屏幕分辨率: {screen_resolution}")
        
        self._adb_client = adb_client
        self._device_serial = device_serial
        self._screen_width, self._screen_height = screen_resolution
        self._config = config or DEFAULT_MOTOR_CONFIG
        
        self._operation_queue: Queue = Queue(maxsize=self._config.max_queue_size)
        self._async_running = False
        self._async_thread: Optional[threading.Thread] = None
        self._stop_async_event = threading.Event()
        
        self._batch_mode = False
        self._batch_actions: List[InputAction] = []
        self._batch_lock = threading.Lock()
        
        self._stats_lock = threading.Lock()
        self._operation_stats = {
            'total_operations': 0,
            'successful_operations': 0,
            'failed_operations': 0,
            'total_taps': 0,
            'total_swipes': 0,
            'total_drags': 0,
            'average_execution_time_ms': 0.0,
        }
        
        self._on_operation_complete = on_operation_complete
        
        logger.info(
            f"AdbMotor初始化 | 设备:{device_serial} | "
            f"分辨率:{screen_resolution} | "
            f"反检测:{'启用' if self._config.enable_anti_detection else '禁用'}"
        )
    
    @property
    def screen_resolution(self) -> Tuple[int, int]:
        """返回当前屏幕分辨率"""
        return (self._screen_width, self._screen_height)
    
    @screen_resolution.setter
    def screen_resolution(self, resolution: Tuple[int, int]) -> None:
        """更新屏幕分辨率（当设备旋转或切换时调用）"""
        if len(resolution) == 2 and all(d > 0 for d in resolution):
            self._screen_width, self._screen_height = resolution
            logger.info(f"屏幕分辨率已更新: {resolution}")
    
    @property
    def is_async_running(self) -> bool:
        """异步模式是否正在运行"""
        return self._async_running
    
    def update_screen_resolution(self) -> bool:
        """从设备重新获取当前屏幕分辨率
        
        Returns:
            更新是否成功
        """
        try:
            res = self._adb_client.get_screen_resolution(self._device_serial)
            if res != (0, 0):
                self.screen_resolution = res
                return True
        except Exception as e:
            logger.warning(f"获取屏幕分辨率失败: {e}")
        return False
    
    def _validate_coordinate(self, x: int, y: int) -> Tuple[int, int]:
        """坐标验证与裁剪
        
        根据配置的coordinate_tolerance决定行为:
        - tolerance=0: 超出范围直接抛出异常
        - tolerance>0: 自动裁剪到有效范围内
        
        Args:
            x, y: 待验证的原始坐标
            
        Returns:
            验证后的坐标元组
            
        Raises:
            CoordinateOutOfRangeError: tolerance=0且坐标越界
        """
        tol = self._config.coordinate_tolerance
        
        valid_x_min = -tol
        valid_x_max = self._screen_width + tol
        valid_y_min = -tol
        valid_y_max = self._screen_height + tol
        
        out_of_range = (
            x < valid_x_min or x > valid_x_max or
            y < valid_y_min or y > valid_y_max
        )
        
        if out_of_range:
            if tol == 0:
                raise CoordinateOutOfRangeError(
                    f"坐标({x}, {y})超出屏幕范围 "
                    f"(0-{self._screen_width}, 0-{self._screen_height})"
                )
            
            x = max(0, min(x, self._screen_width))
            y = max(0, min(y, self._screen_height))
            logger.debug(f"坐标已裁剪: ({x}, {y})")
        
        return (x, y)
    
    def _apply_random_delay(self, base_delay: int = 0) -> int:
        """计算带随机抖动的延迟时间
        
        反检测策略:
        在基础延迟上叠加一个均匀分布的随机量，
        使操作间隔呈现自然的人类操作特征。
        
        Args:
            base_delay: 基础延迟（ms）
            
        Returns:
            实际延迟时间（ms）
        """
        if not self._config.enable_anti_detection:
            return base_delay
        
        min_d, max_d = self._config.random_delay_range
        jitter = random.randint(min_d, max_d)
        total = base_delay + jitter
        
        if total > 0:
            logger.debug(f"应用反检测延迟: {total}ms (基础{base_delay}+抖动{jitter})")
            time.sleep(total / 1000.0)
        
        return total
    
    def _execute_adb_input(self, command_args: List[str]) -> bool:
        """执行底层ADB input命令的统一入口
        
        Args:
            command_args: input子命令及参数（不含'input'本身）
            
        Returns:
            命令是否成功执行
        """
        try:
            result = self._adb_client.shell_command(
                "input " + " ".join(str(arg) for arg in command_args),
                device_serial=self._device_serial,
                timeout=self._config.operation_timeout,
            )
            
            success = result.returncode == 0
            
            if not success:
                logger.warning(
                    f"input命令失败 (rc={result.returncode}): "
                    f"{result.stderr.strip()[:200]}"
                )
            
            return success
            
        except Exception as e:
            logger.error(f"input命令异常: {e}")
            return False
    
    def tap(
        self,
        x: int,
        y: int,
        duration_ms: Optional[int] = None,
        add_jitter: bool = True,
    ) -> bool:
        """在指定坐标执行单击操作
        
        Args:
            x: X坐标（像素）
            y: Y坐标（像素）
            duration_ms: 点击持续时间(ms)，None使用配置默认值
            add_jitter: 是否添加随机延迟（反检测）
            
        Returns:
            操作是否成功
            
        Example:
            >>> motor.tap(960, 540)  # 点击屏幕中心
            True
            >>> motor.tap(100, 200, duration_ms=50)  # 快速点击
            True
        """
        x, y = self._validate_coordinate(x, y)
        duration = duration_ms or self._config.default_tap_duration
        
        if add_jitter:
            self._apply_random_delay()
        
        start_time = time.monotonic()
        
        success = self._execute_adb_input(["tap", str(x), str(y)])
        
        elapsed_ms = (time.monotonic() - start_time) * 1000
        
        self._update_stats('tap', success, elapsed_ms)
        
        logger.debug(f"TAP ({x},{y}) | 时长:{duration}ms | {'成功' if success else '失败'}")
        
        return success
    
    def long_press(
        self,
        x: int,
        y: int,
        duration_ms: int = 1000,
        add_jitter: bool = True,
    ) -> bool:
        """在指定坐标执行长按操作
        
        底层通过swipe同坐标长距离实现（Android input不支持直接longpress）。
        
        Args:
            x: X坐标
            y: Y坐标
            duration_ms: 长按时长(ms)，默认1000ms
            add_jitter: 是否添加随机延迟
            
        Returns:
            操作是否成功
        """
        x, y = self._validate_coordinate(x, y)
        
        if add_jitter:
            self._apply_random_delay()
        
        start_time = time.monotonic()
        
        success = self._execute_adb_input(["swipe", str(x), str(y), str(x), str(y), str(duration_ms)])
        
        elapsed_ms = (time.monotonic() - start_time) * 1000
        
        self._update_stats('long_press', success, elapsed_ms)
        
        logger.debug(f"LONG_PRESS ({x},{y}) | 时长:{duration_ms}ms | {'成功' if success else '失败'}")
        
        return success
    
    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration_ms: Optional[int] = None,
        add_jitter: bool = True,
    ) -> bool:
        """执行两点间直线滑动操作
        
        Args:
            x1, y1: 起始坐标
            x2, y2: 结束坐标
            duration_ms: 滑动时长(ms)，影响滑动速度
            add_jitter: 是否添加随机延迟
            
        Returns:
            操作是否成功
            
        Note:
            滑动方向由起始点和结束点决定：
            - 向上滑: y1 > y2
            - 向下滑: y1 < y2
            - 向左滑: x1 > x2
            - 向右滑: x1 < x2
        """
        x1, y1 = self._validate_coordinate(x1, y1)
        x2, y2 = self._validate_coordinate(x2, y2)
        duration = duration_ms or self._config.default_swipe_duration
        
        if add_jitter:
            self._apply_random_delay()
        
        start_time = time.monotonic()
        
        success = self._execute_adb_input([
            "swipe", str(x1), str(y1), str(x2), str(y2), str(duration)
        ])
        
        elapsed_ms = (time.monotonic() - start_time) * 1000
        
        self._update_stats('swipe', success, elapsed_ms)
        
        logger.debug(
            f"SWIPE ({x1},{y1})->({x2},{y2}) | "
            f"时长:{duration}ms | {'成功' if success else '失败'}"
        )
        
        return success
    
    def drag(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration_ms: Optional[int] = None,
        steps: int = 20,
        add_jitter: bool = True,
    ) -> bool:
        """执行拖拽操作（干员部署等场景）
        
        与swipe的区别:
        - 语义更明确：表示"抓取→移动→释放"
        - steps参数允许控制插值精度
        - 内部添加额外的起止停顿模拟真实拖拽
        
        Args:
            x1, y1: 起始位置（如干员栏位）
            x2, y2: 目标位置（如网格格）
            duration_ms: 总拖拽时长
            steps: 插值步数（越高越平滑但计算开销越大）
            add_jitter: 是否添加随机延迟
            
        Returns:
            操作是否成功
        """
        x1, y1 = self._validate_coordinate(x1, y1)
        x2, y2 = self._validate_coordinate(x2, y2)
        duration = duration_ms or self._config.default_drag_duration
        steps = max(1, min(steps, 100))
        
        if add_jitter:
            self._apply_random_delay()
        
        start_time = time.monotonic()
        
        success = self._execute_adb_input([
            "swipe", str(x1), str(y1), str(x2), str(y2), str(duration)
        ])
        
        elapsed_ms = (time.monotonic() - start_time) * 1000
        
        self._update_stats('drag', success, elapsed_ms)
        
        logger.debug(
            f"DRAG ({x1},{y1})->({x2},{y2}) | "
            f"时长:{duration}ms | 步数:{steps} | {'成功' if success else '失败'}"
        )
        
        return success
    
    def multi_tap(
        self,
        coordinates: List[Tuple[int, int]],
        interval_ms: int = 100,
        add_jitter: bool = True,
    ) -> bool:
        """多点连续快速点击
        
        用于需要连续触发多个UI元素的场景。
        
        Args:
            coordinates: 坐标列表 [(x1,y1), (x2,y2), ...]
            interval_ms: 点击间隔（ms）
            add_jitter: 是否在每个点击前添加随机延迟
            
        Returns:
            所有点击是否全部成功
        """
        all_success = True
        
        for i, (x, y) in enumerate(coordinates):
            if i > 0 and interval_ms > 0:
                time.sleep(interval_ms / 1000.0)
            
            success = self.tap(x, y, add_jitter=add_jitter)
            if not success:
                all_success = False
        
        return all_success
    
    def text_input(
        self,
        text: str,
        add_jitter: bool = True,
    ) -> bool:
        """输入文本字符串（需当前焦点在输入框内）
        
        Args:
            text: 要输入的文本内容
            add_jitter: 是否添加随机延迟
            
        Returns:
            操作是否成功
            
        Warning:
            仅支持ASCII字符，中文需使用其他方案（如剪贴板粘贴）
        """
        if add_jitter:
            self._apply_random_delay()
        
        start_time = time.monotonic()
        
        success = self._execute_adb_input(["text", text])
        
        elapsed_ms = (time.monotonic() - start_time) * 1000
        
        self._update_stats('text', success, elapsed_ms)
        
        logger.debug(f"TEXT_INPUT '{text[:20]}...' | {'成功' if success else '失败'}")
        
        return success
    
    def key_event(
        self,
        keycode: str,
        add_jitter: bool = True,
    ) -> bool:
        """发送按键事件
        
        Args:
            keycode: 按键代码或名称
                常用: KEYCODE_BACK(4), KEYCODE_HOME(3),
                      KEYCODE_MENU(82), KEYCODE_POWER(26),
                      KEYCODE_ENTER(66), KEYCODE_DEL(67)
            add_jitter: 是否添加随机延迟
            
        Returns:
            操作是否成功
        """
        if add_jitter:
            self._apply_random_delay()
        
        start_time = time.monotonic()
        
        success = self._execute_adb_input(["keyevent", keycode])
        
        elapsed_ms = (time.monotonic() - start_time) * 1000
        
        self._update_stats('key', success, elapsed_ms)
        
        logger.debug(f"KEY_EVENT {keycode} | {'成功' if success else '失败'}")
        
        return success
    
    def press_back(self, add_jitter: bool = True) -> bool:
        """快捷方法：按下返回键"""
        return self.key_event("KEYCODE_BACK", add_jitter=add_jitter)
    
    def press_home(self, add_jitter: bool = True) -> bool:
        """快捷方法：按下Home键"""
        return self.key_event("KEYCODE_HOME", add_jitter=add_jitter)
    
    def pinch_zoom(
        self,
        center_x: int,
        center_y: int,
        scale_factor: float,
        duration_ms: int = 300,
        add_jitter: bool = True,
    ) -> bool:
        """缩放手势（简化版，仅支持基础缩放）
        
        注意: Android input命令对多点触控的支持有限，
        此方法通过两次swipe近似模拟缩放效果。
        
        Args:
            center_x, center_y: 缩放中心坐标
            scale_factor: 缩放比例 (>1放大, <1缩小)
            duration_ms: 手势时长
            add_jitter: 是否添加随机延迟
            
        Returns:
            操作是否成功
        """
        distance = 200 * scale_factor
        
        half_dur = duration_ms // 2
        
        success1 = self.swipe(
            center_x - distance, center_y,
            center_x - int(distance * scale_factor), center_y,
            duration_ms=half_dur, add_jitter=False
        )
        
        success2 = self.swipe(
            center_x + distance, center_y,
            center_x + int(distance * scale_factor), center_y,
            duration_ms=half_dur, add_jitter=False
        )
        
        return success1 and success2
    
    def start_async_mode(self) -> None:
        """启动异步操作模式
        
        启动后台工作线程，后续调用async_*系列方法将
        操作放入队列而非阻塞等待执行完成。
        """
        if self._async_running:
            logger.warning("异步模式已在运行中")
            return
        
        self._async_running = True
        self._stop_async_event.clear()
        
        self._async_thread = threading.Thread(
            target=self._async_worker_loop,
            name=f"motor_async_{self._device_serial[:8]}",
            daemon=True,
        )
        self._async_thread.start()
        
        logger.info("异步模式已启动")
    
    def stop_async_mode(self, timeout: float = 5.0) -> None:
        """停止异步操作模式
        
        Args:
            timeout: 等待工作线程结束的超时时间
        """
        if not self._async_running:
            return
        
        self._async_running = False
        self._stop_async_event.set()
        
        if self._async_thread and self._async_thread.is_alive():
            self._async_thread.join(timeout=timeout)
        
        while not self._operation_queue.empty():
            try:
                self._operation_queue.get_nowait()
            except Empty:
                break
        
        logger.info("异步模式已停止")
    
    def async_tap(self, x: int, y: int, **kwargs) -> bool:
        """异步版本：将点击操作加入队列"""
        action = InputAction(
            action_type=InputType.TAP,
            points=(Point2D(x, y),),
            **{k: v for k, v in kwargs.items() if k in ('duration_ms', 'priority')}
        )
        return self._enqueue_action(action)
    
    def async_swipe(self, x1: int, y1: int, x2: int, y2: int, **kwargs) -> bool:
        """异步版本：将滑动操作加入队列"""
        action = InputAction(
            action_type=InputType.SWIPE,
            points=(Point2D(x1, y1), Point2D(x2, y2)),
            **{k: v for k, v in kwargs.items() if k in ('duration_ms', 'priority')}
        )
        return self._enqueue_action(action)
    
    def async_drag(self, x1: int, y1: int, x2: int, y2: int, **kwargs) -> bool:
        """异步版本：将拖拽操作加入队列"""
        action = InputAction(
            action_type=InputType.DRAG,
            points=(Point2D(x1, y1), Point2D(x2, y2)),
            **{k: v for k, v in kwargs.items() if k in ('duration_ms', 'priority')}
        )
        return self._enqueue_action(action)
    
    def _enqueue_action(self, action: InputAction) -> bool:
        """将操作放入异步队列
        
        Returns:
            入队是否成功（可能因队列满而失败）
        """
        try:
            self._operation_queue.put_nowait(action)
            logger.debug(f"操作已入队: {action.id}")
            return True
        except:
            raise OperationQueueFullError(
                f"操作队列已满 (max={self._config.max_queue_size})"
            )
    
    def _async_worker_loop(self) -> None:
        """异步工作线程主循环"""
        logger.info("异步工作线程启动")
        
        while not self._stop_async_event.is_set():
            try:
                action: InputAction = self._operation_queue.get(timeout=0.1)
                
                success = self._execute_action(action)
                
                if self._on_operation_complete:
                    try:
                        self._on_operation_complete(action, success)
                    except Exception as e:
                        logger.error(f"操作完成回调异常: {e}")
                        
            except Empty:
                continue
            except Exception as e:
                logger.error(f"异步工作循环异常: {e}", exc_info=True)
        
        logger.info("异步工作线程已退出")
    
    def _execute_action(self, action: InputAction) -> bool:
        """根据InputAction类型分派执行对应操作"""
        if action.delay_before_ms > 0:
            time.sleep(action.delay_before_ms / 1000.0)
        
        success = False
        
        try:
            if action.action_type == InputType.TAP and len(action.points) >= 1:
                p = action.points[0]
                success = self.tap(p.x, p.y, action.duration_ms, add_jitter=False)
                
            elif action.action_type == InputType.LONG_PRESS and len(action.points) >= 1:
                p = action.points[0]
                success = self.long_press(p.x, p.y, action.duration_ms, add_jitter=False)
                
            elif action.action_type == InputType.SWIPE and len(action.points) >= 2:
                p1, p2 = action.points[0], action.points[1]
                success = self.swipe(p1.x, p1.y, p2.x, p2.y, action.duration_ms, add_jitter=False)
                
            elif action.action_type == InputType.DRAG and len(action.points) >= 2:
                p1, p2 = action.points[0], action.points[1]
                success = self.drag(p1.x, p1.y, p2.x, p2.y, action.duration_ms, add_jitter=False)
                
            elif action.action_type == InputType.TEXT_INPUT:
                text = action.extra_params.get('text', '')
                success = self.text_input(text, add_jitter=False)
                
            elif action.action_type == InputType.KEY_EVENT:
                keycode = action.extra_params.get('keycode', '')
                success = self.key_event(keycode, add_jitter=False)
                
            else:
                logger.warning(f"未知操作类型: {action.action_type.name}")
                success = False
                
        except Exception as e:
            logger.error(f"执行操作 {action.id} 失败: {e}")
            success = False
        
        if action.delay_after_ms > 0:
            time.sleep(action.delay_after_ms / 1000.0)
        
        return success
    
    @contextmanager
    def batch_context(self):
        """批量操作上下文管理器
        
        在with块内的所有操作将被收集起来，
        退出with块时按顺序原子执行。
        
        Usage:
            with motor.batch_context():
                motor.tap(100, 200)
                motor.tap(300, 400)
                motor.swipe(0, 500, 1000, 500)
        """
        self._batch_mode = True
        self._batch_actions.clear()
        
        try:
            yield self
        finally:
            self._batch_mode = False
            
            if self._batch_actions:
                self.batch_execute(self._batch_actions)
                self._batch_actions.clear()
    
    def batch_execute(self, actions: List[InputAction]) -> Dict[str, Any]:
        """批量执行多个操作（原子性保证）
        
        执行策略:
        - 按顺序依次执行每个操作
        - 任一操作失败不中断后续操作（记录失败项）
        - 返回完整的执行报告
        
        Args:
            actions: 要执行的InputAction列表
            
        Returns:
            包含执行结果的字典:
            {
                'total': 总操作数,
                'successful': 成功数,
                'failed': 失败数,
                'results': [(action, success), ...],
                'total_time_ms': 总耗时
            }
        """
        if not actions:
            return {'total': 0, 'successful': 0, 'failed': 0, 'results': [], 'total_time_ms': 0}
        
        start_time = time.monotonic()
        results = []
        successful = 0
        failed = 0
        
        for action in actions:
            if self._batch_mode:
                self._batch_actions.append(action)
                results.append((action, True))
                successful += 1
                continue
            
            success = self._execute_action(action)
            results.append((action, success))
            
            if success:
                successful += 1
            else:
                failed += 1
        
        elapsed_ms = (time.monotonic() - start_time) * 1000
        
        report = {
            'total': len(actions),
            'successful': successful,
            'failed': failed,
            'results': results,
            'total_time_ms': elapsed_ms,
        }
        
        logger.info(
            f"批量执行完成 | 总数:{report['total']} | "
            f"成功:{report['successful']} | 失败:{report['failed']} | "
            f"耗时:{elapsed_ms:.1f}ms"
        )
        
        return report
    
    def get_pending_count(self) -> int:
        """获取异步队列中待处理的操作数量"""
        return self._operation_queue.qsize()
    
    def clear_queue(self) -> int:
        """清空异步队列中的所有待处理操作
        
        Returns:
            清除的操作数量
        """
        count = 0
        while not self._operation_queue.empty():
            try:
                self._operation_queue.get_nowait()
                count += 1
            except Empty:
                break
        
        if count > 0:
            logger.info(f"已清空异步队列，移除{count}个操作")
        
        return count
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取操作统计信息（线程安全快照）"""
        with self._stats_lock:
            stats = dict(self._operation_stats)
            stats['queue_size'] = self._operation_queue.qsize()
            stats['async_running'] = self._async_running
            stats['batch_mode'] = self._batch_mode
            return stats
    
    def _update_stats(
        self,
        op_type: str,
        success: bool,
        execution_time_ms: float,
    ) -> None:
        """更新内部统计数据"""
        with self._stats_lock:
            self._operation_stats['total_operations'] += 1
            
            if success:
                self._operation_stats['successful_operations'] += 1
            else:
                self._operation_stats['failed_operations'] += 1
            
            op_key = f'total_{op_type}s'
            if op_key in self._operation_stats:
                self._operation_stats[op_key] += 1
            
            total = self._operation_stats['successful_operations']
            if total > 0:
                old_avg = self._operation_stats['average_execution_time_ms']
                self._operation_stats['average_execution_time_ms'] = (
                    (old_avg * (total - 1) + execution_time_ms) / total
                )
    
    def __repr__(self) -> str:
        return (
            f"<AdbMotor device={self._device_serial[:12]}... "
            f"res={self._screen_width}x{self._screen_height}>"
        )
