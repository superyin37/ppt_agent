# PPT Agent — 开发进度总结

> 更新日期：2026-04-10
> 测试状态：**102 test functions**（96 unit × 11 files + 6 integration × 1 file）
> 实际 pytest 运行数因 `@pytest.mark.parametrize` 展开可能更多。

---

## 一、项目概况

PPT Agent 是一个面向建筑方案汇报的全自动 PPT 生成系统。用户提供素材包（图片、图表、文档），系统自动完成素材摄入、设计任务书生成、大纲策划、素材绑定、页面内容编排、视觉主题生成、HTML 渲染、截图、多层审查修复及 PDF 导出，输出一份符合 40 页结构标准的建筑方案汇报 PPT。

### 技术栈
- **后端**：FastAPI + SQLAlchemy + PostgreSQL (pgvector) + Celery + Redis
- **LLM**：OpenRouter（通过 `config/llm.py` 统一调用，STRONG_MODEL / FAST_MODEL / CRITIC_MODEL）
- **渲染**：动态 CSS + Python 拼接 HTML（结构化模式）/ LLM 直出 HTML（v3 模式）+ Playwright 截图
- **图像**：Nanobanana AI（待集成）
- **搜索**：联网搜索工具（待集成）
- **部署**：Docker Compose（api + worker + renderer + db + redis）

### 当前 LLM 模型配置

| 阶段 | 模型 |
|------|------|
| BriefDoc | `STRONG_MODEL`（claude-opus-4-6） |
| Outline | `STRONG_MODEL` |
| Composer | `STRONG_MODEL` |
| Semantic review | `CRITIC_MODEL`（google/gemini-3.1-pro-preview） |
| Vision review / Design advisor | `CRITIC_MODEL` |

---

## 二、已完成模块

### Phase 1 — 基础设施 ✅

| 文件 | 内容 |
|------|------|
| `config/settings.py` | Pydantic Settings，读取所有 .env 变量 |
| `db/base.py` + `db/session.py` | SQLAlchemy Base + Session 工厂 |
| `db/models/*.py` | 全部 ORM 模型（见下方数据库表清单） |
| `alembic/versions/001~004` | 数据库迁移（已执行至 004） |
| `schema/*.py` | 全部 Pydantic 模型 |
| `main.py` | FastAPI 入口，挂载所有路由 |
| `docker-compose.yml` | 完整服务编排 |

**数据库表（已建）：**
- `projects` / `project_briefs` — 项目与设计任务书
- `site_locations` / `site_polygons` — 场地信息
- `reference_cases` / `project_reference_selections` — 案例库与选择记录
- `assets` — 多类型资产（地图/图表/图片/文本）
- `outlines` — PPT 大纲
- `slides` — 单页规格与渲染结果
- `reviews` — 审查报告（含 `design_advice_json` JSONB 列）
- `jobs` — 异步任务记录
- `visual_themes` — 视觉主题（Migration 002）
- `brief_docs` — 设计建议书大纲（Migration 003）
- `material_packages` / `material_items` / `slide_material_bindings` — 素材包系统（Migration 004）

---

### Phase 2 — Tool 层 ✅

| 文件 | 功能 |
|------|------|
| `tool/input/compute_far.py` | FAR / GFA / 用地面积 互推计算 |
| `tool/input/validate_brief.py` | 设计任务书字段验证 |
| `tool/input/geocode.py` | 高德地图地理编码 |
| `tool/input/normalize_polygon.py` | 场地多边形标准化 |
| `tool/input/extract_brief.py` | 从自然语言中提取 ProjectBriefData |
| `tool/reference/search.py` | pgvector 向量检索案例 |
| `tool/reference/rerank.py` | 案例重排序 |
| `tool/reference/preference_summary.py` | 生成案例偏好摘要 |
| `tool/slide/content_fit.py` | 内容密度检测 |
| `tool/review/layout_lint.py` | 布局规则检查（无 LLM） |
| `tool/review/repair_plan.py` | 修复方案执行 |
| `tool/review/semantic_check.py` | 语义一致性检查（快速 LLM），含 SEMANTIC_SKIPPED 降级 |
| `tool/site/poi_retrieval.py` | 高德 POI 检索 |
| `tool/site/mobility_analysis.py` | 交通可达性分析 |
| `tool/asset/chart_generation.py` | matplotlib 图表生成 |
| `tool/asset/map_annotation.py` | 高德静态地图标注 |
| `tool/_oss_client.py` | OSS 文件上传 |

