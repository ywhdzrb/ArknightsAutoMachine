**Arknights Auto Machine (AAM) 版本化开发路线图**

基于语义化版本（SemVer），从 `v0.1.0-alpha`（契约奠基）迭代至 `v1.0.0`（生产就绪）。

---

## v0.1.0-alpha：契约冻结版（The Contract）

**目标**: 建立不可变的接口契约与构建系统，此后任何 Breaking Change 需通过 RFC 流程。

### 文件级交付清单

**协议层 (`proto/`)**
- [ ] `proto/common/types.proto`：定义 `LogicalCoord`（逻辑坐标结构）、`TimestampNs`（纳秒时间戳）、`Resolution`（分辨率枚举 1080p/2K/4K）
- [ ] `proto/ama/l0_frame.proto`：定义 `FrameMetadata`（H264 流序号、PTS/DTS、编码格式枚举 H264/HEVC）、`FrameBufferDescriptor`（共享内存句柄描述符）
- [ ] `proto/ama/l1_perception.proto`：定义 `DetectionBox`（归一化坐标 xywh + 置信度 + 类别枚举 Enemy/Operator/SkillButton）、`OCRResult`（文本内容 + 边界框 + 识别置信度）
- [ ] `proto/ama/l2_action.proto`：定义 `ActionPrimitive`（枚举 Tap/Swipe/Drag/KeyPress）、`PhysicalCoord`（设备物理像素坐标）、`ActionCommand`（序列号 + 坐标 + 持续时间 + 随机抖动幅度）
- [ ] `proto/ama/l3_tactical.proto`：定义 `TacticalBytecode`（操作码枚举 DEPLOY/SKILL/RETREAT/WAIT）、`CostCondition`（费用阈值触发条件）、`Direction`（枚举 UP/DOWN/LEFT/RIGHT）
- [ ] `proto/ama/l4_state.proto`：定义 `GameSnapshot`（状态机枚举 Preparation/Combat/Paused/Victory/Defeat + 干员部署列表 + 敌人波次计数器）、`DeltaFrame`（增量编码的位掩码）
- [ ] `proto/inference/l5_strategy.proto`：定义 `StrategyRequest`（Base64 压缩图像 + 上下文 JSON + 历史操作序列）、`StrategyResponse`（决策列表 + 置信度分数 + CoT 思维链文本）
- [ ] `proto/services/control_service.proto`：定义 `StartSession`/`StopSession`/`Heartbeat` RPC 方法（含 gRPC 健康检查协议）

**构建系统**
- [ ] `CMakeLists.txt`（根）：定义 `aam_core` 静态库目标、设置 C++23 标准、强制 `-fvisibility=hidden`、启用 IPO/LTO
- [ ] `cmake/compiler_flags.cmake`：平台特定标志（Windows: `/permissive- /W4 /WX` 视警告为错误；Linux: `-Wall -Wextra -Wpedantic -fno-rtti`）
- [ ] `cmake/FindZeroMQ.cmake`：ZeroMQ 自动发现模块（备用传输方案）
- [ ] `.clang-format`：基于 LLVM 风格，缩进 4 空格，行宽 100 字符，指针左对齐 `int* ptr`
- [ ] `.clang-tidy`：启用 `cppcoreguidelines-*`, `modernize-*`, `performance-*`, `portability-*` 检查集，禁用 `google-runtime-references`

**持续集成**
- [ ] `.github/workflows/ci.yml`：矩阵构建 {Windows Server 2022 (MSVC 19.39), Ubuntu 22.04 (GCC 13), macOS 14 (Clang 15)} × {Debug, Release}
- [ ] `.github/workflows/codeql.yml`：CodeQL C++ 安全分析工作流（初始化数据库、构建、分析）
- [ ] `scripts/codegen/protobuf_gen.py`：自动化生成脚本（调用 `protoc` 生成 C++ 文件至 `build/generated/cpp/`、Python 文件至 `build/generated/py/`）

**验收标准**
- 执行 `cmake --build build --target protobuf_gen` 成功生成 14 个 C++ 头文件与 14 个 Python 模块，零警告
- CodeQL 扫描零高危漏洞（Critical/High）
- 提交哈希 `v0.1.0-alpha` 打 Tag，此后 `proto/` 目录受保护（PR 需双 Review）

---

## v0.2.0-alpha：感知硬化版（The Sensor）

**目标**: L0 层具备稳定帧捕获能力，P99 延迟 < 20ms，内存零拷贝。

