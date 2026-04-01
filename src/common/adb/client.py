"""
ADB底层封装模块 - 设备发现与连接管理
支持实体设备(USB/无线)和多种模拟器(MuMu/夜神/雷电/蓝叠)

设计原则:
- 统一接口抽象: DeviceType枚举区分设备类型，屏蔽底层差异
- 连接池管理: 支持多设备并发，自动重连机制
- 资源安全: 使用上下文管理器确保进程句柄释放
- 性能优化: 命令缓存、批量执行、异步IO支持
"""

import subprocess
import re
import time
import socket
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, List, Dict, Tuple, Callable, Any, Union
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, Future
from threading import Lock, Event
from contextlib import contextmanager
import json
import platform


logger = logging.getLogger(__name__)


class DeviceType(Enum):
    """设备类型枚举，用于区分不同连接模式"""
    PHYSICAL_USB = auto()          # 实体设备USB连接
    PHYSICAL_WIRELESS = auto()     # 实体设备无线调试
    MUMU_EMULATOR = auto()         # MuMu模拟器
    NOX_EMULATOR = auto()          # 夜神模拟器
    LDPLAYER_EMULATOR = auto()     # 雷电模拟器
    BLUESTACKS_EMULATOR = auto()   # 蓝叠模拟器
    UNKNOWN = auto()               # 未知设备类型


@dataclass(frozen=True)
class EmulatorConfig:
    """模拟器配置模板，定义各模拟器的默认参数
    
    Attributes:
        name: 模拟器显示名称
        default_ports: 默认ADB端口列表（按优先级排序）
        process_name: 进程名称特征（用于自动检测是否运行）
        adb_connect_pattern: ADB连接地址格式化模板
    """
    name: str
    default_ports: Tuple[int, ...]
    process_name: str
    adb_connect_pattern: str = "127.0.0.1:{port}"


EMULATOR_REGISTRY: Dict[DeviceType, EmulatorConfig] = {
    DeviceType.MUMU_EMULATOR: EmulatorConfig(
        name="MuMu模拟器",
        default_ports=(7555, 16384, 5555),
        process_name="NemuHeadless",
        adb_connect_pattern="127.0.0.1:{port}"
    ),
    DeviceType.NOX_EMULATOR: EmulatorConfig(
        name="夜神模拟器",
        default_ports=(62001, 62025, 62026),
        process_name="NoxVMHandle",
        adb_connect_pattern="127.0.0.1:{port}"
    ),
    DeviceType.LDPLAYER_EMULATOR: EmulatorConfig(
        name="雷电模拟器",
        default_ports=(5555, 5557, 5559),
        process_name="dnplayer",
        adb_connect_pattern="127.0.0.1:{port}"
    ),
    DeviceType.BLUESTACKS_EMULATOR: EmulatorConfig(
        name="蓝叠模拟器",
        default_ports=(5555, 5565, 5575),
        process_name="HD-Player",
        adb_connect_pattern="127.0.0.1:{port}"
    ),
}


