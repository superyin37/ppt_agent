---
name: ops docs 入口
description: 运营类文档索引 + 六层框架说明 + 文档分层速查表
last_updated: 2026-04-20
owner: superxiaoyin
---

# PPT Agent — 运营文档(ops docs)

> 给团队成员和 Coding Agent 看的**动态文档**。架构/规范类静态文档仍在 [../](../)(01-28 号文档)。

---

## 文档分层速查表

```
我想知道...              →  看哪份文档
─────────────────────────────────────────────
这项目是干嘛的?          →  ../SUMMARY.md  或 ../README(若有)
现在状态如何?            →  STATUS.md
下一步做什么?            →  TODO.md
这个 bug 修过吗?         →  BUGS.md
为什么这样设计?          →  decisions/ADR-*.md
上次开发到哪了?          →  handoffs/(最新日期)
这个术语啥意思?          →  GLOSSARY.md
Agent 怎么上手?          →  CLAUDE.md
等我拍板的问题?          →  DECISIONS_NEEDED.md
重大 bug 复盘?           →  postmortems/
API / Schema / 审查规则? →  ../04_api_definition.md 等静态文档
```

---

## 六层框架

| 层 | 目的 | 变化频率 | 写入方式 | 文档 |
|----|------|---------|---------|------|
| **L1 入口** | 3 分钟找到一切 | 架构变时 | 覆写 | [README.md](README.md)、[CLAUDE.md](CLAUDE.md) |
| **L2 状态** | 今天的真实状态 | 每天 | **覆写** | [STATUS.md](STATUS.md)、[BUGS.md](BUGS.md) |
| **L3 计划** | 下一步做什么 | 每周 | 覆写 | [TODO.md](TODO.md)、[ROADMAP.md](ROADMAP.md)、[DECISIONS_NEEDED.md](DECISIONS_NEEDED.md) |
| **L4 历史** | 发生过什么 | 有事件时 | **追加** | [CHANGELOG.md](CHANGELOG.md)、[decisions/](decisions/)、[postmortems/](postmortems/)、[handoffs/](handoffs/) |
| **L5 规范** | 系统怎么运作 | 架构变时 | 覆写 | [../00_index.md](../00_index.md) 01-15 号 |
| **L6 Agent 上下文** | Agent 必读 | 不定 | 覆写 | [CLAUDE.md](CLAUDE.md)、[GLOSSARY.md](GLOSSARY.md)、[briefs/](briefs/) |

---

## 核心规则

1. **状态类永远覆写** — `STATUS.md`、`BUGS.md`、`TODO.md` 只保留当前真相,不堆积历史
2. **历史类永远追加** — `CHANGELOG`、`ADR`、`postmortems`、`handoffs` 不改旧条目,只加新的
3. **同一事实只在一处写** — 其他地方用链接,避免多源矛盾
4. **每份文档顶部必须有** `last_updated` + `owner` — 读者自己判断时效性
5. **过时内容不删除**,加 `[DEPRECATED]` 标注并指向新文档

---

## 快速更新路径(给自己的 checklist)

| 什么时候 | 更新哪些 |
|---------|---------|
| 每次大会话结束 | `handoffs/YYYY-MM-DD.md`(新建)+ `STATUS.md`(覆写) |
| 发现新 bug | `BUGS.md` 追加一行 |
| 修完一个 bug | `BUGS.md` 改状态;若是重大 bug 写 `postmortems/` |
| 完成一个 feature | `CHANGELOG.md` 追加 + `TODO.md` 删对应条目 |
| 做出架构决策 | `decisions/ADR-NNN-*.md` 新建 |
| 有等我拍板的问题 | `DECISIONS_NEEDED.md` 追加 |

---

## 与 `docs/` 其他文档的关系

- **`docs/01-15`** — 静态架构规范,本框架不动它们,只在需要时从 ops 里**链接**过去
- **`docs/16-28`** — 混合了设计/总结/bug 日志,**保留不动**,本框架从中**提炼关键信息**到 L2/L4
- **`docs/TODO.md`** — 已失效(只有 3 行),被本目录的 [TODO.md](TODO.md) 替代
- **根目录 `DEVLOG.md` / `SUMMARY.md`** — 作为长期文档保留,STATUS.md 指向它们作为"历史背景"
