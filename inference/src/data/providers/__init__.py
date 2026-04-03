# -*- coding: utf-8 -*-
"""
数据提供者模块

包含各种数据源的具体实现
"""

from .github_provider import GitHubDataProvider
from .prts_provider import PRTSDataProvider
from .data_manager import DataManager

__all__ = [
    'GitHubDataProvider',
    'PRTSDataProvider',
    'DataManager',
]
