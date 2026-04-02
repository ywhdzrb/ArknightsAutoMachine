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
from typing import Optional, Callable, Tuple


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
        update_start = time.time()
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
            
            # 使用更快的BILINEAR算法代替LANCZOS，减少主线程阻塞
            resized = pil_image.resize((new_width, new_height), Image.Resampling.BILINEAR)
            
            resize_time = time.time() - update_start
            if resize_time > 0.01:  # 如果缩放超过10ms
                logger.debug(f"图像缩放耗时: {resize_time*1000:.1f}ms | 尺寸:{new_width}x{new_height}")
            
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
            # 计算并存储缩放比例（显示尺寸 / 原始尺寸）
            self._scale_x = new_width / img_width if img_width > 0 else 1.0
            self._scale_y = new_height / img_height if img_height > 0 else 1.0
            
            total_time = time.time() - update_start
            if total_time > 0.02:  # 如果总时间超过20ms
                logger.debug(f"Canvas.update_image 总耗时: {total_time*1000:.1f}ms")
        except Exception as e:
            logger.debug(f"Canvas更新图像失败: {e}")
    
    def update_image_direct(self, pil_image: Image.Image, 
                           original_size: Optional[Tuple[int, int]] = None,
                           crop_offsets: Optional[Tuple[int, int, int, int]] = None) -> None:
        """直接显示已经缩放好的图像（不进行缩放，用于后台线程已处理好的图像）
        
        Args:
            pil_image: PIL Image对象（已经缩放好的RGB格式）
            original_size: 原始屏幕分辨率（宽, 高），用于点击坐标映射
            crop_offsets: 裁剪偏移量 (top, bottom, left, right)
        """
        
        update_start = time.time()
        try:
            canvas_width = self.winfo_width()
            canvas_height = self.winfo_height()
            
            
            if canvas_width <= 1 or canvas_height <= 1:
                
                return
            
            img_width, img_height = pil_image.size
            
            
            if img_width < 1 or img_height < 1:
                
                return
            
            
            # 直接使用传入的图像，不进行缩放
            self._image_ref = ImageTk.PhotoImage(pil_image)
            
            
            
            self.delete("all")
            
            
            # 居中显示
            x_offset = (canvas_width - img_width) // 2
            y_offset = (canvas_height - img_height) // 2
            
            
            self.create_image(
                x_offset + img_width // 2,
                y_offset + img_height // 2,
                image=self._image_ref,
                anchor=tk.CENTER,
                tags="frame",
            )
            
            
            self._display_size = (img_width, img_height)
            self._offset = (x_offset, y_offset)
            # 存储原始屏幕分辨率（用于点击坐标映射）
            self._original_size = original_size if original_size else (img_width, img_height)
            # 计算并存储缩放比例（显示尺寸 / 原始尺寸）
            orig_w, orig_h = self._original_size
            self._scale_x = img_width / orig_w if orig_w > 0 else 1.0
            self._scale_y = img_height / orig_h if orig_h > 0 else 1.0
            # 存储裁剪偏移量
            self._crop_offsets = crop_offsets if crop_offsets else (0, 0, 0, 0)
            
            total_time = time.time() - update_start
            
        except Exception as e:
            print(f"[ERROR] update_image_direct 异常: {e}")
            import traceback
            traceback.print_exc()
    
    def _on_click(self, event) -> None:
        """鼠标点击事件：计算并报告屏幕坐标
        
        坐标映射流程:
        1. 将 Canvas 坐标转换为显示图像坐标（考虑偏移）
        2. 根据缩放比例，映射到原始屏幕坐标
        """
        if not hasattr(self, '_offset') or not hasattr(self, '_original_size'):
            return
        
        ox, oy = self._offset
        
        # 计算相对于显示图像的坐标
        display_x = event.x - ox
        display_y = event.y - oy
        
        # 获取显示图像尺寸和原始屏幕分辨率
        display_w, display_h = self._display_size
        orig_w, orig_h = self._original_size
        
        # 检查点击是否在图像范围内
        if not (0 <= display_x <= display_w and 0 <= display_y <= display_h):
            return
        
        # 使用存储的缩放比例映射到原始屏幕坐标
        if hasattr(self, '_scale_x') and hasattr(self, '_scale_y'):
            screen_x = int(display_x / self._scale_x)
            screen_y = int(display_y / self._scale_y)
        else:
            # 回退方案：根据尺寸比例计算
            if display_w > 0 and display_h > 0:
                screen_x = int(display_x * orig_w / display_w)
                screen_y = int(display_y * orig_h / display_h)
            else:
                screen_x = display_x
                screen_y = display_y
        
        # 加上裁剪偏移量（如果有裁剪）
        if hasattr(self, '_crop_offsets'):
            crop_top, crop_bottom, crop_left, crop_right = self._crop_offsets
            screen_x += crop_left
            screen_y += crop_top
        
        # 确保坐标在有效范围内
        screen_x = max(0, min(screen_x, orig_w))
        screen_y = max(0, min(screen_y, orig_h))
        
        self._draw_coord_marker(event.x, event.y, screen_x, screen_y)
        
        if self._click_callback:
            self._click_callback(screen_x, screen_y)
    
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
    
    DEFAULT_FPS = 30  # 默认帧率（降低以减少CPU占用）
    
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
        self._interaction_enabled = False  # 实时预览操作开关
        self._active_threads = []  # 跟踪活动的后台线程
        self._shutdown_event = threading.Event()  # 用于通知线程退出
        
        # 从设置读取帧率
        self._update_interval_ms = self._get_update_interval_from_settings()

        self._create_widgets()
        self._layout_widgets()
        
        # 绑定销毁事件，确保正确清理
        self.bind('<Destroy>', self._on_destroy)
    
    def _get_update_interval_from_settings(self) -> int:
        """从设置中读取帧率并计算更新间隔（毫秒）
        
        Returns:
            更新间隔（毫秒），0表示无限制
        """
        try:
            from ...utils.config import get_config
            config = get_config()
            fps = config.get('ui.preview_fps', self.DEFAULT_FPS)
            if fps <= 0:
                return 0  # 无限制
            return int(1000 / fps)
        except Exception:
            return int(1000 / self.DEFAULT_FPS)
    
    def refresh_settings(self) -> None:
        """刷新设置（在设置更改后调用）"""
        self._update_interval_ms = self._get_update_interval_from_settings()
        logger.info(f"预览帧率已更新: {self._update_interval_ms}ms 间隔")
    
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

        # 实时预览操作开关
        self._interaction_var = tk.BooleanVar(value=False)
        self._interaction_btn = ttk.Checkbutton(
            toolbar,
            text="🖱️ 启用操作",
            variable=self._interaction_var,
            command=self._on_interaction_toggle,
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
            'interaction_btn': self._interaction_btn,
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
        w['interaction_btn'].pack(side=tk.LEFT, padx=2)
        
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
        logger.info(f"开始启动预览 | bridge={self._bridge is not None}")

        if self._bridge is None:
            logger.warning("无法启动预览: bridge为None")
            return

        if not self._bridge.is_ready:
            logger.warning(f"无法启动预览: bridge未就绪 | state={self._bridge.state if self._bridge else 'N/A'}")
            return

        # 防止重复启动
        if self._starting or self._running:
            logger.warning(f"无法启动预览: 已在运行中 | starting={self._starting}, running={self._running}")
            return

        self._starting = True
        self._widgets['start_btn'].config(text="⏹ 停止预览", state=tk.DISABLED)
        self._widgets['status_label'].config(text="正在启动传感器...")

        # 在后台线程启动传感器，避免阻塞 GUI
        def start_sensor_async():
            logger.info("后台线程: 开始启动传感器")
            try:
                # 使用bridge的start方法启动传感器
                if hasattr(self._bridge, 'start'):
                    logger.debug("调用 bridge.start()")
                    self._bridge.start()
                    logger.info("传感器启动成功，准备调度UI更新")
                    # 使用 after 回到主线程
                    logger.debug("正在调用 self.after(0, self._on_sensor_started)...")
                    self.after(0, self._safe_on_sensor_started)
                    logger.debug("self.after(0, ...) 返回")
                else:
                    logger.error("bridge没有start方法")
                    self.after(0, lambda: self._on_sensor_failed("bridge不支持启动传感器"))
            except Exception as e:
                error_msg = str(e)
                logger.error(f"启动传感器异常: {error_msg}", exc_info=True)
                self.after(0, lambda msg=error_msg: self._on_sensor_failed(msg))

        threading.Thread(target=start_sensor_async, daemon=True).start()

    def _safe_on_sensor_started(self) -> None:
        """传感器启动成功回调（带异常捕获的安全包装）"""
        try:
            self._on_sensor_started()
        except Exception as e:
            logger.error(f"_on_sensor_started 异常: {e}", exc_info=True)
            self._on_sensor_failed(str(e))

    def _on_sensor_started(self) -> None:
        """传感器启动成功回调（在主线程执行）"""
        print("[_on_sensor_started] 开始执行")
        self._starting = False
        self._running = True
        self._frame_count = 0
        self._fps_calc_start = time.monotonic()
        print("[_on_sensor_started] 更新按钮状态")
        self._widgets['start_btn'].config(state=tk.NORMAL)
        print("[_on_sensor_started] 更新状态标签")
        self._widgets['status_label'].config(text="预览中...")
        print("[_on_sensor_started] 调度更新")
        self._schedule_update()
        print("[_on_sensor_started] 完成")

    def _on_sensor_failed(self, error_msg: str) -> None:
        """传感器启动失败回调（在主线程执行）"""
        self._starting = False
        self._running = False
        self._widgets['status_label'].config(text=f"启动失败: {error_msg}")
        self._widgets['start_btn'].config(text="▶ 开始预览", state=tk.NORMAL)
    
    def stop_preview(self) -> None:
        """停止实时预览"""
        logger.info("停止预览...")
        self._starting = False
        self._running = False
        self._shutdown_event.set()  # 通知所有后台线程退出

        # 停止传感器
        if self._bridge and hasattr(self._bridge, 'sensor') and self._bridge.sensor:
            try:
                self._bridge.sensor.stop()
            except Exception as e:
                logger.error(f"停止传感器失败: {e}")

        # 清理活动线程
        active_count = len([t for t in self._active_threads if t.is_alive()])
        if active_count > 0:
            logger.debug(f"等待 {active_count} 个后台线程结束...")
            for thread in self._active_threads[:]:
                if thread.is_alive():
                    thread.join(timeout=1.0)
            self._active_threads = [t for t in self._active_threads if t.is_alive()]
        
        # 重置处理标志
        self._processing_frame = False
        
        # 重置关闭事件，以便下次启动
        self._shutdown_event.clear()

        self._widgets['start_btn'].config(text="▶ 开始预览", state=tk.NORMAL)
        self._widgets['status_label'].config(text="预览已停止")
        
        self._widgets['fps_label'].config(text="FPS: --")
        self._widgets['latency_label'].config(text="延迟: --ms")
        
        logger.info("预览已停止")
    
    def _schedule_update(self) -> None:
        """调度下一次画面更新（使用 after 异步调度，避免阻塞 UI）"""
        if not self._running or self._shutdown_event.is_set():
            return

        # 使用保守的更新策略：每50ms更新一次（约20fps），避免Tkinter过载
        update_interval = 50  # 20fps
        
        # 只在未处理帧时才调度新帧更新
        if not self._processing_frame:
            self.after(0, self._update_frame)

        # 调度下一次更新
        self.after(update_interval, self._schedule_update)

    def _update_frame(self) -> None:
        """获取并渲染最新帧（非阻塞，只处理新帧）"""
        if not self._running or not self._bridge or self._shutdown_event.is_set():
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

                # 图像转换移到后台线程，避免阻塞 GUI
                self._process_frame_async(frame)

        except Exception as e:
            logger.debug(f"帧更新异常: {e}")

    def _process_frame_async(self, frame) -> None:
        """在后台线程处理图像转换和缩放，然后回到主线程更新 GUI"""
        # 防止并发处理（如果上一帧还在处理中，跳过当前帧）
        if self._processing_frame:
            return
        
        # 检查是否正在关闭
        if self._shutdown_event.is_set():
            return

        self._processing_frame = True
        
        # 获取canvas尺寸（需要在主线程获取）
        canvas_width = self._canvas.winfo_width()
        canvas_height = self._canvas.winfo_height()

        def process_task():
            try:
                # 检查关闭事件
                if self._shutdown_event.is_set():
                    self._processing_frame = False
                    return
                
                # 获取裁剪设置
                crop_top = self._get_crop_setting('top', 0)
                crop_bottom = self._get_crop_setting('bottom', 0)
                crop_left = self._get_crop_setting('left', 0)
                crop_right = self._get_crop_setting('right', 0)
                
                # 应用裁剪
                img = frame.image_numpy
                h, w = img.shape[:2]
                
                # 计算裁剪边界（确保不超出图像范围）
                y1 = min(crop_top, h)
                y2 = max(h - crop_bottom, y1)
                x1 = min(crop_left, w)
                x2 = max(w - crop_right, x1)
                
                if y2 > y1 and x2 > x1:
                    img = img[y1:y2, x1:x2]
                    cropped = True
                else:
                    cropped = False
                
                # BGR to RGB 转换
                rgb_image = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(rgb_image)
                
                # 在后台线程进行图像缩放（避免阻塞GUI）
                if canvas_width > 1 and canvas_height > 1:
                    img_width, img_height = pil_image.size
                    scale_w = canvas_width / img_width
                    scale_h = canvas_height / img_height
                    scale = min(scale_w, scale_h, 1.0)
                    
                    new_width = int(img_width * scale)
                    new_height = int(img_height * scale)
                    
                    if new_width > 1 and new_height > 1:
                        # 使用BILINEAR算法，比LANCZOS快很多
                        pil_image = pil_image.resize((new_width, new_height), Image.Resampling.BILINEAR)

                # 获取元数据
                # 原始屏幕分辨率（用于点击坐标映射）
                original_resolution = frame.metadata.resolution if frame.metadata else (w, h)
                # 裁剪后的分辨率
                cropped_resolution = (x2 - x1, y2 - y1) if cropped else original_resolution
                
                metadata = {
                    'timestamp': frame.metadata.timestamp if frame.metadata else 0.0,
                    'latency': frame.metadata.capture_latency_ms if frame.metadata else 0.0,
                    'resolution': cropped_resolution,
                    'original_resolution': original_resolution,
                    'crop_offsets': (crop_top, crop_bottom, crop_left, crop_right),
                }

                # 回到主线程更新 GUI - 使用线程安全的方式
                try:
                    # 检查关闭事件
                    if not self._shutdown_event.is_set():
                        # 使用 root.after 确保在主线程执行
                        root = self.winfo_toplevel()
                        root.after(0, lambda: self._update_gui_with_frame(pil_image, metadata))
                except Exception as e:
                    logger.error(f"调度GUI更新失败: {e}")
                    self._processing_frame = False
            except Exception as e:
                logger.error(f"process_task 异常: {e}")
                self._processing_frame = False

        # 创建并跟踪线程
        thread = threading.Thread(target=process_task, daemon=True)
        self._active_threads.append(thread)
        thread.start()
        
        # 清理已结束的线程
        self._active_threads = [t for t in self._active_threads if t.is_alive()]

    def _update_gui_with_frame(self, pil_image: Image.Image, metadata: dict) -> None:
        """在主线程更新 GUI（由 _process_frame_async 回调）
        
        注意：图像已经在后台线程缩放好了，这里直接显示
        """
        try:
            if not self._running or self._shutdown_event.is_set():
                return

            # 获取分辨率和裁剪信息，用于点击坐标映射
            # 优先使用 bridge 的传感器分辨率（与 ADB 操作分辨率一致）
            if self._bridge:
                sensor_resolution = self._bridge.get_sensor_resolution()
            else:
                sensor_resolution = metadata.get('original_resolution', metadata.get('resolution', (0, 0)))
            crop_offsets = metadata.get('crop_offsets', (0, 0, 0, 0))
            
            # 直接使用已经缩放好的图像显示，同时传递传感器分辨率和裁剪偏移量
            self._canvas.update_image_direct(pil_image, sensor_resolution, crop_offsets)

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
            logger.error(f"_update_gui_with_frame 异常: {e}")
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

    def _on_interaction_toggle(self) -> None:
        """实时预览操作开关切换"""
        self._interaction_enabled = self._interaction_var.get()
        state_text = "已启用" if self._interaction_enabled else "已禁用"
        self._widgets['status_label'].config(text=f"操作模式: {state_text}")
        logger.info(f"实时预览操作开关: {state_text}")

    def _on_canvas_click(self, screen_x: int, screen_y: int) -> None:
        """画布点击事件回调
        
        注意: PreviewCanvas._on_click 已经将画布坐标映射为屏幕坐标，
        所以这里的 screen_x, screen_y 已经是屏幕坐标，可以直接使用。
        
        Args:
            screen_x: 屏幕 X 坐标
            screen_y: 屏幕 Y 坐标
        """
        logger.debug(f"画布点击: 屏幕坐标({screen_x}, {screen_y})")
        
        if not self._interaction_enabled:
            # 如果未启用操作，只更新坐标显示
            self._update_control_panel_coordinate(screen_x, screen_y)
            return

        # 启用操作模式：执行点击并更新坐标
        logger.info(f"执行点击: 屏幕坐标 ({screen_x}, {screen_y})")

        # 在后台线程执行点击操作，避免阻塞 GUI
        def click_task():
            try:
                if self._bridge and hasattr(self._bridge, 'tap'):
                    self._bridge.tap(screen_x, screen_y)
                    logger.info(f"点击执行成功: ({screen_x}, {screen_y})")
            except Exception as e:
                logger.error(f"点击执行失败: {e}")

        threading.Thread(target=click_task, daemon=True).start()

        # 同时更新坐标显示
        self._update_control_panel_coordinate(screen_x, screen_y)
    
    def _on_destroy(self, event) -> None:
        """控件销毁时的清理处理"""
        logger.info("PreviewPanel 正在销毁，开始清理...")
        self._shutdown_event.set()  # 通知所有线程退出
        self._running = False
        self._starting = False
        
        # 停止传感器
        if self._bridge and hasattr(self._bridge, 'sensor') and self._bridge.sensor:
            try:
                self._bridge.sensor.stop()
            except Exception as e:
                logger.error(f"销毁时停止传感器失败: {e}")
        
        # 等待活动线程结束（最多2秒）
        for thread in self._active_threads:
            if thread.is_alive():
                thread.join(timeout=0.5)
        
        logger.info("PreviewPanel 销毁完成")
    
    def _get_crop_setting(self, edge: str, default: int = 0) -> int:
        """获取裁剪设置
        
        Args:
            edge: 边缘名称 ('top', 'bottom', 'left', 'right')
            default: 默认值
            
        Returns:
            裁剪像素数
        """
        try:
            from ...utils.config import get_config
            config = get_config()
            crop_settings = config.get('preview.crop', {})
            return crop_settings.get(edge, default)
        except Exception:
            return default
    
    def _update_control_panel_coordinate(self, x: int, y: int) -> None:
        """更新控制面板的坐标显示
        
        Args:
            x: X 坐标
            y: Y 坐标
        """
        try:
            # 通过父窗口查找控制面板
            app = self.winfo_toplevel()
            if hasattr(app, '_panels'):
                control_panel = app._panels.get('control')
                if control_panel and hasattr(control_panel, 'update_coordinate'):
                    control_panel.update_coordinate(x, y)
        except Exception as e:
            logger.debug(f"更新坐标显示失败: {e}")
