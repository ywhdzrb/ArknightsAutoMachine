"""
启动 GUI
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import QApplication
from gui.qt.src import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Arknights Auto Machine")
    app.setApplicationVersion("0.1.0")
    
    window = MainWindow()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
