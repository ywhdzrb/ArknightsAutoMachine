# -*- coding: utf-8 -*-
"""
明日方舟数据模块

提供游戏数据的同步、查询和管理功能

Author: Data System
Version: 1.0.0
"""

from .providers import DataManager, GitHubDataProvider, PRTSDataProvider
from .providers.data_manager import ManagerConfig, CacheConfig
from .providers.github_provider import SyncConfig
from .providers.prts_provider import PRTSConfig
from .models import (
    Operator, OperatorSkill, OperatorTalent, OperatorPhase,
    Stage, StageDrop, StageCondition,
    Item, ItemType,
    Enemy, EnemyAbility,
    ArkDataModel, DataSource, DataVersion
)

__version__ = "1.0.0"

__all__ = [
    # 数据管理器
    'DataManager',
    'ManagerConfig',
    'CacheConfig',
    # 数据提供者
    'GitHubDataProvider',
    'SyncConfig',
    'PRTSDataProvider',
    'PRTSConfig',
    # 数据模型
    'Operator',
    'OperatorSkill',
    'OperatorTalent',
    'OperatorPhase',
    'Stage',
    'StageDrop',
    'StageCondition',
    'Item',
    'ItemType',
    'Enemy',
    'EnemyAbility',
    'ArkDataModel',
    'DataSource',
    'DataVersion',
]