### 文件级交付清单

**L0 实现 (`core/src/l0_sensing/`)**
- [ ] `include/aam/l0/capture_backend.hpp`：纯虚接口 `ICaptureBackend`（方法 `startStream(callback)`/`stopStream()`/`getLastFrame()`）
- [ ] `include/aam/l0/frame_buffer.hpp`：模板类 `LockFreeFrameBuffer<T>`（基于 `boost::lockfree::spsc_queue`，容量 120 帧 @ 60fps 双缓冲）
- [ ] `src/l0_sensing/shm_transport.cpp`：实现 `ShmTransport`（Boost.Interprocess `mapped_region` 管理 1GB 环形缓冲区，支持多分辨率动态适配）
- [ ] `src/l0_sensing/adb_capture.cpp`：实现 `AdbCaptureBackend`（`adb shell screenrecord --output-format=h264 --size 1920x1080` 管道读取，使用 `libavcodec` 硬解码）
- [ ] `src/l0_sensing/maa_adapter.cpp`：实现 `MaaCaptureBackend`（MaaFramework 句柄桥接，备用方案）
- [ ] `src/l0_sensing/win32_window_capture.cpp`：实现 `Win32CaptureBackend`（`PrintWindow` API 后备方案，用于无 ADB 环境）
- [ ] `src/l0_sensing/tests/test_frame_sync.cpp`：单元测试（连续捕获 1000 帧，验证时间戳单调递增，无丢帧）
- [ ] `src/l0_sensing/tests/test_shm_throughput.cpp`：基准测试（测量 1920x1080 H264 帧 memcpy 到 SHM 耗时 < 1ms）

**基础设施 (`core/src/common/`)**
- [ ] `include/aam/core/timer.hpp`：`HighResolutionTimer` 类（封装 `std::chrono::steady_clock` + `QueryPerformanceCounter` Win32 API）
- [ ] `include/aam/core/memory_pool.hpp`：`FixedMemoryPool` 类（定长内存池，用于帧数据预分配，避免运行时 malloc）
- [ ] `src/common/logger.cpp`：`spdlog` 封装，异步日志队列（环形缓冲区 8192 条），支持日志分级（Debug/Info/Warning/Error）

**配置**
- [ ] `configs/ama/capture.yaml`：L0 配置模板（`backend: adb`，`target_fps: 60`，`resolution: 1920x1080`，`buffer_size_mb: 1024`）

**验收标准**
- 运行 `build/tests/test_l0_frame_sync` 输出：`PASSED: 1000/1000 frames, 0 dropped, avg_latency 12ms, p99_latency 18ms`
- Valgrind `massif` 报告：峰值内存占用 < 150MB，无泄漏（definitely lost: 0 bytes）
- 跨平台编译通过：Windows (MSVC)、Linux (GCC)、macOS (Clang) 均生成可执行测试文件

---

## v0.3.0-alpha：空间映射版（The Mapper）

**目标**: L2 层实现逻辑坐标到物理坐标的亚像素级映射，支持多分辨率自适应。

### 文件级交付清单

**L2 实现 (`core/src/l2_motor/`)**
- [ ] `include/aam/l2/coordinate_transform.hpp`：`CoordinateTransformer` 类（方法 `logicalToPhysical(LogicalCoord) -> PhysicalCoord`，透视变换矩阵管理）
- [ ] `include/aam/l2/human_simulator.hpp`：`HumanSimulator` 类（贝塞尔曲线生成 `generateBezierCurve(start, end, control_points)`，速度曲线模拟人类手指动力学）
- [ ] `include/aam/l2/action_executor.hpp`：`IActionExecutor` 接口（`execute(ActionCommand)` 纯虚方法）
- [ ] `src/l2_motor/coordinate_transform.cpp`：实现 4 点标定法（求解 3x3 单应矩阵 `H`），支持 1080p/2K/4K 自动识别
- [ ] `src/l2_motor/trajectory_generator.cpp`：实现三次贝塞尔曲线（Cubic Bezier）轨迹生成，随机扰动幅度 ±5px 符合均匀分布
- [ ] `src/l2_motor/input_adapters/adb_input.cpp`：`AdbInputExecutor` 类（调用 `adb shell input tap x y` 或 `input swipe x1 y1 x2 y2 duration`）
- [ ] `src/l2_motor/input_adapters/win32_postmessage.cpp`：`Win32InputExecutor` 类（`PostMessage(hwnd, WM_LBUTTONDOWN, ...)` 实现后台点击）
- [ ] `src/l2_motor/feedback_loop.cpp`：`FeedbackLoop` 类（操作后 200ms 截图比对，像素差分确认操作成功）

