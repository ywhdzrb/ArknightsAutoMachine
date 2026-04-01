"""
GUI面板 - 性能监控与日志面板(MonitorPanel)

右侧信息区域，提供:
- L0-L5各层延迟实时显示
- 操作日志输出
- 设备状态监控
- 系统资源使用情况
"""

import tkinter as tk
from tkinter import ttk
import logging
import threading
import time
from typing import Optional, Callable, Dict, Any
from datetime import datetime


logger = logging.getLogger(__name__)


class LogHandler(logging.Handler):
    """自定义日志处理器，将日志消息转发到GUI组件
    
    设计为线程安全的桥梁，后台线程产生的日志通过
    queue传递到主线程的GUI更新。
    """
    
    def __init__(self, callback: Callable[[str, str], None]):
        super().__init__()
        self._callback = callback
    
    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            level = record.levelname
            
            if self._callback:
                self._callback(level, msg)
        except Exception:
            pass


class MonitorPanel(ttk.LabelFrame):
    """性能监控与日志面板
    
    功能分区:
    1. 延迟仪表盘：L0截图/输入延迟、L5推理延迟等
    2. 日志区域：系统操作日志（可过滤级别）
    3. 设备信息：连接状态、分辨率、Android版本
    4. 统计摘要：总帧数/成功率/运行时长
    """
    
    LOG_MAX_LINES = 500
    UPDATE_INTERVAL_MS = 1000
    
    def __init__(self, parent: tk.Widget):
        """初始化监控面板
        
        Args:
            parent: 父容器widget
        """
        super().__init__(parent, text="监控面板", style='Panel.TLabelframe')
        
        self._bridge = None
        self._update_job = None
        self._fetching_health = False  # 防止重复获取健康报告

        self._create_widgets()
        self._layout_widgets()
        
        self._setup_log_capture()
    
    def _create_widgets(self) -> None:
        """创建所有子控件"""
        
        perf_frame = ttk.LabelFrame(self, text="性能指标", padding=8)
        
        metrics = [
            ("L0 截图延迟", "l0_screenshot", "ms"),
            ("L0 输入延迟", "l0_input", "ms"),
            ("传感器 FPS", "sensor_fps", "fps"),
            ("总帧数", "total_frames", ""),
            ("成功帧", "success_frames", ""),
            ("失败帧", "failed_frames", ""),
            ("缓冲区溢出", "buffer_overflow", "次"),
            ("运行时长", "uptime", "s"),
        ]
        
        self._metric_vars = {}
        self._metric_labels = {}
        
        for i, (label_text, key, unit) in enumerate(metrics):
            row_frame = ttk.Frame(perf_frame)
            
            name_label = ttk.Label(row_frame, text=f"{label_text}:", width=14, anchor=tk.W)
            value_var = tk.StringVar(value="--")
            value_label = ttk.Label(row_frame, textvariable=value_var, font=('Consolas', 10), width=10)
            unit_label = ttk.Label(row_frame, text=unit, width=4)
            
            row = i // 2
            col = (i % 2) * 3
            
            name_label.grid(row=row, column=col, sticky=tk.W, padx=2)
            value_label.grid(row=row, column=col + 1, sticky=tk.E, padx=2)
            unit_label.grid(row=row, column=col + 2, sticky=tk.W, padx=2)
            
            self._metric_vars[key] = value_var
            self._metric_labels[key] = value_label
        
        log_frame = ttk.LabelFrame(self, text="操作日志", padding=8)
        
        log_toolbar = ttk.Frame(log_frame)
        
        self._log_level_var = tk.StringVar(value="DEBUG")
        level_combo = ttk.Combobox(
            log_toolbar,
            textvariable=self._log_level_var,
            values=["DEBUG", "INFO", "WARNING", "ERROR"],
            state="readonly",
            width=8,
        )
        level_combo.pack(side=tk.LEFT, padx=(0, 5))
        
        self._auto_scroll_var = tk.BooleanVar(value=True)
        auto_scroll_cb = ttk.Checkbutton(
            log_toolbar,
            text="自动滚动",
            variable=self._auto_scroll_var,
        )
        auto_scroll_cb.pack(side=tk.LEFT)
        
        clear_btn = ttk.Button(
            log_toolbar,
            text="清空",
            command=self.clear_log,
            width=6,
        )
        clear_btn.pack(side=tk.RIGHT)
        
        log_container = ttk.Frame(log_frame)
        
        self._log_text = tk.Text(
            log_container,
            height=15,
            font=('Consolas', 8),
            bg='#0d1117',
            fg='#c9d1d9',
            insertbackground='#c9d1d9',
            selectbackground='#388bfd',
            wrap=tk.WORD,
            state=tk.DISABLED,
        )
        
        log_scrollbar = ttk.Scrollbar(
            log_container,
            orient=tk.VERTICAL,
            command=self._log_text.yview,
        )
        self._log_text.config(yscrollcommand=log_scrollbar.set)
        
        self._configure_log_tags()
        
        device_frame = ttk.LabelFrame(self, text="设备信息", padding=8)
        
        device_info_fields = [
            ("序列号", "serial"),
            ("型号", "model"),
            ("Android版本", "android_version"),
            ("分辨率", "resolution"),
            ("设备类型", "device_type"),
            ("连接状态", "state"),
        ]
        
        self._device_info_vars = {}
        
        for label_text, key in device_info_fields:
            row = ttk.Frame(device_frame)
            ttk.Label(row, text=f"{label_text}:", width=12, anchor=tk.W).pack(side=tk.LEFT)
            var = tk.StringVar(value="--")
            ttk.Label(row, textvariable=var, font=('Consolas', 9)).pack(side=tk.LEFT, fill=tk.X, expand=True)
            self._device_info_vars[key] = var
        
        status_frame = ttk.Frame(self)
        
        self._status_var = tk.StringVar(value="等待连接")
        status_label = ttk.Label(
            status_frame,
            textvariable=self._status_var,
            font=('Segoe UI', 9),
            wraplength=280,
        )
        
        self._widgets = {
            'perf_frame': perf_frame,
            'log_frame': log_frame,
            'log_toolbar': log_toolbar,
            'level_combo': level_combo,
            'clear_btn': clear_btn,
            'log_container': log_container,
            'log_text': self._log_text,
            'log_scrollbar': log_scrollbar,
            'device_frame': device_frame,
            'status_frame': status_frame,
            'status_label': status_label,
        }
    
    def _layout_widgets(self) -> None:
        """布局子控件"""
        w = self._widgets
        
        w['perf_frame'].pack(fill=tk.X, pady=(0, 5))
        
        w['log_frame'].pack(fill=tk.BOTH, expand=True, pady=5)
        w['log_toolbar'].pack(fill=tk.X)
        
        w['log_container'].pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        w['log_text'].pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        w['log_scrollbar'].pack(side=tk.RIGHT, fill=tk.Y)
        
        w['device_frame'].pack(fill=tk.X, pady=5)
        
        w['status_frame'].pack(fill=tk.X, side=tk.BOTTOM)
        w['status_label'].pack(anchor=tk.W)
    
    def _configure_log_tags(self) -> None:
        """配置日志文本标签样式（颜色编码）"""
        tag_colors = {
            'DEBUG': '#6e7681',
            'INFO': '#58a6ff',
            'WARNING': '#d29922',
            'ERROR': '#f85149',
            'CRITICAL': '#ff7b72',
        }
        
        for tag, color in tag_colors.items():
            self._log_text.tag_configure(tag, foreground=color)
    
    def _setup_log_capture(self) -> None:
        """设置全局日志捕获"""
        handler = LogHandler(self.add_log)
        handler.setLevel(logging.DEBUG)
        
        formatter = logging.Formatter('%(asctime)s | %(name)-20s | %(message)s', datefmt='%H:%M:%S')
        handler.setFormatter(formatter)
        
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        
        logger.info("日志监控系统已启动")
    
    def set_bridge(self, bridge) -> None:
        """绑定L0Bridge实例并启动监控更新循环
        
        Args:
            bridge: L0Bridge对象或None
        """
        self._bridge = bridge
        
        if bridge is None:
            if self._update_job:
                self.after_cancel(self._update_job)
                self._update_job = None
            
            self._reset_all_displays()
            self._status_var.set("未连接")
        else:
            self._status_var.set("监控中...")
            self._schedule_update()
    
    def _schedule_update(self) -> None:
        """调度周期性数据刷新"""
        self._update_metrics()
        self._update_device_info()
        
        self._update_job = self.after(self.UPDATE_INTERVAL_MS, self._schedule_update)
    
    def _update_metrics(self) -> None:
        """从Bridge获取最新性能数据并更新显示"""
        if not self._bridge:
            return
        
        try:
            stats = {}
            
            if hasattr(self._bridge, 'sensor') and self._bridge.sensor:
                sensor_stats = self._bridge.sensor.get_performance_stats()
                stats.update({
                    'sensor_fps': f"{sensor_stats.get('current_fps', 0):.1f}",
                    'total_frames': str(sensor_stats.get('total_frames_captured', 0)),
                    'success_frames': str(sensor_stats.get('successful_frames', 0)),
                    'failed_frames': str(sensor_stats.get('failed_frames', 0)),
                    'buffer_overflow': str(sensor_stats.get('buffer_overflows', 0)),
                    'avg_latency_ms': sensor_stats.get('average_latency_ms', 0),
                })
                
                self._metric_vars['sensor_fps'].set(stats.get('sensor_fps', '--'))
                self._metric_vars['total_frames'].set(stats.get('total_frames', '--'))
                self._metric_vars['success_frames'].set(stats.get('success_frames', '--'))
                self._metric_vars['failed_frames'].set(stats.get('failed_frames', '--'))
                self._metric_vars['buffer_overflow'].set(stats.get('buffer_overflow', '--'))
                
                latency = stats.get('avg_latency_ms', 0)
                self._metric_vars['l0_screenshot'].set(f"{latency:.1f}" if latency > 0 else "--")
            
            if hasattr(self._bridge, 'motor') and self._bridge.motor:
                motor_stats = self._bridge.motor.get_statistics()
                avg_time = motor_stats.get('average_execution_time_ms', 0)
                self._metric_vars['l0_input'].set(f"{avg_time:.1f}" if avg_time > 0 else "--")
            
            # 获取健康报告（注意：get_health_report 可能执行 ADB 命令，已改为异步获取）
            self._fetch_health_report_async()

        except Exception as e:
            logger.debug(f"指标更新异常: {e}")

    def _fetch_health_report_async(self) -> None:
        """异步获取健康报告，避免阻塞 GUI"""
        if self._fetching_health or not self._bridge:
            return

        self._fetching_health = True

        def fetch_task():
            try:
                report = self._bridge.get_health_report() if hasattr(self._bridge, 'get_health_report') else None
                if report:
                    # 回到主线程更新 GUI
                    self.after(0, lambda: self._update_health_display(report))
            except Exception as e:
                logger.debug(f"获取健康报告失败: {e}")
            finally:
                self._fetching_health = False

        threading.Thread(target=fetch_task, daemon=True).start()

    def _update_health_display(self, report) -> None:
        """更新健康报告显示（在主线程执行）"""
        try:
            uptime = int(report.uptime_seconds)
            hours = uptime // 3600
            minutes = (uptime % 3600) // 60
            seconds = uptime % 60

            if hours > 0:
                uptime_str = f"{hours}h{minutes}m"
            elif minutes > 0:
                uptime_str = f"{minutes}m{seconds}s"
            else:
                uptime_str = f"{seconds}s"

            self._metric_vars['uptime'].set(uptime_str)

            state_str = "● 运行" if report.bridge_state.name == "RUNNING" else report.bridge_state.name
            self._status_var.set(f"状态: {state_str}")
        except Exception as e:
            logger.debug(f"更新健康显示失败: {e}")

    def _update_device_info(self) -> None:
        """更新设备信息显示"""
        if not self._bridge or not hasattr(self._bridge, '_adb_client'):
            return
        
        try:
            devices = self._bridge._adb_client.get_device_list()
            
            if devices:
                dev = devices[0]
                info = dev.to_dict() if hasattr(dev, 'to_dict') else {}
                
                self._device_info_vars['serial'].set(info.get('serial', '--'))
                self._device_info_vars['model'].set(info.get('model', '--'))
                self._device_info_vars['android_version'].set(info.get('android_version', '--'))
                
                res = info.get('resolution', (0, 0))
                if res != (0, 0):
                    self._device_info_vars['resolution'].set(f"{res[0]}×{res[1]}")
                
                type_name = info.get('device_type', 'UNKNOWN')
                type_display = {
                    'PHYSICAL_USB': '物理(USB)',
                    'PHYSICAL_WIRELESS': '物理(无线)',
                    'MUMU_EMULATOR': 'MuMu模拟器',
                    'NOX_EMULATOR': '夜神模拟器',
                    'LDPLAYER_EMULATOR': '雷电模拟器',
                    'BLUESTACKS_EMULATOR': '蓝叠模拟器',
                }.get(type_name, type_name)
                
                self._device_info_vars['device_type'].set(type_display)
                self._device_info_vars['state'].set("已连接" if info.get('is_connected') else "离线")
                
        except Exception as e:
            logger.debug(f"设备信息更新异常: {e}")
    
    def add_log(self, level: str, message: str) -> None:
        """添加一条日志记录到显示区域（线程安全）
        
        Args:
            level: 日志级别（DEBUG/INFO/WARNING/ERROR）
            message: 日志消息文本
        """
        min_level = self._log_level_var.get()
        level_priority = {'DEBUG': 0, 'INFO': 1, 'WARNING': 2, 'ERROR': 3}
        
        current_prio = level_priority.get(level, 1)
        min_prio = level_priority.get(min_level, 0)
        
        if current_prio < min_prio:
            return
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] [{level:<7}] {message}\n"
        
        def do_insert():
            try:
                self._log_text.config(state=tk.NORMAL)
                self._log_text.insert(tk.END, formatted, level)
                
                total_lines = int(self._log_text.index('end-1c').split('.')[0])
                
                if total_lines > self.LOG_MAX_LINES:
                    self._log_text.delete('1.0', f'{total_lines - self.LOG_MAX_LINES}.0')
                
                if self._auto_scroll_var.get():
                    self._log_text.see(tk.END)
                
                self._log_text.config(state=tk.DISABLED)
            except Exception as e:
                pass
        
        try:
            self.after(0, do_insert)
        except Exception:
            pass
    
    def clear_log(self) -> None:
        """清空日志区域"""
        self._log_text.config(state=tk.NORMAL)
        self._log_text.delete('1.0', tk.END)
        self._log_text.config(state=tk.DISABLED)
    
    def _reset_all_displays(self) -> None:
        """重置所有显示为默认值"""
        for var in self._metric_vars.values():
            var.set("--")
        
        for var in self._device_info_vars.values():
            var.set("--")
