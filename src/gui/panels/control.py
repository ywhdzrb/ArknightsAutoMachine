"""
GUI面板 - 设备连接与手动控制面板(ControlPanel)

左侧功能区域，包含:
- ADB设备发现与选择
- 连接/断开控制
- 手动操作按钮（tap/swipe/key）
- 基础配置选项
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import logging
from pathlib import Path
from typing import Optional, Callable, Dict, List, Any


logger = logging.getLogger(__name__)


class ControlPanel(ttk.LabelFrame):
    """设备连接与控制面板
    
    职责:
    - 展示可用设备列表供用户选择
    - 提供连接/断开按钮
    - 手动操作调试（点击/滑动/按键）
    - 模拟器端口快速扫描
    
    回调接口:
    - on_connect(device_info): 用户点击连接时触发
    - on_disconnect(): 用户点击断开时触发
    - on_action(action_type, **kwargs): 手动操作时触发
    """
    
    def __init__(
        self,
        parent: tk.Widget,
        on_connect: Optional[Callable] = None,
        on_disconnect: Optional[Callable] = None,
        on_action: Optional[Callable] = None,
    ):
        """初始化控制面板
        
        Args:
            parent: 父容器widget
            on_connect: 连接回调函数
            on_disconnect: 断开回调函数
            on_action: 操作回调函数
        """
        super().__init__(parent, text="设备控制", style='Panel.TLabelframe')
        
        self._on_connect_cb = on_connect
        self._on_disconnect_cb = on_disconnect
        self._on_action_cb = on_action
        
        self._current_device = None
        self._is_connected = False
        
        self._create_widgets()
        self._layout_widgets()
    
    def _create_widgets(self) -> None:
        """创建所有子控件"""
        
        device_frame = ttk.LabelFrame(self, text="设备列表", padding=10)
        self._device_frame = device_frame
        
        # 先创建 list_frame 作为容器
        list_frame = ttk.Frame(device_frame)
        self._list_frame = list_frame

        self._device_listbox = tk.Listbox(
            list_frame,
            height=6,
            font=('Consolas', 9),
            selectmode=tk.SINGLE,
            bg='#1e1e1e',
            fg='#ffffff',
            selectbackground='#0078d4',
            selectforeground='#ffffff',
        )

        device_scrollbar = ttk.Scrollbar(
            list_frame,
            orient=tk.VERTICAL,
            command=self._device_listbox.yview
        )
        self._device_listbox.config(yscrollcommand=device_scrollbar.set)
        
        self._refresh_btn = ttk.Button(
            device_frame,
            text="🔄 刷新设备",
            command=self.refresh_device_list,
        )
        
        self._scan_btn = ttk.Button(
            device_frame,
            text="🔍 扫描模拟器",
            command=self.scan_emulator_ports,
        )
        
        self._connect_btn = ttk.Button(
            device_frame,
            text="🔗 连接",
            command=self._on_connect_clicked,
            state=tk.DISABLED,
        )
        self._disconnect_btn = ttk.Button(
            device_frame,
            text="✖ 断开",
            command=self._on_disconnect_clicked,
            state=tk.DISABLED,
        )

        # 手动连接区域
        manual_connect_frame = ttk.LabelFrame(device_frame, text="手动连接", padding=5)
        self._manual_connect_frame = manual_connect_frame

        self._manual_addr_var = tk.StringVar(value="192.168.0.110:5555")
        self._manual_addr_entry = ttk.Entry(
            manual_connect_frame,
            textvariable=self._manual_addr_var,
            font=('Consolas', 9),
            width=20
        )
        self._manual_connect_btn = ttk.Button(
            manual_connect_frame,
            text="🔗 连接指定地址",
            command=self._on_manual_connect,
            width=18
        )

        manual_frame = ttk.LabelFrame(self, text="手动控制", padding=10)
        self._manual_frame = manual_frame
        
        coord_frame = ttk.Frame(manual_frame)
        ttk.Label(coord_frame, text="X:").pack(side=tk.LEFT)
        self._x_entry = ttk.Entry(coord_frame, width=6)
        self._x_entry.pack(side=tk.LEFT, padx=2)
        self._x_entry.insert(0, "500")
        
        ttk.Label(coord_frame, text="Y:").pack(side=tk.LEFT, padx=(8, 0))
        self._y_entry = ttk.Entry(coord_frame, width=6)
        self._y_entry.pack(side=tk.LEFT, padx=2)
        self._y_entry.insert(0, "500")
        
        self._coord_var = tk.StringVar(value="(---, ---)")
        coord_display = ttk.Label(manual_frame, textvariable=self._coord_var, font=('Consolas', 9))
        
        btn_grid = ttk.Frame(manual_frame)
        
        self._tap_btn = ttk.Button(btn_grid, text="👆 点击", width=10, command=lambda: self._do_action('tap'))
        self._swipe_up_btn = ttk.Button(btn_grid, text="⬆ 上滑", width=10, command=lambda: self._do_action('swipe_up'))
        self._swipe_down_btn = ttk.Button(btn_grid, text="⬇ 下滑", width=10, command=lambda: self._do_action('swipe_down'))
        self._swipe_left_btn = ttk.Button(btn_grid, text="⬅ 左滑", width=10, command=lambda: self._do_action('swipe_left'))
        self._swipe_right_btn = ttk.Button(btn_grid, text="➡ 右滑", width=10, command=lambda: self._do_action('swipe_right'))
        self._home_btn = ttk.Button(btn_grid, text="🏠 Home", width=10, command=lambda: self._do_action('home'))
        self._back_btn = ttk.Button(btn_grid, text="⬅ Back", width=10, command=lambda: self._do_action('back'))
        
        config_frame = ttk.LabelFrame(self, text="设置", padding=10)
        self._config_frame = config_frame
        
        self._auto_connect_var = tk.BooleanVar(value=False)
        auto_connect_cb = ttk.Checkbutton(
            config_frame,
            text="自动连接首台设备",
            variable=self._auto_connect_var,
        )
        
        self._anti_detect_var = tk.BooleanVar(value=True)
        anti_detect_cb = ttk.Checkbutton(
            config_frame,
            text="启用反检测延迟",
            variable=self._anti_detect_var,
        )
        
        self._preview_fps_var = tk.StringVar(value="15")
        fps_frame = ttk.Frame(config_frame)
        ttk.Label(fps_frame, text="预览FPS:").pack(side=tk.LEFT)
        fps_spin = ttk.Spinbox(
            fps_frame,
            from_=1,
            to=60,
            width=5,
            textvariable=self._preview_fps_var,
        )
        fps_spin.pack(side=tk.LEFT, padx=5)
        
        info_frame = ttk.Frame(self)
        self._info_label = ttk.Label(
            info_frame,
            text="状态: 未连接",
            font=('Segoe UI', 9),
            wraplength=250,
        )
        
        self._widgets = {
            'device_frame': device_frame,
            'list_frame': self._list_frame,
            'device_listbox': self._device_listbox,
            'device_scrollbar': device_scrollbar,
            'refresh_btn': self._refresh_btn,
            'scan_btn': self._scan_btn,
            'connect_btn': self._connect_btn,
            'disconnect_btn': self._disconnect_btn,
            'manual_connect_frame': self._manual_connect_frame,
            'manual_addr_entry': self._manual_addr_entry,
            'manual_connect_btn': self._manual_connect_btn,
            'manual_frame': manual_frame,
            'coord_frame': coord_frame,
            'coord_display': coord_display,
            'btn_grid': btn_grid,
            'tap_btn': self._tap_btn,
            'swipe_up_btn': self._swipe_up_btn,
            'swipe_down_btn': self._swipe_down_btn,
            'swipe_left_btn': self._swipe_left_btn,
            'swipe_right_btn': self._swipe_right_btn,
            'home_btn': self._home_btn,
            'back_btn': self._back_btn,
            'config_frame': config_frame,
            'auto_connect': auto_connect_cb,
            'anti_detect': anti_detect_cb,
            'fps_frame': fps_frame,
            'info_label': self._info_label,
            'info_frame': info_frame,
        }
    
    def _layout_widgets(self) -> None:
        """布局所有子控件"""
        w = self._widgets

        # === 手动连接区域（放在最上方，方便桥接模式使用）===
        w['manual_connect_frame'].pack(fill=tk.X, pady=(0, 5))
        w['manual_addr_entry'].pack(fill=tk.X, pady=(0, 3))
        w['manual_connect_btn'].pack(fill=tk.X)

        # === 设备列表区域 ===
        w['device_frame'].pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        # list_frame 占据主要空间
        w['list_frame'].pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        w['device_listbox'].pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        w['device_scrollbar'].pack(side=tk.RIGHT, fill=tk.Y)

        btn_row = ttk.Frame(w['device_frame'])
        btn_row.pack(fill=tk.X, pady=(5, 0))
        w['refresh_btn'].pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        w['scan_btn'].pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(2, 0))

        conn_row = ttk.Frame(w['device_frame'])
        conn_row.pack(fill=tk.X, pady=(5, 0))
        w['connect_btn'].pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        w['disconnect_btn'].pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(2, 0))

        w['manual_frame'].pack(fill=tk.X, pady=5)
        w['coord_frame'].pack(fill=tk.X, pady=(0, 3))
        w['coord_display'].pack(anchor=tk.W, pady=(0, 5))
        
        w['btn_grid'].pack(fill=tk.X)
        
        w['tap_btn'].grid(row=0, column=0, padx=2, pady=2)
        w['swipe_up_btn'].grid(row=0, column=1, padx=2, pady=2)
        w['home_btn'].grid(row=0, column=2, padx=2, pady=2)
        w['swipe_left_btn'].grid(row=1, column=0, padx=2, pady=2)
        w['swipe_down_btn'].grid(row=1, column=1, padx=2, pady=2)
        w['back_btn'].grid(row=1, column=2, padx=2, pady=2)
        w['swipe_right_btn'].grid(row=2, column=0, padx=2, pady=2)
        
        w['config_frame'].pack(fill=tk.X, pady=5)
        w['auto_connect'].pack(anchor=tk.W, pady=2)
        w['anti_detect'].pack(anchor=tk.W, pady=2)
        w['fps_frame'].pack(fill=tk.X, pady=2)
        
        w['info_frame'].pack(fill=tk.X, side=tk.BOTTOM)
        w['info_label'].pack(anchor=tk.W)
    
    def _get_adb_path(self) -> str:
        """从设置文件加载ADB路径"""
        try:
            settings_file = Path(__file__).parent.parent.parent.parent / "config" / "user_settings.json"
            if settings_file.exists():
                import json
                with open(settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    return settings.get("adb", {}).get("executable_path", "") or ""
        except Exception as e:
            logger.debug(f"无法加载ADB路径设置: {e}")
        return ""

    def refresh_device_list(self) -> None:
        """刷新设备列表（后台执行）"""
        def do_refresh():
            try:
                from common.adb.client import ADBClient

                adb_path = self._get_adb_path()
                client = ADBClient(adb_path=adb_path if adb_path else None, auto_reconnect=False)
                devices = client.discover_devices(include_emulators=True)
                
                self.after(0, lambda: self._update_device_list(devices))
                
                if self._auto_connect_var.get() and devices and not self._is_connected:
                    self.after(500, lambda: self._select_and_connect(devices[0]))
                    
                client.shutdown()
                
            except Exception as e:
                logger.error(f"设备刷新失败: {e}")
                err_msg = str(e)
                self.after(0, lambda msg=err_msg: messagebox.showerror("错误", f"设备扫描失败:\n{msg}"))
        
        threading.Thread(target=do_refresh, daemon=True).start()
    
    def scan_emulator_ports(self) -> None:
        """扫描本地模拟器端口"""
        def do_scan():
            try:
                from common.adb.utils import scan_adb_ports, detect_emulator_type_by_port
                
                results = scan_adb_ports(common_ports_only=True)
                
                found_devices = []
                for r in results:
                    emu_name = detect_emulator_type_by_port(r.port)
                    display = f"{emu_name or f'未知(:{r.port})'} - {r.response_time_ms:.0f}ms"
                    found_devices.append((r.port, display, r.is_open))
                
                self.after(0, lambda: self._show_scan_results(found_devices))
                
            except Exception as e:
                logger.error(f"端口扫描失败: {e}")
                err_msg = str(e)
                self.after(0, lambda msg=err_msg: messagebox.showerror("错误", f"端口扫描失败:\n{msg}"))
        
        threading.Thread(target=do_scan, daemon=True).start()
    
    def _update_device_list(self, devices) -> None:
        """更新设备列表UI（必须在主线程调用）"""
        self._device_listbox.delete(0, tk.END)
        
        self._devices_cache = devices
        
        if not devices:
            self._device_listbox.insert(tk.END, "(未检测到设备)")
            self._info_label.config(text="状态: 未检测到设备\n请确认ADB已安装且设备已连接")
            return
        
        for dev in devices:
            display = dev.display_name if hasattr(dev, 'display_name') else str(dev.serial)
            status_icon = "●" if (hasattr(dev, 'is_connected') and dev.is_connected) else "○"
            entry = f"{status_icon} {display}"
            self._device_listbox.insert(tk.END, entry)

        self._info_label.config(text=f"状态: 发现 {len(devices)} 台设备\n选择后点击连接")

        # 绑定选择事件
        self._device_listbox.bind('<<ListboxSelect>>', self._on_device_selected)
    
    def _show_scan_results(self, results: List[tuple]) -> None:
        """显示端口扫描结果"""
        self._device_listbox.delete(0, tk.END)
        
        open_count = sum(1 for _, _, is_open in results if is_open)
        
        if not results:
            self._device_listbox.insert(tk.END, "(未检测到开放端口)")
            return
        
        self._device_listbox.insert(tk.END, f"=== 扫描结果 ({open_count}个开放端口) ===")
        
        for port, display, is_open in results:
            icon = "🟢" if is_open else "🔴"
            entry = f"{icon} {display}"
            self._device_listbox.insert(tk.END, entry)
        
        self._info_label.config(text=f"端口扫描完成 | 开放:{open_count}")
    
    def _select_and_connect(self, device) -> None:
        """自动选择并连接第一台设备"""
        if hasattr(self, '_devices_cache') and device in self._devices_cache:
            idx = self._devices_cache.index(device)
            self._device_listbox.selection_set(idx)
            self._on_connect_clicked()

    def _on_device_selected(self, event=None) -> None:
        """设备列表选择事件处理"""
        selection = self._device_listbox.curselection()
        if selection and not self._is_connected:
            # 检查选中的是否是有效设备（不是提示文本）
            idx = selection[0]
            if hasattr(self, '_devices_cache') and idx < len(self._devices_cache):
                self._connect_btn.config(state=tk.NORMAL)
            else:
                self._connect_btn.config(state=tk.DISABLED)

    def _on_connect_clicked(self) -> None:
        """连接按钮点击处理"""
        selection = self._device_listbox.curselection()

        if not selection:
            messagebox.showwarning("提示", "请先从列表中选择一台设备")
            return

        idx = selection[0]

        # 调试信息
        logger.debug(f"选中索引: {idx}, 设备缓存数量: {len(self._devices_cache) if hasattr(self, '_devices_cache') else 'N/A'}")

        if not hasattr(self, '_devices_cache') or not self._devices_cache:
            messagebox.showwarning("提示", "设备列表为空，请先刷新设备")
            return

        if idx >= len(self._devices_cache):
            messagebox.showwarning("提示", "请选择一个有效的设备")
            return

        device = self._devices_cache[idx]
        logger.debug(f"准备连接设备: {device}")

        if self._on_connect_cb:
            self._on_connect_cb(device)
    
    def _on_manual_connect(self) -> None:
        """手动连接指定地址"""
        addr = self._manual_addr_var.get().strip()
        if not addr:
            messagebox.showwarning("提示", "请输入设备地址")
            return

        # 验证地址格式
        if ':' not in addr:
            # 如果没有端口，默认添加 5555
            addr = f"{addr}:5555"
            self._manual_addr_var.set(addr)

        logger.info(f"手动连接地址: {addr}")

        # 创建一个模拟的设备信息对象
        class ManualDeviceInfo:
            def __init__(self, serial):
                self.serial = serial
                self.display_name = f"手动连接: {serial}"
                self.device_type = None
                self.is_connected = False

        device = ManualDeviceInfo(addr)

        if self._on_connect_cb:
            self._on_connect_cb(device)

    def _on_disconnect_clicked(self) -> None:
        """断开按钮点击处理"""
        if self._on_disconnect_cb:
            self._on_disconnect_cb()
    
    def _do_action(self, action_type: str) -> None:
        """执行手动操作"""
        try:
            x = int(self._x_entry.get())
            y = int(self._y_entry.get())
        except ValueError:
            x, y = 500, 500
        
        kwargs = {'x': x, 'y': y}
        
        if action_type == 'swipe_up':
            action_type = 'swipe'
            kwargs.update({'x1': x, 'y1': y + 300, 'x2': x, 'y2': y - 200})
        elif action_type == 'swipe_down':
            action_type = 'swipe'
            kwargs.update({'x1': x, 'y1': y - 200, 'x2': x, 'y2': y + 300})
        elif action_type == 'swipe_left':
            action_type = 'swipe'
            kwargs.update({'x1': x + 300, 'y1': y, 'x2': x - 200, 'y2': y})
        elif action_type == 'swipe_right':
            action_type = 'swipe'
            kwargs.update({'x1': x - 200, 'y1': y, 'x2': x + 300, 'y2': y})
        
        if self._on_action_cb:
            self._on_action_cb(action_type, **kwargs)
    
    def on_connected(self, device_info) -> None:
        """外部调用：标记为已连接状态"""
        self._is_connected = True
        self._current_device = device_info
        
        self._connect_btn.config(state=tk.DISABLED)
        self._disconnect_btn.config(state=tk.NORMAL)
        
        name = device_info.display_name if hasattr(device_info, 'display_name') else str(device_info)
        res = getattr(device_info, 'resolution', (0, 0))
        
        self._info_label.config(
            text=f"状态: 已连接 ✓\n{name}\n分辨率: {res[0]}×{res[1]}"
        )
    
    def on_disconnected(self) -> None:
        """外部调用：标记为已断开状态"""
        self._is_connected = False
        self._current_device = None
        
        self._connect_btn.config(state=tk.NORMAL)
        self._disconnect_btn.config(state=tk.DISABLED)
        
        self._info_label.config(text="状态: 未连接")
    
    def update_coordinate(self, x: int, y: int) -> None:
        """更新坐标显示（由预览面板点击回调）"""
        self._coord_var.set(f"({x}, {y})")
        self._x_entry.delete(0, tk.END)
        self._x_entry.insert(0, str(x))
        self._y_entry.delete(0, tk.END)
        self._y_entry.insert(0, str(y))