---

### Phase 3 — FastAPI + CRUD ✅

| 路由文件 | 提供的接口 |
|----------|-----------|
| `api/routers/projects.py` | `POST /projects`，`GET /projects/{id}`，`PATCH /brief`，`POST /confirm-brief` |
| `api/routers/sites.py` | `POST /site/point`，`POST /site/polygon` |
| `api/routers/references.py` | `POST /references/recommend`，`POST /references/confirm`（含触发 VisualTheme 生成） |
| `api/routers/assets.py` | 资产上传与查询 |
| `api/routers/outlines.py` | `POST /outline/generate`（Celery 任务），`GET /outline`，`POST /outline/confirm` |
| `api/routers/slides.py` | 单页查询与状态更新 |
| `api/routers/render.py` | 触发渲染任务 |
| `api/routers/exports.py` | 触发 PDF 导出 |
| `api/routers/material_packages.py` | 素材包摄入、重新生成（**Phase 9 新增**） |

---

### Phase 4 — LLM 层 + Intake Agent ✅

| 文件 | 内容 |
|------|------|
| `config/llm.py` | 统一 LLM 调用封装（`call_llm_with_limit` / `call_llm_structured`），OpenRouter 后端 |
| `agent/intake.py` | Intake Agent：多轮对话提取 ProjectBrief，支持追问 |
| `prompts/intake_system.md` | Intake 提示词（building_type 动态注入） |

---

### Phase 5 — 案例库 + Reference Agent ✅

| 文件 | 内容 |
|------|------|
| `scripts/seed_cases.py` | 案例库数据导入脚本 |
| `agent/reference.py` | Reference Agent：案例推荐 + 偏好摘要生成 |
| `tool/reference/_embedding.py` | 文本向量化 |

---

### Phase 6 — 资产生成 ✅

| 文件 | 内容 |
|------|------|
| `tasks/celery_app.py` | Celery 配置（default / export / render 三队列） |
| `tasks/asset_tasks.py` | 并发资产生成任务（地图/POI/图表） |

---

### Phase 7 — 视觉主题 + Composer + Render ✅（核心重构）

#### 视觉主题系统

| 文件 | 内容 |
|------|------|
| `schema/visual_theme.py` | VisualTheme 全部子系统（ColorSystem / TypographySystem / SpacingSystem / DecorationStyle / CoverStyle） + 11 种布局原语（LayoutPrimitive 辨别联合类型）+ LayoutSpec / ContentBlock / RegionBinding |
| `db/models/visual_theme.py` | visual_themes ORM |
| `agent/visual_theme.py` | 生成 + 读取 VisualTheme，含 `build_theme_input_from_package()` 辅助函数 |
| `prompts/visual_theme_system.md` | 视觉主题生成提示词（WCAG AA 色彩约束、字体选择指南） |

**11 种布局原语：**

| 原语 | 适用场景 |
|------|---------|
| `full-bleed` | 封面、章节页、大图展示 |
| `split-h` | 左图右文、左案例右分析 |
| `split-v` | 上下分区 |
| `single-column` | 正文、策略文字 |
| `grid` | KPI 卡片、指标矩阵、多图等分 |
| `hero-strip` | 大主视觉 + 下方内容条 |
| `sidebar` | 主内容 + 侧边注释/导航 |
| `triptych` | 三等分并排（三策略/三方案） |
| `overlay-mosaic` | 地图/大图 + 浮层分析标注 |
| `timeline` | 时间轴、流程图 |
| `asymmetric` | 非均等分割（强调一侧） |

#### Render Engine（完全重写）

| 文件 | 内容 |
|------|------|
| `render/engine.py` | `generate_theme_css(theme)` 动态 CSS 生成；`_render_block(block)` 13 种内容类型渲染；11 个 `_render_*` 布局函数；`render_slide_html(spec, theme, assets, deck_meta)` 主入口；HTML 直通分支支持 |
| `render/exporter.py` | Playwright 截图 + PDF 导出（`compile_pdf()` 支持批量 PNG → PDF） |
| `render/html_sanitizer.py` | HTML 安全层：过滤 `<script>`、事件处理器、`javascript:` URL、`@import`（**Phase 11 新增**） |

13 种内容类型：`heading` / `subheading` / `body-text` / `caption` / `label` / `bullet-list` / `numbered-list` / `image` / `chart` / `table` / `quote` / `kpi-card` / `divider`

#### Composer Agent（完全重写，双模式）