**配置数据**
- [ ] `configs/ama/input_profiles/bluestacks.yaml`：蓝叠模拟器参数（物理分辨率 1920x1080，导航栏偏移 0，DPI 280）
- [ ] `configs/ama/input_profiles/rog_phone_8.yaml`：ROG Phone 8 参数（144Hz 屏幕，触控采样率 720Hz，坐标系偏移校准值）
- [ ] `core/src/l2_motor/resolvers/1920x1080.cpp`：1080p 分辨率下网格坐标映射表（9x5 地图网格原点 (300,200)，单元格 120x120）
- [ ] `core/src/l2_motor/resolvers/2560x1440.cpp`：2K 分辨率映射表（自动插值计算）

**验收标准**
- 单元测试 `test_coordinate_transform`：输入逻辑坐标 (4,3)，输出物理坐标误差 < 2px（1080p 下）
- 贝塞尔曲线测试：生成 100 条轨迹，速度曲线符合正态分布 N(80ms, 15ms)（通过 Kolmogorov-Smirnov 检验，p-value > 0.05）
- 反馈闭环测试：1000 次点击操作，确认成功率 998/1000（允许 2 次 ADB 延迟导致的误判）

---

## v0.4.0-alpha：记忆架构版（The Memory）

**目标**: L4 层实现分层状态机（HFSM）与增量快照，支持崩溃恢复。

### 文件级交付清单

**L4 实现 (`core/src/l4_state/`)**
- [ ] `include/aam/l4/game_fsm.hpp`：`HierarchicalFSM` 类（三层状态：GameState {Preparation, Combat, Ended} → WaveState {Wave1, Wave2, Boss} → OperatorState {Deployed, Retreating, SkillCD}）
- [ ] `include/aam/l4/snapshot_serializer.hpp`：`SnapshotSerializer` 类（方法 `serialize(GameSnapshot) -> std::vector<uint8_t>`，支持 MessagePack 格式）
- [ ] `src/l4_state/hfsm_impl.cpp`：实现状态转换表（Transition Table），状态切换回调注册机制
- [ ] `src/l4_state/sqlite_storage.cpp`：`SQLiteStorage` 类（Schema：表 `snapshots`（id, timestamp, delta_blob, full_snapshot_ref），表 `level_data`（关卡 ID, 波次配置 JSON））
- [ ] `src/l4_state/delta_encoder.cpp`：`DeltaEncoder` 类（实现增量编码：仅记录与上一帧变化的干员位置、费用值，压缩率目标 90%）
- [ ] `src/l4_state/prts_data_loader.cpp`：`PrtsDataLoader` 类（解析 PRTS Wiki JSON，加载关卡网格、敌人波次时间线、机制点位置）

**数据层**
- [ ] `scripts/db_migrate/fetch_prts_data.py`：每日自动同步脚本（下载 PRTS 关卡数据，转换为 SQLite 格式写入 `data/levels.db`）
- [ ] `tests/fixtures/level_1-7.json`：1-7 关卡测试数据（包含 3 个波次，敌人路径点坐标）

**验收标准**
- 状态机测试：从 Preparation → Combat → Victory 状态转换延迟 < 50ms
- 崩溃恢复测试：模拟进程 kill，从 SQLite 读取最近快照恢复，丢失游戏进度 < 5 秒（即最多重打 5 秒内容）
- 存储测试：1000 局游戏数据，SQLite 文件大小 < 100MB（增量编码生效）

---

## v0.5.0-alpha：视觉皮层版（The Vision）

**目标**: L1 层实现 GPU 加速预处理与本地 OCR/YOLO，单帧处理 < 30ms。

### 文件级交付清单

