"""
ADB工具函数模块
提供设备发现、连接辅助、环境检测等实用功能

职责划分:
- client.py: 核心ADB客户端管理器（面向对象API）
- utils.py: 纯函数工具集（无状态、可独立使用）
"""

import subprocess
import re
import socket
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Callable, Any
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
import time


logger = logging.getLogger(__name__)


@dataclass
class PortScanResult:
    """端口扫描结果数据类"""
    host: str
    port: int
    is_open: bool
    response_time_ms: float = 0.0
    service_banner: str = ""


def check_adb_available() -> Tuple[bool, str]:
    """检查系统是否安装了ADB且可用
    
    Returns:
        (是否可用, 版本信息或错误描述)
    
    Time Complexity:
        O(1) - 单次进程调用
    """
    try:
        result = subprocess.run(
            ["adb", "version"],
            capture_output=True,
            text=True,
            timeout=5.0,
            creationflags=subprocess.CREATE_NO_WINDOW if __import__('platform').system() == "Windows" else 0
        )
        
        if result.returncode == 0:
            version_match = re.search(r'Version\s+([\d.]+)', result.stdout)
            version = version_match.group(1) if version_match else "Unknown"
            return True, f"ADB {version}"
        return False, f"ADB返回错误码: {result.returncode}"
        
    except FileNotFoundError:
        return False, "ADB未找到，请确认已添加到PATH或设置自定义路径"
    except subprocess.TimeoutExpired:
        return False, "ADB响应超时"
    except Exception as e:
        return False, f"检测异常: {e}"


def scan_adb_ports(
    host: str = "127.0.0.1",
    port_range: Optional[Tuple[int, int]] = None,
    common_ports_only: bool = True,
    timeout_per_port: float = 0.5,
    max_workers: int = 50,
) -> List[PortScanResult]:
    """扫描指定主机上的ADB相关端口
    
    扫描策略:
    - 当common_ports_only=True时，仅扫描已知模拟器的常用端口（速度更快）
    - 否则扫描完整端口范围（更全面但耗时更长）
    - 使用线程池并发扫描提升效率
    
    Args:
        host: 目标主机地址（默认扫描本机）
        port_range: 端口范围元组 (start, end)，None时根据common_ports_only决定
        common_ports_only: 是否只扫描已知模拟器端口
        timeout_per_port: 每个端口的连接超时（秒）
        max_workers: 并发扫描线程数
        
    Returns:
        开放端口列表（按端口号排序）
    
    Time Complexity:
        O(n/t) 其中n=端口数, t=max_workers
    """
    if common_ports_only or not port_range:
        known_ports = [
            5555, 5556, 5557, 5558, 5559,
            62001, 62025, 62026,
            7555, 16384, 16400,
            5565, 5575, 21503,
        ]
        ports_to_scan = list(set(known_ports))
    else:
        ports_to_scan = list(range(port_range[0], port_range[1] + 1))
    
    results: List[PortScanResult] = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_port = {
            executor.submit(_probe_single_port, host, port, timeout_per_port): port
            for port in ports_to_scan
        }
        
        for future in as_completed(future_to_port):
            port = future_to_port[future]
            try:
                result = future.result()
                if result.is_open:
                    results.append(result)
            except Exception as e:
                logger.debug(f"探测端口 {port} 异常: {e}")
    
    results.sort(key=lambda r: r.port)
    open_count = len(results)
    
    if open_count > 0:
        logger.info(f"端口扫描完成 | 主机:{host} | 开放端口数:{open_count}")
        for r in results[:10]:
            logger.info(f"  - :{r.port} ({r.response_time_ms:.1f}ms)")
        if open_count > 10:
            logger.info(f"  ... 还有 {open_count - 10} 个开放端口")
    
    return results


def _probe_single_port(
    host: str,
    port: int,
    timeout: float,
) -> PortScanResult:
    """探测单个端口是否开放的内部函数"""
    start = time.monotonic()
    banner = ""
    is_open = False
    
    try:
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            
            if result == 0:
                is_open = True
                try:
                    sock.sendall(b'\r\n')
                    banner = sock.recv(1024).decode('utf-8', errors='ignore').strip()
                except (socket.timeout, OSError):
                    pass
                    
    except Exception:
        pass
    
    elapsed_ms = (time.monotonic() - start) * 1000
    return PortScanResult(
        host=host,
        port=port,
        is_open=is_open,
        response_time_ms=elapsed_ms,
        service_banner=banner,
    )


def detect_emulator_type_by_port(port: int) -> Optional[str]:
    """根据端口号推断模拟器类型
    
    Args:
        port: ADB监听端口号
        
    Returns:
        模拟器名称字符串，无法识别则返回None
    """
    port_mapping = {
        7555: "MuMu模拟器 (主控)",
        16384: "MuMu模拟器 (子窗口)",
        16400: "MuMu模拟器 (备用)",
        62001: "夜神模拟器",
        62025: "夜神模拟器 (多开2)",
        62026: "夜神模拟器 (多开3)",
        5555: "Android默认/雷电/蓝叠",
        5557: "雷电模拟器 (多开2)",
        5559: "雷电模拟器 (多开3)",
        21503: "逍遥模拟器",
    }
    return port_mapping.get(port)


