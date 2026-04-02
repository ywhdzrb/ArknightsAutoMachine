"""配置管理模块

提供统一的配置读取和写入接口，支持JSON格式配置文件。
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from threading import Lock

logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_CONFIG: Dict[str, Any] = {
    "adb": {
        "executable_path": "",
        "timeout_seconds": 30,
        "auto_reconnect": True,
        "health_check_interval": 10,
        "muMu_default_port": 7555,
        "nox_default_port": 62001,
        "ldplayer_default_port": 5555,
        "bluestacks_default_port": 5555,
        "transport_mode": "original",  # original, scrcpy, adbblitz (Windows only)
    },
    "emulator": {
        "scan_common_ports": True,
        "custom_ports": "16384,7555,62001",
        "connection_mode": "wireless",
    },
    "capture": {
        "method": "auto",
        "window_title": "",
        "window_hwnd": 0,
        "auto_detect_window": False,
        "client_only": True,
        "windows_specific_method": "auto",
    },
    "ui": {
        "theme": "dark",
        "preview_fps": 60,
        "show_fps_counter": True,
        "log_level": "INFO",
        "auto_connect_on_startup": False,
    },
    "preview": {
        "crop": {
            "top": 0,
            "bottom": 0,
            "left": 0,
            "right": 0,
        }
    },
    "advanced": {
        "enable_anti_detection": True,
        "min_operation_interval_ms": 50,
        "screenshot_compression_quality": 95,
        "max_buffer_size": 10,
    }
}


class ConfigManager:
    """配置管理器（单例模式）
    
    线程安全的配置管理，支持自动加载和保存。
    """
    
    _instance: Optional['ConfigManager'] = None
    _lock: Lock = Lock()
    
    def __new__(cls) -> 'ConfigManager':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        self._config_lock = Lock()
        self._config_file = Path(__file__).parent.parent.parent / "config" / "user_settings.json"
        self._config: Dict[str, Any] = {}
        self._load_config()
    
    def _load_config(self) -> None:
        """从文件加载配置"""
        try:
            if self._config_file.exists():
                with open(self._config_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    # 合并默认配置和加载的配置
                    self._config = self._merge_config(DEFAULT_CONFIG.copy(), loaded)
                    logger.info(f"配置已加载: {self._config_file}")
            else:
                self._config = DEFAULT_CONFIG.copy()
                logger.info("使用默认配置")
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            self._config = DEFAULT_CONFIG.copy()
    
    def _merge_config(self, default: Dict, loaded: Dict) -> Dict:
        """递归合并配置，确保所有默认键都存在"""
        result = default.copy()
        for key, value in loaded.items():
            if key in result:
                if isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = self._merge_config(result[key], value)
                else:
                    result[key] = value
            else:
                result[key] = value
        return result
    
    def save_config(self) -> bool:
        """保存配置到文件
        
        Returns:
            是否保存成功
        """
        try:
            self._config_file.parent.mkdir(parents=True, exist_ok=True)
            with self._config_lock:
                with open(self._config_file, 'w', encoding='utf-8') as f:
                    json.dump(self._config, f, indent=4, ensure_ascii=False)
            logger.info(f"配置已保存: {self._config_file}")
            return True
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值
        
        Args:
            key: 配置键，支持点号分隔的路径（如 'ui.preview_fps'）
            default: 默认值
            
        Returns:
            配置值，如果不存在则返回默认值
        """
        try:
            with self._config_lock:
                keys = key.split('.')
                value = self._config
                for k in keys:
                    if isinstance(value, dict):
                        value = value.get(k)
                        if value is None:
                            return default
                    else:
                        return default
                return value if value is not None else default
        except Exception:
            return default
    
    def set(self, key: str, value: Any) -> None:
        """设置配置值
        
        Args:
            key: 配置键，支持点号分隔的路径
            value: 配置值
        """
        try:
            with self._config_lock:
                keys = key.split('.')
                config = self._config
                for k in keys[:-1]:
                    if k not in config:
                        config[k] = {}
                    config = config[k]
                config[keys[-1]] = value
        except Exception as e:
            logger.error(f"设置配置失败: {e}")
    
    def get_all(self) -> Dict[str, Any]:
        """获取所有配置
        
        Returns:
            配置字典的副本
        """
        with self._config_lock:
            return self._config.copy()
    
    def update(self, config: Dict[str, Any]) -> None:
        """更新配置
        
        Args:
            config: 新的配置字典
        """
        with self._config_lock:
            self._config = self._merge_config(self._config, config)


# 全局配置管理器实例
_config_manager: Optional[ConfigManager] = None


def get_config() -> ConfigManager:
    """获取配置管理器实例
    
    Returns:
        ConfigManager 实例
    """
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def get_config_value(key: str, default: Any = None) -> Any:
    """快捷函数：获取配置值
    
    Args:
        key: 配置键
        default: 默认值
        
    Returns:
        配置值
    """
    return get_config().get(key, default)


def set_config_value(key: str, value: Any) -> None:
    """快捷函数：设置配置值
    
    Args:
        key: 配置键
        value: 配置值
    """
    get_config().set(key, value)


def save_config() -> bool:
    """快捷函数：保存配置
    
    Returns:
        是否保存成功
    """
    return get_config().save_config()
