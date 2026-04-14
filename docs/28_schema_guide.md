# Schema 模块说明文档

> 覆盖范围：[schema/](../schema/) 目录下全部 Pydantic 模型（共 11 个文件，~900 行）
> 读者：项目新成员、需要修改数据契约的工程师、Agent 开发者、前后端接口对接方
> 更新时间：2026-04-14

---

## 0. 为什么存在 schema 模块

`schema/` 是整个 PPT Agent 的**数据契约层**。它不是单一用途的 DTO，而是同时承担四种职责：

1. **API I/O 模型**：FastAPI 路由的请求体 / 响应体（`*Create`、`*Read`、`*Input`）
2. **Agent I/O 契约**：Agent 与 Agent 之间、Agent 与 LLM 之间传递的结构化数据（`OutlineSpec`、`LayoutSpec`、`VisualTheme`、`ReviewReport`）
3. **枚举与常量的单一事实源**：状态机、资产类型、严重级别等
4. **ORM ↔ 业务对象的桥梁**：几乎所有 Read 模型都开了 `from_attributes=True`，可以直接从 SQLAlchemy 实例 `model_validate` 得到

因此理解 `schema/` 就相当于理解整套系统的**数据流形态**。读完 `schema/` 再去读 `agent/`、`api/`、`render/`，效率会高一个量级。

---

## 1. 目录总览

```
schema/
├── __init__.py           # 空文件（本模块不做集中导出，全部按子模块显式引用）
├── common.py             # 基类 + 所有枚举
├── project.py            # Project / ProjectBrief / Intake
├── material_package.py   # MaterialPackage / MaterialItem / Binding（Read 视图）
├── asset.py              # Asset + ChartConfig / MapAnnotationConfig
├── outline.py            # OutlineSpec / OutlineSlideEntry
├── page_slot.py          # 蓝图 PageSlot + SlotAssignment（编排中介层）
├── slide.py              # 旧版 SlideSpec + SlideRead（历史兼容）
├── visual_theme.py       # VisualTheme + 11 种 LayoutPrimitive + LayoutSpec ★
├── reference.py          # 参考案例（保留支线）
├── review.py             # 审查报告 + 设计顾问评分
└── site.py               # 地块点位 / 多边形
```

★ 标记的是当前主流程核心。

---

## 2. 基础约定（先读这些再读其它）

### 2.1 `BaseSchema`

