---
name: Task Briefs 目录说明
description: 启动大任务前写给 Coding Agent 的任务简报 —— 给 Agent 对齐的快照上下文
last_updated: 2026-04-25
owner: superxiaoyin
---

# Task Briefs

> **给 Coding Agent 的"任务书"**。在把大活儿交给 Agent 之前,写一份 brief,让 Agent 对齐目标、约束、验收标准。

---

## 何时写 brief

- 准备让 Agent 独立完成一项工作量 > 2 小时的任务
- 任务有**明确的验收标准**和**多个可选实现路径**
- 任务跨多个文件 / 模块
- 需要**在 Agent 开始写代码之前就明确边界**,避免跑偏

**不必写**:
- 一眼能改完的小任务(直接对话里说)
- 纯探索性任务(让 Agent 先调研)

---

## 格式

文件名:`YYYY-MM-DD-<task-slug>.md`

**模板**:
```markdown
---
date: YYYY-MM-DD
status: Draft | In Progress | Done | Abandoned
owner: <发起人>
assignee: <Agent 名 or 人名>
---

# Task Brief:<任务标题>

## 1. Goal(目标)
一句话:做到什么就算完成。

## 2. Context(背景)
为什么要做这个。关联哪个 P0/P1 todo、哪个 bug、哪个 user story。

## 3. Out of Scope(明确不做)
防止 Agent 过度发挥。

## 4. Constraints(约束)
- 必须用 XXX,不能用 YYY
- 不能破坏 ZZZ(现有功能 / 测试)
- API 调用必须经 config/llm.py
- ...

## 5. Acceptance Criteria(验收标准)
- [ ] 具体可测的 checkboxes
- [ ] 必须跑通某个命令
- [ ] 测试覆盖 xx%

## 6. Suggested Approach(建议路径)
非强制,可供参考。列 2-3 个候选方案让 Agent 选。

## 7. Relevant Files(相关文件)
- 主要改动:[file.py](../../../file.py)
- 参考实现:[other.py](../../../other.py)
- 不要动:[readonly.py](../../../readonly.py)

## 8. Questions / Risks
Agent 开工前可能要问清楚的点。

## 9. Updates(执行过程追记,可选)
Agent 开干后追加笔记:
- HH:MM 做了 X
- HH:MM 遇到 Y,改用 Z 方案
```

---

## 与其他文档的关系

| 文档 | 粒度 | 何时 |
|------|------|-----|
| **ROADMAP.md** | 季度里程碑 | 月度规划 |
| **TODO.md** | 单个 todo(P0/P1/P2) | 每周 |
| **brief(本目录)** | 单次 Agent 会话的任务书 | 启动 Agent 前 |
| **handoff** | 单次会话结束的交接 | Agent 会话结束后 |

---

## 索引

| 日期 | 状态 | 主题 | 对应 TODO |
|------|------|------|----------|
| [2026-04-20](2026-04-20-concept-render.md) | Draft | 概念方案建筑渲染图生成(runninghub image-to-image) | P1-2 |
| [2026-04-25](2026-04-25-html-bold-design-upgrade.md) | In Progress | HTML 默认化与 Bold Visual Design 升级 | P1-6 |

示例可用场景:
- 接入联网搜索(对应 TODO `P1-3`)
- 修复中文引号 JSON 解析(对应 BUG-007 / TODO `P1-4`)
- 串联 `tasks/outline_tasks.py` 的 brief_doc→outline 两步(对应 TODO `P1-5`)

---

## 规则

- brief 一旦指派给 Agent 就**不应再大幅修改方向**,发现方向错了就 `Abandoned` 状态 + 写新 brief
- brief 的 "Constraints" 部分直接翻译到 Agent prompt,**越精确 Agent 产出越稳**
- 完成后的 brief **保留不删**,作为该任务的历史档案