**L1 实现 (`core/src/l1_perception/`)**
- [ ] `include/aam/l1/gpu_pipeline.hpp`：`GpuPipeline` 类（CUDA 流管理，方法 `submitKernel(kernel, args)`）
- [ ] `include/aam/l1/tensor_converter.hpp`：`TensorConverter` 类（OpenCV `Mat` ↔ ONNX Runtime `Ort::Value` 零拷贝转换）
- [ ] `src/l1_perception/cuda_kernels/color_convert.cu`：CUDA 核函数（RGB → HSV 色彩空间转换，用于敌人血条红色识别）
- [ ] `src/l1_perception/cuda_kernels/pyramid_down.cu`：CUDA 核函数（图像金字塔降采样，支持 1/2/4 倍缩放）
- [ ] `src/l1_perception/ocr_engine.cpp`：`PaddleOCREngine` 类（封装 PaddleOCR C++ 推理，识别费用数字、干员名、技能 CD 文本）
- [ ] `src/l1_perception/yolo_detector.cpp`：`YoloDetector` 类（ONNX Runtime 加载 YOLOv8-nano，输入 640x640，输出检测框，置信度阈值 0.5）
- [ ] `src/l1_perception/region_of_interest.cpp`：`RoiProcessor` 类（ROI 裁剪，仅处理地图中央 60% 区域 + 干员栏底部区域）

**模型文件**
- [ ] `models/yolov8n-arknights.onnx`：量化后的 YOLOv8-nano（6MB，INT8 精度，识别干员/敌人/地形三类目标）
- [ ] `models/ppocr-v4-rec/`: PaddleOCR 识别模型（本地文件，非 Python 后端依赖）

**验收标准**
- 性能测试：1080p 输入帧，CUDA 预处理（颜色转换+降采样）< 8ms（GTX 4060 Laptop）
- OCR 准确率：费用数字识别准确率 > 95%（测试集 100 张截图）
- YOLO 检测：干员栏 12 个位置检测 mAP > 0.85，单帧推理 < 20ms

---

## v0.6.0-alpha：战术执行版（The Tactics）

**目标**: L3 层实现战术 DSL 编译器与虚拟机，支持费用管理与碰撞检测。

### 文件级交付清单

**L3 实现 (`core/src/l3_tactical/`)**
- [ ] `include/aam/l3/tactical_engine.hpp`：`TacticalEngine` 类（方法 `compile(script) -> Bytecode`，`execute(Bytecode)`）
- [ ] `include/aam/l3/dsl_compiler.hpp`：`DslCompiler` 类（战术脚本语法分析器，支持 `deploy("Exusiai", tile=(3,4), direction=RIGHT)` 语法）
- [ ] `src/l3_tactical/tactical_vm.cpp`：`TacticalVM` 类（基于栈的虚拟机，实现指令集：DEPLOY, SKILL, RETREAT, WAIT, IF_COST_GT）
- [ ] `src/l3_tactical/bytecode/opcodes.hpp`：操作码枚举（`OP_DEPLOY = 0x01`, `OP_SKILL = 0x02`, ... `OP_HALT = 0xFF`）
- [ ] `src/l3_tactical/bytecode/assembler.cpp`：`Assembler` 类（文本 DSL 汇编为二进制字节码）
- [ ] `src/l3_tactical/cost_manager.cpp`：`CostManager` 类（实时追踪费用曲线，预测 5 秒后费用值，防卡费逻辑）
- [ ] `src/l3_tactical/collision_predictor.cpp`：`CollisionPredictor` 类（敌人路径与干员攻击范围碰撞检测，预测敌人何时进入射程）

**战术脚本示例**
- [ ] `tactics/1-7_default.tactical`：1-7 关卡默认战术脚本（部署 3 个干员的字节码序列）

**验收标准**
- VM 性能：1000 条指令执行 < 2ms
- DSL 编译：脚本 `deploy("Amiya", (4,3), RIGHT)` 正确编译为字节码 [0x01, 0x04, 0x03, 0x01]（假设 RIGHT=0x01）
- 费用预测：基于 OCR 费用值 + 自然回费速率（1 秒 1 费），预测 5 秒后费用误差 < 2 费

---

## v0.7.0-beta：桥接版（The Bridge）

**目标**: C++ 核心与 Python L5 建立稳定通信，支持双向流与故障转移。

### 文件级交付清单

**Bridge 层 (`bridge/`)**
- [ ] `include/aam_bridge/ipc_client.hpp`：`IpcClient` 接口（`sendRequest(Request) -> Response`，`registerCallback(event, handler)`）
- [ ] `include/aam_bridge/transport_factory.hpp`：`TransportFactory` 类（工厂方法创建 gRPC 或 SHM 传输）
- [ ] `src/grpc_client.cpp`：`GrpcClient` 类（gRPC 异步 CompletionQueue 实现，支持 10k QPS）
- [ ] `src/shm_segment.cpp`：`ShmTransport` 类（Boost.Interprocess 零拷贝传输，回退方案当 gRPC 延迟 > 100ms）
- [ ] `src/pybind_module.cpp`：`PYBIND11_MODULE(aam_native, m)` 定义（Python 可调用的 C++ API，调试模式使用）

