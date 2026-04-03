# services - 推理服务

## 目录说明

本目录包含 L5 推理层的服务封装，提供 gRPC 和 WebSocket 接口。

## 服务架构

```
┌─────────────────────────────────────────┐
│           Service Layer                 │
├─────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    │
│  │ gRPC Server │    │  WebSocket  │    │
│  │   :50051    │    │   :50053    │    │
│  └──────┬──────┘    └──────┬──────┘    │
│         │                  │           │
│         └────────┬─────────┘           │
│                  ▼                     │
│         ┌─────────────┐                │
│         │ L5Controller│                │
│         │  (决策核心)  │                │
│         └──────┬──────┘                │
│                │                       │
│    ┌───────────┼───────────┐           │
│    ▼           ▼           ▼           │
│ ┌──────┐  ┌──────┐  ┌──────────┐      │
│ │ Open │  │Claude│  │  Local   │      │
│ │ AI   │  │      │  │  LLaVA   │      │
│ └──────┘  └──────┘  └──────────┘      │
└─────────────────────────────────────────┘
```

## gRPC 服务

### grpc_server.py

主控制服务实现:

```python
class L5InferenceServicer(inference_pb2_grpc.L5InferenceServicer):
    async def PredictStrategy(
        self,
        request: StrategyRequest,
        context: grpc.ServicerContext
    ) -> StrategyResponse:
        # 调用 L5 Controller
        return await self.controller.predict(request)
    
    async def StreamStrategy(
        self,
        request_iterator,
        context
    ):
        # 流式推理
        async for request in request_iterator:
            async for chunk in self.controller.stream_predict(request):
                yield chunk
```

### 启动服务

```python
async def serve():
    server = grpc.aio.server(
        options=[
            ('grpc.max_send_message_length', 50 * 1024 * 1024),
            ('grpc.max_receive_message_length', 50 * 1024 * 1024),
        ]
    )
    
    inference_pb2_grpc.add_L5InferenceServicer_to_server(
        L5InferenceServicer(), server
    )
    
    server.add_insecure_port('[::]:50051')
    await server.start()
    await server.wait_for_termination()
```

## WebSocket 服务

### websocket_server.py

实时流服务:

```python
class WebSocketHandler:
    async def handle(self, websocket, path):
        async for message in websocket:
            data = json.loads(message)
            
            if data['type'] == 'predict':
                result = await self.controller.predict(data)
                await websocket.send(json.dumps(result))
            
            elif data['type'] == 'stream':
                async for chunk in self.controller.stream_predict(data):
                    await websocket.send(json.dumps(chunk))
```

## L5 控制器

### l5_controller.py

决策主循环:

```python
class L5Controller:
    def __init__(self, config: L5Config):
        self.llm_adapter = self._create_adapter(config.provider)
        self.prompt_builder = PromptBuilder()
        self.command_parser = CommandParser()
    
    async def predict(
        self,
        state: GameSnapshot
    ) -> TacticalCommand:
        # 构建提示词
        prompt = self.prompt_builder.build(state)
        
        # 调用 LLM
        response = await self.llm_adapter.predict(
            image=state.screenshot,
            context=prompt
        )
        
        # 解析命令
        return self.command_parser.parse(response)
    
    async def stream_predict(self, state):
        # 流式返回
        async for chunk in self.llm_adapter.stream_predict(state):
            yield self.command_parser.parse_partial(chunk)
```

## LLM 适配器

### llm_adapters/openai_adapter.py

```python
class OpenAIAdapter(LLMAdapter):
    def __init__(self, api_key: str, model: str):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
    
    async def predict(self, image: bytes, context: dict) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": context['system']},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": context['prompt']},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=4096
        )
        return response.choices[0].message.content
```

### llm_adapters/claude_adapter.py

```python
class ClaudeAdapter(LLMAdapter):
    async def predict(self, image: bytes, context: dict) -> str:
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": base64_image,
                        },
                    },
                    {"type": "text", "text": context['prompt']},
                ],
            }]
        )
        return response.content[0].text
```

### llm_adapters/local_llava.py

```python
class LocalLLaVAAdapter(LLMAdapter):
    """本地 LLaVA 模型适配器（通过 Ollama）"""
    
    async def predict(self, image: bytes, context: dict) -> str:
        response = await self.ollama.chat(
            model='llava:7b',
            messages=[{
                'role': 'user',
                'content': context['prompt'],
                'images': [base64_image]
            }]
        )
        return response['message']['content']
```

## 健康检查

```python
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "llm_provider": controller.llm_adapter.name,
        "queue_size": controller.queue.qsize(),
        "uptime": time.time() - start_time
    }
```

## 监控指标

```python
# Prometheus 指标
PREDICTION_LATENCY = Histogram(
    'l5_prediction_latency_seconds',
    'Time spent on prediction',
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0]
)

PREDICTION_COUNT = Counter(
    'l5_predictions_total',
    'Total predictions',
    ['provider', 'status']
)
```

## 相关目录

- [inference/src/](../src/): 核心实现
- [proto/inference/](../../proto/inference/): 协议定义