| 文件 | 内容 |
|------|------|
| `agent/composer.py` | `ComposerMode.STRUCTURED`（v2，LayoutSpec 中间层）+ `ComposerMode.HTML`（v3，LLM 直出 body_html）；`recompose_slide_html()` 用于 review 回环修复 |
| `prompts/composer_system_v2.md` | 结构化模式提示词（11 原语参数表 + 内容块类型表 + 视觉决策规则） |
| `prompts/composer_system_v3.md` | HTML 直出模式提示词（CSS 变量 + 1920x1080 画布 + SVG 装饰指引）（**Phase 11 新增**） |
| `prompts/composer_repair.md` | 审查反馈修复专用提示词（保留原始设计，只修复指出的问题）（**Phase 13 新增**） |

---

### Phase 7 续 — 40 页蓝图 + Brief Doc Agent + Outline Agent v2 ✅

#### 40 页 PPT 蓝图

| 文件 | 内容 |
|------|------|
| `schema/page_slot.py` | `PageSlot` / `PageSlotGroup` / `SlotAssignment` / `SlotAssignmentList` 模型 |
| `config/ppt_blueprint.py` | 完整 40 页蓝图（`PPT_BLUEPRINT` 列表），覆盖封面至结尾全部章节 |

**蓝图章节结构：**

| 章节 | 页数 | 生成方式 |
|------|------|---------|
| 封面 + 目录 | 2 页 | LLM_TEXT + NANOBANANA |
| 背景研究 | 11 页 | LLM_TEXT + WEB_SEARCH + CHART + ASSET_REF |
| 场地分析 | 7 页 | ASSET_REF + LLM_TEXT + CHART |
| 竞品分析 | 3 页 | WEB_SEARCH + LLM_TEXT + CHART |
| 参考案例 | 2~5 页（可变） | ASSET_REF + LLM_TEXT |
| 项目定位 | 1 页 | LLM_TEXT |
| 设计策略 | 2 页 | LLM_TEXT |
| 概念方案 | 9 页（3方案x3页） | NANOBANANA + LLM_TEXT |
| 深化比选 | 1 页 | LLM_TEXT + CHART |
| 设计任务书 | 1 页 | LLM_TEXT |
| 结尾 | 1 页 | LLM_TEXT |

#### Brief Doc Agent

| 文件 | 内容 |
|------|------|
| `db/models/brief_doc.py` | BriefDoc ORM（outline_json / slot_assignments_json / narrative_summary） |
| `alembic/versions/003_brief_doc.py` | 已执行迁移 |
| `agent/brief_doc.py` | 读取素材包上下文 → 调用 LLM → 生成设计建议书大纲（positioning_statement / design_principles / narrative_arc） |
| `prompts/brief_doc_system.md` | Brief Doc Agent 提示词 |

#### Outline Agent v2（重构）

| 文件 | 内容 |
|------|------|
| `agent/outline.py` | 蓝图驱动：展开 PPT_BLUEPRINT → 读取 BriefDoc → 为每个 slot 生成具体 content_directive（200~300 字）；`total_pages` 以实际生成数为准 |
| `prompts/outline_system_v2.md` | Outline v2 提示词（slot 列表注入、narrative_arc 注入） |

---

### Phase 8 — Critic Agent + LangGraph ✅（已更新适配）

| 文件 | 状态 | 说明 |
|------|------|------|
| `agent/critic.py` | ✅ 已更新 | 支持 LayoutSpec + HTML 模式；含 `_design_review()` 设计顾问；`_evaluate()` 区分 SKIPPED issue |
| `agent/graph.py` | ⚠️ 待更新 | render/review 节点仍用旧 `SlideSpec.model_validate`，需改为 `LayoutSpec` |
| `tasks/render_tasks.py` | ✅ | 已更新，支持新 LayoutSpec + 旧格式向后兼容 |
| `tasks/outline_tasks.py` | ⚠️ 待更新 | 未串联 `generate_brief_doc` → `generate_outline` 两步 |
| `tasks/review_tasks.py` | ✅ 已更新 | HTML 模式检测、spec 写回守卫、内联 recompose、vision-only 审查层 |
| `tasks/export_tasks.py` | ✅ | 功能完整 |

---

### Phase 9 — 素材包系统（Material Package）✅（2026-04-04 ~ 04-05 新增）

这是 3 月 21 日以来最大的新增功能，完整实现了"素材包 → PDF"新管线。

#### 数据模型层

