---
name: 变更日志
description: 按时间倒序记录用户/开发者可见的变更 — 追加式,不删除旧条目
last_updated: 2026-04-21
owner: superxiaoyin
---

# CHANGELOG

> **格式**:[Keep a Changelog](https://keepachangelog.com/) 风格。
> **更新规则**:追加新版本到顶部,旧条目**永不修改**。技术细节流水账在 [../../DEVLOG.md](../../DEVLOG.md)。

---

## [Unreleased]

### In Progress
- 41 页 real-LLM 全量回归验证
- runninghub 真机 workflow 验证(本地仅覆盖 placeholder fallback 路径)

---

## 2026-04-21 — Concept Render 管线(ADR-005)

### Added
- **Concept Render 管线步骤**:Outline 之后、Material Binding 之前,产出 9 张概念建筑表现图(3 方案 × 鸟瞰/外视/内视)
- `schema/concept_proposal.py` — `ConceptProposal` 结构化方案描述 + `ConceptViewKind` 枚举 + `concept_logical_key(index, view)`
- `agent/concept_render.py` — 编排器,方案间并行、视图间串行链式(denoise 0.75→0.60→0.50,前图做下一视图的参考)
- `tool/image_gen/runninghub.py` — runninghub 异步 REST 客户端(upload / create / poll / outputs / download)
- `tool/image_gen/concept_prompts.py` — 3 视图 prompt 模板 + 共享 NEGATIVE_PROMPT + `denoise_for(view)`
- `tool/image_gen/placeholder.py` — 纯灰底 + "生成失败" 水印降级图
- `tasks/concept_render_tasks.py` + `concept_render` 专用 Celery 队列
- Outline 输出扩展 `concept_proposals`(`agent/outline.py`,`prompts/outline_system_v2.md`)
- `tests/unit/test_runninghub.py`(10 个用例,httpx MockTransport)
- `tests/integration/test_concept_render.py`(3 个用例:成功 / 全降级 / disabled)
- `.env.example` — 环境变量模板
- `docs/ops/decisions/ADR-005-concept-render-via-outline.md` — 架构决策

### Changed
- `config/ppt_blueprint.py` — 概念方案鸟瞰/人视图的 `required_inputs` 增加 `concept_aerial` / `concept_ext_perspective` / `concept_int_perspective`
- `tool/material_resolver.py` — `INPUT_ALIAS_PATTERNS` 增加 `concept_*` → `concept.*.{view}` 映射
- `scripts/material_package_e2e.py` — 在 Outline 之后调用 `run_concept_render`,新增 `--skip-concept-render` 开关
- `config/settings.py` — 新增 `concept_render_enabled` + `running_hub_*` 配置块(匹配 `.env` 既有命名约定 `RUNNING_HUB_*`)
- `tasks/celery_app.py` — 注册 `concept_render` 队列并 include `tasks.concept_render_tasks`

---

## 2026-04-07 — Review Loop v2

### Fixed
- HTML 模式 review 崩溃(`LayoutSpec.model_validate` 不兼容 html_mode spec)
- Review 写回覆盖 `body_html` 导致 HTML 内容丢失
- LLM 调用失败时审查静默通过(现在返回 `SEMANTIC_SKIPPED`/`VISION_SKIPPED`)
- HTML 模式回环空转(新增 `recompose_slide_html()`)
- fallback_spec phantom issues 导致回环 100% 不收敛(HTML 模式改为 vision-only)

### Added
- `prompts/composer_repair.md` — 专用 HTML 修复 prompt
- `agent/composer.py::recompose_slide_html()` — HTML 修复入口

详细:[postmortems/2026-04-07-review-loop-v2.md](postmortems/2026-04-07-review-loop-v2.md)

---

## 2026-04-06 — Vision Review v2: Design Advisor

### Added
- 5 维度设计评分体系(color / typography / layout / focal_point / polish)
- 12 种设计建议代号(D001~D012)
- `schema/review.py::DesignAdvice`
- `db/models/review.py::design_advice_json` 列

### Changed
- `agent/critic.py::_design_review()` — 新增设计顾问模式
- Vision review 分为 Mode A(缺陷检测)/ Mode B(设计顾问)双模式

---

## 2026-04-05 — Composer v3 + Visual Theme 修复

### Added
- **Composer HTML 直出模式(v3)** — LLM 直接输出 body_html,绕过 LayoutSpec 中间层
- `render/html_sanitizer.py` — 过滤 `<script>`、事件处理器、`javascript:` URL
- `prompts/composer_system_v3.md` — HTML 模式系统 prompt
- `build_theme_input_from_package()` — 从素材包提取 dominant_styles/features
- E2E 脚本 `--composer-mode html|structured` 切换(默认 html)

### Fixed
- 视觉主题生成被 bypass,所有项目都是默认蓝黄配色
- Outline `total_pages` 字段与实际 slide 数不一致(42 vs 41)
- `openai/gpt-4.5` 无效模型导致 review 链失败
- `VisualThemeInput` 缺 `project_id` 字段

### Changed
- 模型配置:Composer 改为 `STRONG_MODEL`,Review 改为 `google/gemini-3.1-pro-preview`

---

## 2026-04-04 ~ 2026-04-05 — 素材包管线(M2 主里程碑)

### Added
- 素材包数据层:`MaterialPackage` / `MaterialItem` / `SlideMaterialBinding`
- `tool/material_pipeline.py` — 本地目录摄入、分类、派生 Asset
- `tool/material_resolver.py` — logical_key 匹配与展开
- `agent/material_binding.py` — 逐页素材绑定 + coverage_score
- `api/routers/material_packages.py` — 摄入/重新生成 API
- `scripts/material_package_e2e.py` — 10 步 E2E 验证脚本
- Migration `004_material_package_pipeline.py`

### Changed
- 所有核心 Agent(`brief_doc` / `outline` / `composer` / `critic` / `visual_theme`)适配素材包上下文
- `Composer` 消费页面级 binding,而非项目级 asset 概要

---

## 2026-04-06 — Review-Render 回环补全

### Changed
- 补全 Celery 链路中 review → render 回环(之前只在已弃用的 `graph.py` 中有)
- `/repair` 接口改为 render + review(之前仅 review)
- 新增 `screenshot_slides_batch()` 批量并发截图(单浏览器多 tab)
- 渲染流程:全部 slide 先生成 HTML → batch 截图 → 批量写回 DB(替代串行)

### Decision
- **删除 `agent/graph.py`** — 双路径维护成本高,见 [decisions/ADR-002](decisions/ADR-002-celery-over-langgraph.md)

---

## 更早期

见 [../../DEVLOG.md](../../DEVLOG.md) 和 [../17_development_progress.md](../17_development_progress.md)。

关键里程碑:
- **2026-03**:Composer v2 + LayoutSpec + 11 种布局原语
- **2026-03 初**:40 页蓝图 + Brief Doc Agent + Outline Agent v2
- **2026-02**:基础地基 + Tool 层 + FastAPI CRUD + Intake Agent