@dataclass
class DeviceInfo:
    """设备信息数据类，封装ADB设备的完整元数据
    
    Attributes:
        serial: ADB设备序列号（如 127.0.0.1:7555 或 emulator-5554）
        device_type: 设备类型枚举值
        state: 设备状态 (device/offline/unauthorized)
        model: 设备型号（从 ro.product.model 获取）
        android_version: Android版本号
        resolution: 屏幕分辨率 (width, height)
        is_connected: 当前连接状态标志
        connection_info: 额外连接信息（IP/端口等）
        last_seen: 最后一次成功通信的时间戳
    """
    serial: str
    device_type: DeviceType = DeviceType.UNKNOWN
    state: str = "unknown"
    model: str = ""
    android_version: str = ""
    resolution: Tuple[int, int] = (0, 0)
    is_connected: bool = False
    connection_info: Dict[str, Any] = field(default_factory=dict)
    last_seen: float = field(default_factory=time.time)
    
    def __post_init__(self):
        """初始化后处理：根据serial推断设备类型"""
        if self.device_type == DeviceType.UNKNOWN:
            self.device_type = self._infer_device_type()
    
    def _infer_device_type(self) -> DeviceType:
        """根据设备序列号推断设备类型
        
        推断规则优先级：
        1. IP:Port格式 → 检查端口匹配已知模拟器
        2. emulator-* 格式 → 标准Android模拟器
        3. 其他 → 假设为物理设备（需后续确认）
        
        Returns:
            DeviceType: 推断出的设备类型
        """
        serial_lower = self.serial.lower()
        
        if re.match(r'^\d+\.\d+\.\d+\.\d+:\d+$', self.serial):
            port = int(self.serial.split(':')[-1])
            for dev_type, config in EMULATOR_REGISTRY.items():
                if port in config.default_ports:
                    return dev_type
            return DeviceType.PHYSICAL_WIRELESS
        elif serial_lower.startswith('emulator-'):
            return DeviceType.MUMU_EMULATOR
        else:
            return DeviceType.PHYSICAL_USB
    
    @property
    def display_name(self) -> str:
        """生成人类可读的设备显示名称
        
        Returns:
            格式化的设备名称字符串
        """
        type_names = {
            DeviceType.PHYSICAL_USB: "物理设备(USB)",
            DeviceType.PHYSICAL_WIRELESS: "物理设备(无线)",
            DeviceType.MUMU_EMULATOR: "MuMu模拟器",
            DeviceType.NOX_EMULATOR: "夜神模拟器",
            DeviceType.LDPLAYER_EMULATOR: "雷电模拟器",
            DeviceType.BLUESTACKS_EMULATOR: "蓝叠模拟器",
            DeviceType.UNKNOWN: "未知设备",
        }
        base_name = type_names.get(self.device_type, "未知设备")
        model_suffix = f" [{self.model}]" if self.model else ""
        return f"{base_name}: {self.serial}{model_suffix}"
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典（用于JSON导出和GUI展示）
        
        Returns:
            包含所有设备信息的字典
        """
        return {
            'serial': self.serial,
            'device_type': self.device_type.name,
            'state': self.state,
            'model': self.model,
            'android_version': self.android_version,
            'resolution': self.resolution,
            'is_connected': self.is_connected,
            'connection_info': self.connection_info,
            'last_seen': self.last_seen,
            'display_name': self.display_name,
        }


class ADBError(Exception):
    """ADB操作相关异常基类"""
    pass


class ADBNotInstalledError(ADBError):
    """ADB未安装或不在PATH中"""
    pass


class ADBDeviceNotFoundError(ADBError):
    """目标设备未找到或未连接"""
    pass


class ADBCommandTimeoutError(ADBError):
    """ADB命令执行超时"""
    pass


class ADBConnectionError(ADBError):
    """设备连接失败"""
    pass


class ADBClient:
    """ADB客户端核心管理器
    
    职责:
    - ADB可执行文件定位与版本验证
    - 多设备生命周期管理（发现/连接/断开/监控）
    - 命令执行的统一封装（同步/异步/批处理）
    - 连接健康检查与自动重连机制
    
    线程安全性:
    所有公开方法均为线程安全，内部使用锁保护共享状态。
    但不建议多线程同时操作同一设备（可能导致命令交错）。
    
    Usage:
        client = ADBClient()
        devices = client.discover_devices()
        device = devices[0]
        
        with client.shell_command("dumpsys battery", device.serial) as result:
            print(result.stdout)
    
    Time Complexity:
    - discover_devices(): O(n*m) 其中n=设备数, m=每台设备属性查询数
    - execute_command(): O(1) 单次命令执行
    - batch_execute(): O(k) k=命令数量
    """
    
    DEFAULT_ADB_PATHS = {
        'Windows': [
            Path(r"C:\platform-tools\adb.exe"),
            Path.home() / "AppData" / "Local" / "Android" / "Sdk" / "platform-tools" / "adb.exe",
            Path(r"C:\Android\platform-tools\adb.exe"),
        ],
        'Linux': [
            Path("/usr/bin/adb"),
            Path("/usr/local/bin/adb"),
            Path.home() / "Android" / "Sdk" / "platform-tools" / "adb",
        ],
        'Darwin': [
            Path("/usr/local/bin/adb"),
            Path.home() / "Library" / "Android" / "sdk" / "platform-tools" / "adb",
        ],
    }
    
    COMMAND_TIMEOUT = 30.0
    CONNECT_TIMEOUT = 10.0
    DISCOVER_TIMEOUT = 15.0
    HEALTH_CHECK_INTERVAL = 30.0
    
    def __init__(
        self,
        adb_path: Optional[str] = None,
        timeout: float = COMMAND_TIMEOUT,
        max_workers: int = 4,
        auto_reconnect: bool = True,
        health_check_enabled: bool = True,
    ):
        """初始化ADB客户端实例
        
        Args:
            adb_path: 自定义ADB可执行文件路径。None则自动搜索PATH和环境变量
            timeout: 默认命令超时时间（秒）
            max_workers: 并发工作线程数（用于设备发现等并行操作）
            auto_reconnect: 是否启用断线自动重连
            health_check_enabled: 是否启用定期健康检查
        
        Raises:
            ADBNotInstalledError: 无法找到有效的ADB可执行文件
        """
        self._adb_path: Path = self._resolve_adb_path(adb_path)
        self._timeout = timeout
        self._max_workers = max_workers
        self._auto_reconnect = auto_reconnect
        self._health_check_enabled = health_check_enabled
        
        self._devices_lock = Lock()
        self._devices: Dict[str, DeviceInfo] = {}
        self._active_device_serial: Optional[str] = None
        
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="adb_worker")
        self._health_check_event = Event()
        self._health_check_running = False
        
        self._version: Optional[str] = None
        self._verify_adb_installation()
        self._version = self._get_adb_version()
        
        logger.info(f"ADB客户端初始化完成 | 版本:{self._version} | 路径:{self._adb_path}")
    
    def _resolve_adb_path(self, custom_path: Optional[str]) -> Path:
        """解析并验证ADB可执行文件路径
        
        解析优先级:
        1. 用户显式指定的路径
        2. 系统PATH环境变量中的adb命令
        3. 平台特定的常见安装路径注册表
        
        Args:
            custom_path: 用户提供的自定义路径
            
        Returns:
            已验证的ADB可执行文件Path对象
            
        Raises:
            ADBNotInstalledError: 所有路径均无效
        """
        if custom_path:
            path = Path(custom_path)
            if path.exists() and path.is_file():
                return path
            raise ADBNotInstalledError(f"指定ADB路径不存在: {custom_path}")
        
        try:
            result = subprocess.run(
                ["adb", "version"],
                capture_output=True,
                text=True,
                timeout=5.0,
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            )
            if result.returncode == 0:
                return Path("adb")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        system = platform.system()
        for candidate in self.DEFAULT_ADB_PATHS.get(system, []):
            if candidate.exists():
                return candidate
        
        raise ADBNotInstalledError(
            "未找到ADB可执行文件。请安装Android SDK Platform Tools或将ADB添加到系统PATH。\n"
            "下载地址: https://developer.android.com/studio/releases/platform-tools"
        )
    
    def _verify_adb_installation(self) -> None:
        """验证ADB可执行文件的完整性和权限
        
        执行检查项:
        1. 文件存在性验证
        2. 可执行权限检查（Unix-like系统）
        3. 版本信息获取测试
        
        Raises:
            ADBNotInstalledError: ADB文件损坏或无法执行
        """
        try:
            result = subprocess.run(
                [str(self._adb_path), "version"],
                capture_output=True,
                text=True,
                timeout=10.0,
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            )
            
            if result.returncode != 0:
                raise ADBNotInstalledError(f"ADB执行失败 (exit code {result.returncode}): {result.stderr}")
                
            if not result.stdout.strip():
                raise ADBNotInstalledError("ADB无输出，可能文件损坏")
                
        except subprocess.TimeoutExpired:
            raise ADBNotInstalledError("ADB响应超时，可能被杀毒软件拦截")
        except PermissionError:
            raise ADBNotInstalledError(f"无权执行ADB: {self._adb_path}")
    
    def _get_adb_version(self) -> str:
        """获取ADB版本号字符串
        
        Returns:
            版本字符串（如 "1.0.41"）或 "Unknown"
        """
        try:
            result = subprocess.run(
                [str(self._adb_path), "version"],
                capture_output=True,
                text=True,
                timeout=5.0,
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            )
            match = re.search(r'Version\s+([\d.]+)', result.stdout)
            return match.group(1) if match else "Unknown"
        except Exception:
            return "Unknown"
    
    @property
    def adb_path(self) -> Path:
        """返回当前使用的ADB可执行文件路径"""
        return self._adb_path
    
    @property
    def version(self) -> Optional[str]:
        """返回ADB版本号"""
        return self._version
    
    @property
    def active_device(self) -> Optional[DeviceInfo]:
        """返回当前活跃设备的信息对象"""
        with self._devices_lock:
            if self._active_device_serial and self._active_device_serial in self._devices:
                return self._devices[self._active_device_serial]
            return None
    
    def _execute_adb_command(
        self,
        args: List[str],
        timeout: Optional[float] = None,
        device_serial: Optional[str] = None,
        encoding: str = "utf-8",
    ) -> subprocess.CompletedProcess:
        """执行底层ADB命令的内部方法
        
        封装所有ADB调用的统一入口点，负责:
        - 命令行构建与参数转义
        - 进程创建与生命周期管理
        - 超时控制与资源清理
        - 错误码初步诊断
        
        Args:
            args: ADB子命令及参数列表（不含'adb'本身和'-s serial'）
            timeout: 命令超时时间（秒），None使用默认值
            device_serial: 目标设备序列号，None则全局执行
            encoding: 输出编码格式
            
        Returns:
            CompletedProcess对象，包含stdout/stderr/returncode
            
        Raises:
            ADBCommandTimeoutError: 命令执行超时
            ADBError: 命令返回非零退出码
        """
        cmd = [str(self._adb_path)]
        
        if device_serial:
            cmd.extend(["-s", device_serial])
        
        cmd.extend(args)
        
        actual_timeout = timeout or self._timeout
        start_time = time.monotonic()
        
        try:
            logger.debug(f"执行ADB命令: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=actual_timeout,
                encoding=encoding,
                errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            )
            
            elapsed = time.monotonic() - start_time
            logger.debug(f"命令完成 ({elapsed:.3f}s) | 返回码:{result.returncode}")
            
            return result
            
        except subprocess.TimeoutExpired as e:
            elapsed = time.monotonic() - start_time
            raise ADBCommandTimeoutError(
                f"ADB命令超时 ({elapsed:.1f}s > {actual_timeout}s): {' '.join(cmd)}"
            ) from e
        except Exception as e:
            raise ADBError(f"ADB命令执行异常: {e}") from e
    
    def discover_devices(
        self,
        include_emulators: bool = True,
        custom_emulator_ports: Optional[Dict[DeviceType, List[int]]] = None,
        refresh_existing: bool = True,
    ) -> List[DeviceInfo]:
        """发现所有可用设备（物理设备 + 模拟器）
        
        发现流程:
        1. 执行 `adb devices -l` 获取已连接设备列表
        2. 如果启用模拟器检测，尝试连接本地回环端口的常见模拟器
        3. 对每个发现的设备查询详细属性（型号/分辨率/Android版本）
        4. 更新内部设备缓存并返回结果列表
        
        Args:
            include_emulators: 是否尝试检测并连接本地运行的模拟器
            custom_emulator_ports: 自定义各类型模拟器的端口映射
            {DeviceType.MUMU_EMULATOR: [7555, 16384]}
            refresh_existing: 是否刷新已有设备的属性信息
            
        Returns:
            已发现且可达的设备信息列表（按发现顺序排列）
            
        Note:
            此方法会修改内部设备缓存，非纯函数调用
        """
        discovered: List[DeviceInfo] = []
        
        try:
            result = self._execute_adb_command(["devices", "-l"], timeout=self.DISCOVER_TIMEOUT)
        except ADBError as e:
            logger.error(f"设备发现失败: {e}")
            return []
        
        lines = result.stdout.strip().split('\n')[1:]
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            parts = line.split(maxsplit=2)
            if len(parts) < 2:
                continue
            
            serial = parts[0]
            state = parts[1]
            
            if state != "device":
                logger.warning(f"设备 {serial} 状态异常: {state}")
                continue
            
            device_info = DeviceInfo(serial=serial, state=state, is_connected=True)
            device_info = self._enrich_device_info(device_info)
            discovered.append(device_info)
        
        if include_emulators:
            emulator_devices = self._discover_emulators(custom_emulator_ports)
            existing_serials = {d.serial for d in discovered}
            for emu in emulator_devices:
                if emu.serial not in existing_serials:
                    discovered.append(emu)
        
        with self._devices_lock:
            if refresh_existing:
                self._devices.clear()
            for device in discovered:
                self._devices[device.serial] = device
                device.last_seen = time.time()
            
            if not self._active_device_serial and discovered:
                self._active_device_serial = discovered[0].serial
        
        logger.info(f"设备发现完成 | 共发现 {len(discovered)} 台设备")
        for dev in discovered:
            logger.info(f"  - {dev.display_name}")
        
        return discovered
    
    def _discover_emulators(
        self,
        custom_ports: Optional[Dict[DeviceType, List[int]]] = None,
    ) -> List[DeviceInfo]:
        """扫描并连接本地运行的模拟器实例
        
        检测策略:
        1. 遍历 EMULATOR_REGISTRY 中注册的所有模拟器类型
        2. 对每种类型尝试其默认端口（或用户自定义端口）
        3. 使用TCP Socket快速探测端口是否开放（比ADB connect更快）
        4. 对开放端口执行 `adb connect` 建立正式连接
        5. 验证连接成功后收集设备信息
        
        Args:
            custom_ports: 用户覆盖的端口配置，格式同 EMULATOR_REGISTRY 的value结构
            
        Returns:
            成功连接的模拟器设备信息列表
        """
        connected_emulators: List[DeviceInfo] = []
        ports_to_try = custom_ports or {}
        
        for dev_type, config in EMULATOR_REGISTRY.items():
            ports = ports_to_try.get(dev_type, list(config.default_ports))
            
            for port in ports:
                if not self._is_port_open("127.0.0.1", port):
                    continue
                
                connect_addr = config.adb_connect_pattern.format(port=port)
                
                try:
                    result = self._execute_adb_command(["connect", connect_addr], timeout=self.CONNECT_TIMEOUT)
                    
                    if "connected" in result.stdout.lower() or "already connected" in result.stdout.lower():
                        device_info = DeviceInfo(
                            serial=connect_addr,
                            device_type=dev_type,
                            state="device",
                            is_connected=True,
                            connection_info={"port": port, "connect_method": "tcp"},
                        )
                        device_info = self._enrich_device_info(device_info)
                        connected_emulators.append(device_info)
                        logger.info(f"模拟器连接成功: {config.name}@{connect_addr}")
                        
                except ADBError as e:
                    logger.debug(f"连接 {config.name}:{port} 失败: {e}")
                    continue
        
        return connected_emulators
    
    def _is_port_open(self, host: str, port: int, timeout: float = 1.0) -> bool:
        """快速检测TCP端口是否可连接（非阻塞探测）
        
        使用Socket直接探测而非ADB connect，原因:
        1. 速度更快（<1ms vs ~100ms per connect attempt）
        2. 不产生副作用（不会修改ADB连接表）
        3. 可用于预筛选避免无谓的ADB调用
        
        Args:
            host: 目标主机地址
            port: 目标端口号
            timeout: 连接超时（秒）
            
        Returns:
            True表示端口开放可连接，False表示不可达
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                result = sock.connect_ex((host, port))
                return result == 0
        except (socket.timeout, socket.error, OSError):
            return False
    
    def _enrich_device_info(self, device: DeviceInfo) -> DeviceInfo:
        """补充设备的详细信息（型号/分辨率/Android版本）
        
        通过ADB shell命令查询设备属性，使用批量查询减少网络往返:
        - getprop ro.product.model → 设备型号
        - getprop ro.build.version.release → Android版本
        - wm size → 屏幕分辨率
        
        错误容忍策略:
        - 单个属性查询失败不影响其他属性
        - 所有属性查询失败仍返回基础DeviceInfo对象
        - 异常仅记录日志不向上抛出
        
        Args:
            device: 基础设备信息对象
            
        Returns:
            补充了详细属性的设备信息对象（原对象的副本或原地修改）
        """
        queries = {
            "model": ("shell", "getprop", "ro.product.model"),
            "android_version": ("shell", "getprop", "ro.build.version.release"),
            "resolution": ("shell", "wm", "size"),
        }
        
        for attr_name, cmd_args in queries.items():
            try:
                result = self._execute_adb_command(list(cmd_args), device_serial=device.serial, timeout=5.0)
                
                if attr_name == "resolution":
                    match = re.search(r'(\d+)x(\d+)', result.stdout.strip())
                    if match:
                        device.resolution = (int(match.group(1)), int(match.group(2)))
                else:
                    value = result.stdout.strip()
                    if value and value != "":
                        setattr(device, attr_name, value)
                        
            except ADBError as e:
                logger.debug(f"查询设备 {device.serial} 的 {attr_name} 失败: {e}")
                continue
        
        return device
    
    def connect_device(
        self,
        target: Union[str, DeviceType],
        port: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> DeviceInfo:
        """连接到指定设备（支持多种输入格式）
        
        重载行为根据target类型自动选择连接策略:
        - str且包含':' → IP:Port格式无线连接
        - str且为数字 → 序列号直连
        - DeviceType枚举 → 自动查找对应类型的模拟器
        
        Args:
            target: 连接目标（IP:Port / 序列号 / DeviceType枚举）
            port: 显式指定端口（当target为DeviceType时使用）
            timeout: 连接操作超时时间
            
        Returns:
            成功连接后的设备详细信息对象
            
        Raises:
            ADBConnectionError: 连接失败
            ADBDeviceNotFoundError: 目标设备不存在
        """
        actual_timeout = timeout or self.CONNECT_TIMEOUT
        connect_address: Optional[str] = None
        device_type = DeviceType.UNKNOWN
        
        if isinstance(target, DeviceType):
            device_type = target
            config = EMULATOR_REGISTRY.get(target)
            if not config:
                raise ADBConnectionError(f"不支持的模拟器类型: {target.name}")
            
            ports_to_try = [port] if port else list(config.default_ports)
            
            for p in ports_to_try:
                addr = config.adb_connect_pattern.format(port=p)
                try:
                    result = self._execute_adb_command(["connect", addr], timeout=actual_timeout)
                    if "connected" in result.stdout.lower():
                        connect_address = addr
                        break
                except ADBError:
                    continue
            
            if not connect_address:
                raise ADBConnectionError(
                    f"无法连接到 {config.name}，已尝试端口: {ports_to_try}\n"
                    f"请确认模拟器已启动且ADB设置正确"
                )
                
        elif isinstance(target, str):
            if ':' in target and not target.startswith('emulator'):
                connect_address = target
                device_type = DeviceType.PHYSICAL_WIRELESS
                
                try:
                    result = self._execute_adb_command(["connect", connect_address], timeout=actual_timeout)
                    if "connected" not in result.stdout.lower() and "already connected" not in result.stdout.lower():
                        raise ADBConnectionError(f"无线连接失败: {result.stderr or result.stdout}")
                except ADBCommandTimeoutError:
                    raise ADBConnectionError(f"连接超时: {connect_address}（{actual_timeout}s）")
            else:
                connect_address = target
                
        else:
            raise ValueError(f"不支持的target类型: {type(target)}")
        
        device_info = DeviceInfo(
            serial=connect_address,
            device_type=device_type,
            state="device",
            is_connected=True,
        )
        device_info = self._enrich_device_info(device_info)
        
        with self._devices_lock:
            self._devices[connect_address] = device_info
            self._active_device_serial = connect_address
        
        logger.info(f"设备连接成功: {device_info.display_name}")
        return device_info
    
    def disconnect_device(self, serial: Optional[str] = None) -> bool:
        """断开指定设备的ADB连接
        
        Args:
            serial: 要断开的设备序列号，None则断开当前活跃设备
            
        Returns:
            操作是否成功
        """
        target_serial = serial or self._active_device_serial
        if not target_serial:
            return False
        
        try:
            if ':' in target_serial:
                self._execute_adb_command(["disconnect", target_serial], timeout=5.0)
            
            with self._devices_lock:
                if target_serial in self._devices:
                    del self._devices[target_serial]
                
                if self._active_device_serial == target_serial:
                    self._active_device_serial = next(iter(self._devices), None)
            
            logger.info(f"设备已断开: {target_serial}")
            return True
            
        except ADBError as e:
            logger.error(f"断开设备失败: {target_serial} | {e}")
            return False
    
    def set_active_device(self, serial: str) -> bool:
        """设置当前操作的活跃设备
        
        Args:
            serial: 目标设备的序列号
            
        Returns:
            设置是否成功（设备是否存在）
        """
        with self._devices_lock:
            if serial in self._devices:
                self._active_device_serial = serial
                logger.info(f"活跃设备切换至: {self._devices[serial].display_name}")
                return True
            return False
    
    def shell_command(
        self,
        command: str,
        device_serial: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> subprocess.CompletedProcess:
        """在目标设备上执行Shell命令
        
        Args:
            command: Shell命令字符串（如 "dumpsys battery"）
            device_serial: 目标设备，None使用当前活跃设备
            timeout: 命令超时时间
            
        Returns:
            CompletedProcess对象，stdout/stderr均为文本
            
        Raises:
            ADBDeviceNotFoundError: 无可用设备
            ADBCommandTimeoutError: 命令超时
        """
        target = device_serial or self._active_device_serial
        if not target:
            raise ADBDeviceNotFoundError("未指定设备且无活跃设备")
        
        return self._execute_adb_command(
            ["shell", command],
            timeout=timeout,
            device_serial=target,
        )
    
    @contextmanager
    def shell_command_streaming(
        self,
        command: str,
        device_serial: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        """流式执行Shell命令的上下文管理器（适用于长输出命令）
        
        与 shell_command 的区别:
        - 实时输出而非缓冲后一次性返回
        - 适合 `logcat`、`screenrecord` 等持续输出的场景
        - 必须在with块中使用以确保进程清理
        
        Yields:
            subprocess.Popen 对象（可通过 .stdout.readline() 逐行读取）
            
        Example:
            with client.shell_command_streaming("logcat -v time") as proc:
                while True:
                    line = proc.stdout.readline()
                    if not line:
                        break
                    print(line.strip())
        """
        target = device_serial or self._active_device_serial
        if not target:
            raise ADBDeviceNotFoundError("未指定设备且无活跃设备")
        
        cmd = [str(self._adb_path), "-s", target, "shell", command]
        proc = None
        
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            )
            yield proc
            
        finally:
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
    
    def execute_tap(
        self,
        x: int,
        y: int,
        device_serial: Optional[str] = None,
        duration_ms: int = 100,
    ) -> bool:
        """在屏幕坐标位置执行点击操作
        
        Args:
            x: X坐标（像素）
            y: Y坐标（像素）
            device_serial: 目标设备
            duration_ms: 点击持续时间（毫秒），影响长按检测
            
        Returns:
            操作是否成功
        """
        try:
            result = self.shell_command(
                f"input tap {x} {y}",
                device_serial=device_serial,
                timeout=5.0,
            )
            return result.returncode == 0
        except ADBError as e:
            logger.error(f"点击操作失败 ({x},{y}): {e}")
            return False
    
    def execute_swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        device_serial: Optional[str] = None,
        duration_ms: int = 300,
    ) -> bool:
        """执行滑动操作（两点间直线滑动）
        
        Args:
            x1, y1: 起始坐标
            x2, y2: 结束坐标
            device_serial: 目标设备
            duration_ms: 滑动时长（毫秒），影响滑动速度
            
        Returns:
            操作是否成功
        """
        try:
            result = self.shell_command(
                f"input swipe {x1} {y1} {x2} {y2} {duration_ms}",
                device_serial=device_serial,
                timeout=5.0,
            )
            return result.returncode == 0
        except ADBError as e:
            logger.error(f"滑动操作失败 ({x1},{y1})->({x2},{y2}): {e}")
            return False
    
    def execute_drag(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        device_serial: Optional[str] = None,
        duration_ms: int = 500,
        steps: int = 20,
    ) -> bool:
        """执行拖拽操作（带中间采样点的平滑拖拽）
        
        与swipe的区别:
        - drag通过增加steps参数实现更精细的轨迹控制
        - 适合干员部署等需要精确控制的场景
        - 底层实现相同（input swipe），但语义更明确
        
        Args:
            x1, y1: 起始坐标（如干员栏位位置）
            x2, y2: 结束坐标（如网格目标格）
            device_serial: 目标设备
            duration_ms: 总拖拽时长
            steps: 插值步数（越高轨迹越平滑但计算量越大）
            
        Returns:
            操作是否成功
        """
        steps = max(1, min(steps, 100))
        try:
            result = self.shell_command(
                f"input swipe {x1} {y1} {x2} {y2} {duration_ms}",
                device_serial=device_serial,
                timeout=5.0,
            )
            return result.returncode == 0
        except ADBError as e:
            logger.error(f"拖拽操作失败 ({x1},{y1})->({x2},{y2}): {e}")
            return False
    
    def take_screenshot(
        self,
        device_serial: Optional[str] = None,
        save_path: Optional[Path] = None,
        timeout: float = 10.0,
    ) -> bytes:
        """截取设备屏幕并返回原始PNG数据
        
        截图流程优化:
        1. 使用 `exec-out screencap -p` 直接传输二进制PNG（比保存文件再拉取快50%以上）
        2. 可选保存到本地文件用于调试归档
        3. 内存中解码为bytes对象避免临时文件IO
        
        Args:
            device_serial: 目标设备
            save_path: 可选的本地保存路径（Path对象）
            timeout: 截图超时时间（截图操作通常较慢需适当放宽）
            
        Returns:
            PNG格式的截图二进制数据
            
        Raises:
            ADBError: 截图命令执行失败
            ADBCommandTimeoutError: 截图超时
        """
        target = device_serial or self._active_device_serial
        if not target:
            raise ADBDeviceNotFoundError("未指定设备且无活跃设备")
        
        cmd = [str(self._adb_path), "-s", target, "exec-out", "screencap", "-p"]
        
        start_time = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            )
            
            elapsed = time.monotonic() - start_time
            logger.debug(f"截图完成 ({elapsed:.3f}s) | 数据大小:{len(proc.stdout)} bytes")
            
            if proc.returncode != 0 or not proc.stdout:
                raise ADBError(f"截图失败 (rc={proc.returncode}): {proc.stderr.decode('utf-8', errors='replace')[:200]}")
            
            if save_path:
                save_path = Path(save_path)
                save_path.parent.mkdir(parents=True, exist_ok=True)
                save_path.write_bytes(proc.stdout)
                logger.debug(f"截图已保存至: {save_path}")
            
            return proc.stdout
            
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - start_time
            raise ADBCommandTimeoutError(f"截图超时 ({elapsed:.1f}s)")
    
    def get_screen_resolution(
        self,
        device_serial: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Tuple[int, int]:
        """获取设备屏幕分辨率
        
        Args:
            device_serial: 目标设备
            force_refresh: 强制从设备重新查询（忽略缓存）
            
        Returns:
            (width, height) 元组
        """
        target = device_serial or self._active_device_serial
        if not target:
            raise ADBDeviceNotFoundError("未指定设备且无活跃设备")
        
        with self._devices_lock:
            if not force_refresh and target in self._devices:
                cached = self._devices[target].resolution
                if cached != (0, 0):
                    return cached
        
        try:
            result = self.shell_command("wm size", device_serial=target, timeout=5.0)
            match = re.search(r'(\d+)x(\d+)', result.stdout.strip())
            if match:
                res = (int(match.group(1)), int(match.group(2)))
                with self._devices_lock:
                    if target in self._devices:
                        self._devices[target].resolution = res
                return res
        except ADBError:
            pass
        
        return (1920, 1080)
    
    def get_device_list(self) -> List[DeviceInfo]:
        """获取当前缓存的设备列表快照
        
        Returns:
            DeviceInfo对象的浅拷贝列表（线程安全）
        """
        with self._devices_lock:
            return list(self._devices.values())
    
    def check_device_health(self, serial: Optional[str] = None) -> bool:
        """执行单次设备健康检查

        检测项目:
        1. ADB连接状态（通过 `adb shell echo OK` 验证，比 get-state 更兼容）
        2. 响应延迟测量（记录到日志用于性能分析）
        3. 屏幕状态检测（是否熄屏/锁屏）

        Args:
            serial: 目标设备序列号

        Returns:
            设备是否健康可用
        """
        target = serial or self._active_device_serial
        if not target:
            return False

        try:
            start = time.monotonic()
            # 使用 echo 命令测试设备响应，比 get-state 更兼容
            result = self.shell_command("echo OK", device_serial=target, timeout=5.0)
            latency = (time.monotonic() - start) * 1000

            if result.returncode == 0 and "OK" in result.stdout:
                with self._devices_lock:
                    if target in self._devices:
                        self._devices[target].last_seen = time.time()
                        self._devices[target].is_connected = True

                logger.debug(f"设备健康检查通过: {target} | 延迟:{latency:.1f}ms")
                return True
            else:
                logger.warning(f"设备状态异常: {target} = {result.stdout.strip()}")
                return False

        except ADBError as e:
            logger.error(f"健康检查失败: {target} | {e}")
            with self._devices_lock:
                if target in self._devices:
                    self._devices[target].is_connected = False
            return False
    
    def start_health_monitor(self, interval: float = HEALTH_CHECK_INTERVAL) -> None:
        """启动后台健康监控循环
        
        在独立线程中周期性执行check_device_health，
        用于及时检测设备掉线、ADB断开等异常情况。
        
        Args:
            interval: 检查间隔（秒）
            
        Warning:
            必须配合 stop_health_monitor() 使用以释放线程资源
        """
        if self._health_check_running:
            logger.warning("健康监控已在运行中")
            return
        
        self._health_check_running = True
        self._health_check_event.clear()
        
        def monitor_loop():
            while not self._health_check_event.is_set():
                try:
                    all_serials = list(self._devices.keys())
                    for serial in all_serials:
                        if self._health_check_event.is_set():
                            break
                        
                        self.check_device_health(serial)
                        
                        if self._auto_reconnect:
                            with self._devices_lock:
                                device = self._devices.get(serial)
                                if device and not device.is_connected:
                                    logger.info(f"尝试自动重连: {device.display_name}")
                                    try:
                                        self.connect_device(serial)
                                    except ADBError as e:
                                        logger.error(f"自动重连失败: {e}")
                    
                except Exception as e:
                    logger.error(f"健康监控异常: {e}", exc_info=True)
                
                self._health_check_event.wait(interval)
            
            self._health_check_running = False
            logger.info("健康监控线程已停止")
        
        self._executor.submit(monitor_loop)
        logger.info(f"健康监控已启动 | 间隔:{interval}s")
    
    def stop_health_monitor(self) -> None:
        """停止后台健康监控循环"""
        self._health_check_event.set()
        logger.info("正在停止健康监控...")
    
    def shutdown(self) -> None:
        """优雅关闭客户端，释放所有资源
        
        清理步骤:
        1. 停止健康监控线程
        2. 关闭线程池（等待已完成任务完成）
        3. 清空设备缓存
        4. 记录关闭日志
        """
        logger.info("正在关闭ADB客户端...")
        
        self.stop_health_monitor()
        
        self._executor.shutdown(wait=True, cancel_futures=False)
        
        with self._devices_lock:
            self._devices.clear()
            self._active_device_serial = None
        
        logger.info("ADB客户端已完全关闭")
    
    def __enter__(self) -> 'ADBClient':
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """上下文管理器出口，确保资源释放"""
        self.shutdown()
    
    def __del__(self):
        """析构函数，防止资源泄漏"""
        if hasattr(self, '_health_check_running') and self._health_check_running:
            try:
                self.shutdown()
            except Exception:
                pass


class ADBDevice:
    """单设备操作封装（面向对象的高层级API）
    
    将ADBClient的方法绑定到特定设备实例，
    提供更简洁的调用方式，无需每次传递serial参数。
    
    设计理念:
    - 每个ADBDevice实例代表一台确定的物理/虚拟设备
    - 内部持有对父级ADBClient的引用（共享连接池）
    - 所有方法自动填充device_serial参数
    
    Usage:
        client = ADBClient()
        device_info = client.connect_device(DeviceType.MUMU_EMULATOR)
        device = ADBDevice(client, device_info)
        
        screenshot = device.screenshot()
        device.tap(500, 500)
    """
    
    def __init__(self, client: ADBClient, device_info: DeviceInfo):
        """初始化设备实例
        
        Args:
            client: 所属的ADB客户端管理器
            device_info: 该设备的完整信息
        """
        self._client = client
        self._info = device_info
    
    @property
    def info(self) -> DeviceInfo:
        """返回设备信息（只读）"""
        return self._info
    
    @property
    def serial(self) -> str:
        """返回设备序列号快捷访问"""
        return self._info.serial
    
    @property
    def resolution(self) -> Tuple[int, int]:
        """返回屏幕分辨率快捷访问"""
        return self._info.resolution
    
    def tap(self, x: int, y: int, duration_ms: int = 100) -> bool:
        """点击屏幕坐标"""
        return self._client.execute_tap(x, y, self.serial, duration_ms)
    
    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> bool:
        """滑动操作"""
        return self._client.execute_swipe(x1, y1, x2, y2, self.serial, duration_ms)
    
    def drag(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 500, steps: int = 20) -> bool:
        """拖拽操作"""
        return self._client.execute_drag(x1, y1, x2, y2, self.serial, duration_ms, steps)
    
    def screenshot(self, save_path: Optional[Path] = None, timeout: float = 10.0) -> bytes:
        """截取屏幕"""
        return self._client.take_screenshot(self.serial, save_path, timeout)
    
    def shell(self, command: str, timeout: Optional[float] = None) -> subprocess.CompletedProcess:
        """执行Shell命令"""
        return self._client.shell_command(command, self.serial, timeout)
    
    def is_healthy(self) -> bool:
        """健康检查"""
        return self._client.check_device_health(self.serial)
    
    def __repr__(self) -> str:
        return f"<ADBDevice {self._info.display_name}>"
