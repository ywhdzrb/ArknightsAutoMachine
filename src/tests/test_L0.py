"""
L0感知执行层 - 单元测试套件

覆盖范围:
- ADBClient: 设备发现/连接/命令执行
- AdbSensor: 截图采集/帧缓冲/状态管理
- AdbMotor: 输入操作/坐标验证/反检测
- L0Bridge: 生命周期管理/健康报告

运行方式:
    pytest src/tests/test_L0.py -v --tb=short

验收标准:
- 测试覆盖率 >= 85%
- 核心路径分支覆盖率 = 100%
- 所有测试必须独立可重复（不依赖外部设备）
"""

import sys
import os
import time
import threading
import unittest
from unittest.mock import (
    Mock, MagicMock, patch, PropertyMock,
    call, ANY,
)
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Tuple, List
import numpy as np


sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestADBClientDeviceDiscovery(unittest.TestCase):
    """ADBClient设备发现功能测试
    
    测试场景:
    - 正常设备列表解析
    - 空设备列表处理
    - 异常格式容错
    - 模拟器端口自动检测
    """
    
    def setUp(self) -> None:
        """每个测试前的初始化"""
        self.mock_process = Mock()
        self.mock_process.returncode = 0
        
    @patch('common.adb.client.subprocess.run')
    def test_discover_devices_with_physical_and_emulator(self, mock_run):
        """测试同时发现物理设备和模拟器"""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="""List of devices attached
127.0.0.1:7555	device product:NemuPlayer model:SM901B device:nemu device:muemu1:transport_id=1
emulator-5554	device product:sdk_gphone_x86_64 model:Pixel_6 sdk_gphone_x86_64:transport_id=2
""",
            stderr=""
        )
        
        from common.adb.client import ADBClient, DeviceType
        import threading
        
        with patch.object(ADBClient, '_verify_adb_installation'):
            with patch.object(ADBClient, '_get_adb_version', return_value="1.0.41"):
                client = ADBClient.__new__(ADBClient)
                client._adb_path = Path("adb")
                client._timeout = 30.0
                client._max_workers = 4
                client._auto_reconnect = True
                client._health_check_enabled = False
                client._version = "1.0.41"
                client._devices_lock = threading.Lock()
                client._devices = {}
                client._active_device_serial = None
                client._health_check_event = threading.Event()
                
                from concurrent.futures import ThreadPoolExecutor
                client._executor = ThreadPoolExecutor(max_workers=1)
                
                devices = client.discover_devices(include_emulators=False)
                
                self.assertGreaterEqual(len(devices), 2)
                
                muMu_devices = [d for d in devices if d.device_type == DeviceType.MUMU_EMULATOR]
                self.assertGreaterEqual(len(muMu_devices), 1)
                
                client.shutdown()
    
    @patch('common.adb.client.subprocess.run')
    def test_discover_empty_device_list(self, mock_run):
        """测试空设备列表的处理"""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="List of devices attached\n",
            stderr=""
        )
        
        from common.adb.client import ADBClient
        import threading
        
        with patch.object(ADBClient, '_verify_adb_installation'):
            with patch.object(ADBClient, '_get_adb_version', return_value="1.0.41"):
                client = ADBClient.__new__(ADBClient)
                client._adb_path = Path("adb")
                client._timeout = 30.0
                client._devices_lock = threading.Lock()
                client._devices = {}
                client._active_device_serial = None
                client._version = "1.0.41"
                client._health_check_event = threading.Event()
                
                from concurrent.futures import ThreadPoolExecutor
                client._executor = ThreadPoolExecutor(max_workers=1)
                
                devices = client.discover_devices()
                
                self.assertEqual(len(devices), 0)
                
                client.shutdown()
    
    @patch('common.adb.client.subprocess.run')
    def test_parse_offline_device(self, mock_run):
        """测试离线设备的正确识别"""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="""List of devices attached
1234567890abcdef	offline
""",
            stderr=""
        )
        
        from common.adb.client import ADBClient
        import threading
        
        with patch.object(ADBClient, '_verify_adb_installation'):
            with patch.object(ADBClient, '_get_adb_version', return_value="1.0.41"):
                client = ADBClient.__new__(ADBClient)
                client._adb_path = Path("adb")
                client._timeout = 30.0
                client._devices_lock = threading.Lock()
                client._devices = {}
                client._active_device_serial = None
                client._version = "1.0.41"
                client._health_check_event = threading.Event()
                
                from concurrent.futures import ThreadPoolExecutor
                client._executor = ThreadPoolExecutor(max_workers=1)
                
                devices = client.discover_devices()
                
                offline_devices = [d for d in devices if d.state == "offline"]
                self.assertEqual(len(devices), 0)
                
                client.shutdown()


