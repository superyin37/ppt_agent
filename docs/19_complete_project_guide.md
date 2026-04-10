# PPT Agent 项目完整说明文档

> 基于当前仓库代码整理，目标是把“项目是什么、怎么工作、代码在哪里、目前做到什么程度、有哪些已知问题”集中到一份文档里。
>
> 更新时间：2026-03-28

---

## 1. 项目定位

PPT Agent 是一个面向建筑方案汇报场景的 AI PPT 生产系统。它不是“输入一句话直接吐一份泛用 PPT”的通用演示文稿工具，而是围绕建筑策划、场地分析、案例参考、设计策略和方案表达这类高结构化内容，按固定生产链路生成可审阅、可渲染、可导出的整套汇报材料。

项目当前形态可以概括为：

- `FastAPI` 提供项目创建、Brief 录入、参考案例选择、资产生成、提纲生成、渲染、审查和导出接口。
- `Celery + Redis` 负责异步任务编排，处理资产生成、渲染、审查、导出。
- `Agent + Tool` 组合负责把“自然语言输入”逐步转成结构化 PPT 数据。
- `VisualTheme + LayoutSpec + Render Engine` 负责把结构化数据变成 HTML/CSS 幻灯片，再截图或导出 PDF。
- `PostgreSQL + pgvector` 保存项目、案例库、资产、提纲、幻灯片、审查记录等核心数据。

项目当前更准确的产物链路是：

`ProjectBrief -> Reference Selection -> Asset -> OutlineSpec -> LayoutSpec -> HTML -> PNG/PDF`

而不是传统 Office/PPTX 直出。PPTX 在代码中有表结构预留和文档规划，但当前主线导出能力仍是 PDF。

---

## 2. 项目目标与边界

### 2.1 主要目标

- 将多轮自然语言需求整理成结构化项目 Brief。
- 基于案例库和风格偏好，生成项目级视觉主题。
- 自动生成适合建筑汇报的完整目录和页级叙事结构。
- 为每一页生成结构化版式描述，而不是直接拼接自由文本。
- 通过渲染引擎稳定输出统一风格的幻灯片 HTML、PNG 和 PDF。
- 在导出前做规则审查、语义审查和视觉审查，尽量避免明显失真或内容错误。

### 2.2 当前边界

- 当前项目更偏“建筑汇报自动化生产线”，不是通用 PPT 编辑器。
- 当前主渲染模型是 `LayoutSpec`，旧版 `SlideSpec` 还留在部分 schema、测试和文档中，但不是现阶段的核心渲染协议。
- 当前前端是轻量 SPA，用于串联流程，不是复杂编辑端。
- 当前对外部搜索、图片生成等能力有设计痕迹，但仓库中的实际主流程尚未完全接入。
- 当前导出主路径是 PDF，不是完整的 PPTX。

---

## 3. 技术栈

### 3.1 后端与服务

- Web API：`FastAPI`
- ORM：`SQLAlchemy 2.x`
- 数据库迁移：`Alembic`
- 数据库：`PostgreSQL 16`
- 向量检索：`pgvector`
- 异步任务：`Celery`
- Broker / Result Backend：`Redis`

### 3.2 AI 与生成

- LLM 调用封装：`config/llm.py`
- 实际接入方式：通过 `OpenRouter`，底层使用 OpenAI SDK 的兼容接口
- 强模型：`settings.llm_strong_model`
- 快模型：`settings.llm_fast_model`
- 审查模型：`settings.llm_critic_model`

### 3.3 渲染与导出

- HTML 渲染：自定义 Python Render Engine
- 截图：`Playwright`
- PDF 合成：优先 `Playwright`，回退 `Pillow`
- 图表生成：`matplotlib`

### 3.4 前端

- 纯静态前端：`frontend/index.html + app.js + style.css`
- 运行方式：由 FastAPI 通过 `/app` 静态挂载

---

## 4. 仓库结构总览

### 4.1 根目录

- `main.py`
  FastAPI 入口，注册所有路由、健康检查、静态目录和前端 SPA。
- `docker-compose.yml`
  本地一键启动编排，包含 `db`、`redis`、`api`、`worker`、`renderer`、`flower`。
