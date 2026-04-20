---
name: Postmortems 目录说明
description: 重大 bug / 事故复盘的格式与索引
last_updated: 2026-04-20
owner: superxiaoyin
---

# Postmortems

> 复盘重大 bug 或事故。**目的不是追责,是防止重犯**。

---

## 何时写 postmortem

满足任一条件:
- **P0 bug**:阻塞核心链路的问题
- **多个 bug 联动**:如 review-loop v2 的 5 个 bug 一起修
- **反直觉的根因**:修复方案不是"直接改那一行",而是揭示了架构问题
- **花了 > 1 天**才定位 / 修复

**不写**:一眼能修的 typo、配置错误、明显的边界 case。

---

## 格式

文件名:`YYYY-MM-DD-<slug>.md`(日期是事件发生日,不是写文档日)

**模板**:
```markdown
---
name: <事件标题>
date: YYYY-MM-DD
severity: P0 | P1 | P2
status: Resolved | Monitoring | Ongoing
owner: <复盘主写人>
---

# <事件标题>

## Impact(影响)
- 用户 / 链路 / 数据的具体影响

## Timeline(时间线)
- HH:MM 发现
- HH:MM 初步定位
- HH:MM 修复
- HH:MM 验证

## Root Cause(根因)
不是"代码写错了",而是"为什么会写错 + 为什么没被测试 / 审查拦住"

## Fix(修复)
做了什么改动

## Lessons Learned(教训)
- 避免同类问题重犯的具体措施
- 需要改的工具 / 流程 / 文档

## Related(关联)
- BUG-ID(在 BUGS.md 的条目)
- ADR-NNN(若催生了架构决策)
- commit hashes
```

---

## 索引

| 日期 | 事件 | 严重度 | 状态 |
|------|------|-------|------|
| [2026-04-07](2026-04-07-review-loop-v2.md) | Review-Render 回环 v2 —— 5 个 bug 联动 | P0 | Resolved |
