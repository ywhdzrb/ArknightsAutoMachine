# -*- coding: utf-8 -*-
"""
关卡分析器

解析关卡数据，提供地图信息、敌人波次和路径模拟

Author: Vision System
Version: 1.0.0
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class TileType(Enum):
    """地块类型"""
    FORBIDDEN = "tile_forbidden"    # 禁用地块
    WALL = "tile_wall"               # 高台/墙壁
    ROAD = "tile_road"               # 可部署近战位
    FLOOR = "tile_floor"             # 地面
    START = "tile_start"             # 敌人出生点
    END = "tile_end"                 # 敌人终点
    FLYING_START = "tile_flyingstart"  # 飞行敌人出生点
    FLYING_END = "tile_flyingend"      # 飞行敌人终点
    HEALING = "tile_healing"         # 治疗地块
    VOLCANO = "tile_volcano"         # 火山地块
    CORROSION = "tile_corrosion"     # 腐蚀地块
    DEEP_WATER = "tile_deepwater"    # 深水地块
    TUNNEL = "tile_tunnel"           # 隧道


class MotionMode(Enum):
    """移动模式"""
    WALK = "WALK"           # 步行
    FLY = "FLY"             # 飞行
    NUM = "E_NUM"           # 数字/其他


@dataclass
class Position:
    """位置坐标"""
    row: int
    col: int

    def to_tuple(self) -> Tuple[int, int]:
        return (self.row, self.col)


@dataclass
class Checkpoint:
    """路径检查点"""
    type: str               # 类型: MOVE, WAIT, etc.
    time: float            # 到达时间
    position: Position     # 位置
    reach_offset: Tuple[float, float] = (0.0, 0.0)
    reach_distance: float = 0.0


@dataclass
class Route:
    """敌人行进路径"""
    route_index: int
    motion_mode: MotionMode
    start_position: Position
    end_position: Position
    checkpoints: List[Checkpoint] = field(default_factory=list)
    allow_diagonal_move: bool = False

    def get_path_length(self) -> float:
        """计算路径长度（格数）"""
        if not self.checkpoints:
            # 直接距离
            return abs(self.end_position.row - self.start_position.row) + \
                   abs(self.end_position.col - self.start_position.col)

        length = 0.0
        prev_pos = self.start_position

        for cp in self.checkpoints:
            length += abs(cp.position.row - prev_pos.row) + \
                     abs(cp.position.col - prev_pos.col)
            prev_pos = cp.position

        length += abs(self.end_position.row - prev_pos.row) + \
                  abs(self.end_position.col - prev_pos.col)

        return length


@dataclass
class EnemySpawn:
    """敌人生成信息"""
    enemy_key: str          # 敌人ID
    count: int             # 数量
    spawn_time: float      # 生成时间（秒）
    route_index: int       # 路径索引
    interval: float = 1.0  # 生成间隔


@dataclass
class Wave:
    """波次数据"""
    wave_index: int
    pre_delay: float       # 前置延迟
    post_delay: float      # 后置延迟
    spawns: List[EnemySpawn] = field(default_factory=list)


@dataclass
class LevelOptions:
    """关卡选项"""
    character_limit: int = 8           # 干员数量限制
    max_life_point: int = 10           # 最大生命值
    initial_cost: int = 10             # 初始费用
    max_cost: int = 99                 # 最大费用
    cost_increase_time: float = 1.0    # 费用增长间隔
    move_multiplier: float = 1.0       # 移动速度倍率


@dataclass
class LevelData:
    """关卡数据"""
    # 基本信息
    level_id: str
    level_path: Path

    # 选项
    options: LevelOptions

    # 地图数据
    map_width: int
    map_height: int
    map_grid: List[List[int]]       # 地图网格索引
    tiles: List[Dict[str, Any]]     # 地块定义

    # 路径和波次
    routes: List[Route]
    waves: List[Wave]

    # 原始数据
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def get_tile_at(self, row: int, col: int) -> Optional[Dict[str, Any]]:
        """获取指定位置的地块"""
        if 0 <= row < self.map_height and 0 <= col < self.map_width:
            tile_index = self.map_grid[row][col]
            if 0 <= tile_index < len(self.tiles):
                return self.tiles[tile_index]
        return None

    def get_start_positions(self) -> List[Position]:
        """获取所有出生点位置"""
        starts = []
        for r in range(self.map_height):
            for c in range(self.map_width):
                tile = self.get_tile_at(r, c)
                if tile and 'start' in tile.get('tileKey', ''):
                    starts.append(Position(r, c))
        return starts

    def get_end_positions(self) -> List[Position]:
        """获取所有终点位置"""
        ends = []
        for r in range(self.map_height):
            for c in range(self.map_width):
                tile = self.get_tile_at(r, c)
                if tile and 'end' in tile.get('tileKey', ''):
                    ends.append(Position(r, c))
        return ends


class LevelAnalyzer:
    """
    关卡分析器

    解析关卡JSON数据，提供地图和敌人信息
    """

    def __init__(self, levels_base_path: Optional[Path] = None):
        """
        初始化关卡分析器

        Args:
            levels_base_path: 关卡数据基础路径
        """
        if levels_base_path is None:
            self.levels_base_path = Path(__file__).parent.parent.parent / \
                                   'ArknightsGameData' / 'zh_CN' / 'gamedata' / 'levels'
        else:
            self.levels_base_path = Path(levels_base_path)

        self._current_level: Optional[LevelData] = None
        self._enemy_data: Optional[Dict[str, Any]] = None

    def load_level(self, level_path: str) -> Optional[LevelData]:
        """
        加载关卡数据

        Args:
            level_path: 关卡路径（如 "obt/main/level_main_01-07"）

        Returns:
            关卡数据或None
        """
        try:
            json_path = self.levels_base_path / f"{level_path}.json"

            if not json_path.exists():
                logger.error(f"关卡文件不存在: {json_path}")
                return None

            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self._current_level = self._parse_level_data(level_path, json_path, data)
            logger.info(f"成功加载关卡: {level_path}")
            return self._current_level

        except Exception as e:
            logger.error(f"加载关卡失败: {e}")
            return None

    def _parse_level_data(self, level_id: str, level_path: Path, data: Dict[str, Any]) -> LevelData:
        """解析关卡数据"""
        # 解析选项
        options_data = data.get('options', {})
        options = LevelOptions(
            character_limit=options_data.get('characterLimit', 8),
            max_life_point=options_data.get('maxLifePoint', 10),
            initial_cost=options_data.get('initialCost', 10),
            max_cost=options_data.get('maxCost', 99),
            cost_increase_time=options_data.get('costIncreaseTime', 1.0),
            move_multiplier=options_data.get('moveMultiplier', 1.0)
        )

        # 解析地图数据
        map_data = data.get('mapData', {})
        map_grid = map_data.get('map', [])
        tiles = map_data.get('tiles', [])

        map_height = len(map_grid) if map_grid else 0
        map_width = len(map_grid[0]) if map_grid and map_grid[0] else 0

        # 解析路径
        routes = self._parse_routes(data.get('routes', []))

        # 解析波次
        waves = self._parse_waves(data.get('waves', []))

        return LevelData(
            level_id=level_id,
            level_path=level_path,
            options=options,
            map_width=map_width,
            map_height=map_height,
            map_grid=map_grid,
            tiles=tiles,
            routes=routes,
            waves=waves,
            raw_data=data
        )

    def _parse_routes(self, routes_data: List[Dict]) -> List[Route]:
        """解析路径数据"""
        routes = []

        for idx, route_data in enumerate(routes_data):
            start_pos = Position(
                row=route_data.get('startPosition', {}).get('row', 0),
                col=route_data.get('startPosition', {}).get('col', 0)
            )
            end_pos = Position(
                row=route_data.get('endPosition', {}).get('row', 0),
                col=route_data.get('endPosition', {}).get('col', 0)
            )

            # 解析检查点
            checkpoints = []
            for cp_data in route_data.get('checkpoints', []) or []:
                cp = Checkpoint(
                    type=cp_data.get('type', 'MOVE'),
                    time=cp_data.get('time', 0.0),
                    position=Position(
                        row=cp_data.get('position', {}).get('row', 0),
                        col=cp_data.get('position', {}).get('col', 0)
                    ),
                    reach_offset=(
                        cp_data.get('reachOffset', {}).get('x', 0.0),
                        cp_data.get('reachOffset', {}).get('y', 0.0)
                    ),
                    reach_distance=cp_data.get('reachDistance', 0.0)
                )
                checkpoints.append(cp)

            route = Route(
                route_index=idx,
                motion_mode=MotionMode(route_data.get('motionMode', 'WALK')),
                start_position=start_pos,
                end_position=end_pos,
                checkpoints=checkpoints,
                allow_diagonal_move=route_data.get('allowDiagonalMove', False)
            )
            routes.append(route)

        return routes

    def _parse_waves(self, waves_data: List[Dict]) -> List[Wave]:
        """解析波次数据"""
        waves = []
        current_time = 0.0

        for wave_idx, wave_data in enumerate(waves_data):
            wave_pre_delay = wave_data.get('preDelay', 0.0)
            current_time += wave_pre_delay

            spawns = []
            fragments = wave_data.get('fragments', [])

            for fragment in fragments:
                fragment_pre_delay = fragment.get('preDelay', 0.0)
                fragment_time = current_time + fragment_pre_delay

                for action in fragment.get('actions', []):
                    if action.get('actionType') == 'SPAWN':
                        spawn = EnemySpawn(
                            enemy_key=action.get('key', ''),
                            count=action.get('count', 1),
                            spawn_time=fragment_time + action.get('preDelay', 0.0),
                            route_index=action.get('routeIndex', 0),
                            interval=action.get('interval', 1.0)
                        )
                        spawns.append(spawn)

                current_time = fragment_time

            wave = Wave(
                wave_index=wave_idx,
                pre_delay=wave_data.get('preDelay', 0.0),
                post_delay=wave_data.get('postDelay', 0.0),
                spawns=spawns
            )
            waves.append(wave)

        return waves

    def get_enemies_in_time_range(
        self,
        start_time: float,
        end_time: float
    ) -> List[Dict[str, Any]]:
        """
        获取时间区间内的敌人

        Args:
            start_time: 开始时间（秒）
            end_time: 结束时间（秒）

        Returns:
            敌人列表，包含位置信息
        """
        if not self._current_level:
            return []

        enemies = []

        for wave in self._current_level.waves:
            for spawn in wave.spawns:
                # 检查生成时间是否在区间内
                if start_time <= spawn.spawn_time <= end_time:
                    # 获取路径
                    route = None
                    if 0 <= spawn.route_index < len(self._current_level.routes):
                        route = self._current_level.routes[spawn.route_index]

                    for i in range(spawn.count):
                        actual_spawn_time = spawn.spawn_time + i * spawn.interval
                        if start_time <= actual_spawn_time <= end_time:
                            enemy_info = {
                                'enemy_key': spawn.enemy_key,
                                'spawn_time': actual_spawn_time,
                                'route_index': spawn.route_index,
                                'position': None,
                                'progress': 0.0
                            }

                            # 如果有路径，计算当前位置
                            if route:
                                position, progress = self._calculate_position_on_route(
                                    route, actual_spawn_time, start_time, end_time
                                )
                                enemy_info['position'] = position
                                enemy_info['progress'] = progress

                            enemies.append(enemy_info)

        return enemies

    def _calculate_position_on_route(
        self,
        route: Route,
        spawn_time: float,
        current_start: float,
        current_end: float
    ) -> Tuple[Optional[Position], float]:
        """
        计算敌人在路径上的位置

        Args:
            route: 路径
            spawn_time: 生成时间
            current_start: 当前时间区间开始
            current_end: 当前时间区间结束

        Returns:
            (位置, 进度0-1)
        """
        # 简化的位置计算（假设移动速度为1格/秒）
        move_speed = 1.0 * self._current_level.options.move_multiplier

        # 计算已经行进的时间
        elapsed = current_end - spawn_time
        if elapsed < 0:
            return (None, 0.0)

        # 计算路径长度
        path_length = route.get_path_length()
        if path_length <= 0:
            return (route.start_position, 0.0)

        # 计算进度
        distance_traveled = elapsed * move_speed
        progress = min(distance_traveled / path_length, 1.0)

        # 计算当前位置（简化版：线性插值）
        if not route.checkpoints:
            # 直接插值
            row = route.start_position.row + \
                  (route.end_position.row - route.start_position.row) * progress
            col = route.start_position.col + \
                  (route.end_position.col - route.start_position.col) * progress
            return (Position(int(row), int(col)), progress)

        # 根据检查点计算位置
        total_length = 0.0
        prev_pos = route.start_position
        target_distance = path_length * progress

        for cp in route.checkpoints:
            segment_length = abs(cp.position.row - prev_pos.row) + \
                            abs(cp.position.col - prev_pos.col)

            if total_length + segment_length >= target_distance:
                # 在这个段内
                segment_progress = (target_distance - total_length) / segment_length if segment_length > 0 else 0
                row = prev_pos.row + (cp.position.row - prev_pos.row) * segment_progress
                col = prev_pos.col + (cp.position.col - prev_pos.col) * segment_progress
                return (Position(int(row), int(col)), progress)

            total_length += segment_length
            prev_pos = cp.position

        # 在最后一段
        segment_length = abs(route.end_position.row - prev_pos.row) + \
                        abs(route.end_position.col - prev_pos.col)
        remaining = target_distance - total_length
        segment_progress = remaining / segment_length if segment_length > 0 else 0
        row = prev_pos.row + (route.end_position.row - prev_pos.row) * segment_progress
        col = prev_pos.col + (route.end_position.col - prev_pos.col) * segment_progress

        return (Position(int(row), int(col)), progress)

    def get_level_summary(self) -> Dict[str, Any]:
        """获取关卡摘要信息"""
        if not self._current_level:
            return {}

        level = self._current_level

        # 统计敌人
        enemy_counts = {}
        for wave in level.waves:
            for spawn in wave.spawns:
                enemy_counts[spawn.enemy_key] = enemy_counts.get(spawn.enemy_key, 0) + spawn.count

        return {
            'level_id': level.level_id,
            'map_size': f"{level.map_width}x{level.map_height}",
            'character_limit': level.options.character_limit,
            'max_life_point': level.options.max_life_point,
            'initial_cost': level.options.initial_cost,
            'routes_count': len(level.routes),
            'waves_count': len(level.waves),
            'enemy_types': list(enemy_counts.keys()),
            'total_enemies': sum(enemy_counts.values()),
            'start_positions': [p.to_tuple() for p in level.get_start_positions()],
            'end_positions': [p.to_tuple() for p in level.get_end_positions()],
        }
