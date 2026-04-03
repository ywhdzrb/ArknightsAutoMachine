# models - AI 模型

## 目录说明

本目录包含 AI 模型的定义、训练和评估代码。

## 子目录

### checkpoints/
本地模型权重:
- YOLO 检测模型
- OCR 识别模型
- （使用 git-lfs 管理）

### training/
训练脚本:
- YOLO 微调
- LLM 知识蒸馏

### eval/
模型评估:
- 精度测试
- 性能基准

## 相关目录

- [inference/services/](../services/): 模型使用
- [core/src/l1_perception/](../../core/src/l1_perception/): C++ 推理
