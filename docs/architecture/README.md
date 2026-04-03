# 架构决策记录（ADR）

## 什么是ADR

架构决策记录（Architecture Decision Records）是轻量级的文档，用于捕获重要的架构决策及其上下文和后果。

## ADR索引

| 编号 | 标题 | 状态 | 日期 |
|---|---|---|---|
| ADR-001 | 为什么C++处理L0-L4而非纯Python | 已接受 | 2026-04 |
| ADR-002 | 多GUI支持策略 | 已接受 | 2026-04 |
| ADR-003 | 通信协议选择 | 已接受 | 2026-04 |
| ADR-004 | 构建系统版本锁定 | 已接受 | 2026-04 |

## ADR模板

创建新ADR时使用以下模板:

```markdown
# ADR-XXX: 标题

## 状态
- 提议（Proposed）
- 已接受（Accepted）
- 已弃用（Deprecated）
- 已替代（Superseded by ADR-YYY）

## 背景
描述驱动此决策的问题、约束和假设。

## 决策
明确描述决策内容。

## 后果

### 正面
- 好处1
- 好处2

### 负面/权衡
- 代价1
- 代价2

## 替代方案

### 选项A: ...
优点: ...
缺点: ...

### 选项B: ...
优点: ...
缺点: ...

## 相关
- 相关的ADR
- 相关的外部文档
```

## 决策流程

1. **识别**: 发现需要记录的架构决策
2. **讨论**: 在 GitHub Discussion 或 PR 中讨论
3. **编写**: 使用模板创建 ADR 草稿
4. **审查**: 团队审查，收集反馈
5. **接受**: 合并到主分支，状态改为"已接受"
6. **维护**: 决策变更时更新或创建新ADR

## 参考

- [ADR 组织网站](https://adr.github.io/)
- [Michael Nygard 的原始文章](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