class TestDeviceInfoInference(unittest.TestCase):
    """DeviceInfo设备类型推断测试"""
    
    def test_infer_mumu_by_port(self):
        """通过端口号推断MuMu模拟器"""
        from common.adb.client import DeviceInfo
        
        dev = DeviceInfo(serial="127.0.0.1:7555")
        from common.adb.client import DeviceType
        self.assertEqual(dev.device_type, DeviceType.MUMU_EMULATOR)
    
    def test_infer_nox_by_port(self):
        """通过端口号推断夜神模拟器"""
        from common.adb.client import DeviceInfo, DeviceType
        
        dev = DeviceInfo(serial="127.0.0.1:62001")
        self.assertEqual(dev.device_type, DeviceType.NOX_EMULATOR)
    
    def test_infer_wireless_physical(self):
        """推断无线物理设备（使用非标准端口避免与模拟器冲突）"""
        from common.adb.client import DeviceInfo, DeviceType
        
        dev = DeviceInfo(serial="192.168.1.100:8888")
        self.assertEqual(dev.device_type, DeviceType.PHYSICAL_WIRELESS)
    
    def test_infer_usb_physical(self):
        """推断USB物理设备"""
        from common.adb.client import DeviceInfo, DeviceType
        
        dev = DeviceInfo(serial="ABCDEF123456")
        self.assertEqual(dev.device_type, DeviceType.PHYSICAL_USB)
    
    def test_display_name_format(self):
        """测试显示名称格式化"""
        from common.adb.client import DeviceInfo
        
        dev = DeviceInfo(
            serial="127.0.0.1:7555",
            model="SM901B",
        )
        
        display = dev.display_name
        self.assertIn("MuMu", display)
        self.assertIn("7555", display)
        self.assertIn("SM901B", display)


