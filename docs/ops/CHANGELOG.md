---
name: 变更日志
description: 按时间倒序记录用户/开发者可见的变更 — 追加式,不删除旧条目
last_updated: 2026-05-06
owner: superxiaoyin
---

# CHANGELOG

> **格式**:[Keep a Changelog](https://keepachangelog.com/) 风格。
> **更新规则**:追加新版本到顶部,旧条目**永不修改**。技术细节流水账在 [../../DEVLOG.md](../../DEVLOG.md)。

---

## [Unreleased]

### In Progress
- Template mode 二轮视觉密度优化，目标收敛 `V007` 大面积留白。
- `competitor-web` 联网搜索 + TABLE 模板接入。
- Outline 页数一致性 gate：project3 出现 LLM 声明 40 页、实际 39 页。

---

## 2026-05-06 — 跨素材包 E2E 验证与素材映射修复

### Changed
- P0 已清零后，下一步先进入跨素材包稳定性验证，而不是直接修改 P1 视觉模板。
- 验证对象扩展到 `test_material/project2` 与 `test_material/project3`，两次均使用完整 real-LLM + RunningHub + template mode 流程。

### Fixed
- 补齐 project2/project3 素材文件名别名：`场地四至`、`参考案例N_详情`、`GDP及其增速`、`常驻人口及其增速`、`城镇化率`、`产业结构`、`第三产业发展情况及其产业增速`、`消费品零售总额发展情况`、`城镇居民人均收支情况`、`外部道路交通`。
- 经济类 PNG 现在推断为 `chart`，并在 `derive_assets_from_items()` 中和 `chart_bundle` 一样派生 `Asset`；修复 LLM 把 `economy.city.chart.0` 等 logical_key 当作图片路径导致 `embed_image: path does not exist` 的问题。

### Verified
- `test_material/project2` 完整 real E2E 通过：

```text
output_dir: D:\projects\PPT_Agent\tmp\template_project2_real_verify\run_20260506T085641Z
project_id: 2c0a19c9-e39d-4dc6-abf4-aea8a023c39a
generate_outline: ok (40 pages)
concept_render: ok (total=9, generated=9, placeholders=0)
compose_slides: ok (40 slides; template=38, html=2)
template_quality: ok (critical_issues=0, warnings=0)
vision_review: PASS=11, P2=29; rules V007=23,V001=5,V004=6
export_pdf: ok (deck.pdf, 31.6 MB)
```

- `test_material/project3` 完整 real E2E 通过：

```text
output_dir: D:\projects\PPT_Agent\tmp\template_project3_real_verify\run_20260506T091205Z
project_id: 53fa4386-a706-43b0-9c10-96a3c14fd968
generate_outline: ok (39 pages; LLM first declared 40, actual outline count was 39)
concept_render: ok (total=9, generated=9, placeholders=0)
compose_slides: ok (39 slides; template=37, html=2)
template_quality: ok (critical_issues=0, warnings=0)
vision_review: PASS=16, P2=23; rules V007=18,V001=3,V004=2,V002=1
export_pdf: ok (deck.pdf, 26.3 MB)
```

- 两个项目的 `slides_spec.json` 均未再出现 `economy.*` 或 `misc.png.*` 作为图片路径；Slide 10/11/12 已使用真实 Asset id 引用经济图表。
- 两个项目的概念图均为 RunningHub 真实输出：鸟瞰图进入 `concept_scheme`，外/内人视图进入 `image_grid`。
- `tests/unit/test_material_pipeline.py`：`7 passed`。

### Known Issues
- `V007` 仍是系统性主问题：project2 为 23 条，project3 为 18 条，下一步应优先做模板密度二轮优化。
- Slide 5 在 project2/project3 中均因 template-mode JSON 失败兜底为 HTML；Slide 22 仍因 `competitor-web` 未接入 web search/TABLE 而兜底为 HTML。
- project3 的 outline 产生 39 页而不是目标 40 页，需要加页数一致性 gate 或明确允许变长。

---

## 2026-05-05 — P0 概念图严格验收

### Added
- `agent.concept_render.run_concept_render()` 新增 strict mode；当任何概念图仍为 placeholder 时抛出 `ConceptRenderStrictError`，真实 E2E 不再把 placeholder 当成功。
- 概念图生成支持复用已有成功 RunningHub asset；重跑时不会清空已成功的 8 张图，只补失败/缺失项。
- RunningHub 单图生成增加有限重试；默认 poll timeout 从 `180s` 提升到 `360s`。
- `scripts/material_package_e2e.py` 新增 `--allow-concept-placeholders`，真实 LLM E2E 默认启用 strict concept gate。

### Fixed
- 修复上次全量 E2E 的 Slide 38 placeholder：重新生成 `concept.3.int_perspective`，更新 slide 38 的 asset refs，并重渲染 `slide_38.png` 与 `deck.pdf`。

### Verified
- 对项目 `566bfb67-eca0-4743-96f3-e184232128f9` 执行 strict retry：`total=9`,`generated=9`,`placeholders=0`,`reused=8`。
- DB 中 9 个 `concept.*` asset 均为 `status=ready`、`source=runninghub`，本地文件均存在。
- `tests/integration/test_concept_render.py`：`5 passed`。
- `tests/unit/test_runninghub.py tests/unit/test_concept_prompts.py`：`14 passed`。

---

## 2026-05-04 — Template Pack 全量真实验证与内容接入修复

### Added
- Template mode 全量质量门禁：`template_quality_report.json` 检查 prompt marker、generic HTML fallback、concept_scheme 缺图、image_grid 重复图等关键问题。
- POI chart 物化 fallback：当 `site.poi.table` 缺少 `preview_rows` 时，从原始 XLSX `source_path` 只读解析预览行并生成 chart PNG。
- `concept-perspective` 模板接入：外视角/内视角两张 RunningHub 图通过 `image_grid` 进入 slide，而不是继续留在 HTML/free path。
- `concept-aerial` 数据装配：RunningHub 鸟瞰图进入 `concept_scheme`，并带入方案名称、设计理念和分析文案。

### Changed
- Template Composer 改为优先读取 `brief.design_outline.source_path` 的完整大纲/设计文本，避免只依赖资产摘要造成正文泛化。
- 政策页分页修复：`policy-1` / `policy-2` 按真实政策条目拆分，不再在第二页重复第一页内容。
- 经济背景、场地背景、POI 等页面按 raw slot id 与 supplemental logical_key 精确选素材，减少跨页串图和内容重复。
- 模板基础字号和密度第一轮上调，覆盖 `viewport-base.css`、`policy_list`、`content_bullets`、`image_grid`、`table`。
- `render_slide_template` 使用章节 divider 推导显示章节编号，减少模板页码/章节显示错位。
- Mock E2E 覆盖 template LLM，并在 mock 模式跳过外部视觉审查，便于快速检查数据装配和模板渲染。

### Fixed
- 修复任务提示词进入正文的问题：全量真实 E2E 未再出现 `[Material Package E2E]`、`调用 Nanobanana`、`联网搜索` 等指令痕迹。
- 修复“内容完全没有参考大纲”的核心路径：文化特征、场地综合、项目定位等页面已能抽取大纲内容。
- 修复经济背景/场地背景多页重复素材的问题：Slide 10/11/12 分别使用城市经济、产业发展、消费水平 chart，Slide 14-17 分别绑定场地四至、外部交通、枢纽/基础设施、区域开发相关资产。

### Verified
- 完成一次 41 页真实全流程：

```text
output_dir: D:\projects\PPT_Agent\tmp\template_full_real_verify\run_20260504T094923Z
mode: real-llm
generate_visual_theme: ok
generate_outline: ok (41 pages)
concept_render: ok (total=9, generated=8, placeholders=1)
compose_slides: ok (41 slides; template=40, html=1)
template_quality: ok (critical_issues=0)
render_and_review: ok (41 rendered)
export_pdf: ok (deck.pdf)
```

- 最新 targeted 测试通过：`47 passed`。
- `slides_spec.json` 模式分布：`template=40`，`html=1`。唯一 HTML 页是 Slide 22 `competitor-web`，原因是联网搜索/TABLE 接入未完成。
- `template_quality_report.json`：`critical_issues=[]`,`warnings=[]`。
- RunningHub 概念图实测：`8/9` 张真实图进入 slide，`concept.3.int_perspective` 因 180 秒超时降级 placeholder。

### Known Issues
- 视觉审查仍有 `28/41` 页 P2，主要是 `V007` 大面积留白。
- Slide 31/34/37 概念大图文字压复杂背景，存在 `V004` 可读性问题。
- Slide 38 右侧仍为“生成失败” placeholder。
- Slide 22 `competitor-web` 仍是 HTML 模式，待 web search + TABLE 模板化。

---

## 2026-04-21 — Concept Render 管线(ADR-005)

### Added
- **Concept Render 管线步骤**:Outline 之后、Material Binding 之前,产出 9 张概念建筑表现图(3 方案 × 鸟瞰/外视/内视)
- `schema/concept_proposal.py` — `ConceptProposal` 结构化方案描述 + `ConceptViewKind` 枚举 + `concept_logical_key(index, view)`
- `agent/concept_render.py` — 编排器,方案间并行、视图间串行链式(denoise 0.75→0.60→0.50,前图做下一视图的参考)
- `tool/image_gen/runninghub.py` — runninghub 异步 REST 客户端(upload / create / poll / outputs / download)
- `tool/image_gen/concept_prompts.py` — 3 视图 prompt 模板
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
