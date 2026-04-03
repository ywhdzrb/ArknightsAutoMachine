# cuda_kernels - CUDA 核函数

## 目录说明

本目录包含 CUDA GPU 加速的图像处理核函数。

## 文件说明

### color_convert.cu
色彩空间转换:
- RGB ↔ HSV
- RGB ↔ 灰度
- 批量处理

### pyramid_down.cu
多分辨率金字塔:
- 高斯金字塔生成
- 快速降采样

## 编译

```bash
# 使用 nvcc 编译
nvcc -c color_convert.cu -o color_convert.o
nvcc -c pyramid_down.cu -o pyramid_down.o

# 链接到主项目
```

## 相关目录

- [core/src/l1_perception/](../): L1 视觉层
