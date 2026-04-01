"""
GUI对话框 - 设置界面(SettingsDialog)

提供应用程序配置功能:
- ADB设置（可执行文件路径、超时时间等）
- 模拟器端口配置
- 界面显示选项
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import logging
from pathlib import Path
from typing import Optional, Dict, Any
import json


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
        },
        "emulator": {
            "scan_common_ports": True,
            "custom_ports": "16384,7555,62001",
            "connection_mode": "wireless",
        },
        "ui": {
            "theme": "dark",
            "preview_fps": 15,
            "show_fps_counter": True,
            "log_level": "INFO",
            "auto_connect_on_startup": False,
        },
        "advanced": {
            "enable_anti_detection": True,
            "min_operation_interval_ms": 50,
            "screenshot_compression_quality": 95,
            "max_buffer_size": 10,
        }
    }
    
    def __init__(self, parent: tk.Tk):
        """初始化设置对话框
        
        Args:
            parent: 父窗口
        """
        self._parent = parent
        self._settings = self._load_settings()
        
        self._dialog = tk.Toplevel(parent)
        self._dialog.title("设置")
        self._dialog.geometry("600x550")
        self._dialog.resizable(False, True)
        self._dialog.transient(parent)
        self._dialog.grab_set()
        
        self._setup_styles()
        self._create_widgets()
        self._load_settings_to_ui()
        self._center_dialog()
        
        self._dialog.protocol("WM_DELETE_WINDOW", self._on_close)
    
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
        self._ui_tab = self._create_ui_tab(notebook)
        self._advanced_tab = self._create_advanced_tab(notebook)
        
        notebook.add(self._adb_tab, text="  ADB  ")
        notebook.add(self._emulator_tab, text="  模拟器  ")
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
            to=60,
            width=8,
            textvariable=self._preview_fps_var
        )
        fps_spin.pack(side=tk.LEFT, padx=(5, 0))
        
        ttk.Label(fps_row, text="FPS").pack(side=tk.LEFT)
        
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
        
        emulator = self._settings.get("emulator", {})
        self._custom_ports_var.set(emulator.get("custom_ports", "16384,7555,62001"))
        self._scan_common_var.set(emulator.get("scan_common_ports", True))
        
        ui = self._settings.get("ui", {})
        self._preview_fps_var.set(ui.get("preview_fps", 15))
        self._show_fps_var.set(ui.get("show_fps_counter", True))
        self._auto_connect_var_ui.set(ui.get("auto_connect_on_startup", False))
        self._log_level_var.set(ui.get("log_level", "INFO"))
        
        advanced = self._settings.get("advanced", {})
        self._anti_detect_var.set(advanced.get("enable_anti_detection", True))
        self._min_interval_var.set(advanced.get("min_operation_interval_ms", 50))
        self._buffer_size_var.set(advanced.get("max_buffer_size", 10))
        self._quality_var.set(advanced.get("screenshot_compression_quality", 95))
    
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
        
        self._settings["emulator"]["custom_ports"] = self._custom_ports_var.get()
        self._settings["emulator"]["scan_common_ports"] = self._scan_common_var.get()
        
        self._settings["ui"]["preview_fps"] = self._preview_fps_var.get()
        self._settings["ui"]["show_fps_counter"] = self._show_fps_var.get()
        self._settings["ui"]["auto_connect_on_startup"] = self._auto_connect_var_ui.get()
        self._settings["ui"]["log_level"] = self._log_level_var.get()
        
        self._settings["advanced"]["enable_anti_detection"] = self._anti_detect_var.get()
        self._settings["advanced"]["min_operation_interval_ms"] = self._min_interval_var.get()
        self._settings["advanced"]["max_buffer_size"] = self._buffer_size_var.get()
        self._settings["advanced"]["screenshot_compression_quality"] = self._quality_var.get()
        
        return self._settings
    
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
    
    def _save_and_close(self) -> None:
        """保存设置并关闭"""
        self._collect_settings_from_ui()
        
        if self._save_settings():
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
