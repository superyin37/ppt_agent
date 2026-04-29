# 当前实现与 LangGraph 实现对比

> 本文对比两个文档体系所描述的 PPT 生成实现方式：
>
> - `docs/`：本项目当前实现，代码在本仓库内。
> - `docs-langgraph/`：另一套基于 LangGraph 的实现说明，代码不在本仓库内。

## 1. 结论摘要

两套方案解决的是同一个业务问题：从建筑设计相关资料生成可展示的 PPT/HTML 演示稿。但它们的工程定位不同。

`docs/` 描述的是一个产品化服务架构。它以 FastAPI、数据库、Celery/Redis、素材包、页面绑定、HTML Composer、渲染截图、审查修复、PDF 导出为主线，强调多项目管理、用户交互、状态持久化、素材追踪、质量闭环和后续增量再生成能力。

`docs-langgraph/` 描述的是一个批处理式图编排架构。它以 LangGraph 的 `ProjectState` 为中心，通过固定节点、并行 fanout、barrier、checkpoint、Jinja2 模板，把 `data/case_<id>/` 目录中的资料生成一个固定结构的 40 页 HTML deck，强调流程图表达、节点并行、快速本地运行和 checkpoint 恢复。

如果目标是继续做可交互、可追踪、可长期维护的 PPT Agent 产品，当前 `docs/` 方案更适合作为主线。如果目标是快速处理固定格式案例、验证 LangGraph 编排、生成单文件 HTML 演示稿，`docs-langgraph/` 方案更轻、更直接。

## 2. 对比范围

当前实现主要参考：

- `docs/04_api_definition.md`
- `docs/06_async_tasks.md`
- `docs/20_material_package_integration.md`
- `docs/26_pipeline_flow_overview.md`
- `docs/27_material_package_complete_guide.md`
- `docs/23_vision_review_v2_design_advisor.md`
- `docs/ops/decisions/ADR-002-celery-over-langgraph.md`
- `docs/ops/decisions/ADR-006-html-mode-bold-visual-design.md`

LangGraph 实现主要参考：

- `docs-langgraph/README.md`
- `docs-langgraph/architecture.md`
- `docs-langgraph/pipeline.md`
- `docs-langgraph/data.md`
- `docs-langgraph/templates.md`
- `docs-langgraph/configuration.md`

注意：`docs-langgraph/` 只提供另一套实现的开发细节说明，实际代码不在本仓库内。因此本文比较的是文档所描述的架构与行为，而不是对两套代码做静态审计。

## 3. 总体架构对比

| 维度 | 当前实现：`docs/` | LangGraph 实现：`docs-langgraph/` |
|---|---|---|
| 系统形态 | Web/API 服务 + 后台任务系统 | CLI 批处理生成器 |
| 主入口 | FastAPI 路由、前端 SPA、Celery 任务 | `python -m ppt_maker run --case <id>` |
| 编排方式 | API 状态流 + Celery 队列 + 普通 Python worker | LangGraph StateGraph + 节点边 + Send fanout + barrier |
| 状态中心 | 数据库实体和项目状态机 | `ProjectState` TypedDict |
| 持久化 | Project、MaterialPackage、MaterialItem、Asset、Slide、Review 等 ORM 表 | `checkpoint.sqlite`、`slide_specs.json`、`logs/run.jsonl` |
| 输入形态 | 项目 brief、用户交互、素材包目录、数据库资源 | `data/case_<id>/` 固定目录和命名约定 |
| 输出形态 | slide HTML、PNG 截图、Review 报告、PDF | `index.html` 单文件 deck、`slide_specs.json` |
| 面向用户 | 多项目、多阶段、可在前端查看和触发操作 | 本地命令行运行、结果目录查看 |
| 核心优势 | 产品化、可追踪、可审查修复、可增量 | 编排清晰、本地轻量、并行节点表达自然 |
| 核心代价 | 工程组件多、运行环境重、链路复杂 | 对固定页数和目录规范依赖强，产品化能力弱 |

当前实现可以理解为“PPT 生成服务平台”。LangGraph 实现可以理解为“固定案例到 HTML deck 的图编排流水线”。

## 4. Pipeline 主流程对比

### 4.1 当前实现流程

当前实现的主流程是素材驱动的项目生命周期：