**Python 服务端 (`inference/services/`)**
- [ ] `grpc_server.py`：`ControlServicer` 类（实现 `StartSession`/`StopSession` RPC，维护 L5 决策循环）
- [ ] `websocket_server.py`：`WebSocketServer` 类（备选实时流传输，用于远程调试）
- [ ] `l5_controller.py`：`L5Controller` 类（主循环：接收 C++ 帧 → 调用 LLM → 返回战术指令）

**监控与容错**
- [ ] `src/pybind_adapter.hpp`：`PythonHealthMonitor` 类（Watchdog 机制，500ms 心跳检测，崩溃后 10 秒内重启 Python 进程）
- [ ] `core/src/common/bus.cpp`：`MessageBus` 类（发布-订阅模式，C++ 侧事件总线，解耦 L0-L4 与 Bridge）

**验收标准**
- 延迟测试：C++ → gRPC → Python → gRPC → C++ 往返 < 150ms（本地部署，不含 LLM 推理）
- 故障注入：Python 进程 `kill -9` 后，C++ 核心 10 秒内检测到失联，自动降级到 L3 本地战术（硬编码保底策略）
- 吞吐量：单连接支持 60fps 帧传输，无背压丢帧

---

## v0.8.0-beta：决策版（The Brain）

**目标**: L5 层接入多 LLM 后端，实现视觉理解（VLM）与战术决策。

### 文件级交付清单

**L5 实现 (`inference/`)**
- [ ] `src/services/llm_adapters/openai_adapter.py`：`OpenAIAdapter` 类（封装 GPT-4V API，多模态输入支持）
- [ ] `src/services/llm_adapters/claude_adapter.py`：`ClaudeAdapter` 类（封装 Claude 3 Vision API）
- [ ] `src/services/llm_adapters/local_llava.py`：`LocalLlavaAdapter` 类（Ollama/llama.cpp 本地 7B 模型适配，GGUF 格式）
- [ ] `configs/inference/prompt_templates/system_expert.txt`：System Prompt（"你是明日方舟战术专家..."）
- [ ] `configs/inference/prompt_templates/cot_format.txt`：思维链格式模板（强制 LLM 输出 JSON 前解释推理过程）
- [ ] `configs/inference/llm_providers.yaml`：配置文件（`provider: openai`, `model: gpt-4-vision-preview`, `api_key: ${OPENAI_API_KEY}`）

**视觉分析增强**
- [ ] `src/vision/squad_recognizer.py`：干员识别（接收 C++ L1 YOLO 输出，匹配干员数据库）
- [ ] `src/vision/game_state_detector.py`：游戏状态机识别（基于 L1 OCR 结果判断当前是准备/战斗/结算）

**验收标准**
- 决策延迟：GPT-4V 首 Token 返回 < 1000ms（网络正常情况），本地模型 < 3000ms
- 决策准确率：1-7 关卡干员部署位置正确率 > 90%（人工标注对比 50 局）
- 多后端切换：修改 `llm_providers.yaml` 后无需重启，热重载生效

---

## v0.9.0-beta：界面版（The Interface）

**目标**: Qt6 GUI 实现实时预览、手动控制、性能监控。

### 文件级交付清单

**GUI 抽象层 (`gui/abstract/`)**
- [ ] `include/aam_gui/i_main_window.hpp`：`IMainWindow` 接口（`showFrame(Frame)`/`logMessage(level, msg)` 纯虚方法）
- [ ] `include/aam_gui/i_map_canvas.hpp`：`IMapCanvas` 接口（`drawGrid()`/`highlightTile(x,y,color)`/`drawEnemyPath(points)`）
- [ ] `src/event_dispatcher.cpp`：`GuiEventDispatcher` 类（C++ 核心事件转发到 GUI 线程）

**Qt6 实现 (`gui/qt/`)**
- [ ] `src/main_window.cpp`：`QtMainWindow` 类（主窗口，集成 `configs/gui/qt_theme.json` 暗色主题）
- [ ] `src/map_view.cpp`：`MapView` 类（OpenGL Widget，渲染地图网格、敌人路径、干员位置）
- [ ] `src/operator_palette.cpp`：`OperatorPalette` 类（干员栏 UI，显示 12 个干员头像与费用）
- [ ] `src/qt_event_bridge.cpp`：`QtEventBridge` 类（信号槽机制连接 AMA 事件总线）

