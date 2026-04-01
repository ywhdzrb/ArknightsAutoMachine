"""
GUI面板 - 实时画面预览窗口(PreviewPanel)

中央主显示区域，提供:
- 实时游戏画面预览（降采样显示）
- 鼠标坐标追踪（点击时显示坐标）
- 截图保存功能
- FPS和延迟叠加显示
"""

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import cv2
import logging
import numpy as np
import threading
import time
from typing import Optional, Callable


logger = logging.getLogger(__name__)


class PreviewCanvas(tk.Canvas):
    """自定义画布组件，用于高效渲染截图帧
    
    优化策略:
    - 使用PhotoImage引用计数防止垃圾回收
    - 双缓冲减少闪烁
    - 自适应缩放保持宽高比
    """
    
    def __init__(self, parent: tk.Widget, **kwargs):
        super().__init__(parent, **kwargs)
        
        self._image_ref: Optional[ImageTk.PhotoImage] = None
        self._current_image: Optional[Image.Image] = None
        self._click_callback: Optional[Callable[[int, int], None]] = None
        
        self.bind('<Button-1>', self._on_click)
        self.bind('<Motion>', self._on_motion)
        
        self._coord_overlay_id = None
        self._stats_overlay_id = None
    
    def set_click_callback(self, callback: Callable[[int, int], None]) -> None:
        """设置鼠标点击回调"""
        self._click_callback = callback
    
    def update_image(self, pil_image: Image.Image) -> None:
        """更新显示的图像
        
        Args:
            pil_image: PIL Image对象（RGB格式）
        """
        try:
            canvas_width = self.winfo_width()
            canvas_height = self.winfo_height()
            
            if canvas_width <= 1 or canvas_height <= 1:
                return
            
            img_width, img_height = pil_image.size
            
            if img_width < 1 or img_height < 1:
                return
            
            scale_w = canvas_width / img_width
            scale_h = canvas_height / img_height
            scale = min(scale_w, scale_h, 1.0)
            
            new_width = int(img_width * scale)
            new_height = int(img_height * scale)
            
            if new_width < 1 or new_height < 1:
                return
            
            resized = pil_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            self._image_ref = ImageTk.PhotoImage(resized)
            
            self.delete("all")
        
            x_offset = (canvas_width - new_width) // 2
            y_offset = (canvas_height - new_height) // 2
            
            self.create_image(
                x_offset + new_width // 2,
                y_offset + new_height // 2,
                image=self._image_ref,
                anchor=tk.CENTER,
                tags="frame",
            )
            
            self._display_size = (new_width, new_height)
            self._offset = (x_offset, y_offset)
            self._original_size = (img_width, img_height)
            self._scale = scale
        except Exception as e:
            logger.debug(f"Canvas更新图像失败: {e}")
    
    def _on_click(self, event) -> None:
        """鼠标点击事件：计算并报告图片坐标"""
        if not hasattr(self, '_offset'):
            return
        
        ox, oy = self._offset
        scale = self._scale
        
        img_x = int((event.x - ox) / scale)
        img_y = int((event.y - oy) / scale)
        
        orig_w, orig_h = self._original_size
        
        if 0 <= img_x <= orig_w and 0 <= img_y <= orig_h:
            self._draw_coord_marker(event.x, event.y, img_x, img_y)
            
            if self._click_callback:
                self._click_callback(img_x, img_y)
    
    def _on_motion(self, event) -> None:
        """鼠标移动事件：实时显示坐标"""
        pass
    
    def _draw_coord_marker(self, canvas_x: int, canvas_y: int, img_x: int, img_y: int) -> None:
        """在点击位置绘制坐标标记"""
        self.delete("marker")
        
        size = 8
        color = "#00ff00"
        
        self.create_line(
            canvas_x - size, canvas_y,
            canvas_x + size, canvas_y,
            fill=color, width=2, tags="marker"
        )
        self.create_line(
            canvas_x, canvas_y - size,
            canvas_x, canvas_y + size,
            fill=color, width=2, tags="marker"
        )
        
        text = f"({img_x}, {img_y})"
        self.create_text(
            canvas_x + size + 4, canvas_y - size - 4,
            anchor=tk.NW,
            text=text,
            fill=color,
            font=('Consolas', 10, 'bold'),
            tags="marker"
        )


