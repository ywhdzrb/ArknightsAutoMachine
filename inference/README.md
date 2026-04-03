# inference - Python 推理后端 (L5)

## 目录说明

本目录包含 L5 推理层的 Python 实现，负责 LLM/VLM 决策和高层视觉分析。

## 架构设计

```
inference/
├── src/                    # 源代码
│   ├── data/              # 数据层
│   ├── map/               # 地图分析
│   └── vision/            # 视觉分析
├── services/              # 服务封装
│   ├── grpc_server.py     # gRPC 服务
│   ├── websocket_server.py # WebSocket 服务
│   ├── l5_controller.py   # L5 决策主循环
│   └── llm_adapters/      # 多模型适配
├── models/                # AI 模型
│   ├── checkpoints/       # 模型权重
│   ├── training/          # 训练脚本
│   └── eval/              # 模型评估
└── tests/                 # 测试
```

## 技术栈

- **Python 3.11+**: 运行时
- **Poetry**: 依赖管理
- **gRPC**: 服务通信
- **OpenAI/Anthropic**: LLM API
- **ONNX Runtime**: 本地推理
- **Pydantic**: 数据验证

## 安装

```bash
# 安装 Poetry
pip install poetry

# 安装依赖
cd inference
poetry install

# 激活环境
poetry shell
```

## 服务启动

```bash
# 启动 gRPC 服务
python -m aam_llm.services.grpc_server

# 启动 WebSocket 服务
python -m aam_llm.services.websocket_server

# 启动完整服务
python -m aam_llm
```

## L5 决策流程

```
┌─────────────────────────────────────────┐
│           L5 Controller                 │
├─────────────────────────────────────────┤
│                                         │
│  1. 接收 L4 状态快照                     │
│     ↓                                   │
│  2. 构建提示词上下文                      │
│     ↓                                   │
│  3. 调用 LLM/VLM                        │
│     ↓                                   │
│  4. 解析战术指令                         │
│     ↓                                   │
│  5. 返回 L3 可执行命令                    │
│                                         │
└─────────────────────────────────────────┘
```

## 多模型支持

### 支持的模型

| 模型 | 类型 | 延迟 | 适用场景 |
|---|---|---|---|
| GPT-4V | 云端 | ~2s | 复杂决策 |
| Claude 3 | 云端 | ~1.5s | 长上下文 |
| LLaVA | 本地 | ~5s | 隐私敏感 |
| Qwen-VL | 本地 | ~3s | 中文优化 |

### 适配器模式

```python
# services/llm_adapters/base.py
from abc import ABC, abstractmethod

class LLMAdapter(ABC):
    @abstractmethod
    async def predict(
        self,
        image: bytes,
        context: dict
    ) -> TacticalCommand:
        pass

# services/llm_adapters/openai_adapter.py
class OpenAIAdapter(LLMAdapter):
    async def predict(self, image, context):
        response = await self.client.chat.completions.create(
            model="gpt-4-vision-preview",
            messages=self.build_messages(image, context)
        )
        return self.parse_response(response)
```

## 提示词工程

### 模板结构
```
system_expert.txt    # 系统角色定义
cot_format.txt       # CoT 格式规范
context_builder.py   # 上下文构建
```

### 示例提示词
```python
SYSTEM_PROMPT = """你是明日方舟自动化专家。
基于当前游戏状态，决定最优战术操作。

规则：
1. 优先部署先锋干员回费
2. 高威胁敌人提前准备技能
3. 保持防线稳定

输出格式必须是有效的 JSON。"""
```

## 数据层

### 目录结构
```
src/data/
├── cache/               # 本地缓存
│   ├── image_cache.py
│   └── model_weights/
├── database/            # 数据库
│   ├── manager.py       # SQLite/Redis 管理
│   └── schema.py        # 数据模型
├── models/              # 领域模型
│   ├── operator.py
│   ├── enemy.py
│   └── stage.py
└── providers/           # 数据源
    ├── github_provider.py
    └── prts_provider.py
```

## 视觉分析

### 模块说明
```
src/vision/
├── enhanced_gui_matcher.py    # 增强版 GUI 匹配
├── game_state_detector.py     # 游戏状态识别
├── gui_matcher.py             # 基础 GUI 匹配
├── squad_analyzer.py          # 编队分析
├── squad_recognizer.py        # 干员识别
└── text_locator.py            # 文本定位
```

## 配置

```yaml
# configs/inference/llm_providers.yaml
providers:
  openai:
    api_key: ${OPENAI_API_KEY}
    model: gpt-4-vision-preview
    max_tokens: 4096
    
  local:
    endpoint: http://localhost:11434
    model: llava:7b
```

## 测试

```bash
# 单元测试
poetry run pytest tests/unit/ -v

# 集成测试
poetry run pytest tests/integration/ -v

# 覆盖率
poetry run pytest --cov=aam_llm --cov-report=html
```

## 相关目录

- [core/](../core/): C++ 核心
- [bridge/](../bridge/): 语言桥接
- [proto/inference/](../proto/inference/): 协议定义
