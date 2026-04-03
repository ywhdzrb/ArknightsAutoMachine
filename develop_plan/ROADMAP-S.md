**AAM 版本交付物与测试规范（AAM Deliverables & Testing Specification）**

本文档作为《AAM 版本化开发路线图》的补充，定义每个版本的**可交付制品**、**验证方法**与**质量门禁**。

---

## v0.1.0-alpha：契约冻结版

### Deliverables（交付物）
| 类别 | 文件/目录 | 描述 | 格式规范 |
|------|-----------|------|----------|
| **接口契约** | `proto/**/*.proto` | 14 个 Protocol Buffer 定义文件 | 遵循 Google API Design Guide，包名 `aam.v1` |
| **生成代码** | `build/generated/cpp/` | C++ 头文件与源文件 | `protoc` 生成，零警告 |
| **生成代码** | `build/generated/py/` | Python 模块 | `grpcio-tools` 生成 |
| **构建脚本** | `CMakeLists.txt` | 根构建配置 | 支持 `cmake --preset default` |
| **编译器配置** | `cmake/compiler_flags.cmake` | 平台特定标志 | 包含 Windows/Linux/macOS 三段逻辑 |
| **代码风格** | `.clang-format` | LLVM 风格，4 空格缩进 | 行宽 100，指针左对齐 |
| **静态检查** | `.clang-tidy` | 检查规则集 | 启用 `cppcoreguidelines-*`, `modernize-*` |
| **CI 配置** | `.github/workflows/ci.yml` | 三平台构建矩阵 | 矩阵：{Win, Linux, macOS} × {Debug, Release} |
| **CI 配置** | `.github/workflows/codeql.yml` | 安全分析 | CodeQL C++ 查询集 |
| **生成工具** | `scripts/codegen/protobuf_gen.py` | 自动化生成脚本 | Python 3.10+，依赖 `jinja2` |

### Test Strategy（测试策略）
- **契约兼容性测试**：使用 Buf CLI 执行 `buf breaking --against '.git#branch=main'`，检测 proto 文件 Breaking Change
- **生成代码编译测试**：验证生成的 C++ 代码可通过 MSVC/GCC/Clang 编译，零警告（`-Werror` 视为错误）
- **静态安全检查**：CodeQL 扫描 Critical/High 级别漏洞

### Acceptance Criteria（验收标准）
- [ ] Buf Breaking Change 检测通过（零不兼容变更）
- [ ] 三平台编译成功（Artifacts 上传到 GitHub Actions 存储）
- [ ] CodeQL 扫描零 Critical/High 漏洞
- [ ] `.proto` 文件变更需通过 GitHub PR Review（双 Reviewer 批准）

### Sign-off Checklist（签核清单）
- [ ] 架构师确认接口设计满足 L0-L5 通信需求
- [ ] 安全审核确认无硬编码密钥或敏感信息泄露
- [ ] 版本 Tag `v0.1.0-alpha` 已打，Branch Protection Rule 已启用

---

## v0.2.0-alpha：感知硬化版

### Deliverables
| 类别 | 文件/目录 | 描述 |
|------|-----------|------|
| **L0 接口** | `include/aam/l0/capture_backend.hpp` | `ICaptureBackend` 纯虚接口 |
| **L0 接口** | `include/aam/l0/frame_buffer.hpp` | `LockFreeFrameBuffer<T>` 模板类 |
| **L0 实现** | `core/src/l0_sensing/shm_transport.cpp` | Boost.Interprocess 共享内存传输 |
| **L0 实现** | `core/src/l0_sensing/adb_capture.cpp` | ADB H264 管道捕获 |
| **L0 实现** | `core/src/l0_sensing/maa_adapter.cpp` | MaaFramework 桥接适配器 |
| **L0 实现** | `core/src/l0_sensing/win32_window_capture.cpp` | Win32 API 后备捕获 |
| **基础设施** | `core/src/common/timer.cpp` | 高精度计时器（纳秒级） |
| **基础设施** | `core/src/common/memory_pool.cpp` | 定长内存池（预分配 1GB） |
| **基础设施** | `core/src/common/logger.cpp` | spdlog 异步日志封装 |
| **单元测试** | `core/src/l0_sensing/tests/test_frame_sync.cpp` | 帧同步单元测试 |
| **基准测试** | `core/src/l0_sensing/tests/test_shm_throughput.cpp` | 共享内存吞吐量测试 |
| **配置文件** | `configs/ama/capture.yaml` | L0 配置模板 |