- `Dockerfile`
  统一镜像定义，安装 Poetry 依赖和 Playwright Chromium。
- `pyproject.toml`
  Python 依赖和 pytest 配置。

### 4.2 业务目录

- `api/`
  HTTP 层、异常、统一响应、依赖注入、中间件。
- `agent/`
  Agent 级业务逻辑，如 Intake、Reference、Outline、Composer、Critic、VisualTheme。
- `tool/`
  被 Agent 或任务调用的细粒度工具模块，如 geocode、embedding、图表、地图、lint。
- `tasks/`
  Celery 任务层。
- `render/`
  HTML/CSS 渲染和截图/PDF 导出。
- `schema/`
  Pydantic 数据协议。
- `db/`
  SQLAlchemy Base、Session 和 ORM 模型。
- `config/`
  运行配置、LLM 封装、PPT 蓝图。
- `frontend/`
  轻量单页应用。

### 4.3 支撑目录

- `prompts/`
  各 Agent 的系统提示词。
- `alembic/`
  数据库迁移脚本。
- `scripts/`
  种子数据、E2E 脚本。
- `tests/`
  单测和集成测试。
- `docs/`
  分章节文档。

---

## 5. 端到端业务流程

项目主流程按状态推进，核心枚举定义在 `schema/common.py` 的 `ProjectStatus` 中：

- `INIT`
- `INTAKE_IN_PROGRESS`
- `INTAKE_CONFIRMED`
- `REFERENCE_SELECTION`
- `ASSET_GENERATING`
- `OUTLINE_READY`
- `SLIDE_PLANNING`
- `RENDERING`
- `REVIEWING`
- `READY_FOR_EXPORT`
- `EXPORTED`
- `FAILED`

### 5.1 项目创建与 Brief 录入

入口：`api/routers/projects.py`

1. `POST /projects`
   创建项目，状态初始化为 `INIT`。
2. `PATCH /projects/{id}/brief`
   调用 `agent/intake.py::run_intake()`。
3. Intake Agent 会：
   - 读取已有 `project_briefs` 最新版本。
   - 调用 `tool/input/extract_brief.py` 从自然语言提取结构化字段。
   - 如果地址可用，调用 `tool/input/geocode.py` 做地址解析补充省市区。
   - 调用 `tool/input/validate_brief.py` 做本地校验。
   - 将结果写回 `project_briefs`。
4. 当必填项完整后，调用 `POST /projects/{id}/confirm-brief` 将项目推进到 `INTAKE_CONFIRMED`。

### 5.2 参考案例推荐与选择

入口：`api/routers/references.py`

1. `POST /projects/{id}/references/recommend`
   调用 `agent/reference.py::recommend_cases()`。
2. Reference Agent 会：
   - 从已确认 Brief 构建查询文本。
   - 调用 `tool/reference/_embedding.py` 生成 embedding。
   - 调用 `tool/reference/search.py` 走 pgvector 或 tag fallback 检索。
   - 调用 `tool/reference/rerank.py` 再排序。
3. 用户通过 `POST /references/select` 提交案例选择。
4. `POST /references/confirm`
   - 调用 `summarise_selection_preferences()` 汇总审美偏好。
   - 调用 `agent/visual_theme.py::generate_visual_theme()` 生成项目级视觉主题。
   - 项目推进到 `ASSET_GENERATING`。

### 5.3 资产生成

入口：`api/routers/assets.py`

1. `POST /projects/{id}/assets/generate`
   触发 `tasks.asset_tasks.generate_all_assets`。
2. 该任务通过 `group + chord` 并行调用：
   - `generate_site_assets`
   - `generate_chart_assets`
   - `generate_case_assets`
3. 当前实际生成的资产包括：
   - 周边 POI 地图
   - 交通可达性地图
   - 体量对比柱状图
   - 已选案例对比数据资产
4. 资产完成后由 `on_all_assets_complete()` 收尾，并更新项目状态。

说明：

- 代码注释中写的是“完成后推进到 OUTLINE_READY 并触发 outline generation”，但当前实现只做状态推进，没有自动触发 Outline Celery 任务。
- 如果一个资产都没生成出来，项目会被标记为 `FAILED`。

