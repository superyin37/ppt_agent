---
name: Handoffs 目录说明
description: Session handoff 文档的格式与索引 —— Agent 换会话 / 人员换班时的上下文交接
last_updated: 2026-04-20
owner: superxiaoyin
---

# Session Handoffs

> 一次开发会话结束时写,给**下一个自己 / 下一个 Agent / 下一个同事**无缝接手用。

---

## 何时写 handoff

- 结束一段连续开发(一天或一次会话),特别是 Agent 即将被清空上下文时
- 交接给另一个人
- 中断开发前(知道下次会隔一段时间才继续)

**不必每次都写**:trivial 改动(改了个字符串)不需要。

---

## 格式

文件名:`YYYY-MM-DD.md`(或 `YYYY-MM-DD-<slug>.md` 如一天多次)

**模板**:
```markdown
---
date: YYYY-MM-DD
owner: <本次会话主写人>
---

# Session Handoff — YYYY-MM-DD

## 1. 本次做了什么
一句话总结 + 关键改动列表

## 2. 当前状态
- 能跑什么 / 不能跑什么
- 未验证 / 待验证的点

## 3. 遇到的问题 + 当时的处理
- 哪些解决了 / 哪些 workaround / 哪些搁置

## 4. 下次推荐从哪开始
- 最高价值的下一步是什么
- 具体命令 / 文件

## 5. 必读文件(给下次的自己 / Agent)
- 本次主要改动的核心文件
- 相关 bug / ADR 链接

## 6. 注意事项 / 陷阱
- 环境约束(Windows / Docker / API key)
- 容易踩的坑
```

---

## 与其他文档的关系

- **STATUS.md**:覆写当前真相。handoff 是"当时真相的快照"
- **CHANGELOG.md**:面向用户 / 版本的变更。handoff 面向**下一个开发者**,可以写"尝试过但放弃"的路径
- **postmortems**:专门为事故写。handoff 是日常交接

---

## 索引(按时间倒序)

| 日期 | 主题 | 主写人 |
|------|------|-------|
| [2026-04-05](2026-04-05.md) | 素材包管线 + Composer v3 初步落地 + Visual Theme 修复 | superxiaoyin |

---

## 规则

- handoff **永不修改**,只追加新的
- 每份 handoff **独立完整**,不要"见上一份"—— 下次会话的 Agent 可能只读最新一份
- 写的时候**假设读者没有任何上下文**,但了解项目基本架构