### Test Strategy
- **帧同步测试**：连续捕获 1000 帧，验证时间戳单调递增，无序列号跳变
- **内存泄漏测试**：Valgrind Massif 工具监控，运行 10 分钟，峰值内存 < 150MB，无 definitely lost 块
- **延迟直方图测试**：使用 `HighResolutionTimer` 测量 `adb shell screenrecord` 到 C++ 内存的端到端延迟，记录 P50/P99/P99.9
- **压力测试**：72 小时连续运行（模拟长时间挂机），监控内存增长曲线（斜率应接近 0）

### Acceptance Criteria
- [ ] **功能**：`AdbCaptureBackend` 可稳定捕获 1920x1080@60fps H264 流
- [ ] **延迟**：P99 延迟 < 20ms（从屏幕渲染到 `FrameBuffer` 可用）
- [ ] **内存**：Valgrind 报告 `definitely lost: 0 bytes`，`indirectly lost: 0 bytes`
- [ ] **并发**：`LockFreeFrameBuffer` 支持单生产者（L0）单消费者（L1）无锁访问，无数据竞争（ThreadSanitizer 验证）
- [ ] **兼容性**：Windows 下支持 MediaFoundation 硬解码（如可用），Linux 下支持 VAAPI

### Sign-off Checklist
- [ ] 性能测试报告（包含延迟直方图 CSV 文件）
- [ ] 内存分析报告（Valgrind XML 输出）
- [ ] 跨平台构建验证（Windows `.lib`，Linux `.a`，macOS `.dylib`）

---

## v0.3.0-alpha：空间映射版

### Deliverables
| 类别 | 文件/目录 | 描述 |
|------|-----------|------|
| **L2 接口** | `include/aam/l2/coordinate_transform.hpp` | 坐标转换器 |
| **L2 接口** | `include/aam/l2/human_simulator.hpp` | 拟人轨迹生成器 |
| **L2 接口** | `include/aam/l2/action_executor.hpp` | 操作执行器接口 |
| **L2 实现** | `core/src/l2_motor/coordinate_transform.cpp` | 4 点标定法实现 |
| **L2 实现** | `core/src/l2_motor/trajectory_generator.cpp` | 贝塞尔曲线轨迹 |
| **L2 实现** | `core/src/l2_motor/input_adapters/adb_input.cpp` | ADB 输入适配 |
| **L2 实现** | `core/src/l2_motor/input_adapters/win32_postmessage.cpp` | Win32 后台输入 |
| **L2 实现** | `core/src/l2_motor/feedback_loop.cpp` | 操作确认闭环 |
| **映射数据** | `core/src/l2_motor/resolvers/1920x1080.cpp` | 1080p 映射表 |
| **映射数据** | `core/src/l2_motor/resolvers/2560x1440.cpp` | 2K 映射表 |
| **配置数据** | `configs/ama/input_profiles/bluestacks.yaml` | 蓝叠配置 |
| **配置数据** | `configs/ama/input_profiles/rog_phone_8.yaml` | ROG Phone 配置 |

### Test Strategy
- **精度测试**：在 1920x1080 分辨率下，输入逻辑坐标 (0,0) 到 (8,4)（9x5 网格所有点），测量物理坐标输出与实际屏幕像素误差
- **拟人性统计测试**：生成 1000 条贝塞尔曲线，统计操作间隔分布，执行 Kolmogorov-Smirnov 检验是否符合正态分布 N(80ms, 15ms)
- **反馈闭环测试**：执行 1000 次点击操作，每次点击后 200ms 截图比对，计算成功率（允许 ADB 延迟导致的误判 < 0.2%）
- **多分辨率适配测试**：在 1080p、2K、4K 分辨率下分别执行坐标转换，验证误差均 < 2px

### Acceptance Criteria
- [ ] **精度**：逻辑坐标到物理坐标转换误差 < 2px（1080p 下），< 3px（2K/4K 下）
- [ ] **拟人性**：操作间隔 KS 检验 p-value > 0.05（符合人类行为分布）
- [ ] **可靠性**：反馈闭环确认成功率 ≥ 99.8%
- [ ] **兼容性**：支持 ADB 与 Win32 两种输入后端，可运行时切换

### Sign-off Checklist
- [ ] 坐标精度测试报告（包含 9x5 网格误差热力图）
- [ ] 行为统计测试报告（包含直方图与 KS 检验结果）
- [ ] 至少 2 种输入设备配置文件验证通过（蓝叠 + 真机）