| 文件 | 内容 |
|------|------|
| `db/models/material_package.py` | `MaterialPackage`（manifest_json / summary_json / source_hash）+ `MaterialItem`（logical_key / kind / text_content / structured_data） |
| `db/models/slide_material_binding.py` | `SlideMaterialBinding`（must_use_item_ids / derived_asset_ids / evidence_snippets / coverage_score / missing_requirements） |
| `alembic/versions/004_material_package_pipeline.py` | 新增三表 + 扩展 asset / brief_doc / outline / slide 表 |
| `schema/material_package.py` | 素材包相关 Pydantic 模型 |

#### 素材包处理管道

| 文件 | 内容 |
|------|------|
| `tool/material_pipeline.py` | `ingest_local_material_package()` 主入口：扫描目录 → 文件分类 → 创建 MaterialItem → `_derive_assets()` 派生 Asset → `_extract_project_brief()` 提取项目元信息 |
| `tool/material_resolver.py` | `expand_requirement()` 将 required_input_keys 展开为正则匹配模式；logical_key 匹配与展开 |

**素材分类逻辑：**

| MaterialItem kind | 派生 Asset Type | 说明 |
|-------------------|----------------|------|
| image（site.* 前缀） | MAP | 场地类图片 |
| image（其他） | IMAGE | 一般图片 |
| chart_bundle | CHART | 图表（JSON + SVG + HTML 变体） |
| spreadsheet | KPI_TABLE | 指标表格 |
| document | TEXT_SUMMARY | 文本摘要 |
| 参考案例聚合 | CASE_CARD | 多张图片 + 分析文本 + 来源 |

**ProjectBrief 自动提取（从素材包的设计建议书大纲文档）：**
- 地理信息：city / province / district / site_address（正则提取）
- 建筑类型：关键词匹配（公厕 → public, 办公 → office, 住宅 → residential 等）
- 风格偏好：style_preferences 关键词检测（现代 / 极简 / 生态 / 科技等）
- 容积率：FAR 数值提取

#### 素材绑定层

| 文件 | 内容 |
|------|------|
| `agent/material_binding.py` | `bind_materials()` 逐页绑定：将 Outline 每页的 required_input_keys 展开 → 正则匹配 MaterialItem → 查找匹配 Asset → 计算 coverage_score |

#### Agent 层更新

所有核心 Agent 已适配素材包上下文：

| Agent | 改动 |
|-------|------|
| `agent/brief_doc.py` | 消费素材包清单和文本摘录生成 BriefDoc |
| `agent/outline.py` | 消费素材包 + 蓝图，写入 coverage / binding hints |
| `agent/composer.py` | 消费页面级 SlideMaterialBinding，而非项目级 asset 概要 |
| `agent/critic.py` | 支持新布局流程，含模型无效时的安全降级 |
| `agent/visual_theme.py` | `build_theme_input_from_package()` 从素材包提取 dominant_styles / features |

#### API 路由

| 路由 | 端点 |
|------|------|
| `api/routers/material_packages.py` | `POST /material-packages/ingest-local`（素材摄入）、`POST /material-packages/{id}/regenerate`（重新生成） |
| `api/routers/outlines.py` | 新增 `POST /outline/confirm` + compose_render_worker 后台线程 |

#### E2E 验证脚本

| 文件 | 内容 |
|------|------|
| `scripts/material_package_e2e.py` | 完整 10 步验证：create project → ingest → BriefDoc → Outline → confirm → bind → compose → render → review → PDF export；支持 `--real-llm` / `--composer-mode html|structured` / `--design-review` / `--max-slides N` |

---

### Phase 10 — 视觉主题 & Pipeline Gap 修复 ✅（2026-04-05 新增）

**问题**：新素材包管线绕过了旧管线中 `confirm_references` 触发的 `generate_visual_theme()`，导致所有项目都用默认蓝黄配色。

**修复内容：**

| 改动 | 说明 |
|------|------|
| `tool/material_pipeline.py` | `_extract_project_brief()` 增强：从设计大纲文档解析 city / province / building_type / style_preferences |
| `schema/visual_theme.py` | `VisualThemeInput` 添加 `project_id: UUID` 字段 |
| `agent/visual_theme.py` | 新增 `build_theme_input_from_package()` 辅助函数，从素材包提取 dominant_styles / dominant_features |
| `scripts/material_package_e2e.py` | 在 outline 之前接入 `generate_visual_theme()` 步骤；启用 vision 审查层 |

---

### Phase 11 — Composer v3: HTML 直出模式 ✅（2026-04-05 新增）

