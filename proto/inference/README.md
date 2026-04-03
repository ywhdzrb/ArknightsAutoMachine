# inference - L5 推理层协议

## 目录说明

本目录包含 L5 推理层（Python 后端）的协议定义，包括 LLM/VLM 交互和策略输出。

## 文件说明

### l5_strategy.proto
**L5 策略定义**

定义 LLM 输入输出格式:

#### 输入消息
```protobuf
message StrategyRequest {
  string request_id = 1;
  ama.l4.GameSnapshot current_state = 2;
  string objective = 3;              // 目标描述
  repeated TacticalHistory history = 4;
  StrategyConstraints constraints = 5;
}
```

#### 输出消息
```protobuf
message StrategyResponse {
  string response_id = 1;
  repeated ama.l3.TacticalCommand commands = 2;
  string reasoning = 3;              // CoT 思维链
  float confidence = 4;
}
```

### llm_stream.proto
**流式推理协议**

定义与 LLM 的双向流式通信:

```protobuf
service L5Inference {
  // 双向流式推理
  rpc StreamStrategy(stream StrategyChunk) 
    returns (stream StrategyChunk);
  
  // 单次推理
  rpc PredictStrategy(StrategyRequest) 
    returns (StrategyResponse);
}

message StrategyChunk {
  oneof content {
    StrategyRequest request = 1;
    StrategyResponse partial_response = 2;
    bytes image_data = 3;            // 分块图像传输
  }
}
```

## 多模型支持

协议设计支持多种 LLM 后端:

| 模型 | 特点 | 适配方式 |
|---|---|---|
| GPT-4V | 云端最强 | OpenAI API |
| Claude 3 | 长上下文 | Anthropic API |
| LLaVA | 本地开源 | Ollama/vLLM |
| Qwen-VL | 中文优化 | 本地部署 |

## 提示词模板

策略请求支持动态提示词:

```protobuf
message PromptTemplate {
  string system_prompt = 1;
  string context_format = 2;
  string instruction_format = 3;
  map<string, string> variables = 4;
}
```

模板文件存储于: `configs/inference/prompt_templates/`

## 图像传输优化

### 分块传输
大图像分块编码，避免内存峰值:
```protobuf
message ImageChunk {
  string transfer_id = 1;
  int32 chunk_index = 2;
  int32 total_chunks = 3;
  bytes data = 4;
}
```

### 动态分辨率
- 本地处理: 1920x1080（原始分辨率）
- LLM 输入: 448x448（降低 Token 数）
- ROI 裁剪: 仅发送关键区域

## 置信度与回退

```protobuf
message ConfidenceScore {
  float overall = 1;
  map<string, float> per_command = 2;
  
  // 低于阈值时触发回退策略
  float fallback_threshold = 0.7;
}
```

当置信度低于阈值时，L5 返回 `FALLBACK` 状态，L4 启用规则引擎保底。

## 相关目录

- [inference/](../../inference/): Python 推理后端实现
- [configs/inference/](../../configs/inference/): 推理配置模板