```text
本地素材包
  -> ingest_local_material_package()
  -> MaterialPackage + MaterialItem + Asset + ProjectBrief
  -> generate_brief_doc()
  -> BriefDoc
  -> generate_outline()
  -> Outline
  -> 用户确认 Outline
  -> bind_materials()
  -> SlideMaterialBinding
  -> compose_all_slides(ComposerMode.HTML)
  -> Slide.spec_json / body_html
  -> generate_visual_theme()
  -> render HTML + Playwright screenshot
  -> review_slides()
  -> repair / recompose / re-render
  -> compile_pdf()
```

它的关键特征是：每个阶段都有数据库实体承载结果，项目状态会随阶段推进，前端或 API 可以读取中间状态。

### 4.2 LangGraph 实现流程

LangGraph 实现的主流程是固定图结构：

```text
START
  -> load_assets
  -> parse_outline + poi_parser
  -> 8 个内容节点并行
  -> case_study_dispatch -> case_study_worker x 3
  -> concept_dispatch -> runninghub_worker x 9
  -> content_join
  -> barrier
  -> summary_node
  -> aggregate_specs
  -> render_html
  -> validate
  -> END
```

它的关键特征是：节点各自写入 `ProjectState` 的局部结果，LangGraph 通过 reducer 合并状态，通过 barrier 保证后续聚合节点在并行任务完成后再执行。

### 4.3 流程差异总结

当前实现是“状态机 + 持久化对象 + 后台任务链”。它更适合用户分阶段介入，例如确认大纲、查看缩略图、触发修复、导出 PDF。

LangGraph 实现是“图节点 + 状态合并 + 一次性批生成”。它更适合固定输入和固定输出的自动化运行，例如一条命令生成完整 40 页 HTML deck。

## 5. 编排模型对比

### 5.1 当前实现：Celery 优先

当前项目已经通过 ADR-002 明确选择 Celery 替代 LangGraph 作为主流程编排方式。主要原因是项目里曾经并存过两条路线：

- `agent/graph.py` 的 LangGraph 路线。
- `api/routers/outlines.py` + Celery 的服务化路线。

ADR-002 的结论是保留 Celery 体系，删除 `agent/graph.py`，避免双流程维护成本。这个决策和当前产品形态一致：服务端需要队列、重试、任务隔离、状态查询、前端轮询、渲染任务限流、导出任务排队。

当前 Celery 体系按任务类型拆分：

| 队列 | 用途 |
|---|---|
| `default` | 素材处理、资产生成、大纲和页面生成 |
| `render` | HTML 渲染、Playwright 截图 |
| `export` | PDF/PPTX 导出 |

这种模型的好处是运维和容量控制直观。渲染任务可以限制 worker 数，导出任务可以单独排队，失败后可以重试或标记项目状态。

### 5.2 LangGraph 实现：图编排优先

LangGraph 方案把流程拆成节点，使用 `ProjectState` 在节点之间传递数据。并发通过两类机制实现：

- 静态并发：多个内容节点从 `parse_outline` 后并行执行。
- 动态并发：`Send` fanout 创建多个 worker，例如案例分析 3 个 worker、概念图 9 个 worker。

状态合并由 reducer 负责，例如：

| 字段 | reducer | 作用 |
|---|---|---|
| `slide_specs` | `merge_dict` | 多个节点分别产出页面 spec 后合并 |
| `charts` | `merge_dict` | 合并图表路径 |
| `generated_images` | `merge_dict` | 合并生成图片路径 |
| `search_cache` | `merge_dict` | 合并搜索结果 |
| `errors` | `operator.add` | 追加节点错误 |

这种模型适合把 PPT 生成过程表达成“可并行的 DAG”。它的优势是流程结构清楚，节点失败可以记录到状态里，checkpoint 可以在崩溃后恢复。

### 5.3 编排取舍

| 问题 | 当前 Celery 方案 | LangGraph 方案 |
|---|---|---|
| 多用户 API 服务 | 更合适 | 需要额外封装 |
| 后台任务监控 | Celery/Redis/Flower 生态成熟 | 依赖自定义日志和 checkpoint |
| 图状依赖表达 | 需要靠代码约定 | 原生表达强 |
| 队列隔离和限流 | 强 | 需要额外实现 |
| 失败恢复 | 任务级重试、状态落库 | checkpoint 恢复 |
| 长期维护 | 更贴近 Web 产品 | 更贴近工作流引擎 |

