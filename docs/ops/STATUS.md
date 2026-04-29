---
name: 项目当前状态
description: 当前能跑什么/不能跑什么/本周焦点/阻塞点 — 覆写式,只保留最新真相
last_updated: 2026-04-25
owner: superxiaoyin
---

# 项目当前状态

> **更新规则:覆写,不追加**。历史进度看 [../../DEVLOG.md](../../DEVLOG.md) 和 [handoffs/](handoffs/)。

---

## 今日一句话状态

项目已完整跑通 **素材包 → 41 页 PDF** 的全链路 real-LLM 流程,review 回环 v2 已修复。ADR-006 的 **HTML 默认化 + Bold Visual Design** 第一轮代码已接入;3 页 real-LLM smoke 已验证 HTML mode 与 PDF 导出,但 Design Advisor smoke 仍需加固。

---

## 能跑什么 ✅

| 能力 | 状态 | 验证方式 |
|------|------|---------|
| 素材包本地摄入 | ✅ | `scripts/material_package_e2e.py` step 1-2 |
| BriefDoc 生成 | ✅ | real-LLM 验证 2026-04-05 |
| Outline 生成(40 页蓝图驱动) | ✅ | page count 与实际 slide 一致 |
| Material Binding(逐页素材绑定) | ✅ | coverage_score 输出正常 |
| Composer HTML 模式(v3) | ✅ | `COMPOSER_MODE=html`;API/Celery 主入口显式传 `ComposerMode.HTML`;body_html 产出 + theme CSS 注入 |
| Composer Structured 模式(v2) | ✅ | LayoutSpec → 11 种布局 |
| Visual Theme 生成 | ✅ | 不再写死蓝黄配色 |
| Playwright 批量截图 | ✅ | batch `screenshot_slides_batch` 并发 4 |
| PDF 拼装 | ✅ | `render.exporter.compile_pdf()` |
| Review v2 回环(HTML 模式) | ✅ | recompose → re-render → re-review,最多 2 轮 |
| Design Advisor(5 维度评分) | ✅ | HTML 模式已接入低分 gate:`overall_score` / `focal_point` / `polish` / 重点页 `D012` 可触发 recompose |
| Celery 异步管线 | ✅ | 5 队列:default / outline / render / export / concept_render |
| **Concept Render(概念渲染)** | ✅ | ADR-005,runninghub 9 图生成,失败降级占位图 |
| 单元测试 | ✅ | 96+10 test functions × 12 files |
| 集成测试 | ✅ | 6+3 test functions × 2 files(需 DB) |

---

## 不能跑什么 ❌

| 缺口 | 严重度 | 指向 |
|------|-------|------|
| **联网搜索**未接入 | P1 | `tool/search/` 目录缺 `web_search.py`,蓝图中"背景研究""竞品分析"章节依赖它 |
| **PPTX 导出**未实现 | P2 | `python-pptx` 已在依赖中,无代码 |
| **真实 OSS 存储**未配置 | P2 | 开发走 `D:\tmp\` mock |
| **案例库**仍是占位 | P2 | `scripts/seed_cases.json` 未填真实案例 |
| `tasks/outline_tasks.py` 未串联 `brief_doc` | P2 | 目前 E2E 脚本手动串联 |
| 上游**移动端素材采集**超出 phase 1 范围 | — | 产品决策,不是技术缺口 |

---

## 已知数据口径(避免三处文档互相矛盾)

| 指标 | 值 | 来源 |
|------|-----|-----|
| 单元测试数 | **96+10 test functions × 12 files** | `tests/unit/` 实际代码,2026-04-21 新增 `test_runninghub.py` |
| 集成测试数 | **6+3 test functions × 2 files** | `test_project_flow.py` + 2026-04-21 新增 `test_concept_render.py` |
| pytest 实际运行数 | 因 parametrize 展开可能更多 | 以 `pytest --collect-only -q` 为准 |
| 蓝图总页数 | **40 页**(可变章节实际 41) | [config/ppt_blueprint.py](../../config/ppt_blueprint.py) |
| 布局原语数 | **11 种** | [schema/visual_theme.py](../../schema/visual_theme.py) |
| 内容块类型 | **13 种** | `_render_block()` |

⚠️ **旧文档中的 "117 tests"、"102 tests"、"131 tests" 数字均已过期**,以本表为准。

---

## 本周焦点

- [ ] **端到端再跑一次全量 real-LLM 41 页** — 距上次成功运行(2026-04-05)已 16 天,需确认 review 回环 v2 + 新增 concept_render 依然稳定
- [ ] 加固 **ADR-006 HTML 默认化 + Bold Visual Design** smoke — 已确认 3 页 `spec_json.html_mode=true` 与 PDF 导出;剩余处理 slide 01 Design Advisor 解析失败、slide 03 `V007` residual repair_required
- [ ] 补 web_search 外部工具,解锁蓝图中"背景研究""竞品分析"占位章节
- [ ] 申请 runninghub 正式 workflow_id / api_key,跑一次真机概念渲染端到端

## 阻塞点(Blockers)

详见 [DECISIONS_NEEDED.md](DECISIONS_NEEDED.md)。

---

## 运行环境关键约束(别忘了)

- **Windows Celery**必须 `--pool=solo`,生产 Linux 无此问题
- **Host 运行脚本**需 override `DATABASE_URL=...@localhost:5432/...`(`.env` 里写的是 docker 网络的 `@db:5432`)
- **Playwright** 在 sandbox 环境可能抛 `WinError 5`,换正常终端即可
- **`.env` 中 `LLM_CRITIC_MODEL`** 一定要是**有效 OpenRouter model ID**,配错了 review 会静默 SKIPPED

---

## 历史状态参考

- 2026-04-05 的详细交接见 [handoffs/2026-04-05.md](handoffs/2026-04-05.md)
- 完整开发阶段进度见 [../17_development_progress.md](../17_development_progress.md)(⚠️ 该文档停留在 2026-04-10,之后未更新)
