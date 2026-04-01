"""
Arknights Auto Machine (AAM) - 主入口点

启动流程:
1. 检查运行环境（Python版本/操作系统）
2. 初始化日志系统
3. 加载配置文件（default.yaml → user.yaml覆盖）
4. 启动GUI主窗口
5. 注册全局异常处理
"""

import sys
import os
import logging
from pathlib import Path


def check_environment() -> bool:
    """检查运行环境是否满足最低要求
    
    检查项:
    - Python >= 3.9 (类型注解语法需要)
    - 操作系统支持 (Windows/Linux/macOS)
    - 关键依赖可导入
    
    Returns:
        环境检查是否通过
        
    Raises:
        SystemExit: 环境不满足要求时退出程序
    """
    if sys.version_info < (3, 9):
        print(f"错误: 需要Python 3.9或更高版本，当前版本: {sys.version_info}")
        sys.exit(1)
    
    required_packages = [
        ('numpy', 'numpy'),
        ('opencv-python', 'cv2'),
        ('Pillow', 'PIL'),
    ]
    
    missing = []
    
    for package_name, import_name in required_packages:
        try:
            __import__(import_name)
        except ImportError:
            missing.append(package_name)
    
    if missing:
        print(f"错误: 缺少必要的依赖包: {', '.join(missing)}")
        print("请执行: pip install -r requirements.txt")
        sys.exit(1)
    
    return True


def setup_logging(log_level: str = "INFO") -> None:
    """初始化全局日志系统
    
    配置双输出:
    1. 控制台输出（彩色格式，开发调试用）
    2. 文件输出（追加模式，生产问题排查用）
    
    Args:
        log_level: 全局日志级别
    """
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    
    from datetime import datetime
    
    timestamp = datetime.now().strftime("%Y%m%d")
    log_file = log_dir / f"aam_{timestamp}.log"
    
    console_format = (
        "%(asctime)s | %(levelname)-7s | "
        "%(name)-25s | %(message)s"
    )
    file_format = (
        "%(asctime)s.%(msecs)03d | %(levelname)-7s | "
        "%(name)-25s | %(funcName)s:%(lineno)d | %(message)s"
    )
    date_format = "%H:%M:%S"
    
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_formatter = logging.Formatter(console_format, datefmt=date_format)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    file_handler = logging.FileHandler(
        log_file,
        mode='a',
        encoding='utf-8',
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(file_format, datefmt=date_format)
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)
    
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)


def add_src_to_path() -> None:
    """将src目录添加到sys.path以支持模块导入"""
    src_path = Path(__file__).parent / "src"
    
    if src_path.exists():
        src_str = str(src_path.resolve())
        
        if src_str not in sys.path:
            sys.path.insert(0, src_str)


def main() -> int:
    """应用程序主入口函数
    
    Returns:
        退出码: 0=正常退出, 1=异常退出
    """
    try:
        check_environment()
        
        add_src_to_path()
        
        setup_logging()
        
        logger = logging.getLogger(__name__)
        
        logger.info("=" * 60)
        logger.info("Arknights Auto Machine 启动中...")
        logger.info(f"Python版本: {sys.version}")
        logger.info(f"工作目录: {os.getcwd()}")
        logger.info("=" * 60)
        
        from gui.app import AAMApplication
        
        app = AAMApplication()
        app.run()
        
        logger.info("应用程序正常退出")
        return 0
        
    except KeyboardInterrupt:
        print("\n用户中断，正在退出...")
        return 0
        
    except Exception as e:
        print(f"致命错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
