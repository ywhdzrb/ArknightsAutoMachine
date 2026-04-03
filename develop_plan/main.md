## 一、仓库总体架构设计

```text
ArknightsAutoMachine/
├── .github/                    # CI/CD与自动化
│   ├── workflows/
│   │   ├── ci.yml              # 跨平台构建矩阵
│   │   ├── release.yml         # 多 artifacts 发布
│   │   └── codeql.yml          # 静态分析
│   ├── ISSUE_TEMPLATE/
│   └── PULL_REQUEST_TEMPLATE.md
├── docs/                       # 技术文档体系
│   ├── architecture/           # ADR (Architecture Decision Records)
│   ├── api/                    # OpenAPI/gRPC proto 文档
│   └── dev-setup.md            # 开发环境搭建
├── proto/                      # 接口契约定义 (Schema First)
│   ├── ama/                    # AMA架构层间通信协议
│   ├── inference/              # 推理服务协议
│   └── common/                 # 共享类型
├── core/                       # C++ AMA架构核心 (L0-L4)
│   ├── include/aam/
│   ├── src/
│   │   ├── l0_sensing/         # 屏幕捕捉/ADB接口
│   │   ├── l1_signal/          # 图像预处理/降噪
│   │   ├── l2_motor/           # 操作抽象 (点击/滑动)
│   │   ├── l3_tactical/        # 战术执行 (部署/技能)
│   │   ├── l4_state/           # 游戏状态机/对局存档
│   │   └── common/             # 工具类/线程池
│   ├── tests/                  # GTest单元测试
│   ├── third_party/            # 子模块管理
│   ├── CMakeLists.txt
│   └── vcpkg.json              # 依赖清单
├── gui/                        # 多前端实现
│   ├── abstract/               # GUI抽象接口 (纯C++)
│   │   ├── include/aam_gui/
│   │   └── src/
│   ├── qt/                     # Qt6实现 (跨平台)
│   │   ├── src/
│   │   ├── resources/
│   │   └── CMakeLists.txt
│   ├── wpf/                    # WPF实现 (Windows)
│   │   ├── AAM.WPF/            # C#项目
│   │   ├── AAM.Native/         # C++/CLI桥接
│   │   └── AAM.sln
│   └── web/                    # 可选: WebAssembly/Electron
├── inference/                  # Python推理后端 (L5)
│   ├── aam_llm/                # 可安装包
│   │   ├── core/               # L5决策引擎
│   │   ├── models/             # 模型定义/微调
│   │   ├── adapters/           # 游戏数据适配器
│   │   └── tests/              # Pytest
│   ├── services/               # 服务化部署
│   │   ├── grpc_server.py      # gRPC服务
│   │   └── websocket_server.py   # 实时流
│   ├── notebooks/              # 实验/分析
│   ├── requirements/
│   │   ├── base.txt
│   │   └── dev.txt
│   └── pyproject.toml          # Poetry配置
├── bridge/                     # 语言桥接层
│   ├── include/aam_bridge/
│   ├── src/
│   │   ├── ipc/                # 共享内存/ZeroMQ
│   │   ├── rpc/                # gRPC客户端
│   │   └── bindings/           # pybind11
│   └── tests/
├── tools/                      # 开发工具链
│   ├── protobuf_codegen.py     # 代码生成
│   ├── db_migration/           # 关卡数据库迁移
│   └── benchmark/              # 性能测试套件
├── configs/                    # 配置文件模板
│   ├── ama/
│   └── inference/
├── scripts/                    # 运维脚本
├── LICENSE
├── README.md
└── CONTRIBUTING.md
```

---

## 二、核心技术方案

### 1. 多语言通信架构

采用**分层协议栈**设计：

```cpp
// bridge/include/aam_bridge/transport.hpp
namespace aam::bridge {

enum class TransportType {
    SHARED_MEMORY,    // L0-L3 高频数据 (屏幕帧/点击坐标)
    GRPC_UNARY,       // L4 状态查询
    GRPC_STREAM,      // L5 实时推理流
    WEBSOCKET         // 调试/监控
};

// 零拷贝共享内存用于L0→L1图像流
class SharedMemoryTransport {
    // 基于boost.interprocess或自定义mmap
    // 环形缓冲区设计，支持多生产者-单消费者
};
}
```

