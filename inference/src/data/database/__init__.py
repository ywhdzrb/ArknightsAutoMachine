# -*- coding: utf-8 -*-
"""
结构化数据库模块

提供完全结构化的SQLite数据库，支持复杂查询

Author: Data System
Version: 1.0.0
"""

from .schema import DatabaseSchema
from .manager import StructuredDatabaseManager

__all__ = ['DatabaseSchema', 'StructuredDatabaseManager']