**动机**：LayoutSpec 中间层限制了 LLM 的设计自由度（固定 HTML 模板、无装饰元素）。

**架构变化：**

```
v2 结构化: Composer LLM → LayoutSpec JSON → render_slide_html() → 固定 HTML 模板
v3 HTML:   Composer LLM → body_html + metadata → sanitize + theme CSS 注入 → HTML
```

| 文件 | 内容 |
|------|------|
| `render/html_sanitizer.py` | 安全层：过滤 `<script>`、事件处理器、`javascript:` URL、`@import`；保留 `<style>`、inline styles、SVG |
| `prompts/composer_system_v3.md` | HTML 模式提示词：CSS 变量、1920x1080 画布、SVG 装饰鼓励 |
| `agent/composer.py` | `ComposerMode.STRUCTURED` / `ComposerMode.HTML` 双模式；`_ComposerHTMLOutput` schema（body_html / asset_refs / content_summary）；`max_tokens` 提升至 4000 |
| `render/engine.py` | HTML 直通分支：body_html 直接嵌入，theme CSS 注入 |

两种模式共存，E2E 脚本通过 `--composer-mode html|structured` 切换，默认 `html`。

---

### Phase 12 — Vision Review v2: 设计顾问系统 ✅（2026-04-06 新增）

在现有 3 层审查基础上，扩展 Vision Review 为双模式。

**Mode A — 缺陷检测**（现有，V001~V007）
**Mode B — 设计顾问**（新增，评分 + 改善建议 + CSS/HTML 修改指令）

#### 5 维度评分体系（每项 0~10 分）

| 维度 | 代号 | 评估标准 |
|------|------|---------|
| 配色与对比度 | `color` | WCAG AA 对比度、主色/辅色/强调色比例、色彩层次 |
| 排版与层次 | `typography` | 字阶分明度、行距舒适度、文字量控制 |
| 布局与平衡 | `layout` | 网格构图、留白节奏、安全区 |
| 视觉焦点 | `focal_point` | 视觉锚点、信息层级、阅读路径 |
| 整体完成度 | `polish` | 装饰精致度、间距一致性、成品感 |

**总分分级：** A (8.0+) / B (6.0~7.9) / C (4.0~5.9) / D (<4.0)

#### 12 种建议代号（D001~D012）

对比度不足 / 配色冲突 / 字阶混乱 / 行距过紧 / 布局偏重 / 对齐偏移 / 缺少焦点 / 装饰过度 / 装饰缺失 / 图文比例 / 留白节奏 / 封面冲击力

#### 实现

| 文件 | 内容 |
|------|------|
| `schema/review.py` | `DesignDimension` / `DesignSuggestion` / `DesignAdvice`；`ReviewReport` 增加 `design_advice` 字段 |
| `db/models/review.py` | 新增 `design_advice_json` JSONB 列 |
| `prompts/vision_design_advisor.md` | 设计顾问 System Prompt |
| `agent/critic.py` | `_design_review()` 函数；`review_slide()` 增加 `design_advisor` / `page_type` / `theme_colors` 参数 |

---

### Phase 13 — Review-Render 回环 v2 修复 ✅（2026-04-07 新增）

修复了 HTML 模式下审查回环的 5 个 bug。

#### Bug 修复清单

| Bug | 严重度 | 问题 | 修复 |
|-----|--------|------|------|
| #1 HTML review 崩溃 | P0 | `LayoutSpec.model_validate()` 对 html_mode spec 抛异常 | `_review_one_slide` 检测 html_mode，构造 fallback LayoutSpec |
| #2 spec 覆盖丢失 body_html | P0 | review 写回 repaired_spec 覆盖原始 body_html | `is_html_mode` 守卫，不覆盖 HTML 模式的 spec_json |
| #3 LLM 失败静默通过 | P1 | 空 issues → PASS | 返回 `SEMANTIC_SKIPPED` / `VISION_SKIPPED` issue (P2)；`_evaluate()` 区分全 SKIPPED → PASS 但记录 |
| #4 HTML 回环空转 | P1 | body_html 不变，review 循环 3 轮无意义 | `recompose_slide_html()` + 专用 repair prompt |
| #5 fallback_spec phantom issues | P1 | R006/R008 规则检查假数据 → 永不收敛 | HTML 模式只用 vision 审查层，跳过 rule/semantic |

#### 修复后的回环链路