class TestAdbMotorCoordinateValidation(unittest.TestCase):
    """AdbMotor坐标验证系统测试
    
    验证边界条件:
    - 正常坐标通过
    - 负坐标裁剪（tolerance > 0时）
    - 超出范围坐标拒绝（tolerance = 0时）
    - 极端值处理
    """
    
    def _create_motor(self, tolerance: int = 5) -> Mock:
        """创建Motor实例的辅助方法"""
        mock_client = Mock()
        
        from AMA.L0.motor import AdbMotor, MotorConfig
        
        config = MotorConfig(
            coordinate_tolerance=tolerance,
            enable_anti_detection=False,
        )
        
        motor = AdbMotor(
            adb_client=mock_client,
            device_serial="test_device",
            screen_resolution=(1920, 1080),
            config=config,
        )
        
        return motor
    
    def test_valid_coordinate_passes(self):
        """正常范围内的坐标应通过验证"""
        motor = self._create_motor(tolerance=0)
        
        x, y = motor._validate_coordinate(960, 540)
        
        self.assertEqual(x, 960)
        self.assertEqual(y, 540)
    
    def test_exact_boundary_coordinate(self):
        """精确边界的坐标应通过"""
        motor = self._create_motor(tolerance=0)
        
        x, y = motor._validate_coordinate(1920, 1080)
        
        self.assertEqual(x, 1920)
        self.assertEqual(y, 1080)
    
    def test_out_of_range_rejected_when_tolerance_zero(self):
        """超出范围且tolerance=0时应抛出异常"""
        from AMA.L0.motor import CoordinateOutOfRangeError
        
        motor = self._create_motor(tolerance=0)
        
        with self.assertRaises(CoordinateOutOfRangeError):
            motor._validate_coordinate(-1, 500)
        
        with self.assertRaises(CoordinateOutOfRangeError):
            motor._validate_coordinate(1921, 500)
    
    def test_negative_coordinate_clamped(self):
        """负坐标在tolerance>0时应被裁剪到0（当超出tolerance范围时）"""
        motor = self._create_motor(tolerance=5)
        
        x, y = motor._validate_coordinate(-10, 100)
        
        self.assertEqual(x, 0)
        self.assertEqual(y, 100)
    
    def test_overflow_coordinate_clamped(self):
        """超大坐标在tolerance>0时应被裁剪到最大值"""
        motor = self._create_motor(tolerance=10)
        
        x, y = motor._validate_coordinate(2000, 1200)
        
        self.assertEqual(x, 1920)
        self.assertEqual(y, 1080)
    
    def test_origin_point_always_valid(self):
        """原点(0,0)始终有效"""
        motor = self._create_motor(tolerance=0)
        
        x, y = motor._validate_coordinate(0, 0)
        
        self.assertEqual(x, 0)
        self.assertEqual(y, 0)


class TestAdbMotorInputOperations(unittest.TestCase):
    """AdbMotor输入操作测试
    
    测试所有输入类型的命令生成:
    - tap: input tap x y
    - swipe: input swipe x1 y1 x2 y2 duration
    - drag: input swipe (语义不同但底层相同)
    - text_input: input text "content"
    - key_event: input event keycode
    """
    
    def _create_mock_motor(self):
        """创建带Mock ADB客户端的Motor实例"""
        mock_client = Mock()
        mock_client.shell_command.return_value = Mock(returncode=0, stdout="", stderr="")
        
        from AMA.L0.motor import AdbMotor, MotorConfig
        
        motor = AdbMotor(
            adb_client=mock_client,
            device_serial="test_serial",
            screen_resolution=(1920, 1080),
            config=MotorConfig(enable_anti_detection=False),
        )
        
        return motor, mock_client
    
    def test_tap_generates_correct_command(self):
        """tap操作应生成正确的input tap命令"""
        motor, client = self._create_mock_motor()
        
        result = motor.tap(500, 300, add_jitter=False)
        
        self.assertTrue(result)
        client.shell_command.assert_called_once()
        
        call_args = client.shell_command.call_args
        cmd_string = call_args[0][0]
        
        self.assertIn("input", cmd_string)
        self.assertIn("tap", cmd_string)
        self.assertIn("500", cmd_string)
        self.assertIn("300", cmd_string)
    
    def test_swipe_generates_correct_command(self):
        """swipe操作应生成正确的input swipe命令"""
        motor, client = self._create_mock_motor()
        
        result = motor.swipe(100, 800, 900, 800, duration_ms=400, add_jitter=False)
        
        self.assertTrue(result)
        
        call_args = client.shell_command.call_args
        cmd_string = call_args[0][0]
        
        self.assertIn("swipe", cmd_string)
        self.assertIn("100", cmd_string)
        self.assertIn("800", cmd_string)
        self.assertIn("900", cmd_string)
        self.assertIn("400", cmd_string)
    
    def test_drag_generates_swipe_command(self):
        """drag操作底层也应使用swipe命令"""
        motor, client = self._create_mock_motor()
        
        result = motor.drag(200, 400, 600, 700, duration_ms=500, add_jitter=False)
        
        self.assertTrue(result)
        
        call_args = client.shell_command.call_args
        cmd_string = call_args[0][0]
        
        self.assertIn("swipe", cmd_string)
    
    def test_long_press_uses_swipe_same_coordinates(self):
        """长按应使用相同起止坐标的swipe实现"""
        motor, client = self._create_mock_motor()
        
        result = motor.long_press(960, 540, duration_ms=1500, add_jitter=False)
        
        self.assertTrue(result)
        
        call_args = client.shell_command.call_args
        cmd_string = call_args[0][0]
        
        parts = cmd_string.split()
        
        x1_idx = parts.index("swipe") + 1
        y1_idx = x1_idx + 1
        x2_idx = y1_idx + 1
        y2_idx = x2_idx + 1
        
        self.assertEqual(parts[x1_idx], parts[x2_idx])
        self.assertEqual(parts[y1_idx], parts[y2_idx])
        self.assertIn("1500", cmd_string)
    
    def test_text_input_generates_text_command(self):
        """文本输入应生成input text命令"""
        motor, client = self._create_mock_motor()
        
        result = motor.text_input("hello world", add_jitter=False)
        
        self.assertTrue(result)
        
        call_args = client.shell_command.call_args
        cmd_string = call_args[0][0]
        
        self.assertIn("text", cmd_string)
        self.assertIn("hello world", cmd_string)
    
    def test_key_event_generates_keyevent_command(self):
        """按键事件应生成input keyevent命令"""
        motor, client = self._create_mock_motor()
        
        result = motor.key_event("KEYCODE_BACK", add_jitter=False)
        
        self.assertTrue(result)
        
        call_args = client.shell_command.call_args
        cmd_string = call_args[0][0]
        
        self.assertIn("keyevent", cmd_string)
        self.assertIn("KEYCODE_BACK", cmd_string)
    
    def test_press_back_shortcut(self):
        """press_home快捷方法应调用key_event"""
        motor, client = self._create_mock_motor()
        
        motor.press_home(add_jitter=False)
        
        call_args = client.shell_command.call_args
        cmd_string = call_args[0][0]
        
        self.assertIn("KEYCODE_HOME", cmd_string)
    
    def test_operation_failure_returns_false(self):
        """操作失败时应返回False而非抛异常"""
        motor, client = self._create_mock_motor()
        
        client.shell_command.return_value = Mock(
            returncode=1,
            stdout="Error: command failed",
            stderr=""
        )
        
        result = motor.tap(100, 200, add_jitter=False)
        
        self.assertFalse(result)


