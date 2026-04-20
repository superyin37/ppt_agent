---
name: 项目路线图
description: 按里程碑粒度的大方向规划 — 月度更新,不记录具体任务(那在 TODO.md)
last_updated: 2026-04-20
owner: superxiaoyin
---

# ROADMAP

> **更新规则**:季度/月度更新,里程碑完成后整段移入 `CHANGELOG.md`。具体任务分解在 [TODO.md](TODO.md)。

---

## 当前阶段:M3 — 功能补全与稳定化

**周期**:2026-04 ~ 2026-05
**目标**:让 40 页蓝图所有章节都有真实内容产出(不是占位),并稳定通过 review 回环。

### 关键指标
- 41 页全量 real-LLM 连续 3 次跑通,全部 slide PASS 或合理 SKIPPED
- 所有 P0/P1 bug 清零(见 [BUGS.md](BUGS.md))
- Nanobanana + web_search 至少二选一接入

---

## 已完成里程碑

### M1 — 基础闭环(2026-02 ~ 2026-03)
- 单体架构、DB schema、API 路由、Agent 骨架
- 单元测试覆盖 > 80%
- Celery 多队列编排

### M2 — 素材包管线(2026-03 ~ 2026-04-05)
- MaterialPackage → BriefDoc → Outline → Binding → Compose → Render → Review → PDF 全链路
- Composer 双模式(v2 结构化 + v3 HTML)
- Visual Theme 动态生成
- Design Advisor 5 维度评分
- Review-Render 回环 v2 修复(5 个 bug)
- 41 页 real-LLM 端到端验证通过

---

## 未来阶段(草案)

### M4 — 生产化与 UX(2026-05 ~ 2026-06,草案)
- 真实 OSS 存储
- 前端可视化流程(候选技术:React + FastAPI WebSocket)
- 增量/差异化再生成(用户只改部分内容,不全量重跑)
- 多用户 / 多项目并发
- 监控与可观测性(Flower 现有,可加 Prometheus/Grafana)

### M5 — 能力扩展(2026-Q3,草案)
- 建筑类型专项 Prompt 调优
- 案例库扩充至 100+
- PPTX 原生导出(非 PDF 转换)
- 移动端素材采集上游

---

## 不做清单(明确排除)

- **多语言 PPT 输出** — 当前仅中文,需求未明确
- **实时协作编辑** — 偏内容工具定位,不做文档协同
- **自研 LLM / 本地部署大模型** — 商业 API 策略优先
