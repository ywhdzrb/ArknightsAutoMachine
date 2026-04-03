# configs - 配置文件

## 目录说明

本目录包含 AAM 项目的运行时配置模板，用户可基于此创建自己的配置。

## 目录结构

```
configs/
├── ama/                    # C++ 核心配置
│   ├── capture.yaml        # L0 捕获配置
│   ├── latency_budget.yaml # 延迟预算
│   └── input_profiles/     # 设备输入参数
├── inference/              # Python 推理配置
│   ├── llm_providers.yaml  # LLM 端点配置
│   └── prompt_templates/   # 提示词模板
└── gui/                    # GUI 配置
    ├── qt_theme.json       # Qt 主题
    └── wpf_settings.json   # WPF 设置
```

## 配置加载顺序

1. **默认配置**: 内置在代码中
2. **系统配置**: `/etc/aam/` (Linux) 或 `C:\ProgramData\AAM\` (Windows)
3. **用户配置**: `~/.config/aam/` (Linux) 或 `%APPDATA%\AAM\` (Windows)
4. **本地配置**: 当前目录 `./aam.yaml`
5. **命令行参数**: 最高优先级

## AMA 核心配置

### capture.yaml

```yaml
# L0 捕获配置
capture:
  backend: adb              # adb / maa / win32
  resolution: [1920, 1080]
  target_fps: 60
  
adb:
  device_id: "auto"         # auto 或具体设备ID
  bit_rate: 8000000
  max_fps: 60
  
maa:
  adb_path: "adb"
  
win32:
  window_title: "明日方舟"
  capture_method: "bitblt"  # bitblt / printwindow

# 共享内存配置
shm:
  buffer_size: "1GB"
  num_buffers: 2
```

### latency_budget.yaml

```yaml
# 各层延迟预算（毫秒）
latency_budget:
  l0_to_l1: 8        # 捕获到感知
  l1_to_l2: 5        # 感知到操作
  l2_to_l3: 2        # 操作到战术
  l3_to_l4: 10       # 战术到状态
  l4_to_l5: 100      # 状态到推理（首Token）
```

### input_profiles/

设备特定的输入参数:

```yaml
# rog_phone_8.yaml
input:
  backend: adb
  
humanization:
  tap_delay_mean: 80
  tap_delay_std: 15
  position_jitter: 5
  min_interval: 120
  
screen:
  resolution: [2448, 1080]
  refresh_rate: 165
  notch_height: 80
```

## 推理配置

### llm_providers.yaml

```yaml
# LLM 提供商配置
providers:
  openai:
    api_key: ${OPENAI_API_KEY}  # 从环境变量读取
    model: gpt-4-vision-preview
    max_tokens: 4096
    temperature: 0.7
    timeout: 30
    
  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
    model: claude-3-opus-20240229
    max_tokens: 4096
    
  ollama:
    endpoint: http://localhost:11434
    model: llava:7b
    
default_provider: openai
fallback_provider: ollama
```

### prompt_templates/

```
prompt_templates/
├── system_expert.txt       # 系统角色定义
├── cot_format.txt          # CoT 格式
└── tactical_dsl.txt        # 战术 DSL 说明
```

## GUI 配置

### qt_theme.json

```json
{
  "theme": "dark",
  "colors": {
    "primary": "#2196F3",
    "background": "#1E1E1E",
    "surface": "#2D2D2D",
    "text": "#FFFFFF"
  },
  "font": {
    "family": "Microsoft YaHei",
    "size": 12
  }
}
```

## 配置验证

```python
from pydantic import BaseModel, validator

class CaptureConfig(BaseModel):
    backend: str
    resolution: tuple[int, int]
    target_fps: int
    
    @validator('target_fps')
    def validate_fps(cls, v):
        if v < 1 or v > 240:
            raise ValueError('FPS must be between 1 and 240')
        return v
```

## 相关目录

- [core/](../core/): C++ 核心（配置消费者）
- [inference/](../inference/): Python 推理（配置消费者）
