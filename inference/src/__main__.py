# -*- coding: utf-8 -*-
"""
模块入口点

允许通过 python -m src 运行CLI
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from cli import main

if __name__ == '__main__':
    sys.exit(main())
