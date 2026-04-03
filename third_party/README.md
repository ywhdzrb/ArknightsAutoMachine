# third_party - 外部依赖

## 目录说明

本目录包含 AAM 项目的外部依赖，通过子模块或下载方式管理。

## 目录结构

```
third_party/
├── vcpkg/                 # C++ 包管理
├── maafw/                 # MaaFramework 适配层
└── onnxruntime/           # ONNX Runtime 推理引擎
```

## vcpkg

### 说明
C++ 依赖包管理器:

```bash
# 初始化 vcpkg
./third_party/vcpkg/bootstrap-vcpkg.sh

# 安装依赖
./third_party/vcpkg/vcpkg install

# 导出依赖清单
./third_party/vcpkg/vcpkg export --raw
```

### 主要依赖
```json
{
  "dependencies": [
    "opencv4[contrib,cuda]",
    "grpc",
    "protobuf",
    "boost-interprocess",
    "boost-asio",
    "spdlog",
    "gtest",
    "benchmark"
  ]
}
```

## maafw

### 说明
MaaFramework 适配层:

```
maafw/
├── include/               # 头文件
├── lib/                   # 库文件
└── adapter.cpp            # 适配实现
```

### 用途
- 复用 Maa 的图像识别能力
- 作为可选捕获后端

## onnxruntime

### 说明
ONNX Runtime 推理引擎:

```
onnxruntime/
├── include/               # C++ API 头文件
├── lib/                   # 库文件
└── bin/                   # 可执行文件
```

### 用途
- YOLO 目标检测推理
- OCR 模型推理
- 支持 CUDA/DirectML/OpenCL

## 依赖管理策略

### 版本锁定
- vcpkg: `vcpkg.json` + `vcpkg-configuration.json`
- Python: `poetry.lock`
- Git 子模块: 锁定到特定 commit

### 更新流程
```bash
# 1. 更新 vcpkg 基线
vcpkg x-update-baseline

# 2. 测试构建
cmake --build build

# 3. 运行测试
ctest --output-on-failure

# 4. 提交更新
git add vcpkg-configuration.json
git commit -m "deps: update vcpkg baseline"
```

## 许可证合规

### 扫描
```bash
# 使用 FOSSA 扫描
fossa analyze

# 生成报告
fossa report
```

### 许可证清单
| 依赖 | 许可证 | 兼容性 |
|---|---|---|
| OpenCV | Apache-2.0 | ✅ |
| gRPC | Apache-2.0 | ✅ |
| Boost | BSL-1.0 | ✅ |
| spdlog | MIT | ✅ |
| GTest | BSD-3 | ✅ |

## 相关目录

- [core/third_party/](../core/third_party/): 核心模块子模块
- [cmake/](../cmake/): CMake 查找模块