## 6. 数据模型与状态管理

### 6.1 当前实现的数据模型

当前实现把中间产物拆成多个持久化实体：

| 实体 | 作用 |
|---|---|
| `Project` | 项目生命周期和状态 |
| `ProjectBrief` | 项目基础信息 |
| `MaterialPackage` | 一次素材包版本 |
| `MaterialItem` | 素材包中的单个文件或 chart bundle |
| `Asset` | 从素材派生出的可渲染资源 |
| `BriefDoc` | 面向叙事和大纲的中间文档 |
| `Outline` | PPT 页面结构 |
| `SlideMaterialBinding` | 每页与素材、资产的绑定关系 |
| `Slide` | 每页 spec、HTML、截图和状态 |
| `Review` | 审查报告和修复建议 |

这个模型的核心价值是可追踪。页面中的图片、图表、表格和文字可以反查到 `Asset`、`MaterialItem` 和原始素材文件。后续做素材版本对比、局部再生成、审查归因，都有数据基础。

### 6.2 LangGraph 实现的数据模型

LangGraph 方案的状态集中在 `ProjectState`。它把运行所需内容放在一个状态对象里：

| 字段类型 | 示例 |
|---|---|
| 输入字段 | `project_id`、`case_dir`、`output_dir`、`template`、`dry_run` |
| 加载结果 | `assets`、`outline`、`user_input`、`site_coords`、`poi_data` |
| 合并结果 | `slide_specs`、`charts`、`generated_images`、`search_cache`、`errors` |
| 输出字段 | `output_html` |

最终页面由 `SlideSpec` 描述：

```python
class SlideSpec(BaseModel):
    page: int
    component: ComponentKind
    title: str = ""
    subtitle_en: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None
```

这个模型更轻，适合一次运行内的状态传递。但它缺少当前实现那种跨项目、跨版本、跨页面的关系型追踪能力。

### 6.3 状态管理差异

当前实现的状态是“业务实体状态”。它关注项目是否进入 `MATERIAL_READY`、`OUTLINE_READY`、`SLIDE_PLANNING`、`REVIEWING`、`EXPORTED` 等阶段。

LangGraph 的状态是“运行时图状态”。它关注节点是否产出了 `slide_specs`、`charts`、`generated_images`，以及是否有 `errors`。

前者更适合产品功能，后者更适合工作流运行。

## 7. 素材输入与绑定机制

### 7.1 当前实现：MaterialPackage 作为唯一事实源

当前实现的素材包设计是整套架构的核心。一次素材导入会形成：

```text
MaterialPackage
  -> MaterialItem x N
  -> Asset x N
  -> ProjectBrief
```

每个素材会被归一化为 `logical_key`，例如：

- `site.boundary.image`
- `site.poi.table`
- `site.transport.hub.image`
- `economy.city.chart.0`
- `reference.case.1.thumbnail`
- `reference.case.1.analysis`
- `brief.design_outline`

之后 `Outline` 通过 `required_input_keys` 描述页面需要什么素材，`MaterialBindingAgent` 再把这些需求匹配到具体 `MaterialItem` 和 `Asset`，生成 `SlideMaterialBinding`。

这一层让页面生成不再直接依赖文件名，而是依赖语义化素材键和绑定结果。

### 7.2 LangGraph 实现：目录约定和 AssetIndex

LangGraph 方案从 `data/case_<id>/` 目录加载文件，通过文件名后缀和命名规则识别输入资料。`load_assets` 会构建 `AssetIndex.images/docs/xlsx`，后续节点按约定 key 读取需要的资料。

这种方式实现简单、运行轻量，但对目录结构和命名规范依赖更强。它适合处理标准化案例目录，不太适合用户不断上传、替换、增量更新素材的产品场景。

### 7.3 素材绑定差异

| 维度 | 当前实现 | LangGraph 实现 |
|---|---|---|
| 素材入口 | 素材包 API 和目录 ingest | 固定 case 目录 |
| 语义索引 | `logical_key` + manifest + summary | 文件 stem/key 约定 |
| 页面绑定 | 显式 `SlideMaterialBinding` | 节点内部按页面逻辑取素材 |
| 可追踪性 | 强，页面可追溯到素材项 | 中等，主要依赖输出 spec 和日志 |
| 增量再生成 | 有明确设计基础 | 需要额外构建依赖图 |

