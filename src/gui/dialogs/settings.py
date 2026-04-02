"""
GUI对话框 - 设置界面(SettingsDialog)

提供应用程序配置功能:
- ADB设置（可执行文件路径、超时时间等）
- 模拟器端口配置
- 界面显示选项
- Windows截图方式设置
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
import json
import threading
import sys

# 添加项目根目录到路径
_import_src_path = Path(__file__).parent.parent.parent
if str(_import_src_path) not in sys.path:
    sys.path.insert(0, str(_import_src_path))

import common.capture.window_utils
WindowEnumerator = common.capture.window_utils.WindowEnumerator
WindowInfo = common.capture.window_utils.WindowInfo
find_emulator_windows = common.capture.window_utils.find_emulator_windows


logger = logging.getLogger(__name__)


class SettingsDialog:
    """设置对话框
    
    模式窗口，阻塞父窗口操作。
    提供配置文件的导入/导出功能。
    """
    
    SETTINGS_FILE = Path(__file__).parent.parent.parent.parent / "config" / "user_settings.json"
    
    DEFAULT_SETTINGS: Dict[str, Any] = {
        "adb": {
            "executable_path": "",
            "timeout_seconds": 30,
            "auto_reconnect": True,
            "health_check_interval": 10,
            "muMu_default_port": 7555,
            "nox_default_port": 62001,
            "ldplayer_default_port": 5555,
            "bluestacks_default_port": 5555,
            "transport_mode": "original",
        },
        "emulator": {
            "scan_common_ports": True,
            "custom_ports": "16384,7555,62001",
            "connection_mode": "wireless",
        },
        "capture": {
            "method": "auto",  # auto, adb, windows, scrcpy
            "window_title": "",
            "window_hwnd": 0,
            "auto_detect_window": False,  # 默认显示所有窗口
            "client_only": True,
            "windows_specific_method": "auto",  # auto, wgc, bitblt, printwindow
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
    
    def __init__(self, parent: tk.Tk, on_save_callback: Optional[callable] = None):
        """初始化设置对话框

        Args:
            parent: 父窗口
            on_save_callback: 保存成功后的回调函数
        """
        self._parent = parent
        self._on_save_callback = on_save_callback
        self._settings = self._load_settings()
        self._saved = False  # 标记是否成功保存

        self._dialog = tk.Toplevel(parent)
        self._dialog.title("设置")
        self._dialog.geometry("600x700")
        self._dialog.minsize(600, 700)
        self._dialog.resizable(False, True)
        self._dialog.transient(parent)
        self._dialog.grab_set()

        self._setup_styles()
        self._create_widgets()
        self._load_settings_to_ui()
        self._center_dialog()

        self._dialog.protocol("WM_DELETE_WINDOW", self._on_close)

    def wait_window(self) -> bool:
        """等待对话框关闭，返回是否保存成功"""
        self._parent.wait_window(self._dialog)
        return self._saved
    
    def _setup_styles(self) -> None:
        """配置对话框样式"""
        style = ttk.Style(self._dialog)
        
        if 'clam' in style.theme_names():
            style.theme_use('clam')
        
        style.configure('Settings.TNotebook', tabposition='n')
        
        style.configure('SettingsTab.TFrame', background='#2b2b2b')
        style.configure('Settings.TLabelframe', background='#1e1e1e', foreground='#00d4ff')
        style.configure('Settings.TLabelframe.Label', foreground='#00d4ff', font=('Segoe UI', 10, 'bold'))
        
        style.configure('SettingsGroup.TLabelframe', background='#252525', foreground='#00d4ff')
        style.configure('SettingsGroup.TLabelframe.Label', foreground='#00d4ff')
        
        style.configure('Settings.TButton', padding=6)
        style.configure('Browse.TButton', padding=4)
        
        style.configure('Settings.TEntry', fieldbackground='#3a3a3a')
        style.configure('Settings.TSpinbox', fieldbackground='#3a3a3a')
    
    def _create_widgets(self) -> None:
        """创建所有控件"""
        main_frame = ttk.Frame(self._dialog, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        notebook = ttk.Notebook(main_frame, style='Settings.TNotebook')
        notebook.pack(fill=tk.BOTH, expand=True)
        
        self._adb_tab = self._create_adb_tab(notebook)
        self._emulator_tab = self._create_emulator_tab(notebook)
        self._capture_tab = self._create_capture_tab(notebook)
        self._ui_tab = self._create_ui_tab(notebook)
        self._advanced_tab = self._create_advanced_tab(notebook)

        notebook.add(self._adb_tab, text="  ADB  ")
        notebook.add(self._emulator_tab, text="  模拟器  ")
        notebook.add(self._capture_tab, text="  截图方式  ")
        notebook.add(self._ui_tab, text="  界面  ")
        notebook.add(self._advanced_tab, text="  高级  ")
        
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(
            btn_frame,
            text="导入配置...",
            command=self._import_config,
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(
            btn_frame,
            text="导出配置...",
            command=self._export_config,
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(
            btn_frame,
            text="恢复默认",
            command=self._reset_to_defaults,
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(
            btn_frame,
            text="确定",
            style='Accent.TButton',
            command=self._save_and_close,
        ).pack(side=tk.RIGHT, padx=(5, 0))
        
        ttk.Button(
            btn_frame,
            text="取消",
            command=self._on_close,
        ).pack(side=tk.RIGHT)
    
    def _create_adb_tab(self, notebook: ttk.Notebook) -> ttk.Frame:
        """创建ADB设置选项卡"""
        tab = ttk.Frame(notebook, style='SettingsTab.TFrame', padding=15)
        
        adb_path_frame = ttk.LabelFrame(
            tab,
            text="ADB可执行文件",
            style='SettingsGroup.TLabelframe',
            padding=10
        )
        adb_path_frame.pack(fill=tk.X, pady=(0, 15))
        
        path_row = ttk.Frame(adb_path_frame)
        path_row.pack(fill=tk.X)
        
        self._adb_path_var = tk.StringVar()
        adb_entry = ttk.Entry(
            path_row,
            textvariable=self._adb_path_var,
            width=50,
            font=('Consolas', 10)
        )
        adb_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        ttk.Button(
            path_row,
            text="浏览...",
            style='Browse.TButton',
            command=self._browse_adb_path,
        ).pack(side=tk.RIGHT)
        
        ttk.Label(
            adb_path_frame,
            text="留空则使用系统PATH中的adb",
            foreground='#888888',
            font=('Segoe UI', 8)
        ).pack(anchor=tk.W, pady=(5, 0))
        
        timeout_frame = ttk.LabelFrame(
            tab,
            text="连接超时",
            style='SettingsGroup.TLabelframe',
            padding=10
        )
        timeout_frame.pack(fill=tk.X, pady=(0, 15))
        
        timeout_row = ttk.Frame(timeout_frame)
        timeout_row.pack(fill=tk.X)
        
        self._timeout_var = tk.IntVar()
        timeout_spin = ttk.Spinbox(
            timeout_row,
            from_=5,
            to=300,
            width=10,
            textvariable=self._timeout_var
        )
        timeout_spin.pack(side=tk.LEFT)
        
        ttk.Label(
            timeout_row,
            text="秒",
        ).pack(side=tk.LEFT, padx=(5, 0))
        
        self._auto_reconnect_var = tk.BooleanVar()
        ttk.Checkbutton(
            timeout_frame,
            text="自动重连断开的设备",
            variable=self._auto_reconnect_var,
        ).pack(anchor=tk.W, pady=(10, 0))
        
        health_frame = ttk.LabelFrame(
            tab,
            text="健康检查",
            style='SettingsGroup.TLabelframe',
            padding=10
        )
        health_frame.pack(fill=tk.X)
        
        health_row = ttk.Frame(health_frame)
        health_row.pack(fill=tk.X)
        
        ttk.Label(health_row, text="检查间隔:").pack(side=tk.LEFT)
        
        self._health_interval_var = tk.IntVar()
        health_spin = ttk.Spinbox(
            health_row,
            from_=5,
            to=60,
            width=10,
            textvariable=self._health_interval_var
        )
        health_spin.pack(side=tk.LEFT, padx=(5, 0))
        
        ttk.Label(health_row, text="秒").pack(side=tk.LEFT)

        # ADB传输模式设置
        transport_frame = ttk.LabelFrame(
            tab,
            text="ADB传输模式",
            style='SettingsGroup.TLabelframe',
            padding=10
        )
        transport_frame.pack(fill=tk.X, pady=(15, 0))

        self._adb_transport_var = tk.StringVar(value="original")

        transport_info = {
            "original": "原始ADB（兼容性好，速度一般）",
            "scrcpy": "Scrcpy模式（速度快，需安装scrcpy）",
            "adbblitz": "ADBBlitz（Windows专用，速度最快）"
        }

        for mode, desc in transport_info.items():
            # ADBBlitz只在Windows上可用
            if mode == "adbblitz" and sys.platform != "win32":
                continue
            ttk.Radiobutton(
                transport_frame,
                text=desc,
                variable=self._adb_transport_var,
                value=mode
            ).pack(anchor=tk.W, pady=2)

        return tab

    def _create_emulator_tab(self, notebook: ttk.Notebook) -> ttk.Frame:
        """创建模拟器设置选项卡"""
        tab = ttk.Frame(notebook, style='SettingsTab.TFrame', padding=15)
        
        ports_frame = ttk.LabelFrame(
            tab,
            text="模拟器默认端口",
            style='SettingsGroup.TLabelframe',
            padding=10
        )
        ports_frame.pack(fill=tk.X, pady=(0, 15))
        
        self._mumu_port_var = tk.IntVar()
        self._nox_port_var = tk.IntVar()
        self._ldplayer_port_var = tk.IntVar()
        self._bluestacks_port_var = tk.IntVar()
        
        port_row = ttk.Frame(ports_frame)
        port_row.pack(fill=tk.X, pady=3)
        ttk.Label(port_row, text="MuMu:", width=15).pack(side=tk.LEFT)
        ttk.Spinbox(port_row, from_=1, to=65535, width=10, textvariable=self._mumu_port_var).pack(side=tk.LEFT)
        
        port_row = ttk.Frame(ports_frame)
        port_row.pack(fill=tk.X, pady=3)
        ttk.Label(port_row, text="夜神:", width=15).pack(side=tk.LEFT)
        ttk.Spinbox(port_row, from_=1, to=65535, width=10, textvariable=self._nox_port_var).pack(side=tk.LEFT)
        
        port_row = ttk.Frame(ports_frame)
        port_row.pack(fill=tk.X, pady=3)
        ttk.Label(port_row, text="雷电:", width=15).pack(side=tk.LEFT)
        ttk.Spinbox(port_row, from_=1, to=65535, width=10, textvariable=self._ldplayer_port_var).pack(side=tk.LEFT)
        
        port_row = ttk.Frame(ports_frame)
        port_row.pack(fill=tk.X, pady=3)
        ttk.Label(port_row, text="蓝叠:", width=15).pack(side=tk.LEFT)
        ttk.Spinbox(port_row, from_=1, to=65535, width=10, textvariable=self._bluestacks_port_var).pack(side=tk.LEFT)
        
        custom_frame = ttk.LabelFrame(
            tab,
            text="自定义端口",
            style='SettingsGroup.TLabelframe',
            padding=10
        )
        custom_frame.pack(fill=tk.X, pady=(0, 15))
        
        self._custom_ports_var = tk.StringVar()
        port_entry = ttk.Entry(
            custom_frame,
            textvariable=self._custom_ports_var,
            font=('Consolas', 10)
        )
        port_entry.pack(fill=tk.X)
        
        ttk.Label(
            custom_frame,
            text="多个端口用逗号分隔，如: 16384,16385,16386",
            foreground='#888888',
            font=('Segoe UI', 8)
        ).pack(anchor=tk.W, pady=(5, 0))
        
        self._scan_common_var = tk.BooleanVar()
        ttk.Checkbutton(
            custom_frame,
            text="启动时扫描常用端口",
            variable=self._scan_common_var,
        ).pack(anchor=tk.W, pady=(10, 0))
        
        return tab
    
    def _create_ui_tab(self, notebook: ttk.Notebook) -> ttk.Frame:
        """创建界面设置选项卡"""
        tab = ttk.Frame(notebook, style='SettingsTab.TFrame', padding=15)

        preview_frame = ttk.LabelFrame(
            tab,
            text="预览设置",
            style='SettingsGroup.TLabelframe',
            padding=10
        )
        preview_frame.pack(fill=tk.X, pady=(0, 15))

        fps_row = ttk.Frame(preview_frame)
        fps_row.pack(fill=tk.X)

        ttk.Label(fps_row, text="预览帧率:").pack(side=tk.LEFT)

        self._preview_fps_var = tk.IntVar()
        fps_spin = ttk.Spinbox(
            fps_row,
            from_=1,
            to=144,
            width=8,
            textvariable=self._preview_fps_var
        )
        fps_spin.pack(side=tk.LEFT, padx=(5, 0))

        ttk.Label(fps_row, text="FPS (0=无限制)").pack(side=tk.LEFT)

        self._show_fps_var = tk.BooleanVar()
        ttk.Checkbutton(
            preview_frame,
            text="显示FPS计数器",
            variable=self._show_fps_var,
        ).pack(anchor=tk.W, pady=(10, 0))

        self._auto_connect_var_ui = tk.BooleanVar()
        ttk.Checkbutton(
            preview_frame,
            text="启动时自动连接首台设备",
            variable=self._auto_connect_var_ui,
        ).pack(anchor=tk.W, pady=(5, 0))

        # 裁剪设置
        crop_frame = ttk.LabelFrame(
            tab,
            text="画面裁剪（用于去除模拟器边框）",
            style='SettingsGroup.TLabelframe',
            padding=10
        )
        crop_frame.pack(fill=tk.X, pady=(0, 15))

        # 上/下裁剪
        crop_v_row = ttk.Frame(crop_frame)
        crop_v_row.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(crop_v_row, text="顶部裁剪:").pack(side=tk.LEFT)
        self._crop_top_var = tk.IntVar(value=0)
        ttk.Spinbox(
            crop_v_row,
            from_=0,
            to=200,
            width=6,
            textvariable=self._crop_top_var
        ).pack(side=tk.LEFT, padx=(5, 15))

        ttk.Label(crop_v_row, text="底部裁剪:").pack(side=tk.LEFT)
        self._crop_bottom_var = tk.IntVar(value=0)
        ttk.Spinbox(
            crop_v_row,
            from_=0,
            to=200,
            width=6,
            textvariable=self._crop_bottom_var
        ).pack(side=tk.LEFT, padx=(5, 0))

        # 左/右裁剪
        crop_h_row = ttk.Frame(crop_frame)
        crop_h_row.pack(fill=tk.X, pady=(5, 0))

        ttk.Label(crop_h_row, text="左侧裁剪:").pack(side=tk.LEFT)
        self._crop_left_var = tk.IntVar(value=0)
        ttk.Spinbox(
            crop_h_row,
            from_=0,
            to=200,
            width=6,
            textvariable=self._crop_left_var
        ).pack(side=tk.LEFT, padx=(5, 15))

        ttk.Label(crop_h_row, text="右侧裁剪:").pack(side=tk.LEFT)
        self._crop_right_var = tk.IntVar(value=0)
        ttk.Spinbox(
            crop_h_row,
            from_=0,
            to=200,
            width=6,
            textvariable=self._crop_right_var
        ).pack(side=tk.LEFT, padx=(5, 0))

        # 预设按钮
        preset_row = ttk.Frame(crop_frame)
        preset_row.pack(fill=tk.X, pady=(10, 0))

        ttk.Label(preset_row, text="预设:").pack(side=tk.LEFT)

        ttk.Button(
            preset_row,
            text="MuMu模拟器 (顶部45px)",
            command=lambda: self._apply_crop_preset(top=45),
            width=20
        ).pack(side=tk.LEFT, padx=(5, 5))

        ttk.Button(
            preset_row,
            text="雷电模拟器",
            command=lambda: self._apply_crop_preset(top=0),
            width=15
        ).pack(side=tk.LEFT, padx=(0, 5))

        ttk.Button(
            preset_row,
            text="清除",
            command=lambda: self._apply_crop_preset(0, 0, 0, 0),
            width=8
        ).pack(side=tk.LEFT)

        log_frame = ttk.LabelFrame(
            tab,
            text="日志设置",
            style='SettingsGroup.TLabelframe',
            padding=10
        )
        log_frame.pack(fill=tk.X)
        
        log_row = ttk.Frame(log_frame)
        log_row.pack(fill=tk.X)
        
        ttk.Label(log_row, text="日志级别:").pack(side=tk.LEFT)
        
        self._log_level_var = tk.StringVar()
        log_combo = ttk.Combobox(
            log_row,
            values=["DEBUG", "INFO", "WARNING", "ERROR"],
            textvariable=self._log_level_var,
            state="readonly",
            width=10
        )
        log_combo.pack(side=tk.LEFT, padx=(5, 0))
        
        return tab
    
    def _create_advanced_tab(self, notebook: ttk.Notebook) -> ttk.Frame:
        """创建高级设置选项卡"""
        tab = ttk.Frame(notebook, style='SettingsTab.TFrame', padding=15)
        
        anti_detect_frame = ttk.LabelFrame(
            tab,
            text="反检测设置",
            style='SettingsGroup.TLabelframe',
            padding=10
        )
        anti_detect_frame.pack(fill=tk.X, pady=(0, 15))
        
        self._anti_detect_var = tk.BooleanVar()
        ttk.Checkbutton(
            anti_detect_frame,
            text="启用反检测延迟",
            variable=self._anti_detect_var,
        ).pack(anchor=tk.W)
        
        interval_row = ttk.Frame(anti_detect_frame)
        interval_row.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Label(interval_row, text="最小操作间隔:").pack(side=tk.LEFT)
        
        self._min_interval_var = tk.IntVar()
        interval_spin = ttk.Spinbox(
            interval_row,
            from_=10,
            to=1000,
            width=8,
            textvariable=self._min_interval_var
        )
        interval_spin.pack(side=tk.LEFT, padx=(5, 0))
        
        ttk.Label(interval_row, text="ms").pack(side=tk.LEFT)
        
        buffer_frame = ttk.LabelFrame(
            tab,
            text="性能设置",
            style='SettingsGroup.TLabelframe',
            padding=10
        )
        buffer_frame.pack(fill=tk.X)
        
        buffer_row = ttk.Frame(buffer_frame)
        buffer_row.pack(fill=tk.X)
        
        ttk.Label(buffer_row, text="帧缓冲区大小:").pack(side=tk.LEFT)
        
        self._buffer_size_var = tk.IntVar()
        buffer_spin = ttk.Spinbox(
            buffer_row,
            from_=1,
            to=60,
            width=8,
            textvariable=self._buffer_size_var
        )
        buffer_spin.pack(side=tk.LEFT, padx=(5, 0))
        
        ttk.Label(buffer_row, text="帧").pack(side=tk.LEFT)
        
        quality_row = ttk.Frame(buffer_frame)
        quality_row.pack(fill=tk.X, pady=(10, 0))

        ttk.Label(quality_row, text="截图压缩质量:").pack(side=tk.LEFT)

        self._quality_var = tk.IntVar()
        quality_spin = ttk.Spinbox(
            quality_row,
            from_=50,
            to=100,
            width=8,
            textvariable=self._quality_var
        )
        quality_spin.pack(side=tk.LEFT, padx=(5, 0))

        ttk.Label(quality_row, text="%").pack(side=tk.LEFT)

        return tab

    def _create_capture_tab(self, notebook: ttk.Notebook) -> ttk.Frame:
        """创建截图方式设置选项卡"""
        tab = ttk.Frame(notebook, style='SettingsTab.TFrame', padding=15)

        # 截图方式选择
        method_frame = ttk.LabelFrame(
            tab,
            text="截图方式",
            style='SettingsGroup.TLabelframe',
            padding=10
        )
        method_frame.pack(fill=tk.X, pady=(0, 15))

        self._capture_method_var = tk.StringVar(value="auto")

        method_info = [
            ("auto", "自动选择", "根据设备类型自动选择最佳方式"),
            ("adb", "ADB截图", "兼容性好，适合物理设备和远程连接（延迟500-1000ms）"),
            ("windows", "Windows截图", "性能优异，仅适合本地模拟器（延迟5-40ms）"),
            ("scrcpy", "Scrcpy截图", "超低延迟，需要安装scrcpy（延迟10-30ms）"),
        ]

        for value, label, desc in method_info:
            rb = ttk.Radiobutton(
                method_frame,
                text=f"{label} - {desc}",
                variable=self._capture_method_var,
                value=value,
                command=self._on_capture_method_changed,
            )
            rb.pack(anchor=tk.W, pady=3)

        # Windows截图窗口选择
        self._window_select_frame = ttk.LabelFrame(
            tab,
            text="Windows截图窗口选择",
            style='SettingsGroup.TLabelframe',
            padding=10
        )
        self._window_select_frame.pack(fill=tk.X, pady=(0, 15))

        # 自动检测复选框
        self._auto_detect_window_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self._window_select_frame,
            text="仅显示模拟器窗口",
            variable=self._auto_detect_window_var,
            command=self._on_auto_detect_changed,
        ).pack(anchor=tk.W, pady=(0, 5))

        # 窗口选择下拉框
        window_row = ttk.Frame(self._window_select_frame)
        window_row.pack(fill=tk.X, pady=5)

        ttk.Label(window_row, text="目标窗口:").pack(side=tk.LEFT)

        self._window_var = tk.StringVar()
        self._window_combo = ttk.Combobox(
            window_row,
            textvariable=self._window_var,
            state="readonly",
            width=50,
        )
        self._window_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))

        # 绑定选择变化事件
        self._window_combo.bind('<<ComboboxSelected>>', self._on_window_selected)

        # 刷新按钮
        btn_row = ttk.Frame(self._window_select_frame)
        btn_row.pack(fill=tk.X, pady=5)

        ttk.Button(
            btn_row,
            text="🔄 刷新窗口列表",
            command=self._refresh_window_list,
        ).pack(side=tk.LEFT, padx=(0, 5))

        ttk.Button(
            btn_row,
            text="🔍 检测模拟器",
            command=self._detect_emulator_windows,
        ).pack(side=tk.LEFT)

        # 窗口信息标签
        self._window_info_var = tk.StringVar(value="未选择窗口")
        ttk.Label(
            self._window_select_frame,
            textvariable=self._window_info_var,
            foreground='#888888',
            font=('Segoe UI', 9),
            wraplength=500,
        ).pack(anchor=tk.W, pady=(5, 0))

        # 选项
        options_frame = ttk.LabelFrame(
            tab,
            text="截图选项",
            style='SettingsGroup.TLabelframe',
            padding=10
        )
        options_frame.pack(fill=tk.X)

        self._client_only_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            options_frame,
            text="只捕获客户区（自动剔除窗口边框）",
            variable=self._client_only_var,
        ).pack(anchor=tk.W)

        # Windows特定捕捉方式下拉框
        windows_method_row = ttk.Frame(options_frame)
        windows_method_row.pack(fill=tk.X, pady=(10, 0))

        ttk.Label(
            windows_method_row,
            text="Windows捕捉方式:",
            width=18,
        ).pack(side=tk.LEFT)

        self._windows_method_var = tk.StringVar(value="auto")
        windows_methods = [
            ("auto", "自动选择（推荐）"),
            ("wgc", "WGC（Windows Graphics Capture）"),
            ("bitblt", "BitBlt（GDI传统方式）"),
            ("printwindow", "PrintWindow（兼容性好）"),
        ]

        windows_method_combo = ttk.Combobox(
            windows_method_row,
            textvariable=self._windows_method_var,
            values=[m[1] for m in windows_methods],
            state="readonly",
            width=30,
        )
        windows_method_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))

        ttk.Label(
            options_frame,
            text="说明: WGC延迟最低(~5ms)但需Win10 1903+；BitBlt兼容性最好；PrintWindow支持后台窗口",
            foreground='#888888',
            font=('Segoe UI', 8),
            wraplength=500,
        ).pack(anchor=tk.W, pady=(5, 0))

        ttk.Label(
            options_frame,
            text="提示: Windows截图方式仅支持本地运行的模拟器",
            foreground='#00d4ff',
            font=('Segoe UI', 9),
            wraplength=500,
        ).pack(anchor=tk.W, pady=(10, 0))

        # 初始化窗口列表
        self._detected_windows: List[WindowInfo] = []
        self._refresh_window_list()
        self._on_capture_method_changed()

        return tab

    def _on_capture_method_changed(self) -> None:
        """截图方式改变时更新UI"""
        method = self._capture_method_var.get()
        if method == "windows":
            # 启用窗口选择
            self._window_select_frame.state(['!disabled'])
            self._enable_window_select(True)
        else:
            # 禁用窗口选择
            self._enable_window_select(False)

    def _enable_window_select(self, enabled: bool) -> None:
        """启用/禁用窗口选择控件"""
        state = "!disabled" if enabled else "disabled"
        for child in self._window_select_frame.winfo_children():
            try:
                child.state([state])
            except tk.TclError:
                # 某些控件不支持 state 方法
                pass

    def _on_auto_detect_changed(self) -> None:
        """自动检测选项改变"""
        if self._auto_detect_window_var.get():
            self._window_combo.config(state="readonly")
            self._detect_emulator_windows()
        else:
            self._window_combo.config(state="normal")
            self._refresh_window_list()

    def _refresh_window_list(self) -> None:
        """刷新窗口列表 - 默认显示所有窗口"""
        def refresh_task():
            try:
                enumerator = WindowEnumerator()

                # 默认显示所有可见窗口，勾选"仅显示模拟器"时过滤
                if self._auto_detect_window_var.get():
                    windows = enumerator.find_emulator_windows()
                    logger.info(f"仅显示模拟器窗口: 找到 {len(windows)} 个")
                else:
                    windows = enumerator.enumerate_windows(visible_only=True)
                    logger.info(f"显示所有窗口: 找到 {len(windows)} 个")
                    # 记录前10个窗口用于调试
                    for i, w in enumerate(windows[:10]):
                        logger.debug(f"  窗口{i+1}: {w.title[:40] if w.title else '无标题'} (PID:{w.pid}, {w.width}x{w.height})")

                # 在主线程更新GUI
                def update_ui():
                    self._detected_windows = windows

                    # 更新下拉框
                    display_names = [enumerator.get_window_display_name(w) for w in windows]
                    self._window_combo['values'] = display_names

                    if display_names:
                        self._window_combo.set(display_names[0])
                        self._update_window_info(windows[0])
                        self._window_info_var.set(f"共 {len(windows)} 个窗口")
                        logger.info(f"窗口列表已更新: {len(windows)} 个窗口")
                    else:
                        self._window_combo.set("")
                        self._window_info_var.set("未检测到窗口")
                        logger.warning("未检测到任何窗口")

                self._dialog.after(0, update_ui)

            except Exception as e:
                logger.error(f"刷新窗口列表失败: {e}", exc_info=True)
                self._dialog.after(0, lambda: self._window_info_var.set(f"刷新失败: {e}"))

        # 在后台线程执行，避免阻塞UI
        threading.Thread(target=refresh_task, daemon=True).start()

    def _detect_emulator_windows(self) -> None:
        """检测模拟器窗口 - 勾选过滤并刷新"""
        self._auto_detect_window_var.set(True)
        self._refresh_window_list()

    def _on_window_selected(self, event=None) -> None:
        """窗口选择变化时更新信息显示"""
        selected = self._window_var.get()
        logger.debug(f"选中窗口: {selected}")

        for window in self._detected_windows:
            display_name = WindowEnumerator().get_window_display_name(window)
            if display_name == selected:
                self._update_window_info(window)
                logger.info(f"已选择窗口: {window.title[:40] if window.title else '无标题'} (PID:{window.pid})")
                return

    def _update_window_info(self, window: WindowInfo) -> None:
        """更新窗口信息显示"""
        info_text = (
            f"句柄: {window.hwnd} | "
            f"类名: {window.class_name} | "
            f"分辨率: {window.width}x{window.height} | "
            f"客户区: {window.client_rect[2]-window.client_rect[0]}x{window.client_rect[3]-window.client_rect[1]}"
        )
        self._window_info_var.set(info_text)

    def _get_selected_window(self) -> Optional[WindowInfo]:
        """获取选中的窗口"""
        selected = self._window_var.get()
        for window in self._detected_windows:
            display_name = WindowEnumerator().get_window_display_name(window)
            if display_name == selected:
                return window
        return None

    def _load_settings(self) -> Dict[str, Any]:
        """从文件加载设置"""
        try:
            if self.SETTINGS_FILE.exists():
                with open(self.SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    return self._merge_settings(self.DEFAULT_SETTINGS.copy(), loaded)
        except Exception as e:
            logger.warning(f"无法加载设置文件，使用默认设置: {e}")
        
        return self.DEFAULT_SETTINGS.copy()
    
    def _merge_settings(self, defaults: Dict, loaded: Dict) -> Dict:
        """递归合并设置"""
        for key, value in loaded.items():
            if key in defaults:
                if isinstance(value, dict) and isinstance(defaults[key], dict):
                    defaults[key] = self._merge_settings(defaults[key], value)
                else:
                    defaults[key] = value
        return defaults
    
    def _load_settings_to_ui(self) -> None:
        """将设置加载到UI控件"""
        adb = self._settings.get("adb", {})
        self._adb_path_var.set(adb.get("executable_path", ""))
        self._timeout_var.set(adb.get("timeout_seconds", 30))
        self._auto_reconnect_var.set(adb.get("auto_reconnect", True))
        self._health_interval_var.set(adb.get("health_check_interval", 10))
        self._mumu_port_var.set(adb.get("muMu_default_port", 7555))
        self._nox_port_var.set(adb.get("nox_default_port", 62001))
        self._ldplayer_port_var.set(adb.get("ldplayer_default_port", 5555))
        self._bluestacks_port_var.set(adb.get("bluestacks_default_port", 5555))
        self._adb_transport_var.set(adb.get("transport_mode", "original"))
        
        emulator = self._settings.get("emulator", {})
        self._custom_ports_var.set(emulator.get("custom_ports", "16384,7555,62001"))
        self._scan_common_var.set(emulator.get("scan_common_ports", True))
        
        ui = self._settings.get("ui", {})
        self._preview_fps_var.set(ui.get("preview_fps", 60))
        self._show_fps_var.set(ui.get("show_fps_counter", True))
        self._auto_connect_var_ui.set(ui.get("auto_connect_on_startup", False))
        self._log_level_var.set(ui.get("log_level", "INFO"))
        
        # 加载裁剪设置
        crop = self._settings.get("preview", {}).get("crop", {})
        self._crop_top_var.set(crop.get("top", 0))
        self._crop_bottom_var.set(crop.get("bottom", 0))
        self._crop_left_var.set(crop.get("left", 0))
        self._crop_right_var.set(crop.get("right", 0))
        
        advanced = self._settings.get("advanced", {})
        self._anti_detect_var.set(advanced.get("enable_anti_detection", True))
        self._min_interval_var.set(advanced.get("min_operation_interval_ms", 50))
        self._buffer_size_var.set(advanced.get("max_buffer_size", 10))
        self._quality_var.set(advanced.get("screenshot_compression_quality", 95))

        # 加载截图设置
        capture = self._settings.get("capture", {})
        self._capture_method_var.set(capture.get("method", "auto"))
        self._auto_detect_window_var.set(capture.get("auto_detect_window", False))
        self._client_only_var.set(capture.get("client_only", True))

        # 加载Windows特定捕捉方式
        windows_method = capture.get("windows_specific_method", "auto")
        self._windows_method_var.set(self._get_windows_method_display(windows_method))

        # 如果有保存的窗口标题，尝试选中
        saved_title = capture.get("window_title", "")
        if saved_title:
            for window in self._detected_windows:
                if saved_title in window.title:
                    display_name = WindowEnumerator().get_window_display_name(window)
                    self._window_var.set(display_name)
                    self._update_window_info(window)
                    break

        self._on_capture_method_changed()

    def _collect_settings_from_ui(self) -> Dict[str, Any]:
        """从UI控件收集设置"""
        self._settings["adb"]["executable_path"] = self._adb_path_var.get()
        self._settings["adb"]["timeout_seconds"] = self._timeout_var.get()
        self._settings["adb"]["auto_reconnect"] = self._auto_reconnect_var.get()
        self._settings["adb"]["health_check_interval"] = self._health_interval_var.get()
        self._settings["adb"]["muMu_default_port"] = self._mumu_port_var.get()
        self._settings["adb"]["nox_default_port"] = self._nox_port_var.get()
        self._settings["adb"]["ldplayer_default_port"] = self._ldplayer_port_var.get()
        self._settings["adb"]["bluestacks_default_port"] = self._bluestacks_port_var.get()
        self._settings["adb"]["transport_mode"] = self._adb_transport_var.get()
        
        self._settings["emulator"]["custom_ports"] = self._custom_ports_var.get()
        self._settings["emulator"]["scan_common_ports"] = self._scan_common_var.get()
        
        self._settings["ui"]["preview_fps"] = self._preview_fps_var.get()
        self._settings["ui"]["show_fps_counter"] = self._show_fps_var.get()
        self._settings["ui"]["auto_connect_on_startup"] = self._auto_connect_var_ui.get()
        self._settings["ui"]["log_level"] = self._log_level_var.get()
        
        # 保存裁剪设置
        if "preview" not in self._settings:
            self._settings["preview"] = {}
        self._settings["preview"]["crop"] = {
            "top": self._crop_top_var.get(),
            "bottom": self._crop_bottom_var.get(),
            "left": self._crop_left_var.get(),
            "right": self._crop_right_var.get()
        }
        
        self._settings["advanced"]["enable_anti_detection"] = self._anti_detect_var.get()
        self._settings["advanced"]["min_operation_interval_ms"] = self._min_interval_var.get()
        self._settings["advanced"]["max_buffer_size"] = self._buffer_size_var.get()
        self._settings["advanced"]["screenshot_compression_quality"] = self._quality_var.get()

        # 收集截图设置
        self._settings["capture"]["method"] = self._capture_method_var.get()
        self._settings["capture"]["auto_detect_window"] = self._auto_detect_window_var.get()
        self._settings["capture"]["client_only"] = self._client_only_var.get()

        # 保存选中的窗口信息
        selected_window = self._get_selected_window()
        if selected_window:
            self._settings["capture"]["window_title"] = selected_window.title
            self._settings["capture"]["window_hwnd"] = selected_window.hwnd
        else:
            self._settings["capture"]["window_title"] = ""
            self._settings["capture"]["window_hwnd"] = 0

        # 保存Windows特定捕捉方式
        self._settings["capture"]["windows_specific_method"] = self._get_windows_method_value()

        return self._settings

    def _get_windows_method_display(self, value: str) -> str:
        """将捕捉方式值转换为显示文本"""
        methods = {
            "auto": "自动选择（推荐）",
            "wgc": "WGC（Windows Graphics Capture）",
            "bitblt": "BitBlt（GDI传统方式）",
            "printwindow": "PrintWindow（兼容性好）",
        }
        return methods.get(value, "自动选择（推荐）")

    def _get_windows_method_value(self) -> str:
        """从显示文本获取捕捉方式值"""
        display = self._windows_method_var.get()
        methods = {
            "自动选择（推荐）": "auto",
            "WGC（Windows Graphics Capture）": "wgc",
            "BitBlt（GDI传统方式）": "bitblt",
            "PrintWindow（兼容性好）": "printwindow",
        }
        return methods.get(display, "auto")
    
    def _save_settings(self) -> bool:
        """保存设置到文件"""
        try:
            self.SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._settings, f, indent=4, ensure_ascii=False)
            
            logger.info(f"设置已保存到: {self.SETTINGS_FILE}")
            return True
            
        except Exception as e:
            logger.error(f"保存设置失败: {e}")
            messagebox.showerror("错误", f"保存设置失败:\n{e}")
            return False
    
    def _browse_adb_path(self) -> None:
        """浏览ADB可执行文件"""
        filepath = filedialog.askopenfilename(
            title="选择ADB可执行文件",
            filetypes=[
                ("ADB可执行文件", "adb.exe"),
                ("所有文件", "*.*")
            ],
            initialdir="C:\\" if Path("C:\\").exists() else str(Path.home())
        )
        
        if filepath:
            self._adb_path_var.set(filepath)
    
    def _import_config(self) -> None:
        """导入配置文件"""
        filepath = filedialog.askopenfilename(
            title="导入配置文件",
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")],
            initialdir=str(Path.home())
        )
        
        if filepath:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                
                self._settings = self._merge_settings(self.DEFAULT_SETTINGS.copy(), loaded)
                self._load_settings_to_ui()
                messagebox.showinfo("成功", "配置文件导入成功")
                
            except Exception as e:
                messagebox.showerror("错误", f"导入失败:\n{e}")
    
    def _export_config(self) -> None:
        """导出配置文件"""
        self._collect_settings_from_ui()
        
        filepath = filedialog.asksaveasfilename(
            title="导出配置文件",
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")],
            initialdir=str(Path.home()),
            initialfile="aam_settings.json"
        )
        
        if filepath:
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(self._settings, f, indent=4, ensure_ascii=False)
                
                messagebox.showinfo("成功", f"配置已导出到:\n{filepath}")
                
            except Exception as e:
                messagebox.showerror("错误", f"导出失败:\n{e}")
    
    def _reset_to_defaults(self) -> None:
        """恢复默认设置"""
        if messagebox.askyesno("确认", "确定要恢复所有设置为默认值吗？"):
            self._settings = self.DEFAULT_SETTINGS.copy()
            self._load_settings_to_ui()

    def _apply_crop_preset(self, top: int = 0, bottom: int = 0, left: int = 0, right: int = 0) -> None:
        """应用裁剪预设

        Args:
            top: 顶部裁剪像素
            bottom: 底部裁剪像素
            left: 左侧裁剪像素
            right: 右侧裁剪像素
        """
        self._crop_top_var.set(top)
        self._crop_bottom_var.set(bottom)
        self._crop_left_var.set(left)
        self._crop_right_var.set(right)
        logger.info(f"应用裁剪预设: 上{top}px 下{bottom}px 左{left}px 右{right}px")
    
    def _save_and_close(self) -> None:
        """保存设置并关闭"""
        self._collect_settings_from_ui()

        if self._save_settings():
            self._saved = True
            # 调用保存回调（在后台线程执行，避免阻塞UI）
            if self._on_save_callback:
                import threading
                def run_callback():
                    try:
                        self._on_save_callback(self._settings)
                    except Exception as e:
                        logger.error(f"保存回调执行失败: {e}")
                threading.Thread(target=run_callback, daemon=True).start()
            self._dialog.destroy()
    
    def _center_dialog(self) -> None:
        """将对话框居中显示"""
        self._dialog.update_idletasks()
        
        parent_x = self._parent.winfo_x()
        parent_y = self._parent.winfo_y()
        parent_w = self._parent.winfo_width()
        parent_h = self._parent.winfo_height()
        
        dialog_w = self._dialog.winfo_width()
        dialog_h = self._dialog.winfo_height()
        
        x = parent_x + (parent_w - dialog_w) // 2
        y = parent_y + (parent_h - dialog_h) // 2
        
        self._dialog.geometry(f"+{x}+{y}")
    
    def _on_close(self) -> None:
        """关闭对话框"""
        self._dialog.destroy()