**v2 结构化模式（不变）：**
```
review → 修 spec 文本 → render(修后的 spec) → review → ... (最多 3 轮)
```

**v3 HTML 模式（新）：**
```
review(vision only) → REPAIR_REQUIRED
  → recompose(body_html + issues → LLM 修改) → render(新 body_html)
  → review → ... (最多 2 轮)
  → 最后一轮: 跑 design_advisor（只输出评分，不触发修改）
```

**LLM 不可用时：**
```
review → SKIPPED(P2) → PASS（记录但不阻塞） → READY_FOR_EXPORT
```

#### 修改文件

| 文件 | 改动 |
|------|------|
| `tasks/review_tasks.py` | html_mode 检测、spec 写回守卫、inline recompose、vision-only layers |
| `tool/review/semantic_check.py` | LLM 失败返回 SEMANTIC_SKIPPED issue |
| `agent/critic.py` | VISION_SKIPPED issue + _evaluate SKIPPED 过滤 |
| `agent/composer.py` | `recompose_slide_html()` + `_load_repair_prompt()` |
| `prompts/composer_repair.md` | 新建专用修复 prompt |
| `scripts/material_package_e2e.py` | review → recompose → re-render 循环 + vision-only layers |

---

## 三、E2E 验证历史

### 3.1 Mock-LLM + 全 41 页渲染（2026-04-04）

- 输出：`test_output/material_package_e2e/run_20260404T093251Z/`
- 41 页 HTML + PNG + review 报告 + summary
- 验证了素材包摄入 → binding → compose → render 全链路

### 3.2 Real-LLM 全量运行（2026-04-05）

- 输出：`test_output/material_package_e2e_real/run_20260405T075719Z/`
- 验证了真实 BriefDoc / Outline / Composer / Screenshot / PDF
- 发现 outline page count mismatch（42 vs 41）和 critic model invalid 两个问题

### 3.3 Bug Fix 验证（2026-04-05）

- 输出：`test_output/material_package_fix_check/run_20260405T084533Z/`
- 2-slide real-LLM 验证 page-count fix + critic fallback fix

### 3.4 Model Switch 验证（2026-04-05）

- 输出：`test_output/material_package_model_switch_check/run_20260405T092149Z/`
- 1-slide 验证 Composer → STRONG_MODEL, Review → google/gemini-3.1-pro-preview

### 3.5 Review Loop v2 验证（2026-04-07）

- 验证 recompose → re-render → re-review 链路
- HTML 模式 vision-only 审查层正常工作

---

## 四、测试覆盖

### 单元测试（11 files, 96 test functions）

| 文件 | 测试数 | 覆盖内容 |
|------|--------|---------|
| `tests/unit/test_render_engine.py` | 24 | 11 种布局渲染 + CSS 生成 + 内容块渲染 |
| `tests/unit/test_reference_tools.py` | 12 | 向量检索 + 重排序 + 偏好摘要 |
| `tests/unit/test_phase6_tools.py` | 9 | 图表生成 + 地图标注 + OSS 上传 |
| `tests/unit/test_validate_brief.py` | 9 | 设计任务书字段验证 |
| `tests/unit/test_compute_far.py` | 7 | FAR / GFA / 用地面积互推 |
| `tests/unit/test_layout_lint.py` | 7 | 布局规则检查 |
| `tests/unit/test_critic.py` | 7 | Critic agent + SKIPPED 过滤 + vision review（**Phase 9+ 新增**） |
| `tests/unit/test_content_fit.py` | 6 | 内容密度检测 |
| `tests/unit/test_material_pipeline.py` | 5 | 素材包摄入 + 分类 + 派生（**Phase 9 新增**） |
| `tests/unit/test_extract_brief.py` | 5 | 自然语言 → ProjectBriefData |
| `tests/unit/test_repair_plan.py` | 5 | 修复方案执行 |

### 集成测试（1 file, 6 test functions）

| 文件 | 测试数 | 覆盖内容 |
|------|--------|---------|
| `tests/integration/test_project_flow.py` | 6 | 项目创建 → outline 生成 → page count 一致性 |

### 测试辅助

| 文件 | 内容 |
|------|------|
| `tests/helpers/theme_factory.py` | 测试用 VisualTheme 工厂 |

---

## 五、文件树总览

