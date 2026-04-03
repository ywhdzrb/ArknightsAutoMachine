# l1_perception - L1 视觉层实现

## 目录说明

本目录包含 GPU 加速的图像处理流水线，包括目标检测和 OCR 引擎。

## 文件说明

### cuda_kernels/
CUDA 核函数目录:
- **color_convert.cu**: RGB↔HSV↔灰度转换
- **pyramid_down.cu**: 多分辨率金字塔生成

### ocr_engine.cpp
**OCR 引擎**

基于 PaddleOCR 的本地推理:
- 支持中英文混合识别
- 自定义字典（明日方舟术语）
- 性能: 单帧 < 30ms (GTX 4060)

### yolo_detector.cpp
**目标检测器**

YOLOv8-nano 本地运行:
- ONNX Runtime DirectML 后端
- INT8 量化: 22MB → 6MB
- 识别: 干员、敌人、地形、UI 元素

### region_of_interest.cpp
**ROI 裁剪优化**

智能区域裁剪:
- 仅处理关键区域（费用栏、干员栏、地图中央）
- 减少 70% 计算量

## 处理流水线

```
输入帧 (1920x1080)
    │
    ▼
┌─────────────┐
│ ROI 裁剪     │ ──► 仅处理关键区域
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 色彩空间转换  │ ──► RGB → HSV (GPU)
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌─────────────┐
│ 目标检测     │ ──► │ YOLO 推理   │
│ (YOLO)      │     │ (ONNX)      │
└──────┬──────┘     └─────────────┘
       │
       ▼
┌─────────────┐     ┌─────────────┐
│ OCR 识别     │ ──► │ PaddleOCR   │
│             │     │ (C++推理)   │
└──────┬──────┘     └─────────────┘
       │
       ▼
输出: DetectionResult + OCRResult
```

## GPU 加速

### CUDA 模块
```cpp
namespace aam::l1::cuda {
    cv::Mat convertColor(const cv::Mat& src, ColorCode code);
    std::vector<cv::Mat> buildPyramid(const cv::Mat& src, int levels);
}
```

### 多后端支持
| 后端 | 平台 | 性能 |
|---|---|---|
| CUDA | NVIDIA | 最优 |
| DirectML | Windows | 良好 |
| OpenCL | 通用 | 中等 |
| CPU | 所有 | 保底 |

## 模型管理

### 模型文件
```
inference/models/checkpoints/
├── yolov8n_arknights.onnx      # 目标检测
├── yolov8n_arknights_int8.onnx # 量化版
├── paddleocr_det.onnx          # OCR 检测
├── paddleocr_rec.onnx          # OCR 识别
└── ppocr_keys_v1.txt           # 字典文件
```

### 热更新
```cpp
class ModelManager {
    bool loadModel(const std::string& path);
    bool reloadModel();  // 运行时更新
};
```

## 性能基准

| 操作 | 时间 (GTX 4060) | 时间 (CPU) |
|---|---|---|
| ROI 裁剪 | 0.1ms | 0.5ms |
| 色彩转换 | 0.2ms | 2ms |
| YOLO 推理 | 8ms | 50ms |
| OCR 识别 | 20ms | 150ms |
| **总计** | **~30ms** | **~200ms** |

## 相关目录

- [include/aam/l1/](../../include/aam/l1/): 接口定义
- [inference/models/](../../../inference/models/): 模型文件