## 8. 页面生成与版式系统

### 8.1 当前实现：Composer v3 HTML mode

当前实现已经通过 ADR-006 确定 HTML mode 是主流程。也就是：

```text
LLM -> body_html -> sanitize -> theme CSS 注入 -> render -> screenshot
```

它保留 structured mode 作为 fallback/debug，但主路径是让 Composer 直接输出 HTML 片段。这个选择的目标是提升视觉表现力，让页面可以使用 CSS Grid、Flexbox、SVG、full-bleed image、poster layout、editorial layout 等方式，突破固定 LayoutSpec primitive 的限制。

配套机制包括：

- `VisualTheme` 扩展：`color_mode`、`contrast_level`、`accent_saturation`、`font_mood`、`visual_intensity` 等。
- HTML 安全约束：禁止 script、外部 URL、iframe、事件属性。
- 素材引用约束：图片只能使用 `asset:{id}`。
- Design Advisor gate：视觉评分过低时触发 `recompose_slide_html()`。

### 8.2 LangGraph 实现：Jinja2 component 模板

LangGraph 方案用 `SlideSpec.component` 映射 Jinja2 组件模板：

- `cover`
- `toc`
- `transition`
- `policy_list`
- `chart`
- `table`
- `image_grid`
- `content_bullets`
- `case_card`
- `concept_scheme`
- `ending`

每个组件的 `data` 结构由模板约定。渲染时 `HtmlRenderer` 根据 component 找到 `templates/<style>/components/<component>.html.j2`，生成完整 HTML deck。

这个方式稳定、可控、易调试。缺点是视觉表达依赖模板库，新增页面形态需要新增 `ComponentKind`、模板和节点输出逻辑。

### 8.3 视觉自由度与稳定性

| 维度 | 当前 HTML Composer | LangGraph Jinja 模板 |
|---|---|---|
| 视觉自由度 | 高 | 中 |
| 结构稳定性 | 依赖 prompt、sanitize、review | 模板强约束，稳定 |
| 页面多样性 | 容易生成非对称、海报式、建筑展示型页面 | 受组件集合限制 |
| 可审查修复 | Design Advisor + recompose | 主要靠模板和 validate |
| 调试方式 | 查看 HTML、截图、review 报告 | 查看 `slide_specs.json` 和模板 |

当前方案更像“设计生成器”，LangGraph 方案更像“模板填充器”。

## 9. 渲染与输出

### 9.1 当前实现

当前实现通常会逐页生成：

- 页面 HTML。
- Playwright 截图 PNG。
- Review 报告。
- 最终 PDF。

这条路径适合前端预览。用户可以看到每页缩略图，也可以对部分页面触发 render、review、repair、export。

导出 PDF 时，系统优先复用已有截图；缺失截图时可以回退重新截图，再用 Playwright 或 Pillow 组合 PDF。

### 9.2 LangGraph 实现

LangGraph 方案输出目录通常包含：

```text
output/case_<id>/
  index.html
  slide_specs.json
  assets/
    charts/
    generated/
  checkpoint.sqlite
  logs/run.jsonl
```

主要交付物是 `index.html`。它是一个可在浏览器中翻页的 HTML deck，配合内置导航 JS 使用。

同时它支持 `render-only`，可以直接读取已有 `slide_specs.json` 重新渲染模板。这对调试模板和 CSS 很方便。

### 9.3 输出差异

当前实现面向“生成可交付 PDF 并支持逐页质量管理”。LangGraph 实现面向“快速生成可浏览 HTML deck 并支持本地回放”。

## 10. 质量控制与修复闭环

### 10.1 当前实现：多层审查 + 自动修复

当前实现包含多层 Review：

| 层级 | 关注点 |
|---|---|
| rule | 布局规则、结构约束、可自动 lint 的问题 |
| semantic | 内容语义、信息一致性 |
| vision | 截图层面的视觉缺陷 |
| design_advisor | 设计质量评分、焦点、层级、排版、完成度 |

HTML mode 下，系统更依赖 vision/design review，而不是对 structured LayoutSpec 做 rule lint。ADR-006 中已经把 Design Advisor 从“建议报告”提升为 recompose gate：当 `overall_score < 7.0`、`focal_point < 6.5`、`polish < 6.5` 或重点页面出现 `D012` 等问题时，可以触发 HTML 重组。

这形成了完整闭环：