class PreviewPanel(ttk.LabelFrame):
    """实时画面预览面板
    
    功能:
    - 接收L0Bridge的帧数据并实时显示
    - 显示性能指标覆盖层（FPS/延迟/分辨率）
    - 支持鼠标点击获取屏幕坐标
    - 截图保存到本地文件
    """
    
    UPDATE_INTERVAL_MS = 66  # ~15 FPS 更新率，减少 GUI 负担
    
    def __init__(self, parent: tk.Widget):
        """初始化预览面板
        
        Args:
            parent: 父容器widget
        """
        super().__init__(parent, text="实时预览", style='Panel.TLabelframe')

        self._bridge = None
        self._running = False
        self._starting = False  # 防止重复启动
        self._last_update_time = 0.0
        self._frame_count = 0
        self._fps_calc_start = 0.0
        self._last_frame_timestamp = 0.0  # 用于检测新帧
        self._processing_frame = False  # 防止并发处理帧
        
        self._create_widgets()
        self._layout_widgets()
    
    def _create_widgets(self) -> None:
        """创建子控件"""
        toolbar = ttk.Frame(self)
        
        self._start_btn = ttk.Button(
            toolbar,
            text="▶ 开始预览",
            command=self.toggle_preview,
            width=12,
        )
        
        self._save_btn = ttk.Button(
            toolbar,
            text="💾 保存截图",
            command=self.save_screenshot,
            width=12,
        )
        
        self._fps_label = ttk.Label(
            toolbar,
            text="FPS: --",
            font=('Consolas', 10),
            width=12,
        )
        
        self._latency_label = ttk.Label(
            toolbar,
            text="延迟: --ms",
            font=('Consolas', 10),
            width=12,
        )
        
        self._resolution_label = ttk.Label(
            toolbar,
            text="分辨率: ---x---",
            font=('Consolas', 10),
        )
        
        self._canvas = PreviewCanvas(
            self,
            bg='#000000',
            highlightthickness=1,
            highlightbackground='#333333',
        )
        
        self._canvas.set_click_callback(self._on_canvas_click)
        
        self._status_label = ttk.Label(
            self,
            text="等待连接...",
            font=('Segoe UI', 9),
        )
        
        self._widgets = {
            'toolbar': toolbar,
            'start_btn': self._start_btn,
            'save_btn': self._save_btn,
            'fps_label': self._fps_label,
            'latency_label': self._latency_label,
            'resolution_label': self._resolution_label,
            'canvas': self._canvas,
            'status_label': self._status_label,
        }
    
    def _layout_widgets(self) -> None:
        """布局子控件"""
        w = self._widgets
        
        w['toolbar'].pack(fill=tk.X, padx=5, pady=5)
        
        left_toolbar = ttk.Frame(w['toolbar'])
        left_toolbar.pack(side=tk.LEFT)
        
        w['start_btn'].pack(side=tk.LEFT, padx=2)
        w['save_btn'].pack(side=tk.LEFT, padx=2)
        
        right_toolbar = ttk.Frame(w['toolbar'])
        right_toolbar.pack(side=tk.RIGHT)
        
        w['fps_label'].pack(side=tk.LEFT, padx=8)
        w['latency_label'].pack(side=tk.LEFT, padx=8)
        w['resolution_label'].pack(side=tk.LEFT, padx=8)
        
        w['canvas'].pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        w['status_label'].pack(fill=tk.X, padx=5, pady=(0, 5))
    
    def set_bridge(self, bridge) -> None:
        """绑定L0Bridge实例
        
        Args:
            bridge: L0Bridge对象或None（解除绑定）
        """
        self._bridge = bridge
        
        if bridge is None:
            self.stop_preview()
            self._widgets['status_label'].config(text="未连接设备")
        else:
            self._widgets['status_label'].config(text="已连接，点击'开始预览'")
    
    def toggle_preview(self) -> None:
        """切换预览开关"""
        if self._running:
            self.stop_preview()
        else:
            self.start_preview()
    
    def start_preview(self) -> None:
        """启动实时预览（异步启动传感器，避免阻塞 GUI）"""
        if self._bridge is None:
            return

        if not self._bridge.is_ready:
            return

        # 防止重复启动
        if self._starting or self._running:
            return

        self._starting = True
        self._widgets['start_btn'].config(text="⏹ 停止预览", state=tk.DISABLED)
        self._widgets['status_label'].config(text="正在启动传感器...")

        # 在后台线程启动传感器，避免阻塞 GUI
        def start_sensor_async():
            if hasattr(self._bridge, 'sensor') and self._bridge.sensor:
                try:
                    self._bridge.sensor.start()
                    # 传感器启动成功后，在主线程启动预览循环
                    self.after(0, self._on_sensor_started)
                except Exception as e:
                    logger.error(f"启动传感器失败: {e}")
                    self.after(0, lambda: self._on_sensor_failed(str(e)))

        threading.Thread(target=start_sensor_async, daemon=True).start()

    def _on_sensor_started(self) -> None:
        """传感器启动成功回调（在主线程执行）"""
        self._starting = False
        self._running = True
        self._frame_count = 0
        self._fps_calc_start = time.monotonic()
        self._widgets['start_btn'].config(state=tk.NORMAL)
        self._widgets['status_label'].config(text="预览中...")
        self._schedule_update()
        logger.info("预览已启动")

    def _on_sensor_failed(self, error_msg: str) -> None:
        """传感器启动失败回调（在主线程执行）"""
        self._starting = False
        self._running = False
        self._widgets['status_label'].config(text=f"启动失败: {error_msg}")
        self._widgets['start_btn'].config(text="▶ 开始预览", state=tk.NORMAL)
    
    def stop_preview(self) -> None:
        """停止实时预览"""
        self._starting = False
        self._running = False

        if self._bridge and hasattr(self._bridge, 'sensor') and self._bridge.sensor:
            try:
                self._bridge.sensor.stop()
            except Exception as e:
                logger.error(f"停止传感器失败: {e}")

        self._widgets['start_btn'].config(text="▶ 开始预览", state=tk.NORMAL)
        self._widgets['status_label'].config(text="预览已停止")
        
        self._widgets['fps_label'].config(text="FPS: --")
        self._widgets['latency_label'].config(text="延迟: --ms")
        
        logger.info("预览已停止")
    
    def _schedule_update(self) -> None:
        """调度下一次画面更新"""
        if not self._running:
            return
        
        self._update_frame()
        
        self.after(self.UPDATE_INTERVAL_MS, self._schedule_update)
    
    def _update_frame(self) -> None:
        """获取并渲染最新帧（非阻塞，只处理新帧）"""
        if not self._running or not self._bridge:
            return

        try:
            # 使用 timeout=0 确保非阻塞，不等待新帧
            frame = self._bridge.get_latest_frame(timeout=0.0)

            if frame and frame.image_numpy is not None:
                # 检查是否是新帧（通过时间戳）
                frame_time = frame.metadata.timestamp if frame.metadata else 0.0
                if frame_time <= self._last_frame_timestamp:
                    # 没有新帧，跳过处理
                    return
                self._last_frame_timestamp = frame_time

                # 验证 numpy 数组有效性
                if not isinstance(frame.image_numpy, np.ndarray):
                    logger.warning(f"无效的图像数据类型: {type(frame.image_numpy)}")
                    return

                if frame.image_numpy.size == 0:
                    logger.warning("图像数据为空")
                    return

                # 图像转换移到后台线程，避免阻塞 GUI
                self._process_frame_async(frame)

        except Exception as e:
            logger.debug(f"帧更新异常: {e}")

    def _process_frame_async(self, frame) -> None:
        """在后台线程处理图像转换，然后回到主线程更新 GUI"""
        # 防止并发处理（如果上一帧还在处理中，跳过当前帧）
        if self._processing_frame:
            return

        self._processing_frame = True

        def process_task():
            try:
                # BGR to RGB 转换
                rgb_image = cv2.cvtColor(frame.image_numpy, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(rgb_image)

                # 获取元数据
                metadata = {
                    'timestamp': frame.metadata.timestamp if frame.metadata else 0.0,
                    'latency': frame.metadata.capture_latency_ms if frame.metadata else 0.0,
                    'resolution': frame.metadata.resolution if frame.metadata else (0, 0),
                }

                # 回到主线程更新 GUI
                self.after(0, lambda: self._update_gui_with_frame(pil_image, metadata))
            except Exception as e:
                logger.warning(f"图像处理失败: {e}")
                self._processing_frame = False

        threading.Thread(target=process_task, daemon=True).start()

    def _update_gui_with_frame(self, pil_image: Image.Image, metadata: dict) -> None:
        """在主线程更新 GUI（由 _process_frame_async 回调）"""
        try:
            if not self._running:
                return

            self._canvas.update_image(pil_image)

            self._frame_count += 1

            now = time.monotonic()
            elapsed = now - self._fps_calc_start

            if elapsed >= 1.0:
                fps = self._frame_count / elapsed
                self._widgets['fps_label'].config(text=f"FPS: {fps:.1f}")
                self._frame_count = 0
                self._fps_calc_start = now

            lat = metadata.get('latency', 0)
            if lat > 0:
                self._widgets['latency_label'].config(text=f"延迟: {lat:.0f}ms")

            res = metadata.get('resolution', (0, 0))
            if res != (0, 0):
                self._widgets['resolution_label'].config(
                    text=f"分辨率: {res[0]}×{res[1]}"
                )
        except Exception as e:
            logger.debug(f"GUI 更新异常: {e}")
        finally:
            self._processing_frame = False
    
    def save_screenshot(self) -> None:
        """保存当前帧到文件"""
        if not self._bridge:
            return
        
        frame = self._bridge.get_latest_frame()
        
        if frame is None or frame.image_numpy is None:
            return
        
        from tkinter import filedialog
        from datetime import datetime
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"aam_screenshot_{timestamp}.png"
        
        path = filedialog.asksaveasfilename(
            title="保存截图",
            defaultextension=".png",
            initialfile=default_name,
            filetypes=[("PNG files", "*.png"), ("JPEG files", "*.jpg"), ("All files", "*.*")]
        )
        
        if path:
            # 在后台线程保存，避免阻塞 GUI
            def save_task():
                try:
                    import cv2
                    cv2.imwrite(path, frame.image_numpy)
                    self.after(0, lambda: self._widgets['status_label'].config(text=f"已保存: {path}"))
                    logger.info(f"截图已保存: {path}")
                except Exception as e:
                    logger.error(f"保存失败: {e}")

            threading.Thread(target=save_task, daemon=True).start()
    
    def _on_canvas_click(self, x: int, y: int) -> None:
        """画布点击事件回调"""
        app = self.winfo_toplevel()
        
        if hasattr(app, 'nametowidget'):
            control_panel = app.nametowidget('.!frame.!labelframe')
            if hasattr(control_panel, 'update_coordinate'):
                control_panel.update_coordinate(x, y)
