---
name: ADR-002 — Celery 链替代 LangGraph
description: 主流程从 LangGraph 切换到 Celery 链,删除 agent/graph.py
status: Accepted
date: 2026-04-06
owner: superxiaoyin
---

# ADR-002:Celery 链替代 LangGraph,删除 graph.py

## Context

项目存在两套编排路径:

1. **`agent/graph.py`(LangGraph)** — 设计阶段产物,有完整的 review → render 条件回环,但**从未被主流程调用**
2. **`api/routers/outlines.py` + Celery 任务链** — 实际运行路径,当时缺少 review → render 回环

问题:
- 规则层修了 spec 但不重新 render,用户看到的截图/PDF 是旧的
- 语义层 `repair_actions`(如 S007 替换甲方名称)被收集但未执行
- `/repair` 接口只是重跑 review,语义与行为不符
- `graph.py` 与实际流程已分叉(缺少 `material_binding`、`brief_doc`)

## Options Considered

| 方案 | 评估 |
|------|-----|
| A:切主流程到 LangGraph,删 Celery 编排 | 高风险重写,graph 节点与当前 agent 代码已分叉,需大幅重构 |
| B:在 Celery 链补全 review → render 回环,删 graph.py | 低风险,回环逻辑不复杂,Celery 完全能表达 |
| C:保留双路径,graph.py 备用 | 维护两套编排成本高,新人 / Agent 容易迷惑 |

## Decision

**选 B**:补全 Celery 链路,删除 `agent/graph.py`。

## Consequences

### 好处
- 消除双路径维护负担
- 新人 / Coding Agent 只需理解一条编排链
- Celery 的可观测性(Flower)直接可用,无需额外工具

### 代价
- 失去 LangGraph 的可视化状态图
- 未来若需要复杂条件分支编排,可能需要重新引入

### 实施清单
- ✅ `tasks/review_tasks.py` — 加回环触发逻辑
- ✅ `tasks/render_tasks.py` — 支持 `slide_nos` 过滤 + `review_after` 参数
- ✅ `api/routers/render.py` — `/repair` 改为 render + review
- ✅ `agent/critic.py` — 执行语义层 repair_actions
- ✅ `agent/graph.py` — **已删除**(验证日 2026-04-20:代码树中不存在)

### 来源
- [../../23_review_render_loop_fix.md](../../23_review_render_loop_fix.md)