---

## v0.4.0-alpha：记忆架构版

### Deliverables
| 类别 | 文件/目录 | 描述 |
|------|-----------|------|
| **L4 接口** | `include/aam/l4/game_fsm.hpp` | 分层状态机接口 |
| **L4 接口** | `include/aam/l4/snapshot_serializer.hpp` | 快照序列化器 |
| **L4 实现** | `core/src/l4_state/hfsm_impl.cpp` | HFSM 实现 |
| **L4 实现** | `core/src/l4_state/sqlite_storage.cpp` | SQLite 存储 |
| **L4 实现** | `core/src/l4_state/delta_encoder.cpp` | 增量编码器 |
| **L4 实现** | `core/src/l4_state/prts_data_loader.cpp` | PRTS 数据加载 |
| **数据脚本** | `scripts/db_migrate/fetch_prts_data.py` | PRTS 数据同步脚本 |
| **测试数据** | `tests/fixtures/level_1-7.json` | 1-7 关卡测试数据 |
| **数据库** | `data/levels.db` | SQLite 关卡数据库 |

### Test Strategy
- **状态机转换测试**：模拟游戏状态变更序列（Preparation → Combat → Wave1 → Boss → Victory），验证状态切换延迟 < 50ms
- **崩溃恢复测试**：模拟进程异常终止（`kill -9`），重启后从 SQLite 读取最近快照，验证恢复后丢失进度 < 5 秒（即最多重打 5 秒内容）
- **存储压缩测试**：记录 1000 帧游戏状态，比较全量存储 vs 增量编码的存储大小，验证压缩率 ≥ 90%
- **数据一致性测试**：验证 `fetch_prts_data.py` 生成的 SQLite 数据与 PRTS Wiki 源数据一致性（字段完整性检查）

### Acceptance Criteria
- [ ] **延迟**：状态切换延迟 P99 < 50ms
- [ ] **可靠性**：崩溃恢复后进度丢失 < 5 秒（最近快照时间戳与崩溃时间差）
- [ ] **压缩**：增量编码压缩率 ≥ 90%（delta 大小 / full 大小 ≤ 10%）
- [ ] **数据**：`levels.db` 包含至少 20 张关卡数据，字段完整率 100%

### Sign-off Checklist
- [ ] 状态机转换延迟测试报告（包含状态转换图）
- [ ] 崩溃恢复测试录像（展示 kill 后恢复过程）
- [ ] PRTS 数据同步日志（最近同步时间戳）

---

## v0.5.0-alpha：视觉皮层版

### Deliverables
| 类别 | 文件/目录 | 描述 |
|------|-----------|------|
| **L1 接口** | `include/aam/l1/gpu_pipeline.hpp` | GPU 流水线接口 |
| **L1 接口** | `include/aam/l1/tensor_converter.hpp` | 张量转换器 |
| **L1 实现** | `core/src/l1_perception/cuda_kernels/color_convert.cu` | CUDA 颜色转换核 |
| **L1 实现** | `core/src/l1_perception/cuda_kernels/pyramid_down.cu` | CUDA 金字塔核 |
| **L1 实现** | `core/src/l1_perception/ocr_engine.cpp` | PaddleOCR 封装 |
| **L1 实现** | `core/src/l1_perception/yolo_detector.cpp` | YOLO 检测器 |
| **L1 实现** | `core/src/l1_perception/region_of_interest.cpp` | ROI 裁剪 |
| **模型文件** | `models/yolov8n-arknights.onnx` | 量化 YOLO 模型（6MB） |
| **模型文件** | `models/ppocr-v4-rec/` | OCR 模型目录 |

### Test Strategy
- **GPU 性能测试**：使用 NVIDIA Nsight Systems，测量单帧 CUDA 核函数执行时间（颜色转换 + 降采样）
- **OCR 准确率测试**：准备 100 张包含费用数字的截图（不同字体大小、光照条件），统计识别准确率
- **YOLO 检测测试**：使用 COCO 格式标注的测试集（500 张截图），计算 mAP@0.5（干员栏检测）
- **内存测试**：监控 GPU 显存占用，单帧处理峰值 < 500MB（GTX 4060 Laptop）

### Acceptance Criteria
- [ ] **性能**：CUDA 预处理 < 8ms（1080p 输入），YOLO 推理 < 20ms，总 L1 处理 < 30ms
- [ ] **准确率**：OCR 费用数字识别准确率 ≥ 95%，YOLO 干员栏检测 mAP ≥ 0.85
- [ ] **资源**：GPU 显存峰值占用 < 500MB，CPU 内存零拷贝（OpenCV CUDA 内存池管理）