### 5.4 Brief Doc 与 Outline

当前仓库存在两层“提纲前置”结构：

- `BriefDoc`
  更偏叙事级的设计说明文档，描述定位语、设计原则、叙事弧线。
- `OutlineSpec`
  更偏页级 PPT 提纲，直接描述每页标题、目的、关键信息、所需资产和布局提示。

#### Brief Doc

实现位置：`agent/brief_doc.py`

其输入是：

- 项目 Brief
- 已生成的各类资产

其输出写入 `brief_docs` 表，包括：

- `outline_json`
- `narrative_summary`
- 可选的 `slot_assignments_json`

但要注意：

- 当前 API 主流程没有单独暴露 Brief Doc 的生成接口。
- `tasks/outline_tasks.py` 也没有先调用 Brief Doc 再调用 Outline 的串联逻辑。
- 换言之，Brief Doc 是“已实现但未完全接入主业务链”的能力。

#### Outline

实现位置：`agent/outline.py`

Outline Agent v2 的特点是：

- 不自由生成页数，而是受 `config/ppt_blueprint.py` 驱动。
- Blueprint 定义了近 40 页的固定页槽（`PageSlot` / `PageSlotGroup`）。
- LLM 的任务是把 Brief、BriefDoc、资产和页槽蓝图映射成具体的页级 `SlotAssignment`。
- 再转成兼容数据库存储的 `OutlineSpec`。

页面结构覆盖：

- 封面与目录
- 背景研究
- 场地分析
- 竞品分析
- 参考案例
- 项目定位
- 设计策略
- 三套概念方案
- 技术/经济/材料策略
- 设计任务书
- 尾页

### 5.5 版式编排与渲染

#### Composer

实现位置：`agent/composer.py`

Composer 的核心职责：

- 输入：`OutlineSlideEntry + VisualTheme + Brief + AssetSummary`
- 输出：`LayoutSpec`

关键点：

- 当前真正进入渲染链路的是 `schema/visual_theme.py` 中定义的 `LayoutSpec`。
- `LayoutSpec` 由两部分组成：
  - `primitive`：页面布局骨架
  - `region_bindings`：不同区域里的内容块
- `primitive` 支持 11 种布局：
  - `full-bleed`
  - `split-h`
  - `split-v`
  - `single-column`
  - `grid`
  - `hero-strip`
  - `sidebar`
  - `triptych`
  - `overlay-mosaic`
  - `timeline`
  - `asymmetric`

#### Render Engine

实现位置：`render/engine.py`

Render Engine 的职责：

- 把 `VisualTheme` 转成一组 CSS 变量。
- 把 `LayoutSpec` 转成完整 HTML。
- 将 `asset:{id}` 形式的资源引用解析成真实 URL。
- 给非封面/非章节页自动生成页脚。

当前支持的内容块类型：

- `heading`
- `subheading`
- `body-text`
- `bullet-list`
- `kpi-value`
- `image`
- `chart`
- `map`
- `table`
- `quote`
- `caption`
- `label`
- `accent-element`

#### 截图与 PDF

实现位置：`render/exporter.py`

流程：

- `screenshot_slide()` 使用 Playwright 把单页 HTML 转成 PNG。
- `compile_pdf()` 将多张 PNG 合并成 PDF。
- Playwright 不可用时会退化为占位图或 Pillow 合成。

### 5.6 审查与修复

入口：

- `tasks/review_tasks.py`
- `agent/critic.py`

Critic 采用三层模型：

1. Rule Layer
   使用 `tool/review/layout_lint.py` 做规则检查，不依赖 LLM。
2. Semantic Layer
   使用 `tool/review/semantic_check.py` 做语义一致性检查。
3. Vision Layer
   使用多模态 LLM 对截图进行视觉检查。

Critic 输出：

- `ReviewReport`
- `ReviewIssue`
- `RepairAction`

决策枚举：

- `pass`
- `repair_required`
- `escalate_human`

当前实现中的自动修复主要来自：

- `tool/review/repair_plan.py`
- Critic 在 rule 层发现问题后会立即尝试执行可自动修复的动作

### 5.7 导出

导出入口有两套路径：

#### API 线程路径

