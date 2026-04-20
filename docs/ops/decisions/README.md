---
name: ADR 目录说明
description: 架构决策记录(Architecture Decision Records)的格式与索引
last_updated: 2026-04-20
owner: superxiaoyin
---

# 架构决策记录(ADR)

> 记录"**为什么**这样设计"的文档。代码能告诉你"**怎么**做",ADR 告诉你"**为什么**"。

---

## 格式约定

每个决策一个文件:`ADR-NNN-<slug>.md`,编号递增不回收,slug 用连字符。

**文件模板**:
```markdown
---
name: ADR-NNN — <决策标题>
description: <一句话总结>
status: Proposed | Accepted | Superseded by ADR-XXX | Deprecated
date: YYYY-MM-DD
owner: <谁拍板的>
---

# ADR-NNN:<决策标题>

## Context(背景)
<当时面临什么问题,有什么约束>

## Options Considered(考虑过的选项)
- A:xxx
- B:xxx
- C:xxx

## Decision(决策)
选 B,原因...

## Consequences(结果)
- 好处:...
- 代价:...
- 未来如果 X 变化,可能需要重新评估
```

---

## 索引

| 编号 | 标题 | 状态 | 日期 |
|-----|------|------|------|
| [ADR-001](ADR-001-modular-monolith.md) | 采用模块化单体而非微服务 | Accepted | 2026-02 初 |
| [ADR-002](ADR-002-celery-over-langgraph.md) | Celery 链替代 LangGraph,删除 graph.py | Accepted | 2026-04-06 |
| [ADR-003](ADR-003-composer-dual-mode.md) | Composer 双模式共存(v2 结构化 + v3 HTML 直出) | Accepted | 2026-04-05 |
| [ADR-004](ADR-004-html-mode-vision-only.md) | HTML 模式审查只用 vision 层 | Accepted | 2026-04-07 |

---

## 规则

- **ADR 不修改旧版**。如果决策变了,新建一个 `Superseded by` 引用旧 ADR,旧 ADR 改 status 但内容保留
- **何时写 ADR**:做出"未来反悔成本高"的选择时,哪怕只是一句话(技术选型、架构取舍、废弃方案)
- **何时不写**:日常 bug 修复、小功能实现、重构