```text
compose -> render -> screenshot -> review -> recompose -> re-render -> re-review
```

### 10.2 LangGraph 实现：容错完成 + validate

LangGraph 方案的质量控制更偏运行完整性：

- 节点异常会被 `_wrap_with_timer` 捕获并记录到 `errors[]`。
- 节点失败不一定中断整个 deck。
- `aggregate_specs` 会给缺失页面生成 `[missing page N]` 占位。
- `validate` 检查是否有 40 页、每页是否有 spec、`index.html` 是否存在。

这保证一次运行尽可能产出可查看结果，但它不是当前实现那种逐页视觉质量闭环。

### 10.3 质量体系差异

| 维度 | 当前实现 | LangGraph 实现 |
|---|---|---|
| 审查目标 | 页面内容、视觉质量、设计完成度 | 运行完整性、页数完整性 |
| 修复方式 | repair / recompose / re-render | 缺页占位、日志定位后人工修 |
| 自动化深度 | 高 | 中 |
| 成本 | LLM 多轮、截图和 review 成本更高 | 成本较低 |
| 适合场景 | 追求交付质量 | 追求稳定产出草稿 |

## 11. 可扩展性对比

### 11.1 新增页面类型

当前实现中，新增页面类型通常涉及：

- 更新 `PPT_BLUEPRINT` 或大纲生成约束。
- 更新 Composer prompt 的页面类型策略。
- 必要时扩展素材绑定规则。
- 扩展 review 规则或 Design Advisor 页面类型。

LangGraph 实现中，新增页面类型通常涉及：

- 在 `ComponentKind` 中新增 literal。
- 新增 Jinja2 component 模板。
- 新增或修改节点，产出对应 `SlideSpec(component=...)`。
- 如果页数变化，还要修改固定 40 页相关逻辑、chrome 页码、validate。

当前实现扩展更偏 prompt/schema/业务流，LangGraph 扩展更偏模板和节点代码。

### 11.2 新增素材类型

当前实现已经有素材归一化层，新增素材类型可以落在 `MaterialItem -> Asset -> Binding -> Composer` 链路上。只要能给出 `logical_key`、摘要和可渲染 `Asset`，后续流程可以复用。

LangGraph 方案新增素材类型时，需要在加载、节点读取、`SlideSpec.data` 和模板渲染之间打通。对固定场景很直接，但通用性弱一些。

### 11.3 增量再生成

当前实现有更完整的增量基础：

- `MaterialPackage.version`
- `source_hash`
- `SlideMaterialBinding.version`
- `MaterialItem / Asset -> SlideMaterialBinding -> Slide` 依赖链
- diff package 后定位受影响页面的设计方向

LangGraph 方案主要依赖 checkpoint 恢复，而不是业务级素材差异分析。checkpoint 能避免重复跑已完成 superstep，但不等同于“素材更新后只重生受影响页面”。

## 12. 运维与开发体验

### 12.1 当前实现

当前实现需要运行：

- FastAPI 服务。
- 数据库。
- Redis。
- Celery worker。
- Playwright/Chromium。
- 可选前端静态页面。

开发和运维成本较高，但它换来的是服务化能力：API、前端、任务队列、状态查询、PDF 下载、项目历史和持久化审查结果。

### 12.2 LangGraph 实现

LangGraph 实现主要依赖本地 CLI：

```bash
python -m ppt_maker run --case 688
python -m ppt_maker render-only --case 688
python -m ppt_maker inspect --case 688 --page 18
```

调试时主要看：

- `output/case_<id>/slide_specs.json`
- `output/case_<id>/logs/run.jsonl`
- `output/case_<id>/checkpoint.sqlite`
- `output/case_<id>/index.html`

它的本地开发体验更轻，尤其适合调模板和节点逻辑。

## 13. 适用场景

### 13.1 当前实现更适合

- 多用户或多项目管理。
- 需要 Web 前端交互。
- 需要用户确认 brief、大纲或页面结果。
- 需要素材版本管理和可追踪引用。
- 需要逐页审查、自动修复、重新渲染。
- 需要交付 PDF。
- 需要未来支持局部再生成。
- 需要长期产品化维护。

### 13.2 LangGraph 实现更适合