实现位置：`api/routers/exports.py`

- 启动一个后台线程 `_export_worker()`
- 读取本地生成的 PNG 或 HTML
- 合成 PDF
- 把结果保存到 `tmp/e2e_output/export`
- 最终在 `project.error_message` 中塞入导出 URL

#### Celery 路径

实现位置：`tasks/export_tasks.py`

- `export_deck(project_id, export_type="pdf")`
- 可以从 OSS 拉取截图，失败时回退重新截图或生成占位页
- 最终上传 PDF 到 OSS

说明：

- 两套导出路径同时存在，职责有重叠。
- 当前 HTTP 主流程更偏向使用 `api/routers/exports.py` 中的线程路径。
- `tasks/export_tasks.py` 更像为异步分布式导出准备的正式实现。

---

## 6. 模块职责拆解

### 6.1 `api/`

#### `api/routers/projects.py`

- 列项目
- 创建项目
- 获取项目
- 录入 Brief
- 确认 Brief

#### `api/routers/sites.py`

- 提交场地点位
- 提交地块 GeoJSON
- 查询场地信息

#### `api/routers/references.py`

- 推荐案例
- 选择案例
- 确认案例并生成视觉主题
- 刷新候选案例

#### `api/routers/assets.py`

- 触发资产生成
- 查询资产列表

#### `api/routers/outlines.py`

- 生成提纲
- 查询提纲
- 确认提纲后启动 Compose + Render + Review

注意：

- 这里大量使用 Python `threading.Thread` 启后台流程，而不是完全通过 Celery。

#### `api/routers/slides.py`

- 查询全部幻灯片
- 查询单页幻灯片

#### `api/routers/render.py`

- 手动触发渲染
- 手动触发审查
- 手动触发修复

#### `api/routers/exports.py`

- 手动触发导出

### 6.2 `agent/`

#### `agent/intake.py`

- 多轮 Brief 抽取与更新。

#### `agent/reference.py`

- 案例推荐与偏好总结。

#### `agent/visual_theme.py`

- 项目级视觉主题生成。

#### `agent/brief_doc.py`

- 设计叙事文档生成。

#### `agent/outline.py`

- Blueprint 驱动提纲生成。

#### `agent/composer.py`

- 页级版式与内容块生成。

#### `agent/critic.py`

- 三层审查与修复决策。

#### `agent/graph.py`

- LangGraph 编排原型。

说明：

- 该文件体现了作者想把整套流程统一编入 StateGraph。
- 但它和当前实际 API/Celery 主流程并不完全一致，存在“图编排设计”和“生产实现”两条并行轨迹。

### 6.3 `tool/`

`tool/` 负责可复用、可测试的原子能力。

#### `tool/input/`

- `extract_brief.py`
- `validate_brief.py`
- `geocode.py`
- `normalize_polygon.py`
- `compute_far.py`

#### `tool/reference/`

- `_embedding.py`
- `search.py`
- `rerank.py`
- `preference_summary.py`

#### `tool/site/`

- `_amap_client.py`
- `poi_retrieval.py`
- `mobility_analysis.py`

#### `tool/asset/`

- `chart_generation.py`
- `map_annotation.py`

#### `tool/review/`

- `layout_lint.py`
- `semantic_check.py`
- `repair_plan.py`

### 6.4 `tasks/`

#### `tasks/celery_app.py`

Celery 路由如下：

- `tasks.render_tasks.*` -> `render` 队列
- `tasks.export_tasks.*` -> `export` 队列
- 其他 -> `default` 队列

#### `tasks/asset_tasks.py`

- 并行生成资产

#### `tasks/outline_tasks.py`

- 生成 Outline
- 生成全部 Slide 并分发渲染任务

#### `tasks/render_tasks.py`

- 批量渲染幻灯片

#### `tasks/review_tasks.py`

- 批量审查幻灯片

#### `tasks/export_tasks.py`

- 批量导出 PDF

---

## 7. 数据模型

### 7.1 项目主表

#### `projects`

字段重点：

- `id`
- `name`
- `status`
- `current_phase`
- `error_message`
- `created_at`
- `updated_at`

作用：

- 记录整个项目状态机的主状态。