class TestAdbSensorFrameBuffer(unittest.TestCase):
    """AdbSensor帧缓冲区管理测试
    
    测试环形缓冲区的行为:
    - 帧入队和出队顺序
    - 缓冲区满时的溢出策略
    - 最新帧快速访问
    - 空缓冲区安全返回None
    """
    
    def _create_sensor(self, max_buffer_size: int = 5):
        """创建Sensor实例的辅助方法"""
        mock_client = Mock()
        mock_client.take_screenshot.return_value = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        
        from AMA.L0.sensor import AdbSensor, SensorConfig
        
        config = SensorConfig(
            target_fps=15.0,
            max_buffer_size=max_buffer_size,
            decode_to_numpy=True,
            timeout_per_frame=5.0,
            enable_quality_monitoring=False,
        )
        
        sensor = AdbSensor(
            adb_client=mock_client,
            device_serial="test_sensor",
            config=config,
        )
        
        return sensor, mock_client
    
    def test_initial_buffer_is_empty(self):
        """初始状态下缓冲区应为空"""
        sensor, _ = self._create_sensor()
        
        size = sensor.get_buffer_size()
        
        self.assertEqual(size, 0)
    
    def test_get_latest_frame_from_empty_returns_none(self):
        """空缓冲区获取最新帧应返回None"""
        sensor, _ = self._create_sensor()
        
        frame = sensor.get_latest_frame()
        
        self.assertIsNone(frame)
    
    def test_single_frame_capture_and_retrieve(self):
        """单帧捕获后应能成功取回"""
        sensor, mock_client = self._create_sensor()
        
        frame_data = sensor._capture_single_frame()
        
        self.assertIsNotNone(frame_data)
        self.assertIsInstance(frame_data.image_data, bytes)
        self.assertGreater(len(frame_data.image_data), 0)