```
ppt_agent/
├── agent/
│   ├── brief_doc.py          ✅ 设计建议书大纲生成（素材包感知）
│   ├── composer.py           ✅ 双模式（Structured v2 + HTML v3）+ recompose
│   ├── critic.py             ✅ 已适配 LayoutSpec + HTML + design advisor
│   ├── graph.py              ⚠️ 待更新节点
│   ├── intake.py             ✅ 项目简报提取
│   ├── material_binding.py   ✅ 素材绑定（新）
│   ├── outline.py            ✅ 蓝图驱动大纲生成（v2，素材包感知）
│   ├── reference.py          ✅ 案例推荐
│   └── visual_theme.py       ✅ 视觉主题生成（含素材包辅助函数）
│
├── api/routers/
│   ├── assets.py             ✅
│   ├── exports.py            ✅
│   ├── material_packages.py  ✅ 素材包 API（新）
│   ├── outlines.py           ✅ 含 confirm + compose_render_worker
│   ├── projects.py           ✅
│   ├── references.py         ✅ (含 VisualTheme 触发)
│   ├── render.py             ✅
│   ├── sites.py              ✅
│   └── slides.py             ✅
│
├── config/
│   ├── llm.py                ✅ OpenRouter 统一封装
│   ├── ppt_blueprint.py      ✅ 40 页完整蓝图
│   └── settings.py           ✅ 含 CRITIC_MODEL 配置
│
├── db/models/
│   ├── asset.py              ✅ (扩展 material_item_id)
│   ├── brief_doc.py          ✅ (扩展 package_id)
│   ├── material_package.py   ✅ 素材包 + 素材条目（新）
│   ├── outline.py            ✅ (扩展 coverage/binding_hints)
│   ├── project.py            ✅
│   ├── reference.py          ✅
│   ├── review.py             ✅ (含 design_advice_json)
│   ├── site.py               ✅
│   ├── slide.py              ✅ (扩展 binding 支持)
│   ├── slide_material_binding.py ✅（新）
│   └── visual_theme.py       ✅
│
├── render/
│   ├── engine.py             ✅ 动态 CSS + 11 种布局 + HTML 直通
│   ├── exporter.py           ✅ Playwright + compile_pdf()
│   └── html_sanitizer.py     ✅ HTML 安全过滤（新）
│
├── schema/
│   ├── asset.py              ✅ (更新)
│   ├── material_package.py   ✅ (新)
│   ├── outline.py            ✅ (更新)
│   ├── page_slot.py          ✅
│   ├── review.py             ✅ (含 DesignAdvice)
│   ├── slide.py              ✅ (更新)
│   ├── visual_theme.py       ✅ 含 LayoutSpec + VisualThemeInput.project_id
│   └── ...其余已有模型      ✅
│
├── tasks/
│   ├── asset_tasks.py        ✅
│   ├── export_tasks.py       ✅
│   ├── outline_tasks.py      ⚠️ 待串联 brief_doc
│   ├── render_tasks.py       ✅ 已适配 LayoutSpec
│   └── review_tasks.py       ✅ html_mode 检测 + recompose + vision-only
│
├── tool/
│   ├── material_pipeline.py  ✅ 素材包摄入全流程（新）
│   ├── material_resolver.py  ✅ logical_key 匹配与展开（新）
│   ├── image_gen/            ❌ 缺 nanobanana.py
│   ├── search/               ❌ 缺 web_search.py
│   └── ...其余工具           ✅
│
├── prompts/
│   ├── brief_doc_system.md   ✅
│   ├── composer_system_v2.md ✅
│   ├── composer_system_v3.md ✅ HTML 直出（新）
│   ├── composer_repair.md    ✅ 修复专用（新）
│   ├── intake_system.md      ✅
│   ├── outline_system_v2.md  ✅
│   ├── vision_design_advisor.md ✅ 设计顾问（新）
│   └── visual_theme_system.md ✅
│
├── scripts/
│   ├── material_package_e2e.py ✅ 10 步 E2E 验证（新）
│   └── seed_cases.py         ✅
│
└── tests/
    ├── unit/                 96 test functions × 11 files ✅
    ├── integration/           6 test functions × 1 file ✅
    └── helpers/              theme_factory.py
```

---

## 六、完成度评估