### Sign-off Checklist
- [ ] NVIDIA Nsight 性能分析报告（包含核函数时间线）
- [ ] OCR 准确率测试集与结果 CSV
- [ ] YOLO mAP 评估报告（包含混淆矩阵）

---

## v0.6.0-alpha：战术执行版

### Deliverables
| 类别 | 文件/目录 | 描述 |
|------|-----------|------|
| **L3 接口** | `include/aam/l3/tactical_engine.hpp` | 战术引擎接口 |
| **L3 接口** | `include/aam/l3/dsl_compiler.hpp` | DSL 编译器接口 |
| **L3 实现** | `core/src/l3_tactical/tactical_vm.cpp` | 战术虚拟机 |
| **L3 实现** | `core/src/l3_tactical/bytecode/opcodes.hpp` | 操作码枚举 |
| **L3 实现** | `core/src/l3_tactical/bytecode/assembler.cpp` | 汇编器 |
| **L3 实现** | `core/src/l3_tactical/cost_manager.cpp` | 费用管理器 |
| **L3 实现** | `core/src/l3_tactical/collision_predictor.cpp` | 碰撞预测器 |
| **战术脚本** | `tactics/1-7_default.tactical` | 1-7 默认战术字节码 |

### Test Strategy
- **VM 性能测试**：执行 10000 条虚拟机指令，测量总耗时，计算单条指令平均延迟
- **DSL 编译测试**：编写 10 个复杂战术脚本（包含嵌套条件、循环），验证正确编译为字节码且无内存泄漏
- **费用预测测试**：模拟费用曲线（初始 10 费，自然回费 1/秒），验证费用管理器预测 5 秒后费用值误差 < 2 费
- **沙箱安全测试**：尝试执行含无限循环的恶意脚本，验证指令计数器在 10000 条后强制终止

### Acceptance Criteria
- [ ] **性能**：VM 执行 1000 条指令 < 2ms（单条 < 2μs）
- [ ] **编译**：DSL 到字节码编译零内存泄漏（Valgrind 验证）
- [ ] **预测**：费用预测误差 < 2 费（测试 20 个随机费用曲线）
- [ ] **安全**：沙箱指令计数器硬限制生效，无限循环脚本被强制终止

### Sign-off Checklist
- [ ] VM 性能基准测试报告
- [ ] DSL 编译测试用例集（10 个复杂脚本）
- [ ] 沙箱安全测试报告（含恶意脚本样本）

---

## v0.7.0-beta：桥接版

### Deliverables
| 类别 | 文件/目录 | 描述 |
|------|-----------|------|
| **Bridge 接口** | `bridge/include/aam_bridge/ipc_client.hpp` | IPC 客户端接口 |
| **Bridge 接口** | `bridge/include/aam_bridge/transport_factory.hpp` | 传输工厂 |
| **Bridge 实现** | `bridge/src/grpc_client.cpp` | gRPC 客户端 |
| **Bridge 实现** | `bridge/src/shm_segment.cpp` | 共享内存传输 |
| **Bridge 实现** | `bridge/src/pybind_module.cpp` | PyBind11 模块 |
| **Python 服务** | `inference/services/grpc_server.py` | gRPC 服务端 |
| **Python 服务** | `inference/services/websocket_server.py` | WebSocket 服务端 |
| **Python 服务** | `inference/services/l5_controller.py` | L5 控制器 |
| **监控** | `bridge/src/pybind_adapter.hpp` | Python 健康监控 |
| **总线** | `core/src/common/bus.cpp` | C++ 事件总线 |

### Test Strategy
- **延迟测试**：测量 C++ → gRPC → Python → gRPC → C++ 往返时间（本地部署，不含 LLM 推理），记录 P99
- **故障注入测试**：在 L5 决策过程中 `kill -9` Python 进程，验证 C++ 核心 10 秒内检测到失联并降级到 L3 本地策略
- **吞吐量测试**：持续发送 60fps 帧数据，监控 gRPC 通道是否出现背压丢帧
- **内存共享测试**：验证 SHM 零拷贝传输，对比 gRPC 序列化拷贝的性能差异（应提升 3 倍以上）