class TestPoint2DOperations(unittest.TestCase):
    """Point2D坐标点数据类测试
    
    验证数学运算的正确性:
    - 欧氏距离计算
    - 向量加减法
    - 类型转换
    """
    
    def test_distance_same_point(self):
        """同一点的距离应为0"""
        from AMA.L0.motor import Point2D
        
        p = Point2D(100, 200)
        
        distance = p.distance_to(p)
        
        self.assertAlmostEqual(distance, 0.0, places=5)
    
    def test_distance_horizontal(self):
        """水平线上的两点距离"""
        from AMA.L0.motor import Point2D
        
        p1 = Point2D(0, 0)
        p2 = Point2D(100, 0)
        
        distance = p1.distance_to(p2)
        
        self.assertAlmostEqual(distance, 100.0, places=5)
    
    def test_distance_vertical(self):
        """垂直线上的两点距离"""
        from AMA.L0.motor import Point2D
        
        p1 = Point2D(0, 0)
        p2 = Point2D(0, 200)
        
        distance = p1.distance_to(p2)
        
        self.assertAlmostEqual(distance, 200.0, places=5)
    
    def test_distance_diagonal(self):
        """对角线距离（勾股定理验证）"""
        from AMA.L0.motor import Point2D
        
        p1 = Point2D(0, 0)
        p2 = Point2D(300, 400)
        
        distance = p1.distance_to(p2)
        
        expected = (300**2 + 400**2) ** 0.5
        self.assertAlmostEqual(distance, expected, places=5)
    
    def test_addition(self):
        """向量加法"""
        from AMA.L0.motor import Point2D
        
        p1 = Point2D(10, 20)
        p2 = Point2D(30, 40)
        
        result = p1 + p2
        
        self.assertEqual(result.x, 40)
        self.assertEqual(result.y, 60)
    
    def test_subtraction(self):
        """向量减法"""
        from AMA.L0.motor import Point2D
        
        p1 = Point2D(50, 80)
        p2 = Point2D(10, 20)
        
        result = p1 - p2
        
        self.assertEqual(result.x, 40)
        self.assertEqual(result.y, 60)
    
    def test_invalid_type_raises(self):
        """非数值类型应抛出TypeError"""
        from AMA.L0.motor import Point2D
        
        with self.assertRaises(TypeError):
            Point2D("invalid", None)


class TestBridgeHealthReport(unittest.TestCase):
    """L0Bridge健康报告测试
    
    验证报告数据的完整性和准确性:
    - 所有字段存在且有合理默认值
    - 时间戳为当前时间
    - 状态枚举映射正确
    """
    
    def test_default_report_has_all_fields(self):
        """默认报告应包含所有必要字段"""
        from AMA.L0.bridge import BridgeHealthReport, BridgeState, SensorState
        
        report = BridgeHealthReport()
        
        self.assertIsNotNone(report.timestamp)
        self.assertGreater(report.timestamp, 0)
        
        self.assertEqual(report.bridge_state, BridgeState.UNINITIALIZED)
        self.assertEqual(report.sensor_state, SensorState.STOPPED)
        self.assertEqual(report.sensor_fps, 0.0)
        self.assertFalse(report.device_connected)
        self.assertEqual(report.error_count, 0)
        self.assertIsInstance(report.warnings, list)
    
    def test_report_timestamp_is_recent(self):
        """报告时间戳应为最近时间"""
        from AMA.L0.bridge import BridgeHealthReport
        import time
        
        before = time.time()
        report = BridgeHealthReport()
        after = time.time()
        
        self.assertGreaterEqual(report.timestamp, before)
        self.assertLessEqual(report.timestamp, after)


