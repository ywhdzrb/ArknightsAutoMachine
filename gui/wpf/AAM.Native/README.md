# AAM.Native - C++/CLI 桥接

## 目录说明

本目录包含 WPF 与 C++ 核心之间的 C++/CLI 桥接层。

## 目录结构

```
AAM.Native/
├── include/            # 头文件
└── src/                # 实现
    ├── cpp_cli_bridge.cpp
    └── frame_pusher.cpp
```

## 职责

- 托管/非托管边界处理
- 类型转换
- 零拷贝帧传递

## 相关目录

- [AAM.WPF/](../AAM.WPF/): C# 主项目