### Acceptance Criteria
- [ ] **延迟**：跨语言往返 P99 < 150ms（本地部署）
- [ ] **容错**：Python 崩溃后 10 秒内 C++ 检测到失联，自动降级到本地战术（测试 5 次均通过）
- [ ] **吞吐量**：支持 60fps 持续传输，无丢帧（测试 5 分钟）
- [ ] **零拷贝**：SHM 传输延迟 < gRPC 传输延迟的 1/3

### Sign-off Checklist
- [ ] 跨语言延迟测试报告（包含直方图）
- [ ] 故障注入测试录像（展示降级过程）
- [ ] 吞吐量测试日志（帧率统计）

---

## v0.8.0-beta：决策版

### Deliverables
| 类别 | 文件/目录 | 描述 |
|------|-----------|------|
| **L5 适配器** | `inference/services/llm_adapters/openai_adapter.py` | OpenAI GPT-4V 适配 |
| **L5 适配器** | `inference/services/llm_adapters/claude_adapter.py` | Claude 3 适配 |
| **L5 适配器** | `inference/services/llm_adapters/local_llava.py` | 本地模型适配 |
| **提示工程** | `configs/inference/prompt_templates/system_expert.txt` | 系统提示词 |
| **提示工程** | `configs/inference/prompt_templates/cot_format.txt` | CoT 格式模板 |
| **配置** | `configs/inference/llm_providers.yaml` | LLM 配置 |
| **视觉** | `inference/src/vision/squad_recognizer.py` | 干员识别 |
| **视觉** | `inference/src/vision/game_state_detector.py` | 状态检测 |

### Test Strategy
- **决策准确率测试**：人工标注 50 局 1-7 关卡的"正确操作"（何时部署、部署到哪个格子），对比 L5 决策，计算准确率
- **延迟测试**：测量从截图发送到首 Token 返回的时间（GPT-4V 目标 < 1000ms，本地模型 < 3000ms）
- **多后端切换测试**：在运行时修改 `llm_providers.yaml`，验证热重载生效且不丢失上下文
- **视觉识别测试**：使用 L1 输出的 YOLO 检测结果，验证干员识别匹配准确率（与数据库对比）

### Acceptance Criteria
- [ ] **准确率**：1-7 关卡干员部署位置正确率 ≥ 90%（50 局测试）
- [ ] **延迟**：GPT-4V 首 Token < 1000ms（网络正常），本地模型 < 3000ms
- [ ] **热重载**：修改配置文件后 5 秒内生效，无需重启进程
- [ ] **匹配**：干员识别匹配准确率 ≥ 95%

### Sign-off Checklist
- [ ] 决策准确率人工评估报告（包含 50 局对比表）
- [ ] 延迟测试报告（不同网络条件下的 P50/P99）
- [ ] 热重载功能演示录像

---

## v0.9.0-beta：界面版

### Deliverables
| 类别 | 文件/目录 | 描述 |
|------|-----------|------|
| **GUI 抽象** | `gui/abstract/include/aam_gui/i_main_window.hpp` | 主窗口接口 |
| **GUI 抽象** | `gui/abstract/include/aam_gui/i_map_canvas.hpp` | 地图画布接口 |
| **GUI 抽象** | `gui/abstract/src/event_dispatcher.cpp` | 事件分发器 |
| **Qt 实现** | `gui/qt/src/main_window.cpp` | Qt 主窗口 |
| **Qt 实现** | `gui/qt/src/map_view.cpp` | OpenGL 地图视图 |
| **Qt 实现** | `gui/qt/src/operator_palette.cpp` | 干员栏 UI |
| **Qt 实现** | `gui/qt/src/qt_event_bridge.cpp` | Qt 事件桥接 |
| **监控** | `gui/panels/monitor.py` | 性能监控面板 |

### Test Strategy
- **帧率测试**：使用 Qt 的 FPS 计数器，验证预览窗口刷新率与 L0 捕获同步（60fps 输入 → 60fps 显示，掉帧率 < 1%）
- **交互延迟测试**：使用高速摄像机（或软件计时）测量从点击 GUI "部署" 按钮到 ADB 执行的延迟
- **跨平台构建测试**：在 Windows 生成 `.exe`，Linux 生成 `AppImage`，验证可独立运行（包含 Qt 运行时）
- **OpenGL 测试**：验证地图渲染在 Intel/AMD/NVIDIA 显卡上均正常（无黑屏/纹理错误）

