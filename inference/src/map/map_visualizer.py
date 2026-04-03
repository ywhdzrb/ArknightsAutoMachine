# -*- coding: utf-8 -*-
"""
地图可视化器

提供关卡地图和敌人位置的可视化

Author: Vision System
Version: 1.0.0
"""

import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont

from .level_analyzer import LevelData, Position, Route


class MapVisualizer:
    """
    地图可视化器

    将关卡地图和敌人位置可视化输出
    """

    # 地块颜色映射 (BGR格式)
    TILE_COLORS = {
        'tile_forbidden': (50, 50, 50),      # 深灰
        'tile_wall': (139, 125, 107),        # 浅棕
        'tile_road': (200, 200, 200),        # 浅灰
        'tile_floor': (180, 180, 180),       # 灰色
        'tile_start': (0, 255, 0),           # 绿色
        'tile_end': (0, 0, 255),             # 红色
        'tile_flyingstart': (0, 200, 0),     # 深绿
        'tile_flyingend': (0, 0, 200),       # 深蓝
        'tile_healing': (0, 255, 255),       # 黄色
        'tile_volcano': (0, 0, 139),         # 深红
        'tile_corrosion': (128, 0, 128),     # 紫色
        'tile_deepwater': (139, 0, 0),       # 深蓝
        'tile_tunnel': (107, 107, 107),      # 灰色
    }

    # 默认颜色
    DEFAULT_TILE_COLOR = (100, 100, 100)

    def __init__(self, tile_size: int = 40):
        """
        初始化可视化器

        Args:
            tile_size: 每个地块的像素大小
        """
        self.tile_size = tile_size
        self._font = None
        self._load_font()

    def _load_font(self):
        """加载中文字体"""
        font_paths = [
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/simsun.ttc",
            "C:/Windows/Fonts/msyh.ttc",
        ]

        for font_path in font_paths:
            try:
                self._font = ImageFont.truetype(font_path, 12)
                return
            except:
                continue

        self._font = ImageFont.load_default()

    def visualize_map(
        self,
        level_data: LevelData,
        enemies: Optional[List[Dict[str, Any]]] = None,
        routes: Optional[List[int]] = None,
        output_path: Optional[Path] = None
    ) -> np.ndarray:
        """
        可视化地图

        Args:
            level_data: 关卡数据
            enemies: 敌人列表（可选）
            routes: 要显示的路径索引列表（可选）
            output_path: 输出路径（可选）

        Returns:
            可视化图像
        """
        # 计算图像尺寸
        img_width = level_data.map_width * self.tile_size
        img_height = level_data.map_height * self.tile_size

        # 创建图像
        image = np.ones((img_height, img_width, 3), dtype=np.uint8) * 255

        # 绘制地块
        for row in range(level_data.map_height):
            for col in range(level_data.map_width):
                tile = level_data.get_tile_at(row, col)
                if tile:
                    tile_key = tile.get('tileKey', '')
                    color = self.TILE_COLORS.get(tile_key, self.DEFAULT_TILE_COLOR)
                else:
                    color = self.DEFAULT_TILE_COLOR

                # 绘制地块矩形
                x1 = col * self.tile_size
                y1 = row * self.tile_size
                x2 = x1 + self.tile_size
                y2 = y1 + self.tile_size

                cv2.rectangle(image, (x1, y1), (x2, y2), color, -1)
                cv2.rectangle(image, (x1, y1), (x2, y2), (0, 0, 0), 1)

        # 绘制路径
        if routes is None:
            routes = list(range(len(level_data.routes)))

        for route_idx in routes:
            if 0 <= route_idx < len(level_data.routes):
                self._draw_route(image, level_data.routes[route_idx])

        # 绘制敌人
        if enemies:
            self._draw_enemies(image, enemies)

        # 转换为PIL图像添加文字
        image = self._add_labels(image, level_data)

        # 保存
        if output_path:
            cv2.imwrite(str(output_path), image)

        return image

    def _draw_route(self, image: np.ndarray, route: Route):
        """绘制路径"""
        color = (255, 0, 0)  # 蓝色路径
        thickness = 2

        # 起点
        start = route.start_position
        x = start.col * self.tile_size + self.tile_size // 2
        y = start.row * self.tile_size + self.tile_size // 2

        # 绘制检查点连线
        for cp in route.checkpoints:
            end_x = cp.position.col * self.tile_size + self.tile_size // 2
            end_y = cp.position.row * self.tile_size + self.tile_size // 2
            cv2.line(image, (x, y), (end_x, end_y), color, thickness)
            x, y = end_x, end_y

        # 最后到终点
        end_x = route.end_position.col * self.tile_size + self.tile_size // 2
        end_y = route.end_position.row * self.tile_size + self.tile_size // 2
        cv2.line(image, (x, y), (end_x, end_y), color, thickness)

        # 绘制起点和终点标记
        cv2.circle(image,
                   (route.start_position.col * self.tile_size + self.tile_size // 2,
                    route.start_position.row * self.tile_size + self.tile_size // 2),
                   5, (0, 255, 0), -1)
        cv2.circle(image,
                   (route.end_position.col * self.tile_size + self.tile_size // 2,
                    route.end_position.row * self.tile_size + self.tile_size // 2),
                   5, (0, 0, 255), -1)

    def _draw_enemies(self, image: np.ndarray, enemies: List[Dict[str, Any]]):
        """绘制敌人位置"""
        for enemy in enemies:
            pos = enemy.get('position')
            if pos:
                x = pos.col * self.tile_size + self.tile_size // 2
                y = pos.row * self.tile_size + self.tile_size // 2

                # 绘制敌人圆圈
                cv2.circle(image, (x, y), 8, (0, 0, 255), -1)
                cv2.circle(image, (x, y), 8, (0, 0, 0), 2)

                # 绘制敌人ID（简化）
                enemy_key = enemy.get('enemy_key', '')
                if enemy_key:
                    # 提取敌人名称（简化）
                    name = enemy_key.split('_')[-1] if '_' in enemy_key else enemy_key[:4]
                    cv2.putText(image, name, (x - 15, y - 10),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255, 255, 255), 1)

    def _add_labels(self, image: np.ndarray, level_data: LevelData) -> np.ndarray:
        """添加文字标签"""
        # 转换为PIL图像
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(image_rgb)
        draw = ImageDraw.Draw(pil_image)

        # 添加坐标标签
        for row in range(level_data.map_height):
            for col in range(level_data.map_width):
                x = col * self.tile_size + 2
                y = row * self.tile_size + 2
                label = f"{row},{col}"
                draw.text((x, y), label, font=self._font, fill=(0, 0, 0))

        # 转换回OpenCV格式
        return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

    def visualize_enemy_timeline(
        self,
        level_data: LevelData,
        time_range: Tuple[float, float],
        output_path: Optional[Path] = None
    ) -> np.ndarray:
        """
        可视化敌人时间线

        Args:
            level_data: 关卡数据
            time_range: 时间区间 (start, end)
            output_path: 输出路径（可选）

        Returns:
            可视化图像
        """
        start_time, end_time = time_range

        # 创建时间线图像
        width = 800
        height = 400
        image = np.ones((height, width, 3), dtype=np.uint8) * 255

        # 绘制时间轴
        cv2.line(image, (50, height - 50), (width - 50, height - 50), (0, 0, 0), 2)

        # 时间刻度
        duration = end_time - start_time
        for i in range(11):
            x = 50 + (width - 100) * i // 10
            t = start_time + duration * i / 10
            cv2.line(image, (x, height - 50), (x, height - 45), (0, 0, 0), 1)
            cv2.putText(image, f"{t:.1f}s", (x - 20, height - 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)

        # 收集所有敌人生成事件
        y_offset = 50
        enemy_y_positions = {}

        for wave in level_data.waves:
            for spawn in wave.spawns:
                if spawn.enemy_key not in enemy_y_positions:
                    enemy_y_positions[spawn.enemy_key] = y_offset
                    y_offset += 30

                # 计算x位置
                if start_time <= spawn.spawn_time <= end_time:
                    progress = (spawn.spawn_time - start_time) / duration
                    x = 50 + int((width - 100) * progress)
                    y = enemy_y_positions[spawn.enemy_key]

                    # 绘制生成点
                    cv2.circle(image, (x, y), 5, (0, 0, 255), -1)

                    # 绘制敌人名称
                    cv2.putText(image, spawn.enemy_key, (10, y + 5),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)

        # 保存
        if output_path:
            cv2.imwrite(str(output_path), image)

        return image
