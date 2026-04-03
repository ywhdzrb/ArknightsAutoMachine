# 技术文档体系

## 目录说明

本目录包含 Arknights Auto Machine (AAM) 项目的完整技术文档，涵盖架构设计、API 文档和开发指南。

## 子目录结构

### architecture/
**用途**: 架构决策记录（ADR - Architecture Decision Records）

包含文件:
- ADR-001: 为什么C++处理L0-L4而非纯Python
- ADR-002: 多GUI支持策略
- ADR-003: 通信协议选择
- ADR-004: 构建系统版本锁定
- ...（更多ADR按序编号）

格式规范:
```markdown
# ADR-XXX: 标题

## 状态
- 提议 / 已接受 / 已弃用 / 已替代

## 背景
问题描述和约束条件

## 决策
明确决策内容

## 后果
正面影响和权衡

## 替代方案
其他考虑过的选项
```

### api/
**用途**: 接口契约文档

包含:
- OpenAPI 规范（REST API）
- gRPC proto 文档（自动生成）
- 内部模块接口说明

### 文件
- **dev-setup.md**: 开发环境搭建完整指南

## 文档规范

- 所有文档使用 Markdown 格式
- 架构文档必须包含决策理由和权衡分析
- API 文档与代码同步更新（通过 CI 检查）
- 图表使用 Mermaid 或 PlantUML 语法

## 贡献文档

修改文档时:
1. 同步更新相关 ADR（如架构变更）
2. 检查链接有效性
3. 遵循中文技术写作规范

## 相关资源

- [项目路线图](../develop_plan/ROADMAP.md)
- [基础架构设计](../develop_plan/main.md)