### Acceptance Criteria
- [ ] **帧率**：预览窗口 60fps 稳定运行，掉帧率 < 1%（测试 5 分钟）
- [ ] **交互**：GUI 点击到 ADB 执行 < 100ms
- [ ] **跨平台**：Windows `.exe` 与 Linux `AppImage` 均可启动并显示主界面
- [ ] **兼容性**：OpenGL 渲染在 GTX 1060 / RTX 4060 / Intel UHD 上均正常

### Sign-off Checklist
- [ ] FPS 测试日志（包含掉帧统计）
- [ ] 跨平台安装包（Artifacts）
- [ ] UI 兼容性测试报告（多显卡）

---

## v1.0.0-rc：生产候选版

### Deliverables
| 类别 | 文件/目录 | 描述 |
|------|-----------|------|
| **E2E 测试** | `tests/e2e/test_1_7_clear.py` | 1-7 通关测试 |
| **E2E 测试** | `tests/e2e/test_crisis_contract.py` | 危机合约测试 |
| **E2E 测试** | `tests/e2e/test_recovery.py` | 异常恢复测试 |
| **安装脚本** | `scripts/setup/install_deps_windows.ps1` | Windows 安装 |
| **安装脚本** | `scripts/setup/setup_vcpkg.sh` | Linux/macOS 安装 |
| **CI 配置** | `.github/workflows/release.yml` | 发版工作流 |
| **文档** | `README.md` | 用户手册 |
| **文档** | `docs/ARCHITECTURE.md` | 架构白皮书 |
| **文档** | `docs/API.md` | 插件 API 文档 |

### Test Strategy
- **稳定性测试**：连续运行 8 小时（约 100 局 1-7），监控崩溃次数、内存增长曲线（应平坦）
- **端到端自动化测试**：`test_1_7_clear.py` 自动执行 10 次 1-7 通关循环，验证成功率 ≥ 95%
- **异常恢复测试**：`test_recovery.py` 模拟网络断开 5 秒、游戏崩溃、分辨率切换，验证恢复能力
- **用户体验测试**：招募 3 名非技术用户，记录从下载到首次成功运行的时间，目标 < 5 分钟

### Acceptance Criteria（冻结线）
- [ ] **稳定性**：8 小时连续运行零崩溃，内存泄漏 0 bytes（Valgrind）
- [ ] **成功率**：1-7 自动通关成功率 ≥ 95%（10 局测试）
- [ ] **恢复**：网络断开 5 秒后 10 秒内自动恢复（测试 5 次均通过）
- [ ] **易用性**：非技术用户 5 分钟内完成安装配置（3/3 用户通过）

### Sign-off Checklist（Release Checklist）
- [ ] 版本 Tag `v1.0.0` 已打，Release Notes 已撰写
- [ ] 安装包 SHA256 校验和已计算并公布
- [ ] 文档完整（用户手册、架构白皮书、API 文档）
- [ ] 安全审计通过（无 Critical/High 漏洞）
- [ ] 性能基准报告（P99 延迟 < 500ms）

---

## v1.1.0：专业版（追加交付物）

### Deliverables
- [ ] `gui/wpf/AAM.WPF/`：WPF 完整项目目录
- [ ] `gui/wpf/AAM.Native/cpp_cli_bridge.cpp`：C++/CLI 桥接实现
- [ ] `plugins/sdk/include/aam_plugin.hpp`：插件 SDK 头文件
- [ ] `docs/WPF_INTEGRATION.md`：WPF 集成指南

### Test Strategy
- **零拷贝测试**：验证 C++/CLI 传递帧数据到 WPF `WriteableBitmap` 无内存拷贝（使用 VMMap 工具监控）
- **Xbox Game Bar 测试**：验证悬浮地图层在游戏内正常显示，不抢占焦点

---

## v1.2.0：生态版（追加交付物）

### Deliverables
- [ ] `plugins/examples/auto_credit_shop.cpp`：示例插件源码
- [ ] `market/schemas/tactical_v1.json`：战术分享格式 Schema
- [ ] `.github/workflows/lts.yml`：LTS 维护工作流
- [ ] `CONTRIBUTING.md`：贡献者指南

### Test Strategy
- **插件加载测试**：动态加载/卸载 100 次插件，验证无内存泄漏，无符号冲突
- **Schema 验证测试**：使用 JSON Schema 验证器检查 50 个社区战术文件，100% 通过

---

**文档维护约定**：
- 每个版本发布后，将本文档中该版本的测试报告链接归档至 `docs/qa/v{X.Y.Z}/`
- 发现漏测项时，通过 PR 更新本文档，并标记 `Amended: YYYY-MM-DD`