#### `project_briefs`

字段重点：

- `building_type`
- `client_name`
- `style_preferences`
- `gross_floor_area`
- `site_area`
- `far`
- `site_address`
- `province / city / district`
- `missing_fields`
- `conversation_history`

作用：

- 存多轮收集后的结构化项目输入。

### 7.2 场地相关

#### `site_locations`

- 经纬度
- 地址解析结果
- POI 名称

#### `site_polygons`

- GeoJSON
- 面积
- 周长
- 版本

### 7.3 案例相关

#### `reference_cases`

包含：

- 标题
- 建筑师
- 地点
- 建筑类型
- 风格标签
- 特征标签
- 面积
- 完成年份
- 图片
- 摘要
- embedding

#### `project_reference_selections`

记录项目对案例的选择结果，包括：

- `selected_tags`
- `selection_reason`
- `rank`

### 7.4 生产中间物

#### `assets`

统一承载地图、图表、案例对比、文本摘要等中间资产。

#### `brief_docs`

承载“设计叙事文档”。

#### `visual_themes`

承载项目级视觉系统。

#### `outlines`

承载页级提纲。

#### `slides`

承载最终页级结构化表示和渲染结果。

字段重点：

- `spec_json`
- `html_content`
- `screenshot_url`
- `repair_count`
- `status`

#### `reviews`

承载每页或每个目标对象的审查结果。

### 7.5 任务与导出

#### `jobs`

预留通用异步任务跟踪。

#### `exports`

预留导出产物跟踪。

说明：

- `jobs` / `exports` 已有表结构，但当前主 HTTP 流程没有充分使用它们做统一的状态追踪。

---

## 8. 数据协议演进：`SlideSpec` 与 `LayoutSpec`

这是理解当前仓库最关键的地方。

### 8.1 旧协议：`schema/slide.py::SlideSpec`

特点：

- 更接近“传统 PPT 页描述”。
- 用 `layout_template + blocks + constraints + style_tokens` 表达一页。

### 8.2 新协议：`schema/visual_theme.py::LayoutSpec`

特点：

- 更接近“设计系统驱动的布局语义”。
- 用 `primitive + region_bindings + visual_focus` 表达一页。
- 与 `VisualTheme` 深度耦合。

### 8.3 当前实际情况

- Composer 输出的是 `LayoutSpec`。
- Render Engine 吃的是 `LayoutSpec`。
- Critic 当前也主要围绕 `LayoutSpec` 工作。
- 但部分测试、旧文档和少量 schema 仍按 `SlideSpec` 编写。

这直接导致当前仓库存在一个明显的协议迁移未完成状态：

- 运行链路已经站在 `LayoutSpec` 上。
- 一部分测试仍然假设 `layout_lint`、`semantic_check` 等处理的是 `SlideSpec`。

这个不一致已经体现在本次本地测试里，见第 14 节。

---

## 9. 视觉系统与渲染体系

### 9.1 VisualTheme

VisualTheme 不是简单的颜色配置，而是一整套页面视觉规范，包含：

- 颜色系统
- 字体系统
- 间距系统
- 装饰风格
- 封面风格
- 风格关键词
- 给后续 Agent 的生成提示

### 9.2 为什么项目采用 VisualTheme + LayoutSpec

原因是作者想避免：

- 直接让 LLM 输出自由 HTML/CSS
- 直接让每页独立风格漂移
- 先做内容、后补视觉时难以统一

因此项目采用了：

- 先做项目级视觉约束
- 再做页级结构布局
- 最后统一渲染

这比传统“直接拼模板字符串”更稳定，也更适合批量审查。

### 9.3 Render Engine 的设计特点

- 不是模板文件驱动，而是 Python 代码驱动。
- 没有依赖 `render/templates/*.html` 作为主路径。
- `render/templates/` 更像历史模板资产或备用资源。
- 实际主链路是 `render/engine.py` 内的 `_render_*` 函数分发。

---

## 10. API 设计概览

### 10.1 项目

- `GET /projects`
- `POST /projects`
- `GET /projects/{project_id}`
- `PATCH /projects/{project_id}/brief`
- `POST /projects/{project_id}/confirm-brief`