位置：[schema/common.py:7-8](../schema/common.py#L7-L8)

```python
class BaseSchema(BaseModel):
    model_config = {"from_attributes": True}
```

**作用**：所有继承 `BaseSchema` 的模型都可以直接从 ORM 实例转换。

```python
from db.models.project import Project as ProjectORM
from schema.project import ProjectRead

orm = db.query(ProjectORM).first()
dto = ProjectRead.model_validate(orm)   # 直接可用
```

**注意**：`visual_theme.py`、`page_slot.py` 里用的是 `pydantic.BaseModel`，**没有** `from_attributes=True`。这是有意的——它们是 LLM 输出契约与蓝图配置，不从 ORM 出发。

### 2.2 命名约定

| 后缀             | 含义                            | 典型来源                       |
|------------------|---------------------------------|--------------------------------|
| `*Create`        | 创建请求体（客户端 → API）      | `ProjectCreate`                |
| `*Input`         | 通用输入体（Agent 或 API 入参） | `ProjectBriefInput`, `VisualThemeInput` |
| `*Read`          | 响应体 / 对外读取视图           | `ProjectRead`, `MaterialItemRead` |
| `*Spec`          | 结构化**产物**契约（LLM 或 Agent 产出） | `OutlineSpec`, `LayoutSpec`, `SlideSpec` |
| `*Report`        | 审查类输出                      | `ReviewReport`                 |
| `*Data`          | 纯字段承载（不绑定 ORM）        | `ProjectBriefData`             |

遇到 `*Spec` 型模型，默认它就是**流水线上的一级产物**，会被落库（通常是 `spec_json` 字段）。

### 2.3 UUID vs str

- 数据库中稳定存在的实体：`project_id`、`package_id`、`slide_id` 等一律用 `UUID`。
- LLM 产出中的业务 ID：`outline_id`、`slide_id`（在 `SlideSpec` 中是 `Optional[str]`）、`review_id` 常为字符串，因为它们**可能在落库前就已经被引用**。
- `slot_id`、`block_id`、`region_id`：业务键，**始终为 str**。

---

## 3. 枚举清单（`common.py`）

`common.py` 是最先需要死记的文件。所有枚举都继承 `str, Enum`，所以可以直接参与 JSON 序列化、SQL 比较、模板字符串插值。

### 3.1 `ProjectStatus`（14 个状态）

项目级状态机。主流程走向：

```
INIT
 └─> INTAKE_IN_PROGRESS ──> INTAKE_CONFIRMED
                              │
                              ├─> REFERENCE_SELECTION (支线)
                              │
                              ├─> ASSET_GENERATING (派生资产)
                              │
                              └─> MATERIAL_READY     ★素材包主流程起点
                                   └─> OUTLINE_READY
                                        └─> BINDING
                                             └─> SLIDE_PLANNING
                                                  └─> RENDERING
                                                       └─> REVIEWING
                                                            └─> READY_FOR_EXPORT
                                                                 └─> EXPORTED
```

`FAILED` 是任意节点都可能转入的终态。

**对齐点**：`docs/05_agent_state_machine.md` 描述了状态迁移的详细规则；`tasks/*.py` 里会看到大量 `project.status = ProjectStatus.XXX` 的赋值。

### 3.2 `SlideStatus`（9 个状态）

单页幻灯片状态机，独立于 `ProjectStatus`。一个项目里的多个 slide 会并发处于不同状态。

```
pending → spec_ready → rendered → review_pending
                                    ├─> review_passed → ready
                                    └─> repair_needed → repair_in_progress → (回到 spec_ready)
failed 可从任意节点进入
```

### 3.3 `AssetType`（9 种）

资产类型分类。**注意**：同一种原始文件可能产生不同 `AssetType`——例如一张图片可能被标为 `IMAGE`，但如果它承担地图角色，会被改成 `MAP`。分类逻辑在 [tool/material_pipeline.py](../tool/material_pipeline.py) 里。

### 3.4 `ReviewSeverity` / `ReviewDecision`

- `P0 / P1 / P2 / PASS`：问题严重级别
- `PASS / REPAIR_REQUIRED / ESCALATE_HUMAN`：审查最终决定

这两个枚举共同决定修复闭环是否触发。

### 3.5 `BuildingType`（8 种）

建筑类型。作用于 `ProjectBriefData.building_type` 与 `ReferenceCase.building_type`，用于参考案例筛选与风格推断。

### 3.6 `LayoutTemplate`（9 种）

**历史模型**。对应旧版 `SlideSpec.layout_template`。当前主流程（`LayoutSpec`）已改用 11 种**布局原语**（见 §7），`LayoutTemplate` 仅在 `schema/slide.py` 中继续使用。新代码不要再基于 `LayoutTemplate` 扩展。

---

## 4. 项目与素材包层（输入契约）

### 4.1 `Project` 相关 — [schema/project.py](../schema/project.py)

| 模型                  | 用途                                            |
|-----------------------|-------------------------------------------------|
| `ProjectCreate`       | `POST /projects` 请求体（只有 `name`）          |
| `ProjectRead`         | 项目视图                                        |
| `ProjectBriefInput`   | 用户原始自然语言输入 + 附件                     |
| `ProjectBriefData`    | 结构化 Brief 字段（Intake Agent 产出）          |
| `ProjectBriefRead`    | `ProjectBriefData` + 持久化字段                 |
| `IntakeFollowUp`      | Intake 阶段的追问响应                           |

**关键点**：
- `ProjectBriefData.far` 有一个 `field_validator`，在未传入 far 时会根据 `gross_floor_area / site_area` 自动计算（见 [project.py:45-53](../schema/project.py#L45-L53)）。改字段时注意这个副作用。
- `missing_fields` 与 `is_complete` 是 Intake 阶段的循环终止条件。

### 4.2 `MaterialPackage` 相关 — [schema/material_package.py](../schema/material_package.py)

这是**当前主流程的事实源**。只定义了 Read 视图（API 返回体），写入路径在 `tool/material_pipeline.py`。

| 模型                       | 对应表                     | 说明                                        |
|----------------------------|----------------------------|---------------------------------------------|
| `LocalMaterialPackageIngestRequest` | —                 | 本地摄入 API 请求体                         |
| `MaterialPackageRead`      | `material_packages`        | 包级别元数据（version、status、manifest）   |
| `MaterialItemRead`         | `material_items`           | 单条素材（图片/表格/文本/文档）             |
| `SlideMaterialBindingRead` | `slide_material_bindings`  | 单页素材绑定结果                            |

**核心概念 `logical_key`**：

`MaterialItem.logical_key` 是一个点分隔的命名空间字符串，用于素材与页面槽位的模式匹配。示例：

```
brief.design_outline              # Brief 级设计总纲文本
site.location.map                 # 地块位置图
reference.case.01.source          # 参考案例 1 的原始材料
reference.case.01.analysis        # 案例 1 的 LLM 分析结果
```

在 [schema/page_slot.py](../schema/page_slot.py) 中，`InputRequirement.logical_key_pattern` 可以带通配符（如 `reference.case.*.analysis`），匹配由 [tool/material_resolver.py](../tool/material_resolver.py) 的 `logical_key_matches` 完成。

**SlideMaterialBinding 字段解读**：
- `must_use_item_ids` / `optional_item_ids`：必用 / 可选素材
- `derived_asset_ids`：由素材派生的资产（图表、地图标注等）
- `evidence_snippets`：绑定时抓取的文本证据，供 Composer 使用
- `coverage_score`：0-1，覆盖度评分
- `missing_requirements`：缺失的需求 pattern，会影响 Critic 判断

### 4.3 `Asset` — [schema/asset.py](../schema/asset.py)

`Asset` 是**渲染层直接消费的资源对象**。与 `MaterialItem` 的区别：

| 对比维度    | `MaterialItem`       | `Asset`                            |
|-------------|----------------------|------------------------------------|
| 来源        | 素材包扫描           | 素材派生（渲染/合成/标注）或直接映射 |
| 消费方      | BriefDoc / Outline Agent | LayoutSpec + 渲染引擎          |
| 引用方式    | `logical_key`        | `asset:{id}` 协议                 |
| 典型内容    | 原始图片 / 文本 / 表格 | PNG 图表 / 标注后地图 / 案例卡片  |

**配置类**：
- `ChartConfig`：生成图表时的描述（类型、数据、配色方案、画布尺寸）。被 [tool/asset/chart_generation.py](../tool/asset/chart_generation.py) 消费。
- `MapAnnotationConfig`：地图标注图的参数。被 [tool/asset/map_annotation.py](../tool/asset/map_annotation.py) 消费。

---

## 5. Outline 层（页级规划）

### 5.1 `OutlineSlideEntry` — [schema/outline.py:8-24](../schema/outline.py#L8-L24)

单页蓝图。是 **Outline Agent 的核心 LLM 输出**。

关键字段：
- `slot_id`：对应 `PageSlot.slot_id`，将本页钉到蓝图模板的某个槽位
- `required_input_keys` / `optional_input_keys`：后续 MaterialBinding Agent 会据此向 `logical_key` 空间匹配
- `coverage_status`：`"covered" | "partial" | "missing" | "unknown"`
- `recommended_binding_scope`：Outline Agent 认为应当优先考虑的 `logical_key` 列表（弱建议）
- `recommended_template`：旧 `LayoutTemplate` 建议，新流程中主要作为 hint
- `is_cover` / `is_chapter_divider`：特殊页标记

### 5.2 `OutlineSpec`

是 LLM 生成的完整大纲：

```
OutlineSpec
 ├─ deck_title
 ├─ theme
 ├─ total_pages
 ├─ sections[]       # 章节名数组
 └─ slides: OutlineSlideEntry[]
```

### 5.3 `OutlineRead`

API 读取视图。注意它没有完全展开 `OutlineSpec`，而是把原始 spec 放在 `spec_json`，再另存 `coverage_json`、`slot_binding_hints_json`。这让数据库侧可以随时加新字段，而不需要迁移表结构。

---

## 6. 蓝图与槽位（`page_slot.py`）

这是连接**静态蓝图（`config/ppt_blueprint.py`）**与**动态大纲（`OutlineSpec`）**的中介层。

### 6.1 `InputRequirement`

描述某个槽位对**一条素材**的需求：

```python
InputRequirement(
    logical_key_pattern="reference.case.*.analysis",
    required=True,
    consume_as="auto",           # 可选 "image" / "text" / ...
    min_count=1, max_count=3,
    preferred_variant=None,
    fallback_policy="allow-empty" # or "fail" / "substitute"
)
```

- `_to_requirement()` 允许传入 `str`、`dict` 或 `InputRequirement` 三种形式，蓝图作者可以用最简 DSL。
- `fallback_policy` 决定素材缺失时的行为——当前主要被 MaterialBinding 阶段读取。

### 6.2 `PageSlot`

蓝图中的**一个槽位模板**。字段分三组：
- 定位：`slot_id` / `title` / `chapter`
- 容量：`page_count_min / max / hint`
- 生成约束：`content_task`（文字化任务描述，给 LLM）+ `required_inputs` + `generation_methods` + `layout_hint`

`generation_methods` 是 `GenerationMethod` 枚举列表，决定本页内容如何产出：
- `LLM_TEXT`：纯 LLM 文字生成
- `CHART`：调用 ChartConfig 生成图
- `NANOBANANA`：图像生成（项目代号）
- `ASSET_REF`：直接引用已有资产
- `WEB_SEARCH`：外部检索
- `COMPOSITE`：混合模式

### 6.3 `PageSlotGroup`

一个**可重复槽位**的定义。典型例子：参考案例页可能有 1-5 个，用 group 表达；Outline Agent 会把 group 展开成多个具体 `SlotAssignment`（`slot_id = "reference-case-1"` / `"reference-case-2"` ...）。

[page_slot.py:102-104](../schema/page_slot.py#L102-L104) 的 `normalize_slot_id()` 用正则把 `reference-case-2` 映射回模板 `reference-case`，在绑定阶段高频使用。

### 6.4 `SlotAssignment` / `SlotAssignmentList`

**LLM 阶段的中间产物**。Outline Agent 先输出 `SlotAssignmentList`，系统再把它转换为 `OutlineSpec`（带 `slide_no`、`coverage_status` 等派生字段）。

---

## 7. 视觉主题与布局（`visual_theme.py`） ★

**这是当前架构中最重要的文件**。900 行的 schema 目录里，这一个文件占 268 行。

### 7.1 整体结构

```
VisualTheme（项目级，一次生成）
 ├─ ColorSystem            # 10 个颜色位
 ├─ TypographySystem       # 字体 / 字阶 / 行高
 ├─ SpacingSystem          # 间距 + 密度
 ├─ DecorationStyle        # 装饰元素语法
 ├─ CoverStyle             # 封面专属
 ├─ style_keywords         # ["水墨留白", "现代简约"]
 └─ generation_prompt_hint # LLM 生成时保留的核心描述

LayoutSpec（页级，每页一次）
 ├─ primitive: LayoutPrimitive    # 11 种之一（见下）
 ├─ region_bindings: RegionBinding[]
 │   └─ blocks: ContentBlock[]    # 文字 / 图像 / 图表 / ...
 ├─ visual_focus                  # 视觉焦点 region_id
 └─ 元信息（slot_id / source_refs / evidence_refs / ...）
```

### 7.2 `VisualTheme` 子系统逐一说明

| 子系统              | 字段数 | 设计动机                                   |
|---------------------|--------|--------------------------------------------|
| `ColorSystem`       | 10     | 强制拆分角色色（primary/accent/surface/overlay/cover_bg）而不是给一张调色板 |
| `TypographySystem`  | 9      | 显式声明字阶比例与行高，避免 LLM 自由发挥 |
| `SpacingSystem`     | 5      | `density` 是重要信号，直接影响 Composer 填充量 |
| `DecorationStyle`   | 7      | 用有限枚举锁定装饰语法，避免 LLM 乱加元素 |
| `CoverStyle`        | 3      | 封面与正文走不同模板                       |

**注意**：`VisualTheme` 是 Pydantic `BaseModel` 而不是 `BaseSchema`——它从 LLM 输出构造，不从 ORM 构造。落库时整体塞进 `visual_themes.theme_json`。

### 7.3 11 种布局原语

每种原语都是一个独立 Pydantic 模型，通过 `LayoutPrimitive = Union[...]` + `Field(discriminator="primitive")` 做**鉴别式联合**。Pydantic 会根据 `primitive` 字段的字面值自动反序列化到正确子类型。

| primitive          | 一句话描述                            | 典型使用场景           |
|--------------------|---------------------------------------|------------------------|
| `full-bleed`       | 整页主视觉 + 可选文字蒙层              | 封面 / 章节过渡        |
| `split-h`          | 左右分栏（ratio 总和 10）              | 地图 + 洞察 / 图 + 文  |
| `split-v`          | 上下分栏                               | 主图 + 信息条          |
| `single-column`    | 单列，带 max_width 与 v_align         | 观点页 / 引文页        |
| `grid`             | 列×行网格，支持 header                 | 画廊 / KPI 矩阵        |
| `hero-strip`       | 主视觉 + 条带（顶部或左侧）            | 封面变体 / 强调页      |
| `sidebar`          | 主区 + 侧栏（含比例与背景）            | 正文 + 注释 / 目录页   |
| `triptych`         | 三联（3 列等宽或非等宽）               | 对比 / 流程三段        |
| `overlay-mosaic`   | 背景图 + 多面板叠加                    | 地图 + 多个数据卡      |
| `timeline`         | 时间轴（水平/垂直、3-7 节点）          | 项目演进 / 进度展示    |
| `asymmetric`       | 自由定位区域（百分比坐标）             | 艺术化编辑页           |

**改动规则**：
- 新增一种原语需要同时改 `render/` 下的模板映射（CSS 与 HTML 框架）。
- 所有几何参数（ratio、opacity、node_count）都带**范围约束注释**，改代码时保留注释。
- `asymmetric` 是万能后门——能不用就不用，因为渲染侧更难保证一致性。

### 7.4 `ContentBlock` 与 `RegionBinding`

原语只描述**空间怎么分**，`region_bindings` 描述**每个区域里放什么**：

- `ContentBlock.content_type` 是 14 种字面值之一（heading/body-text/kpi-value/image/chart/...）
- `content` 可以是字符串、字符串列表，或 `None`（纯装饰元素）
- `emphasis`：`normal | highlight | muted`——Composer 用来控制视觉权重
- `source_refs` / `evidence_refs`：追溯到 `MaterialItem.logical_key` 与证据片段，这是审查与修复闭环的关键

### 7.5 `LayoutSpec` 的元信息字段

```python
section: str = ""         # 所属章节名
title: str = ""           # 页标题（渲染器页脚用）
slot_id: str = ""         # 关联蓝图槽位，便于调试
binding_id: str = ""      # 关联 SlideMaterialBinding，便于溯源
source_refs / evidence_refs  # 全页级溯源
```

这些元信息**不参与视觉渲染**，但参与日志、审查、调试。生成 LayoutSpec 时不要遗漏。

### 7.6 Visual Theme Agent I/O

- `VisualThemeInput`：来自 Brief + Preference + 项目基本信息
- `VisualThemeRead`：API 返回体，扁平化了部分字段（`colors_primary` 等）便于前端直接展示

---

## 8. Slide 旧模型（`slide.py`）

历史上页级协议是 `SlideSpec`，现在已被 `LayoutSpec` 取代。保留它的原因：
- 数据库迁移与历史数据兼容
- `SlideRead` 仍是部分 API 的返回体（`spec_json` 字段可能是 `SlideSpec` 也可能是 `LayoutSpec`）

**新代码不要再产生 `SlideSpec`**。如果你看到 `slide.py` 里的 `BlockContent`、`StyleTokens`、`SlideConstraints`，请注意它们与 `visual_theme.py` 里的 `ContentBlock`、`TypographySystem` 并非同一套——**两套共存是技术债，不是设计**。

如果要做清理，顺序是：
1. 确认所有渲染入口都不再读 `SlideSpec`
2. 把 `SlideRead.spec_json` 的写入方改成只写 `LayoutSpec`
3. 迁移脚本把历史 `SlideSpec` JSON 转成 `LayoutSpec`
4. 最后删除 `schema/slide.py`

---

## 9. 审查层（`review.py`）

### 9.1 规则层审查

`ReviewIssue` 是单条问题，`ReviewReport` 是一次审查的完整结果。`layer` 字段区分来源：
- `"rule"` — 规则层，由 [tool/review/](../tool/review/) 的确定性规则生成
- `"semantic"` — 语义层，LLM 判断
- `"vision"` — 视觉层，基于截图（能力演进中）

### 9.2 设计顾问

`DesignAdvice` 是一条相对独立的审查产物——**维度打分**风格。

- 5 个维度：`color | typography | layout | focal_point | polish`
- `grade`：`"A" | "B" | "C" | "D"`
- `DesignSuggestion.code`：`"D001" ~ "D012"`，用码制便于前端分类展示

`design_advice` 是 `ReviewReport` 的一个可选子字段。并非每次审查都生成，取决于调用方是否启用 `--design-review`（见 [scripts/material_package_e2e.py](../scripts/material_package_e2e.py)）。

### 9.3 修复动作

`RepairAction`：
- `action_type`：如 `"rewrite_block"`、`"replace_asset"`、`"adjust_layout"`
- `target_block_id`：要修改的 `ContentBlock.block_id`
- `params`：自由 dict，具体由 Critic Agent 与修复执行器约定

修复闭环的实际实现分散在 `tasks/review_tasks.py` 与 `agent/critic.py`。

---

## 10. 参考案例与地块（支线）

### 10.1 `reference.py`

参考案例召回/重排/选择链路。当前主流程（素材包优先）不强依赖。`PreferenceSummary` 会被传入 `VisualThemeInput`，影响视觉主题生成——这是这条支线与主线的唯一接触点。

### 10.2 `site.py`

地块点位（经纬度）或多边形（GeoJSON Polygon）。`SitePolygonInput` 带一个 `model_validator` 强制校验 `geojson.type == "Polygon"`（见 [site.py:15-19](../schema/site.py#L15-L19)），多边形以外的 GeoJSON 类型会被拒绝。

---

## 11. Schema 与数据库的映射关系

粗略规则：`schema/*.py` 多数模型都有同名 `db/models/*.py` 对应表。

| schema 文件                | db/models 文件                          | 表名                        |
|----------------------------|-----------------------------------------|-----------------------------|
| `project.py`               | `project.py`（Project + ProjectBrief）  | `projects`, `project_briefs` |
| `material_package.py`      | `material_package.py` + `material_item.py` + `slide_material_binding.py` | `material_packages`, `material_items`, `slide_material_bindings` |
| `asset.py`                 | `asset.py`                              | `assets`                    |
| `outline.py`               | `outline.py`                            | `outlines`                  |
| `slide.py`                 | `slide.py`                              | `slides`                    |
| `visual_theme.py`          | `visual_theme.py`                       | `visual_themes`             |
| `reference.py`             | `reference.py`                          | `reference_cases` 等        |
| `review.py`                | `review.py`                             | `reviews`                   |
| `site.py`                  | `site.py`                               | `sites`                     |

**没有直接对应表的 schema**：
- `common.py`（全是枚举与基类）
- `page_slot.py`（蓝图来自 Python 代码 [config/ppt_blueprint.py](../config/ppt_blueprint.py)，不落库）
- `visual_theme.py` 里的 `VisualTheme` 主体与 11 种原语：整体落在 `visual_themes.theme_json` / `slides.spec_json` 的 JSON 字段里

**核心模式**：主体字段结构化 + 非核心/可演进字段用 `*_json` 存。这是项目的约定之一——改 schema 时先考虑能不能塞进 JSON 字段，避免频繁迁移表。

---

## 12. 修改 schema 的注意事项

### 12.1 新增字段

- **Read 模型**：加 `Optional[...] = None` 是安全的（老数据返回 null）。
- **Input/Create 模型**：必填字段会破坏既有前端调用，默认加可选字段。
- **`*Spec` 模型**：如果字段是 LLM 产物，同时更新对应 prompt 模板（[prompts/](../prompts/)）并跑一次 E2E 验证。

### 12.2 修改枚举

- `ProjectStatus` / `SlideStatus`：改动需要同步 `tasks/`、`api/routers/` 里所有状态跳转，以及前端状态展示。
- `AssetType` / `LayoutTemplate`：删除值会破坏历史数据，优先标记弃用而不是删除。

### 12.3 数据库 JSON 字段

很多字段的实际内容藏在 `spec_json` / `coverage_json` / `theme_json` 里。改这些字段的 Python schema 时，**历史数据不会自动变形**——需要手写迁移脚本或在读取路径做兼容。

### 12.4 兼容性检查清单

改动任何 schema 前，快速 grep：

```bash
grep -r "SchemaName" agent/ api/ tasks/ render/ tool/ tests/
```

尤其注意 `tests/` 下的 fixture，它们经常硬编码了字段名。

---

## 13. 阅读顺序建议

给第一次接触项目的人，推荐按这个顺序读 schema：

1. [common.py](../schema/common.py) — 所有枚举
2. [project.py](../schema/project.py) — 最小闭环模型
3. [material_package.py](../schema/material_package.py) + [asset.py](../schema/asset.py) — 素材侧
4. [page_slot.py](../schema/page_slot.py) — 蓝图层
5. [outline.py](../schema/outline.py) — Outline 产物
6. [visual_theme.py](../schema/visual_theme.py) — **最重要**，反复读
7. [review.py](../schema/review.py) — 审查
8. [slide.py](../schema/slide.py) — 只读，理解历史
9. [reference.py](../schema/reference.py) + [site.py](../schema/site.py) — 支线

读完后，推荐再去翻一次 `test_output/material_package_e2e/run_<时间戳>/` 下的 `outline.json` / `slides_spec.json` / `bindings.json`，把文本读物和真实 JSON 对上，schema 层就吃透了。

---

## 14. 一句话总结

**`schema/` 是系统的数据骨骼；`common.py` 定枚举，`visual_theme.py` 定页面协议，`page_slot.py` 定蓝图语法，其余模块多数是这三者的视图或扩展。**
