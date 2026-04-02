"""
高性能屏幕捕获模块

提供多种截图方式，按性能排序：
1. Windows Graphics Capture (WGC) - Windows 10 1903+，GPU 加速，最低延迟
2. DXGI Desktop Duplication - 需要全屏/独占模式，高性能
3. BitBlt - 传统方式，兼容性最好
4. ADB screencap - 适用于物理设备

使用示例:
    from common.capture import WindowCapture, CaptureMethod

    # 自动选择最佳方式
    capture = WindowCapture("MuMu模拟器12", method=CaptureMethod.AUTO)

    # 获取截图
    frame = capture.capture()
    if frame:
        cv2.imshow("Capture", frame.image_numpy)
"""

from .capture import (
    WindowCapture,
    CaptureMethod,
    CaptureFrame,
    CaptureError,
    WindowNotFoundError,
    CaptureMethodNotAvailable,
)

__all__ = [
    'WindowCapture',
    'CaptureMethod',
    'CaptureFrame',
    'CaptureError',
    'WindowNotFoundError',
    'CaptureMethodNotAvailable',
]