### 10.2 场地

- `POST /projects/{project_id}/site/point`
- `POST /projects/{project_id}/site/polygon`
- `GET /projects/{project_id}/site`

### 10.3 参考案例

- `POST /projects/{project_id}/references/recommend`
- `POST /projects/{project_id}/references/select`
- `POST /projects/{project_id}/references/confirm`
- `POST /projects/{project_id}/references/refresh`

### 10.4 资产

- `POST /projects/{project_id}/assets/generate`
- `GET /projects/{project_id}/assets`

### 10.5 提纲与幻灯片

- `POST /projects/{project_id}/outline/generate`
- `GET /projects/{project_id}/outline`
- `POST /projects/{project_id}/outline/confirm`
- `POST /projects/{project_id}/slides/plan`
- `GET /projects/{project_id}/slides`
- `GET /projects/{project_id}/slides/{slide_no}`

### 10.6 渲染、审查、导出

- `POST /projects/{project_id}/render`
- `POST /projects/{project_id}/review`
- `POST /projects/{project_id}/repair`
- `POST /projects/{project_id}/export`

### 10.7 通用

- `GET /health`

---

## 11. 前端实现说明

前端位于 `frontend/`，是一个纯静态 SPA。

### 11.1 路由

通过 hash 路由切换：

- `#/`
  项目列表
- `#/new`
  新建项目
- `#/project/{id}`
  项目详情

### 11.2 页面职责

#### 项目列表

- 拉取 `/projects`
- 展示项目卡片和状态 badge

#### 新建项目页

- 将表单整理成 `raw_text`
- 先调 `POST /projects`
- 再调 `PATCH /brief`
- 如果 `brief.is_complete` 为真，再自动调 `confirm-brief`

#### 项目详情页

- 轮询项目状态
- 在不同状态下展示不同主按钮
- 状态流大致对应：
  - Brief 确认后生成 Outline
  - Outline 确认后开始 Compose + Render
  - Ready for Export 后导出 PDF
- 当状态进入 `REVIEWING / READY_FOR_EXPORT / EXPORTED` 时拉取缩略图

### 11.3 前端定位

它的定位不是编辑器，而是一个最小流程面板：

- 看状态
- 点下一步
- 预览缩略图
- 下载结果

---

## 12. 部署与运行方式

### 12.1 本地开发

推荐顺序：

1. 启动数据库和 Redis
2. 执行 Alembic 迁移
3. 导入案例库
4. 启动 API
5. 启动 Celery worker
6. 启动 render worker

### 12.2 Docker Compose

`docker-compose.yml` 当前定义：

- `db`
- `redis`
- `api`
- `worker`
- `renderer`
- `flower`

作用分工：

- `api`
  提供 HTTP 服务
- `worker`
  执行默认队列和导出队列
- `renderer`
  执行渲染队列
- `flower`
  查看 Celery 任务

### 12.3 环境变量

来自 `config/settings.py` 的关键配置有：

- `DATABASE_URL`
- `REDIS_URL`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- `OPENROUTER_API_KEY`
- `OPENROUTER_BASE_URL`
- `AMAP_API_KEY`
- `OSS_ENDPOINT / OSS_BUCKET / OSS_ACCESS_KEY / OSS_SECRET_KEY / OSS_BASE_URL`
- `EMBEDDING_PROVIDER`
- `OPENAI_API_KEY / VOYAGE_API_KEY / QWEN_API_KEY`
- `PLAYWRIGHT_HEADLESS`
- `SLIDE_WIDTH_PX / SLIDE_HEIGHT_PX`

安全说明：

- `.env.example` 当前不适合作为可公开分发的示例文件使用，建议清理敏感值并替换为占位符。

---

## 13. 当前实现特征与架构判断

综合代码来看，项目当前不是单一风格架构，而是三种思路并存：

### 13.1 生产链式实现

体现在：

- `api/routers/*`
- `tasks/*`
- `agent/*`

这是实际可跑的主路径。

### 13.2 设计型编排实现

体现在：

- `agent/graph.py`
- `agent/brief_doc.py`
- `config/ppt_blueprint.py`

这部分更像“下一阶段想收敛成统一编排框架”的设计方向。