| 维度 | 完成度 | 备注 |
|------|--------|------|
| 数据库 & 迁移 | 100% | 全部表已建，004 已执行（含素材包三表） |
| API 路由 | 95% | 新增素材包路由；仅缺 visual-theme 独立端点 |
| Tool 层（静态） | 100% | 全部纯函数工具完整 |
| Tool 层（外部 API） | 70% | 缺 web_search + nanobanana |
| Agent 层 | 95% | 全部核心 agent 已适配素材包 + HTML 模式 |
| 素材包管线 | 100% | 摄入 → 分类 → 派生 → 绑定 全链路完整 |
| 渲染引擎 | 100% | 11 种布局 + HTML 直通 + 安全过滤 |
| Composer 双模式 | 100% | v2 结构化 + v3 HTML 直出 + recompose 修复 |
| 审查系统 | 95% | 3 层审查 + 设计顾问评分 + review 回环修复 |
| LangGraph 流程 | 70% | 节点存在但部分用旧 API |
| Celery 任务 | 85% | outline_task 需串联 brief_doc；review_tasks 已更新 |
| E2E 验证 | 100% | 41 页 real-LLM 运行已通过，PDF 导出验证 |
| 测试覆盖 | 85% | 102 test functions；新增 material_pipeline + critic 测试 |
| **整体** | **~92%** | 核心素材包管线完整可用，review 回环已修复 |

---

## 七、剩余工作

### 高优先级（功能缺口）

#### 1. `tool/search/web_search.py` — 联网搜索工具
蓝图中 5 个以上 slot 依赖联网搜索，目前完全缺失。

#### 2. `tool/image_gen/nanobanana.py` — Nanobanana 图像生成
封面 logo、目录插画、概念方案鸟瞰图 / 人视图均依赖此工具。

### 中优先级（系统打通）

#### 3. `agent/graph.py` — LangGraph 流程更新
需要适配新的素材包管线流程（MaterialPackage → BriefDoc → Outline → Binding → Compose → Render → Review）。

#### 4. `tasks/outline_tasks.py` — 串联 Brief Doc
在 `generate_outline_task` 之前，需先调用 `generate_brief_doc`。

#### 5. Review Loop v2 最终验证
Bug 5 修复后的全量 E2E 验证待执行，需确认 HTML 模式回环能收敛到 PASS。

### 低优先级（完善）

#### 6. Design Advisor Phase 2 — 自动修改闭环
根据 `DesignAdvice.suggestions` 生成修改指令，回传 Composer 重写 HTML（目前只输出评分报告）。

#### 7. 全局一致性审查
收集所有页面的 DesignAdvice，做跨页配色/字号/装饰风格一致性评估。

#### 8. 测试补充

| 缺失测试 | 说明 |
|----------|------|
| `test_html_sanitizer.py` | HTML 安全过滤测试 |
| `test_composer_html_mode.py` | HTML 直出模式测试 |
| `test_recompose.py` | recompose_slide_html 测试 |
| `test_design_advisor.py` | 设计顾问评分测试 |
| `test_web_search.py` | Web search tool 单元测试（mock HTTP） |
| `test_nanobanana.py` | Nanobanana tool 单元测试（mock API） |

---

## 八、文档索引

| 文档 | 内容 |
|------|------|
| `docs/00_index.md` | 文档目录 |
| `docs/01_project_structure.md` | 项目结构 |
| `docs/02_database_schema.md` | 数据库 Schema |
| `docs/11_review_rules.md` | 审查规则 |
| `docs/15_testing_strategy.md` | 测试策略 |
| `docs/16_ppt_generation_pipeline.md` | PPT 生成管线 |
| `docs/17_development_progress.md` | 本文档 |
| `docs/20_material_package_integration.md` | 素材包集成设计 |
| `docs/21_material_package_implementation_appendix.md` | 素材包实现附录 |
| `docs/22_session_handoff_20260405.md` | 2026-04-05 会话交接 |
| `docs/23_vision_review_v2_design_advisor.md` | Vision Review v2 设计顾问 |
| `docs/24_review_loop_v2_fixes.md` | Review 回环 v2 修复设计 |
| `docs/25_bugfix_log_review_loop_v2.md` | Review 回环 Bug 修复日志 |
| `docs/26_pipeline_flow_overview.md` | 素材包到 PDF 全流程 9 阶段详解 |

---

## 九、推荐下一步顺序

```
1. Review Loop v2 全量验证        ← 确认回环收敛
2. tool/search/web_search.py     ← 独立叶子节点，5+ slot 依赖
3. tool/image_gen/nanobanana.py  ← 独立叶子节点，封面/效果图依赖
4. agent/graph.py 更新节点        ← 完整 LangGraph 流程串联
5. tasks/outline_tasks.py 串联   ← brief_doc → outline 两步
6. Design Advisor Phase 2        ← 自动修改闭环
7. 测试补充 + API 收尾            ← 收尾
```
