# services - 服务定义

## 目录说明

本目录包含 AAM 系统对外暴露的 gRPC 服务定义，包括主控制服务和调试服务。

## 文件说明

### control_service.proto
**主控制服务**

系统核心控制接口，提供启动/停止/配置等功能:

```protobuf
service AAMControl {
  // 系统生命周期
  rpc Initialize(InitConfig) returns (InitResponse);
  rpc Start(StartRequest) returns (StartResponse);
  rpc Stop(StopRequest) returns (StopResponse);
  rpc Shutdown(Empty) returns (ShutdownResponse);
  
  // 配置管理
  rpc GetConfig(ConfigKey) returns (ConfigValue);
  rpc SetConfig(ConfigUpdate) returns (ConfigResponse);
  rpc ReloadConfig(Empty) returns (ConfigResponse);
  
  // 状态监控
  rpc GetSystemStatus(Empty) returns (SystemStatus);
  rpc StreamStatus(Empty) returns (stream StatusEvent);
  
  // 对局控制
  rpc StartMission(MissionConfig) returns (MissionResponse);
  rpc PauseMission(Empty) returns (MissionResponse);
  rpc ResumeMission(Empty) returns (MissionResponse);
  rpc AbortMission(Empty) returns (MissionResponse);
}
```

### debug_service.proto
**调试服务**

开发和诊断接口，用于远程调试和性能分析:

```protobuf
service AAMDebug {
  // 日志流
  rpc StreamLogs(LogFilter) returns (stream LogEntry);
  rpc GetLogs(LogQuery) returns (LogBatch);
  
  // 性能分析
  rpc GetPerformanceMetrics(Empty) returns (PerformanceMetrics);
  rpc StartProfiling(ProfileConfig) returns (ProfileResponse);
  rpc StopProfiling(Empty) returns (ProfileResult);
  
  // 状态快照
  rpc CaptureSnapshot(Empty) returns (ama.l4.GameSnapshot);
  rpc RestoreSnapshot(ama.l4.GameSnapshot) returns (RestoreResponse);
  
  // 手动操作（调试用）
  rpc ExecuteManualAction(ama.l2.ActionCommand) returns (ActionResult);
  rpc InjectEvent(DebugEvent) returns (InjectResponse);
}
```

## 服务端口

| 服务 | 端口 | 协议 | 用途 |
|---|---|---|---|
| AAMControl | 50051 | gRPC | 主控制 |
| AAMDebug | 50052 | gRPC | 调试接口 |
| WebSocket | 50053 | WS | 实时流（Web UI） |
| Prometheus | 9090 | HTTP | 指标暴露 |

## 认证与授权

生产环境启用 mTLS:

```protobuf
message AuthConfig {
  string client_cert_path = 1;
  string client_key_path = 2;
  string ca_cert_path = 3;
  bool require_mutual_tls = 4;
}
```

## 错误处理

统一错误码定义:

```protobuf
enum ErrorCode {
  ERROR_UNSPECIFIED = 0;
  ERROR_INVALID_ARGUMENT = 1;
  ERROR_NOT_FOUND = 2;
  ERROR_ALREADY_EXISTS = 3;
  ERROR_PERMISSION_DENIED = 4;
  ERROR_RESOURCE_EXHAUSTED = 5;
  ERROR_INTERNAL = 6;
  ERROR_NOT_IMPLEMENTED = 7;
  ERROR_UNAVAILABLE = 8;
}
```

## 相关工具

- [grpcurl](https://github.com/fullstorydev/grpcurl): 命令行 gRPC 测试
- [BloomRPC](https://github.com/bloomrpc/bloomrpc): GUI gRPC 客户端
- [grpcui](https://github.com/fullstorydev/grpcui): Web 界面 gRPC 测试