def parse_devices_output(output: str) -> List[Dict[str, str]]:
    """解析 `adb devices -l` 命令输出
    
    解析规则:
        - 跳过首行标题 "List of devices attached"
        - 按空格分割每行提取 serial 和 state
        - 后续字段为附加信息（product/model/device）
    
    Args:
        output: adb devices -l 的原始stdout文本
        
    Returns:
        设备信息字典列表，每个字典包含 serial/state/product/model/device 字段
    
    Example:
        >>> output = '''List of devices attached
        ... 127.0.0.1:7555 device product:NemuPlayer model:SM901B ...
        ... emulator-5554 offline'''
        >>> parse_devices_output(output)
        [{'serial': '127.0.0.1:7555', 'state': 'device', 'product': 'NemuPlayer', ...}]
    """
    devices = []
    lines = output.strip().split('\n')
    
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
            
        parts = line.split(maxsplit=5)
        if len(parts) < 2:
            continue
        
        entry = {'serial': parts[0], 'state': parts[1]}
        
        for part in parts[2:]:
            if ':' in part:
                key, value = part.split(':', 1)
                entry[key.lower()] = value
        
        devices.append(entry)
    
    return devices


def validate_ip_address(ip_str: str) -> bool:
    """验证IPv4地址格式合法性
    
    Args:
        ip_str: 待验证的IP地址字符串
        
    Returns:
        格式是否合法
    """
    pattern = r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$'
    match = re.match(pattern, ip_str.strip())
    
    if not match:
        return False
    
    for octet in match.groups():
        num = int(octet)
        if num < 0 or num > 255:
            return False
    
    return True


def validate_port(port: int) -> bool:
    """验证端口号是否在有效范围内
    
    Args:
        port: 待验证的端口号
        
    Returns:
        是否在 [1, 65535] 范围内
    """
    return isinstance(port, int) and 1 <= port <= 65535


def format_bytes(size_bytes: int) -> str:
    """将字节数格式化为人类可读的单位表示
    
    Args:
        size_bytes: 字节数
        
    Returns:
        格式化字符串（如 "15.23 MB"）
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"


def measure_command_latency(
    command_func: Callable,
    iterations: int = 10,
    warmup: int = 3,
) -> Dict[str, float]:
    """测量命令执行延迟统计指标
    
    通过多次执行采集样本，计算:
        - 平均延迟 (mean)
        - 最小/最大延迟 (min/max)
        - P95/P99 百分位延迟
        - 标准差 (std)
    
    Args:
        command_func: 无参可调用对象，执行被测命令并返回耗时（秒）
        iterations: 正式测量迭代次数
        warmup: 预热迭代次数（不计入统计）
        
    Returns:
        包含各项统计指标的字典
        
    Time Complexity:
        O(n) n=iterations+warmup
    """
    latencies = []
    
    for i in range(warmup + iterations):
        start = time.monotonic()
        try:
            command_func()
        except Exception:
            pass
        elapsed = time.monotonic() - start
        
        if i >= warmup:
            latencies.append(elapsed)
    
    if not latencies:
        return {'mean': 0, 'min': 0, 'max': 0, 'p95': 0, 'p99': 0, 'std': 0}
    
    sorted_latencies = sorted(latencies)
    n = len(sorted_latencies)
    mean = sum(sorted_latencies) / n
    
    variance = sum((x - mean) ** 2 for x in sorted_latencies) / n
    std = variance ** 0.5
    
    p95_idx = min(int(n * 0.95), n - 1)
    p99_idx = min(int(n * 0.99), n - 1)
    
    return {
        'mean': mean * 1000,
        'min': min(sorted_latencies) * 1000,
        'max': max(sorted_latencies) * 1000,
        'p95': sorted_latencies[p95_idx] * 1000,
        'p99': sorted_latencies[p99_idx] * 1000,
        'std': std * 1000,
        'iterations': n,
    }


def cleanup_stale_connections(threshold_seconds: float = 300.0) -> int:
    """清理长时间无响应的陈旧ADB连接
    
    检测机制:
        - 列出所有已连接设备
        - 对每个设备尝试get-state快速探测
        - 超过阈值时间未响应的视为陈旧连接并断开
    
    Args:
        threshold_seconds: 无响应时间阈值（秒），超过此时间的连接将被清理
        
    Returns:
        清理的连接数量
    """
    cleaned = 0
    
    try:
        result = subprocess.run(
            ["adb", "devices", "-l"],
            capture_output=True,
            text=True,
            timeout=10.0,
            creationflags=subprocess.CREATE_NO_WINDOW if __import__('platform').system() == "Windows" else 0
        )
        
        devices = parse_devices_output(result.stdout)
        
        for dev in devices:
            serial = dev['serial']
            if ':' not in serial:
                continue
            
            try:
                proc = subprocess.run(
                    ["adb", "-s", serial, "get-state"],
                    capture_output=True,
                    text=True,
                    timeout=threshold_seconds,
                    creationflags=subprocess.CREATE_NO_WINDOW if __import__('platform').system() == "Windows" else 0
                )
                
                if proc.stdout.strip() != "device":
                    subprocess.run(
                        ["adb", "disconnect", serial],
                        capture_output=True,
                        timeout=5.0,
                        creationflags=subprocess.CREATE_NO_WINDOW if __import__('platform').system() == "Windows" else 0
                    )
                    cleaned += 1
                    logger.info(f"清理陈旧连接: {serial}")
                    
            except subprocess.TimeoutExpired:
                subprocess.run(
                    ["adb", "disconnect", serial],
                    capture_output=True,
                    timeout=5.0,
                    creationflags=subprocess.CREATE_NO_WINDOW if __import__('platform').system() == "Windows" else 0
                )
                cleaned += 1
                logger.info(f"清理超时连接: {serial}")
                
    except Exception as e:
        logger.error(f"清理陈旧连接失败: {e}")
    
    return cleaned