### 13.3 历史协议残留

体现在：

- `schema/slide.py`
- 部分旧测试
- 部分旧文档

这部分与 `LayoutSpec` 主链路已经不完全一致。

因此，这个仓库更像“正在从 v1 SlideSpec 架构迁移到 v2 VisualTheme/LayoutSpec 架构”的中间态版本。

---

## 14. 测试与当前健康状况

### 14.1 本次本地验证

执行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit -q
```

结果：

- `103` 个测试通过
- `13` 个测试失败

### 14.2 失败的主要原因

失败集中在两类：

#### 1. `SlideSpec` 与 `LayoutSpec` 协议不一致

表现：

- `tool/review/layout_lint.py` 现在读取的是 `LayoutSpec.region_bindings`
- 但若干测试仍向它传 `SlideSpec`
- 因而出现 `AttributeError: 'SlideSpec' object has no attribute 'region_bindings'`

影响文件：

- `tests/unit/test_layout_lint.py`
- `tests/unit/test_repair_plan.py`
- `tests/unit/test_critic.py` 的一部分

#### 2. SemanticCheck 输入协议已改为 `LayoutSpec`

表现：

- `SemanticCheckInput.spec` 要求是 `LayoutSpec`
- 旧测试仍传 `SlideSpec`
- 导致 Pydantic ValidationError

### 14.3 当前可以得出的结论

- 项目代码不是完全不可运行，而是“主链路协议已迁移，测试尚未完全跟上”。
- 这属于典型的架构升级后测试夹层问题。
- 文档、测试、旧 schema 三者需要统一一次。

### 14.4 其他测试信号

- 图表和地图测试里有大量中文字体缺失 warning，说明运行环境对 CJK 字体支持不完整。
- `.pytest_cache` 在 Windows 下有缓存路径 warning，但不影响主结论。

---

## 15. 已知问题与技术债

### 15.1 双轨编排并存

项目同时存在：

- API 线程式后台执行
- Celery 正式异步执行
- LangGraph 统一编排原型

这导致职责边界不够单一。

### 15.2 导出链路重复

`api/routers/exports.py` 和 `tasks/export_tasks.py` 都在做导出，长期看应收敛为一条主链路。

### 15.3 Outline/BriefDoc 串联未完全打通

BriefDoc 已实现，但当前主 API 流程没有完整接入“先生成 BriefDoc，再生成 Outline”的正式链路。

### 15.4 协议迁移未收口

`SlideSpec` 仍残留在：

- 部分测试
- 部分 schema
- 部分文档表述

而主链路已经转向 `LayoutSpec`。

### 15.5 文档与实现存在时间差

`docs/17_development_progress.md` 仍记录了一部分“计划中”内容，与当前仓库代码不完全同步，应视作阶段记录，不应视作当前实现说明。

### 15.6 编码与注释质量问题

在当前终端环境下，部分中文注释和字符串存在乱码现象，说明仓库中可能混杂了不同编码或历史复制内容。核心代码结构不受影响，但阅读体验较差，也会影响后续维护。

---

## 16. 建议的阅读顺序

如果是第一次接手这个项目，建议按下面顺序读：

1. `main.py`
2. `api/routers/projects.py`
3. `agent/intake.py`
4. `api/routers/references.py`
5. `agent/reference.py`
6. `agent/visual_theme.py`
7. `tasks/asset_tasks.py`
8. `agent/outline.py`
9. `agent/composer.py`
10. `render/engine.py`
11. `agent/critic.py`
12. `tasks/review_tasks.py`
13. `api/routers/exports.py`
14. `schema/visual_theme.py`
15. `config/ppt_blueprint.py`

这样读可以最快建立“从输入到输出”的心智模型。

---

## 17. 一句话总结

PPT Agent 当前已经具备一个建筑汇报自动生成系统的核心骨架：它能把多轮 Brief、案例偏好和场地/图表资产，逐步转成项目级视觉系统、页级提纲、结构化布局、HTML 幻灯片和最终 PDF；但它仍处在从旧 `SlideSpec` 体系向新 `VisualTheme + LayoutSpec` 体系迁移的中间阶段，主链路已成形，工程收口尚未完成。