**协议选择策略**：
- **L0-L2（感知→运动）**：共享内存（延迟<1ms）
- **L3-L4（战术→状态）**：gRPC Unary（可靠传输）
- **L5（LLM决策）**：gRPC Bidirectional Streaming或WebSocket

### 2. GUI抽象层设计

实现**抽象工厂模式**隔离框架差异：

```cpp
// gui/abstract/include/aam_gui/gui_factory.hpp
class IGUIFactory {
public:
    virtual ~IGUIFactory() = default;
    virtual std::unique_ptr<IMainWindow> createMainWindow() = 0;
    virtual std::unique_ptr<IMapView> createMapView() = 0;
    virtual std::unique_ptr<IOperatorPanel> createOperatorPanel() = 0;
    
    // 统一事件总线，解耦AMA核心与GUI
    virtual void bindEventBus(std::shared_ptr<aam::core::EventBus>) = 0;
};

// Qt实现
class QtGUIFactory : public IGUIFactory { ... };

// WPF通过C++/CLI桥接
class WpfBridgeFactory : public IGUIFactory {
    // 通过C++/CLI调用C# WPF控件
};
```

### 3. AMA L0-L5 工程实现

#### L0-L3（C++实时层）

```cpp
// core/src/l0_sensing/capture_engine.hpp
class CaptureEngine {
    // 支持多种源：ADB scrcpy / MaaTools / 直接投屏
    // 输出：原始帧 (cv::Mat) + 时间戳
    // 性能目标：144Hz捕获，零分配循环
};

// core/src/l2_motor/action_executor.hpp
class ActionExecutor {
    // 抽象操作：DeployOperator, UseSkill, Retreat等
    // 后端实现：ADB点击 / Win32 SendMessage / 物理机械臂(未来)
    // 支持操作队列与撤销 (用于调试)
};
```

#### L4（状态机）

```cpp
// core/src/l4_state/game_fsm.hpp
// 基于Boost.MSM或自定义状态机
enum class GameState {
    PREPARATION,    // 选卡/部署前
    COMBAT,         // 战斗中
    PAUSED,         // 暂停（战术规划）
    ENDED           // 结算
};

class GameStateManager {
    // 对局存档序列化（用于LLM上下文）
    json snapshot() const;
    void restore(const json& snapshot);
};
```

#### L5（Python推理层）

```python
# inference/aam_llm/core/l5_controller.py
class L5Controller:
    """
    L5: 战略决策层
    - 接收L4状态快照
    - 调用VLM(视觉语言模型)或LLM
    - 输出L3可执行战术指令
    """
    def __init__(self, model_endpoint: str):
        self.vision_client = VisionAPIClient(endpoint)
        self.tactical_planner = TacticalPlanner()
        
    async def decision_loop(self, l4_state: GameSnapshot) -> TacticalCommand:
        # 流式推理支持
        context = self.build_prompt(l4_state)
        async for chunk in self.vision_client.stream_analyze(context):
            yield self.parse_tactical(chunk)
```

---

## 三、构建系统工程方案

### C++部分（CMake + vcpkg）

```cmake
# core/CMakeLists.txt
cmake_minimum_required(VERSION 3.25)
project(AAMCore CXX)

# 严格标准
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# 编译器特定优化
if(MSVC)
    add_compile_options(/W4 /WX /permissive- /Zc:__cplusplus)
else()
    add_compile_options(-Wall -Wextra -Wpedantic -Werror -march=native)
endif()

# 模块化处理L0-L4
add_subdirectory(src/l0_sensing)
add_subdirectory(src/l1_signal)
add_subdirectory(src/l2_motor)
add_subdirectory(src/l3_tactical)
add_subdirectory(src/l4_state)

# 统一接口库
add_library(aam_core INTERFACE)
target_link_libraries(aam_core INTERFACE 
    aam_l0 aam_l1 aam_l2 aam_l3 aam_l4)
```

### Python部分（Poetry + Mypy严格模式）