**监控面板**
- [ ] `gui/panels/monitor.py`：性能监控面板（显示 L0-L5 各层延迟直方图，使用 PyQtGraph 实时绘制）

**验收标准**
- 帧率：预览窗口与 L0 捕获同步 60fps，无掉帧（OpenGL 纹理直接映射 SHM）
- 交互延迟：点击 GUI "部署" 按钮到 ADB 执行 < 100ms
- 跨平台：Windows 生成 `.exe`，Linux 生成 `AppImage`，均包含 Qt 运行时

---

## v1.0.0-rc：生产候选版（The Release）

**目标**: 全链路集成测试通过，达到生产可用标准。

### 文件级交付清单

**端到端测试 (`tests/e2e/`)**
- [ ] `test_1_7_clear.py`：自动化测试脚本（启动 AAM → 进入 1-7 → 自动部署通关 → 点击"再次作战" → 循环 10 次）
- [ ] `test_crisis_contract.py`：危机合约特定测试（验证 Tag 识别与策略切换）
- [ ] `test_recovery.py`：异常恢复测试（模拟网络断开 5 秒、模拟游戏崩溃、模拟分辨率切换）

**工程化**
- [ ] `scripts/setup/install_deps_windows.ps1`：Windows 一键安装脚本（安装 Python、CUDA、ADB 驱动）
- [ ] `scripts/setup/setup_vcpkg.sh`：Linux/macOS 依赖安装脚本
- [ ] `.github/workflows/release.yml`：自动化发版工作流（生成 MSI/APP/DMG 安装包，计算 SHA256 校验和）

**文档**
- [ ] `README.md`：用户手册（安装、配置、使用）
- [ ] `docs/ARCHITECTURE.md`：架构设计白皮书（AMA L0-L5 详细设计）
- [ ] `docs/API.md`：插件 API 文档

**验收标准（冻结线）**
- 稳定性：连续运行 8 小时（约 100 局 1-7）无崩溃、无内存泄漏（Valgrind 报告 definitely lost: 0）
- 性能：端到端延迟 P99 < 500ms（从屏幕变化到操作执行，含 LLM 决策）
- 可用性：非技术用户可在 5 分钟内完成安装配置（通过 GUI 向导）

---

## v1.1.0：专业版（The Professional）

**目标**: Windows WPF 深度集成，Xbox Game Bar 插件，企业级功能。

**新增文件**
- [ ] `gui/wpf/AAM.WPF/Views/MainWindow.xaml`：WPF 主窗口（MVVM 模式）
- [ ] `gui/wpf/AAM.Native/cpp_cli_bridge.cpp`：C++/CLI 桥接（零拷贝传递帧到 `WriteableBitmap`）
- [ ] `gui/wpf/AAM.WPF/Views/MapOverlay.xaml`：悬浮地图层（画中画模式）
- [ ] `plugins/sdk/include/aam_plugin.hpp`：C++ 插件 SDK 头文件（定义 `IPlugin` 接口）

---

## v1.2.0：生态版（The Ecosystem）

**目标**: 插件系统、社区市场、长期支持（LTS）。

**新增文件**
- [ ] `plugins/examples/auto_credit_shop.cpp`：示例插件（自动购买信用商店物品）
- [ ] `market/schemas/tactical_v1.json`：战术分享格式 Schema
- [ ] `.github/workflows/lts.yml`：LTS 分支维护工作流（仅修复关键 Bug，每 6 个月发布补丁版本）

---

**版本依赖关系图**:
```
v0.1.0 (契约) 
    → v0.2.0 (L0) → v0.3.0 (L2) → v0.4.0 (L4) → v0.5.0 (L1) → v0.6.0 (L3) [C++ 核心闭环]
                                                    ↓
v0.7.0 (Bridge) → v0.8.0 (L5) [跨语言打通]
                        ↓
                    v0.9.0 (GUI) [可视化]
                        ↓
                    v1.0.0 (RC) [生产就绪]
                        ↓
            v1.1.0 (WPF) / v1.2.0 (Eco) [扩展]
```

**关键冻结点**:
- **v0.1.0**: `proto/` 目录冻结，Breaking Change 需 RFC
- **v0.3.0**: `core/src/l2_motor/resolvers/` 坐标映射表冻结，新分辨率添加需 PR
- **v0.7.0**: gRPC 接口冻结，v1.x 期间保持向后兼容
- **v1.0.0**: 主分支冻结为 `main`，仅接受 Bugfix PR，新功能进入 `dev` 分支等待 v1.1.0