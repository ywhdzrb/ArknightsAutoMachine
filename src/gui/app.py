"""
Arknights Auto Machine - GUI主应用框架

基于tkinter的现代化桌面应用入口，
整合设备管理、实时预览、手动控制、性能监控等功能面板。

架构设计:
┌──────────────────────────────────────────────────────┐
│  AAM Main Window (ttk.Frame)                         │
├──────────┬─────────────────────┬─────────────────────┤
│  Control  │   Preview Panel     │  Monitor Panel      │
│  Panel    │   (Canvas+Label)    │  (Treeview)         │
│          │                     │                     │
│  -设备连接 │   [实时画面]        │  -L0延迟            │
│  -操作按钮 │   [坐标显示]        │  -FPS统计           │
│  -配置项   │                     │  -日志输出          │
└──────────┴─────────────────────┴─────────────────────┘
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import logging
import sys
import threading
from pathlib import Path
from typing import Optional, Dict, Any, Callable


logger = logging.getLogger(__name__)


class AAMApplication:
    """AAM主应用程序类
    
    职责:
    - 创建并管理主窗口和布局
    - 协调各功能面板之间的交互
    - 管理ADB客户端和L0Bridge的生命周期
    - 处理全局事件（关闭/刷新/重置）
    
    线程安全:
    所有GUI更新必须在主线程执行（通过after()方法调度），
    后台任务通过线程池异步执行。
    """
    
    APP_NAME = "Arknights Auto Machine"
    VERSION = "0.1.0-alpha"
    MIN_WINDOW_SIZE = (1200, 700)
    DEFAULT_WINDOW_SIZE = (1400, 900)
    
    def __init__(self):
        """初始化应用程序"""
        self._root: Optional[tk.Tk] = None
        self._adb_client = None
        self._bridge: Optional[object] = None
        
        self._style: Optional[ttk.Style] = None
        self._panels: Dict[str, ttk.Frame] = {}
        
        self._is_closing = False
        self._lock = threading.Lock()
        
        self._setup_logging()
        logger.info(f"{self.APP_NAME} v{self.VERSION} 启动中...")
    
    def _setup_logging(self) -> None:
        """配置应用级日志系统 - 同时输出到控制台、文件和GUI"""
        log_format = "%(asctime)s | %(levelname)-7s | %(name)-25s | %(message)s"
        date_format = "%H:%M:%S"

        # 创建日志目录
        log_dir = Path(__file__).parent.parent.parent / "logs"
        log_dir.mkdir(exist_ok=True)

        # 生成日志文件名（包含日期和时间，避免覆盖）
        from datetime import datetime
        log_file = log_dir / f"aam_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        # 配置根日志记录器
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)

        # 清除现有处理器
        root_logger.handlers.clear()

        # 控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter(log_format, date_format))
        root_logger.addHandler(console_handler)

        # 文件处理器
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(log_format, date_format))
        root_logger.addHandler(file_handler)

        logger.info(f"日志已配置 | 控制台级别: INFO | 文件级别: DEBUG | 日志文件: {log_file}")

    def _get_adb_path(self) -> str:
        """从设置文件加载ADB路径"""
        try:
            import json
            settings_file = Path(__file__).parent.parent.parent / "config" / "user_settings.json"
            if settings_file.exists():
                with open(settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    return settings.get("adb", {}).get("executable_path", "") or ""
        except Exception as e:
            logger.debug(f"无法加载ADB路径设置: {e}")
        return ""

    def create_window(self) -> tk.Tk:
        """创建主窗口并初始化所有UI组件
        
        Returns:
            根窗口Tk对象
            
        Raises:
            RuntimeError: 窗口创建失败
        """
        root = tk.Tk()
        root.title(f"{self.APP_NAME} v{self.VERSION}")
        root.geometry(f"{self.DEFAULT_WINDOW_SIZE[0]}x{self.DEFAULT_WINDOW_SIZE[1]}")
        root.minsize(*self.MIN_WINDOW_SIZE)
        
        try:
            icon_path = Path(__file__).parent / "assets" / "icon.ico"
            if icon_path.exists():
                root.iconbitmap(str(icon_path))
        except Exception as e:
            logger.debug(f"无法加载图标: {e}")
        
        self._configure_style(root)
        self._create_menu(root)
        self._create_main_layout(root)
        self._bind_events(root)
        
        self._root = root
        
        logger.info("主窗口创建完成")
        
        return root
    
    def _configure_style(self, root: tk.Tk) -> None:
        """配置ttk样式主题（现代化深色主题）"""
        style = ttk.Style()
        
        available_themes = style.theme_names()
        
        if 'clam' in available_themes:
            style.theme_use('clam')
        elif 'vista' in available_themes:
            style.theme_use('vista')
        elif 'xpnative' in available_themes:
            style.theme_use('xpnative')
        
        root.configure(bg='#1e1e1e')
        
        style.configure('TFrame', background='#2b2b2b')
        style.configure('Secondary.TFrame', background='#252525')
        style.configure('Card.TFrame', background='#2d2d2d', relief='flat')
        
        style.configure('TLabel', background='#2b2b2b', foreground='#e0e0e0', font=('Segoe UI', 9))
        style.configure('Secondary.TLabel', background='#252525', foreground='#b0b0b0')
        style.configure('Header.TLabel', font=('Segoe UI', 12, 'bold'), foreground='#ffffff')
        style.configure('Title.TLabel', font=('Segoe UI', 14, 'bold'), foreground='#00d4ff')
        style.configure('Status.TLabel', font=('Consolas', 9), foreground='#00ff88')
        style.configure('Error.TLabel', font=('Segoe UI', 9), foreground='#ff6b6b')
        style.configure('Muted.TLabel', foreground='#808080', font=('Segoe UI', 8))
        
        style.configure('TButton', padding=(10, 6), font=('Segoe UI', 9))
        style.configure('Action.TButton', padding=(15, 8), font=('Segoe UI', 9, 'bold'))
        style.configure('Danger.TButton', padding=(10, 6))
        style.configure('Icon.TButton', padding=4)
        
        style.map('TButton',
                  background=[('active', '#0078d4'), ('pressed', '#005a9e'), ('disabled', '#3a3a3a')],
                  foreground=[('disabled', '#606060')])
        
        style.map('Action.TButton',
                  background=[('active', '#00b4ff'), ('pressed', '#008bcc')])
        
        style.configure('Panel.TLabelframe', background='#1e1e1e', relief='flat')
        style.configure('Panel.TLabelframe.Label',
                       font=('Segoe UI', 10, 'bold'),
                       foreground='#00d4ff',
                       background='#1e1e1e')
        
        style.configure('Card.TLabelframe', background='#252525', relief='flat')
        style.configure('Card.TLabelframe.Label',
                       font=('Segoe UI', 9, 'bold'),
                       foreground='#00d4ff',
                       background='#252525')
        
        style.configure('TEntry', fieldbackground='#3a3a3a', foreground='#ffffff', insertcolor='#ffffff')
        style.configure('TCombobox', fieldbackground='#3a3a3a', foreground='#ffffff')
        style.configure('TSpinbox', fieldbackground='#3a3a3a', foreground='#ffffff')
        
        style.configure('TCheckbutton', background='#2b2b2b', foreground='#e0e0e0')
        style.configure('TRadiobutton', background='#2b2b2b', foreground='#e0e0e0')
        
        style.configure('Treeview',
                        background='#252525',
                        foreground='#e0e0e0',
                        fieldbackground='#252525',
                        rowheight=24)
        style.configure('Treeview.Heading',
                        font=('Segoe UI', 9, 'bold'),
                        foreground='#00d4ff')
        
        style.map('Treeview',
                  background=[('selected', '#0078d4')],
                  foreground=[('selected', '#ffffff')])
        
        style.configure('TScrollbar', background='#3a3a3a', troughcolor='#2b2b2b')
        style.map('TScrollbar',
                  background=[('active', '#0078d4'), ('pressed', '#005a9e')])
        
        style.configure('TNotebook', background='#1e1e1e', tabmargins=[5, 5, 0, 0])
        style.configure('TNotebook.Tab',
                        font=('Segoe UI', 9),
                        padding=[15, 5],
                        background='#2b2b2b',
                        foreground='#b0b0b0')
        style.map('TNotebook.Tab',
                  background=[('selected', '#0078d4')],
                  foreground=[('selected', '#ffffff'), ('active', '#e0e0e0')])
        
        self._style = style
    
    def _create_menu(self, root: tk.Tk) -> None:
        """创建菜单栏"""
        menubar = tk.Menu(root)
        root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="导入配置...", command=self._on_import_config)
        file_menu.add_command(label="导出配置...", command=self._on_export_config)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self._on_quit)
        
        device_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="设备", menu=device_menu)
        device_menu.add_command(label="刷新设备列表", command=self._on_refresh_devices)
        device_menu.add_command(label="断开当前设备", command=self._on_disconnect_device)
        device_menu.add_separator()
        device_menu.add_command(label="扫描模拟器端口", command=self._on_scan_ports)
        
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="视图", menu=view_menu)
        view_menu.add_command(label="重置布局", command=self._reset_layout)

        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="工具", menu=tools_menu)
        tools_menu.add_command(label="设置...", command=self._on_settings)

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="帮助", menu=help_menu)
        help_menu.add_command(label="关于", command=self._on_about)
    
    def _create_main_layout(self, root: tk.Tk) -> None:
        """创建主界面布局（三栏式）"""
        main_container = ttk.Frame(root)
        main_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        left_panel = ttk.Frame(main_container, width=280)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))
        left_panel.pack_propagate(False)
        
        center_panel = ttk.Frame(main_container)
        center_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        right_panel = ttk.Frame(main_container, width=320)
        right_panel.pack(side=tk.RIGHT, fill=tk.Y)
        right_panel.pack_propagate(False)
        
        from .panels.control import ControlPanel
        from .panels.preview import PreviewPanel
        from .panels.monitor import MonitorPanel
        
        self._panels['control'] = ControlPanel(
            left_panel,
            on_connect=self._handle_device_connect,
            on_disconnect=self._handle_device_disconnect,
            on_action=self._handle_manual_action,
        )
        self._panels['control'].pack(fill=tk.BOTH, expand=True)

        self._panels['preview'] = PreviewPanel(center_panel)
        self._panels['preview'].pack(fill=tk.BOTH, expand=True)

        self._panels['monitor'] = MonitorPanel(right_panel)
        self._panels['monitor'].pack(fill=tk.BOTH, expand=True)
        
        self._create_statusbar(root)
    
    def _create_statusbar(self, root: tk.Tk) -> None:
        """创建底部状态栏"""
        status_frame = ttk.Frame(root)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(5, 0))
        
        self._status_label = ttk.Label(
            status_frame,
            text="就绪 | 未连接设备",
            style='Status.TLabel'
        )
        self._status_label.pack(side=tk.LEFT, padx=10)
        
        self._device_status_label = ttk.Label(
            status_frame,
            text="",
            style='Status.TLabel'
        )
        self._device_status_label.pack(side=tk.RIGHT, padx=10)
    
    def _bind_events(self, root: tk.Tk) -> None:
        """绑定全局事件"""
        root.protocol("WM_DELETE_WINDOW", self._on_quit)
        root.bind('<F5>', lambda e: self._on_refresh_devices())
        root.bind('<Control-q>', lambda e: self._on_quit())
    
    def update_status(self, message: str) -> None:
        """更新状态栏文本"""
        if hasattr(self, '_status_label') and self._status_label:
            self._root.after(0, lambda: self._status_label.config(text=message))
    
    def update_device_status(self, message: str) -> None:
        """更新设备状态区域"""
        if hasattr(self, '_device_status_label') and self._device_status_label:
            self._root.after(0, lambda: self._device_status_label.config(text=message))
    
    def log_message(self, level: str, message: str) -> None:
        """发送消息到日志系统（控制台、文件、GUI）

        Args:
            level: 日志级别 (DEBUG/INFO/WARNING/ERROR)
            message: 日志消息
        """
        # 同时输出到标准日志系统
        log_level = getattr(logging, level.upper(), logging.INFO)
        logger.log(log_level, message)

        # 发送到GUI监控面板
        if 'monitor' in self._panels:
            monitor = self._panels['monitor']
            if hasattr(monitor, 'add_log'):
                self._root.after(0, lambda lvl=level, msg=message: monitor.add_log(lvl, msg))
    
    def _handle_device_connect(self, device_info) -> None:
        """处理设备连接请求"""
        def connect_task():
            try:
                from common.adb.client import ADBClient

                if self._adb_client is None:
                    adb_path = self._get_adb_path()
                    self._adb_client = ADBClient(
                        adb_path=adb_path if adb_path else None,
                        auto_reconnect=True
                    )

                device = self._adb_client.connect_device(
                    target=device_info.serial if hasattr(device_info, 'serial') else device_info
                )

                # 加载截图设置
                capture_settings = self._load_capture_settings()
                capture_method = capture_settings.get("method", "auto")

                # 根据设置选择桥接器类型
                if capture_method in ["windows", "scrcpy"]:
                    # 使用 HybridL0Bridge 支持 Windows 截图或 Scrcpy
                    from AMA.L0.hybrid_bridge import HybridL0Bridge, HybridBridgeConfig, CaptureBackend

                    if capture_method == "windows":
                        preferred_backend = CaptureBackend.WINDOWS
                        backend_name = "Windows截图"
                    else:  # scrcpy
                        preferred_backend = CaptureBackend.SCRCPY
                        backend_name = "Scrcpy截图"

                    config = HybridBridgeConfig(
                        preferred_backend=preferred_backend,
                        emulator_window_title=capture_settings.get("window_title"),
                        windows_specific_method=capture_settings.get("windows_specific_method", "auto"),
                    )

                    self._bridge = HybridL0Bridge(
                        adb_client=self._adb_client,
                        device_serial=device.serial,
                        config=config,
                    )
                    logger.info(f"使用{backend_name}方式 | 目标窗口: {config.emulator_window_title or '自动检测'} | 捕捉方式: {config.windows_specific_method}")
                else:
                    # 使用标准 ADB 截图或自动检测
                    from AMA.L0.bridge import L0Bridge

                    self._bridge = L0Bridge(
                        adb_client=self._adb_client,
                        device_serial=device.serial,
                    )
                    logger.info(f"使用标准ADB截图方式 | 方法: {capture_method}")

                self._bridge.initialize()

                self.update_status(f"已连接: {device.display_name}")
                self.update_device_status(f"{device.model} | {device.resolution[0]}x{device.resolution[1]}")

                self.log_message("INFO", f"设备连接成功: {device.display_name}")

                preview_panel = self._panels.get('preview')
                if preview_panel and self._bridge:
                    preview_panel.set_bridge(self._bridge)

                monitor_panel = self._panels.get('monitor')
                if monitor_panel and self._bridge:
                    monitor_panel.set_bridge(self._bridge)

                control_panel = self._panels.get('control')
                if control_panel:
                    control_panel.on_connected(device)

            except Exception as e:
                error_msg = f"连接失败: {e}"
                self.log_message("ERROR", error_msg)
                self.update_status(error_msg)

                self._root.after(0, lambda err=str(e): messagebox.showerror("连接错误", err))

        threading.Thread(target=connect_task, daemon=True).start()

    def _load_capture_settings(self) -> dict:
        """加载截图设置"""
        try:
            import json
            settings_file = Path(__file__).parent.parent.parent / "config" / "user_settings.json"
            logger.info(f"正在加载设置文件: {settings_file}")
            if settings_file.exists():
                with open(settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    capture_settings = settings.get("capture", {})
                    logger.info(f"加载的截图设置: {capture_settings}")
                    return capture_settings
            else:
                logger.warning(f"设置文件不存在: {settings_file}")
        except Exception as e:
            logger.error(f"无法加载截图设置: {e}")
        return {}
    
    def _handle_device_disconnect(self) -> None:
        """处理设备断开请求"""
        try:
            if self._bridge:
                self._bridge.shutdown()
                self._bridge = None
            
            if self._adb_client:
                self._adb_client.disconnect_device()
            
            self.update_status("已断开")
            self.update_device_status("")
            self.log_message("INFO", "设备已断开")
            
            control_panel = self._panels.get('control')
            if control_panel:
                control_panel.on_disconnected()
                
            preview_panel = self._panels.get('preview')
            if preview_panel:
                preview_panel.set_bridge(None)
                
        except Exception as e:
            self.log_message("ERROR", f"断开异常: {e}")
    
    def _handle_manual_action(self, action_type: str, **kwargs) -> None:
        """处理手动控制操作（异步执行，避免阻塞 GUI）"""
        if not self._bridge or not self._bridge.is_ready:
            messagebox.showwarning("警告", "请先连接设备")
            return

        # 在后台线程执行操作，避免阻塞 GUI
        def action_task():
            try:
                if action_type == 'tap':
                    success = self._bridge.tap(kwargs.get('x', 0), kwargs.get('y', 0))
                elif action_type == 'swipe':
                    success = self._bridge.swipe(
                        kwargs.get('x1', 0), kwargs.get('y1', 0),
                        kwargs.get('x2', 0), kwargs.get('y2', 0),
                    )
                elif action_type == 'home':
                    success = self._bridge.press_home()
                elif action_type == 'back':
                    success = self._bridge.press_back()
                else:
                    return

                status = "成功" if success else "失败"
                self.log_message("INFO", f"手动操作 [{action_type}] {status}")

            except Exception as e:
                self.log_message("ERROR", f"操作异常: {e}")

        threading.Thread(target=action_task, daemon=True).start()
    
    def _on_refresh_devices(self) -> None:
        """刷新设备列表（菜单事件）"""
        control = self._panels.get('control')
        if control and hasattr(control, 'refresh_device_list'):
            control.refresh_device_list()
    
    def _on_disconnect_device(self) -> None:
        """断开设备（菜单事件）"""
        self._handle_device_disconnect()
    
    def _on_scan_ports(self) -> None:
        """扫描模拟器端口（菜单事件）"""
        control = self._panels.get('control')
        if control and hasattr(control, 'scan_emulator_ports'):
            control.scan_emulator_ports()
    
    def _on_import_config(self) -> None:
        """导入配置文件"""
        path = filedialog.askopenfilename(
            title="导入配置",
            filetypes=[("YAML files", "*.yaml"), ("JSON files", "*.json"), ("All files", "*.*")]
        )
        if path:
            self.log_message("INFO", f"导入配置: {path}")
    
    def _on_export_config(self) -> None:
        """导出配置文件"""
        path = filedialog.asksaveasfilename(
            title="导出配置",
            defaultextension=".yaml",
            filetypes=[("YAML files", "*.yaml"), ("JSON files", "*.json")]
        )
        if path:
            self.log_message("INFO", f"导出配置: {path}")
    
    def _reset_layout(self) -> None:
        """重置窗口布局"""
        if self._root:
            self._root.geometry(f"{self.DEFAULT_WINDOW_SIZE[0]}x{self.DEFAULT_WINDOW_SIZE[1]}")
    
    def _on_about(self) -> None:
        """显示关于对话框"""
        about_text = (
            f"{self.APP_NAME}\n"
            f"版本: {self.VERSION}\n\n"
            f"基于AMA分层架构的明日方舟自动化代理工具\n"
            f"\n"
            f"L0感知执行层 - 第一阶段实现\n"
            f"\n"
            f"支持:\n"
            f"• Android实体设备 (USB/无线)\n"
            f"• MuMu / 夜神 / 雷电 / 蓝叠 模拟器"
        )
        messagebox.showinfo("关于", about_text)

    def _on_settings(self) -> None:
        """打开设置对话框"""
        from .dialogs.settings import SettingsDialog

        def on_settings_saved(settings):
            """设置保存后的回调 - 刷新预览设置并重新初始化设备连接"""
            # 刷新预览面板设置（帧率、裁剪等）
            preview_panel = self._panels.get('preview')
            if preview_panel and hasattr(preview_panel, 'refresh_settings'):
                preview_panel.refresh_settings()
                logger.info("预览设置已刷新")
            
            # 如果已连接设备，重新初始化以应用新设置
            if self._bridge and self._bridge.is_ready:
                logger.info("设置已更改，正在重新初始化设备连接...")
                # 保存当前设备信息
                device_serial = self._bridge._device_serial if hasattr(self._bridge, '_device_serial') else None
                if device_serial:
                    # 断开当前连接
                    try:
                        self._bridge.shutdown()
                    except Exception as e:
                        logger.debug(f"关闭旧连接时出错: {e}")
                    self._bridge = None

                    # 重新连接以应用新设置
                    self._root.after(100, lambda: self._reconnect_device(device_serial))

        if self._root:
            dialog = SettingsDialog(self._root, on_save_callback=on_settings_saved)
            dialog.wait_window()

    def _reconnect_device(self, device_serial: str) -> None:
        """重新连接设备（用于应用新设置）"""
        logger.info(f"正在使用新设置重新连接设备: {device_serial}")
        # 创建设备信息对象
        class DeviceInfo:
            pass
        device_info = DeviceInfo()
        device_info.serial = device_serial
        self._handle_device_connect(device_info)
    
    def _on_quit(self) -> None:
        """退出应用程序 - 优化版，避免阻塞"""
        if self._is_closing:
            return
        
        self._is_closing = True
        logger.info("正在关闭应用程序...")
        
        # 在后台线程执行清理，避免阻塞主线程
        def cleanup_task():
            try:
                # 停止预览面板
                preview_panel = self._panels.get('preview')
                if preview_panel and hasattr(preview_panel, 'stop'):
                    preview_panel.stop()
                
                # 断开设备连接（带超时）
                if self._bridge:
                    try:
                        self._bridge.shutdown()
                    except Exception as e:
                        logger.debug(f"关闭bridge时出错: {e}")
                    finally:
                        self._bridge = None
                
                # 关闭ADB客户端
                if self._adb_client:
                    try:
                        self._adb_client.shutdown()
                    except Exception as e:
                        logger.debug(f"关闭adb_client时出错: {e}")
                    finally:
                        self._adb_client = None
                        
            except Exception as e:
                logger.error(f"关闭过程异常: {e}")
            finally:
                # 确保在主线程销毁窗口
                if self._root:
                    self._root.after(0, self._root.destroy)
        
        # 启动清理线程
        import threading
        cleanup_thread = threading.Thread(target=cleanup_task, daemon=True)
        cleanup_thread.start()
        
        # 设置超时，强制关闭
        def force_quit():
            if self._root:
                logger.warning("强制关闭窗口")
                self._root.destroy()
        
        self._root.after(3000, force_quit)  # 3秒后强制关闭
    
    def run(self) -> None:
        """启动应用程序主循环"""
        root = self.create_window()
        
        self.update_status("就绪 | 请连接设备")
        self.log_message("INFO", "应用程序启动完成")
        
        root.mainloop()


def main():
    """应用入口点"""
    app = AAMApplication()
    app.run()


if __name__ == "__main__":
    main()
