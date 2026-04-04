# -*- coding: utf-8 -*-
"""
Arknights Auto Machine (AAM) - scrcpy 客户端（重导出）

Copyright (C) 2026 AAM Contributors

此文件仅为兼容性重导出，实际实现在 bridge/python/aam_bridge/ 中。
新代码应直接从 bridge.python.aam_bridge 导入。
"""

# 从 bridge 模块重导出
from bridge.python.aam_bridge import ScrcpyClient, ScrcpyConfig

__all__ = ['ScrcpyClient', 'ScrcpyConfig']