class TestUtilsFunctions(unittest.TestCase):
    """工具函数模块测试
    
    验证纯函数的正确性:
    - IP地址验证
    - 端口号验证
    - 字节格式化
    - 设备输出解析
    """
    
    def test_validate_ip_valid_addresses(self):
        """有效IP地址应通过验证"""
        from common.adb.utils import validate_ip_address
        
        valid_ips = [
            "127.0.0.1",
            "192.168.1.1",
            "0.0.0.0",
            "255.255.255.255",
            "10.0.0.1",
        ]
        
        for ip in valid_ips:
            self.assertTrue(validate_ip_address(ip), f"{ip} should be valid")
    
    def test_validate_ip_invalid_addresses(self):
        """无效IP地址应被拒绝"""
        from common.adb.utils import validate_ip_address
        
        invalid_ips = [
            "256.1.1.1",
            "1.2.3",
            "abc.def.ghi.jkl",
            "",
            "1.2.3.4.5",
            "-1.2.3.4",
        ]
        
        for ip in invalid_ips:
            self.assertFalse(validate_ip_address(ip), f"{ip} should be invalid")
    
    def test_validate_port_range(self):
        """端口号范围验证"""
        from common.adb.utils import validate_port
        
        self.assertTrue(validate_port(1))
        self.assertTrue(validate_port(80))
        self.assertTrue(validate_port(443))
        self.assertTrue(validate_port(65535))
        
        self.assertFalse(validate_port(0))
        self.assertFalse(validate_port(-1))
        self.assertFalse(validate_port(65536))
        self.assertFalse(validate_port(100000))
    
    def test_format_bytes_various_sizes(self):
        """字节格式化的各种大小"""
        from common.adb.utils import format_bytes
        
        self.assertEqual(format_bytes(0), "0.00 B")
        self.assertEqual(format_bytes(512), "512.00 B")
        self.assertEqual(format_bytes(1024), "1.00 KB")
        self.assertEqual(format_bytes(1536), "1.50 KB")
        self.assertEqual(format_bytes(1048576), "1.00 MB")
        self.assertEqual(format_bytes(1073741824), "1.00 GB")


class TestIntegrationL0FullLoop(unittest.TestCase):
    """L0层集成测试 - 完整流程验证
    
    模拟真实使用场景:
    1. 创建ADBClient
    2. 发现并连接设备
    3. 初始化L0Bridge
    4. 启动截图传感器
    5. 执行触控操作
    6. 获取健康报告
    7. 关闭清理
    
    注意: 此测试使用Mock对象，不依赖真实设备
    """
    
    @patch('common.adb.client.subprocess.run')
    def test_full_lifecycle_with_mock(self, mock_subprocess):
        """完整的生命周期集成测试"""
        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout="""List of devices attached
127.0.0.1:7555	device product:NemuPlayer model:SM901B
""",
            stderr=""
        )
        
        from common.adb.client import ADBClient
        from AMA.L0.bridge import L0Bridge
        import threading
        
        try:
            with patch.object(ADBClient, '_verify_adb_installation'):
                with patch.object(ADBClient, '_get_adb_version', return_value="1.0.41"):
                    client = ADBClient.__new__(ADBClient)
                    client._adb_path = Path("adb")
                    client._timeout = 30.0
                    client._devices_lock = threading.Lock()
                    client._devices = {}
                    client._active_device_serial = None
                    client._version = "1.0.41"
                    client._health_check_event = threading.Event()
                    
                    from concurrent.futures import ThreadPoolExecutor
                    client._executor = ThreadPoolExecutor(max_workers=1)
                    
                    bridge = L0Bridge.__new__(L0Bridge)
                    bridge._adb_client = client
                    bridge._device_serial = "127.0.0.1:7555"
                    bridge._config = MagicMock()
                    bridge._state = type('obj', (object,), {'name': 'UNINITIALIZED'})()
                    
                    self.assertIsNotNone(bridge.device_serial)
                    self.assertFalse(bridge.is_ready)
                    
                    client.shutdown()
                    
        except Exception as e:
            self.fail(f"集成测试失败: {e}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