- 输入目录结构固定。
- 页数和章节结构固定，例如稳定生成 40 页。
- 主要目标是快速生成 HTML 演示稿。
- 需要把复杂流程表达成清晰图节点。
- 需要本地 checkpoint 恢复。
- 需要在研究或原型阶段快速验证内容节点和模板。
- 不强调多用户 Web 服务和数据库实体追踪。

## 14. 可以相互借鉴的点

### 14.1 当前实现可借鉴 LangGraph 的点

1. **更清晰的流程图文档**

   LangGraph 文档把节点、barrier、fanout、输出页面关系写得很直观。当前实现虽然有完整 pipeline 文档，但可以进一步补一张“任务链 + 状态迁移 + 数据实体”的总图。

2. **`render-only` 快速回放能力**

   LangGraph 的 `render-only` 对模板调试很实用。当前实现也可以提供类似命令：读取已有 `Slide.spec_json` 或 `body_html`，跳过 LLM，快速重渲染截图/PDF。

3. **简洁的 `run.jsonl` 事件日志**

   当前实现有 Celery 和应用日志，但可以增加面向单次生成 run 的结构化事件日志，记录每个阶段耗时、页数、失败原因、repair 次数。

4. **fanout/barrier 的文档表达方式**

   当前实现虽然用 Celery group 或批量任务也能并发，但文档可借鉴 LangGraph 的表达方式，把“哪些步骤可并行，哪些步骤必须汇合”写清楚。

### 14.2 LangGraph 实现可借鉴当前实现的点

1. **素材包和 `logical_key` 体系**

   如果 LangGraph 方案要提升通用性，应该引入类似 `MaterialPackage`、`MaterialItem`、`logical_key` 的中间层，减少对文件名硬编码的依赖。

2. **显式页面绑定层**

   `SlideMaterialBinding` 能把“本页应该使用哪些素材”固化下来。这对审查、追踪、局部再生成非常重要。

3. **Design Advisor 与修复闭环**

   LangGraph 当前更像一次性生成。若要提高交付质量，可以增加截图审查、设计评分和自动重渲染策略。

4. **API 和前端状态管理**

   如果 LangGraph 方案要产品化，需要补项目状态、任务状态、页面预览、导出下载等服务层能力。

## 15. 迁移判断

不建议当前项目把主流程迁回 LangGraph。原因如下：

- 当前项目已经围绕 API、DB、Celery、素材包、绑定、HTML Composer、Review、PDF 导出形成完整链路。
- ADR-002 已经明确选择 Celery，避免维护双主流程。
- 当前产品目标更偏服务化和交付质量，而不是单次 CLI 生成。
- LangGraph 的优势主要在图编排表达和 checkpoint，而当前项目最需要的是项目生命周期、素材追踪、审查修复和前端可操作性。

更合适的做法是：

- 主流程继续以 `docs/` 当前实现为准。
- `docs-langgraph/` 作为参考设计保留。
- 有选择地吸收 LangGraph 方案中的流程可视化、run 日志、render-only、并行节点文档表达。
- 不把 LangGraph 重新引入为第二套生产编排体系，除非未来有明确需求要支持独立的 CLI 批生成模式。

## 16. 决策表

| 判断项 | 更适合当前实现 | 更适合 LangGraph 实现 |
|---|---:|---:|
| 产品化 Web 服务 | 是 | 否 |
| 多项目持久化 | 是 | 否 |
| 固定 case 快速批处理 | 否 | 是 |
| 流程图表达 | 中 | 强 |
| 队列隔离和后台任务治理 | 强 | 中 |
| checkpoint 恢复 | 中 | 强 |
| 素材版本管理 | 强 | 弱 |
| 页面素材可追踪 | 强 | 中 |
| 自动视觉审查和修复 | 强 | 弱 |
| 模板稳定性 | 中 | 强 |
| 视觉自由度 | 强 | 中 |
| 运维复杂度 | 高 | 低 |
| 适合长期主线 | 是 | 作为参考更合适 |

## 17. 最终建议

当前项目应继续沿用 `docs/` 所描述的服务化架构：素材包作为事实源，Celery 负责任务编排，Composer v3 HTML mode 负责视觉生成，Review/Design Advisor 负责质量闭环，数据库实体负责追踪和增量基础。

`docs-langgraph/` 不应被视为替代主线，而应被视为一套有价值的批处理/图编排参考。它最值得吸收的是流程表达、并行节点拆分、checkpoint 思路、`render-only` 调试体验和结构化运行日志。