```toml
# inference/pyproject.toml
[tool.poetry]
name = "aam-llm"
version = "0.1.0"
description = "Arknights Auto Machine L5 Inference Backend"

[tool.poetry.dependencies]
python = "^3.11"
grpcio = "^1.60"
numpy = "^1.26"
opencv-python = "^4.9"
pillow = "^10.0"
openai = "^1.0"  # 或其他LLM SDK
pydantic = "^2.5"

[tool.poetry.group.dev.dependencies]
pytest = "^7.4"
mypy = "^1.7"
black = "^23.0"
ruff = "^0.1"

[tool.mypy]
strict = true
disallow_untyped_defs = true
warn_return_any = true
```

### 协议生成（自动化）

```bash
# tools/protobuf_codegen.py
# 生成：
# - C++ headers/impl (grpc_cpp_plugin)
# - Python stubs (grpc_python_plugin + mypy_protobuf)
# - TypeScript definitions (用于Web调试界面)
```

---

## 四、开发路线图

### Phase 1: 基础设施（Week 1-2）
- [ ] 仓库脚手架搭建（CI/CD矩阵：Windows/ Linux/ macOS）
- [ ] Protobuf接口定义冻结（L0-L5数据契约）
- [ ] C++核心编译系统（CMake + vcpkg manifest）
- [ ] Python推理服务基础架构（FastAPI/gRPC）

### Phase 2: L0-L2 感知-运动层（Week 3-5）
- [ ] **L0**: 多源捕获引擎（ADB/ scrcpy/ MaaTools适配器）
- [ ] **L1**: GPU加速图像流水线（OpenCV CUDA/OpenCL）
- [ ] **L2**: 操作抽象与物理仿真（点击确认回环）
- [ ] IPC性能基准：144Hz帧传输延迟<5ms

### Phase 3: L3-L4 战术-状态层（Week 6-8）
- [ ] **L3**: 战术原语实现（干员部署/技能释放/撤退）
- [ ] **L4**: 游戏状态机与对局存档系统
- [ ] 地图数据库集成（PRTS数据解析器）
- [ ] 单元测试覆盖>80%（GTest + Pytest）

### Phase 4: L5 推理层与GUI（Week 9-12）
- [ ] **L5**: LLM/VLM连接器（支持OpenAI/ Claude/ 本地模型）
- [ ] **GUI**: Qt6基础界面（地图可视化/干员面板）
- [ ] **GUI**: WPF高级界面（Windows专属/ 更优视觉效果）
- [ ] 端到端集成测试（1-7关卡全自动通关）

### Phase 5: 工程化强化（Week 13+）
- [ ] 性能剖析与内存优化（C++热点函数）
- [ ] 模型量化与边缘部署（TensorRT/ ONNX Runtime）
- [ ] 遥测系统（匿名使用数据收集）
- [ ] 插件系统（支持社区自定义战术）

---

## 五、关键工程决策（ADR）

### ADR-001: 为什么C++处理L0-L4而非纯Python？
- **实时性要求**：屏幕捕获→操作执行需<50ms延迟，Python GIL无法满足144Hz场景
- **资源占用**：C++核心内存占用<200MB，Python推理独立进程避免影响主循环

### ADR-002: 多GUI支持策略
- **Qt6**: 主要开发目标，Linux/macOS/Windows跨平台
- **WPF**: Windows原生体验，通过C++/CLI桥接共享C++核心，避免性能损失

### ADR-003: 通信协议选择
- **避免直接Python-C++绑定**（pybind11仅用于测试）
- **独立进程+IPC**：Python推理崩溃不影响游戏控制核心，符合安全隔离原则

### ADR-004: 构建系统版本锁定
- C++依赖通过`vcpkg.json`锁定版本
- Python通过`poetry.lock`确保可复现构建
- Docker镜像用于CI环境固化

---

## 六、质量保证体系

```yaml
# .github/workflows/ci.yml 关键配置
strategy:
  matrix:
    os: [windows-2022, ubuntu-22.04, macos-14]
    build_type: [Debug, Release]
    gui: [Qt, None]  # WPF仅Windows测试
    
jobs:
  cpp-check:
    - uses: cpp-linter/cpp-linter-action@v2  # clang-tidy
    - run: ctest --output-on-failure -j$(nproc)
    
  python-check:
    - run: mypy inference/
    - run: pytest --cov=aam_llm --cov-report=xml
```