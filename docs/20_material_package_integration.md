# 素材包驱动的 PPT 生成流程改造开发文档

## 1. 背景

当前项目已经具备 `BriefDoc -> Outline -> Compose -> Render -> Review` 的基本链路，但素材的参与方式仍然偏弱：

- 素材以松散的 `Asset` 列表形式参与流程，缺少统一的素材包抽象。
- `Outline` 和 `Composer` 只能看到浅层素材摘要，无法稳定消费结构化图表、表格、案例原文、地图等输入。
- `PPT_BLUEPRINT.required_inputs` 已经表达了每页所需信息类型，但这些语义需求与实际资产生成结果没有严格对齐。
- 页面生成阶段没有强制的“素材绑定”机制，导致图表、图片、文字内容可能脱离素材包自由发挥。
- 手机端用户每次补充信息后，即使后台重新生成素材，也缺少按素材变化范围进行局部重生成的能力。

在新的产品形态下，假设后台会在每次手机用户输入之后自动生成一个“素材包”，其内容类似 `test_material/project1` 中的目录结构。此时 PPT 生成链路应当以素材包为唯一事实源，确保每一页的图表、图片、数据和文字结论都使用或参考素材包中的对应素材。

本开发文档定义一套完整的素材包集成方案，用于把当前系统从“素材可选参考”改造成“素材强绑定驱动”。

实施层细化请继续参考 [21_material_package_implementation_appendix.md](./21_material_package_implementation_appendix.md)。

## 2. 改造目标

本次改造的目标如下：

1. 将“素材包”提升为 PPT 生成流程中的一级对象，成为整条链路的单一事实源。
2. 将当前“先大纲、后页面”的生成链路升级为“先绑定素材、再生成页面”的链路。
3. 让每一页中的每个核心内容块都能追溯到素材包中的具体来源文件或派生资产。
4. 支持素材包版本化，并基于素材差异进行增量重生成。
5. 在不彻底推翻现有架构的前提下，以渐进方式接入当前系统。

## 3. 核心设计原则

### 3.1 单一事实源

从手机端输入衍生出的素材包是唯一事实源。后续 `BriefDoc`、`Outline`、`Binding`、`Composer`、`Render`、`Review` 都不再直接面向散落文件，而是只消费一个明确版本的素材包。

### 3.2 先绑定，后生成

页面不能在没有素材绑定结果的情况下直接生成。每个页面在进入 `Composer` 前必须明确：

- 本页必须使用哪些素材
- 本页可以参考哪些素材
- 当前是否缺少必要素材
- 这些素材分别将以什么方式被消费

### 3.3 原始素材与派生资产分层

原始素材包中的文件和 PPT 页面可直接消费的页面资产不是同一个层级：

- 原始素材用于表达来源、证据和完整上下文
- 派生资产用于直接服务页面渲染，如图表 SVG、案例缩略图、POI 摘要表等

### 3.4 页面内容可追溯

页面中的图、表、文案应当记录来源引用，使系统能够回答：

- 这张图来自素材包中的哪个文件？
- 这段结论基于哪个表格或案例分析？
- 为什么这一页选用了这个案例而不是另一个？

### 3.5 增量更新优先

手机端补充信息后，不应默认整套 PPT 重做，而应基于素材包版本差异，只重跑受影响的中间层和页面。

## 4. 当前流程与缺口

### 4.1 当前链路

当前主链路可概括为：

1. `ProjectBrief` 进入系统
2. `BriefDoc` 生成叙事中间层
3. `Outline` 基于 `PPT_BLUEPRINT` 生成页面级大纲
4. `Composer` 将每页大纲生成 `LayoutSpec`
5. `Render` 将 `LayoutSpec` 渲染成 HTML / PNG
6. `Review` 对页面进行审查和部分修复

### 4.2 当前素材参与方式

当前素材大致通过 `Asset` 列表接入：

- `tasks/asset_tasks.py` 生成一批通用资产
- `outline.py` 读取资产摘要，供 LLM 参考
- `composer.py` 读取前 20 个素材摘要，供页面生成参考
- `render/engine.py` 只在页面显式输出 `asset:{id}` 时解析资产 URL

### 4.3 当前主要缺口

当前链路相对于素材包驱动模式，存在以下不足：

1. 没有素材包版本对象，只有扁平资产列表。
2. 没有统一逻辑键体系，素材和蓝图需求不能稳定匹配。
3. 没有素材归一化层，xlsx、md、json/svg/html 图表组无法统一消费。
4. 没有页级素材绑定层，导致页面生成缺乏强约束。
5. 没有页面内容到素材来源的追溯信息。
6. 没有基于素材变更的依赖追踪与增量重生成。

## 5. 目标架构

目标架构如下：

1. 手机端用户输入
2. 后台生成 `MaterialPackage vN`
3. 归一化原始素材，生成 `MaterialItem`
4. 基于 `MaterialItem` 生成派生资产 `Asset`
5. `BriefDoc` 基于素材包生成项目叙事摘要
6. `Outline` 基于蓝图和素材覆盖率生成页面大纲
7. `Binding` 将每个页面与具体素材建立绑定关系
8. `Composer` 仅基于页级绑定结果生成 `LayoutSpec`
9. `Render` 根据资产类型选择最佳变体并渲染
10. `Review` 校验页面内容与绑定素材的一致性
11. 如果素材包版本更新，则进行差异分析并增量重生成受影响页面

该架构中最关键的新层为：

- `MaterialPackage`：素材包版本对象
- `MaterialItem`：素材包中的归一化文件对象
- `SlideMaterialBinding`：页面级素材绑定对象

## 6. 数据模型设计

### 6.1 新增 `MaterialPackage`

建议新增表：`material_packages`

推荐字段：

```python
class MaterialPackage(Base):
    __tablename__ = "material_packages"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String, default="ready")
    source_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    manifest_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_from: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

职责：

- 表示某次手机输入后生成的一整包素材快照
- 为后续所有生成阶段提供稳定版本号
- 作为增量重生成的版本边界

### 6.2 新增 `MaterialItem`

建议新增表：`material_items`

推荐字段：

```python
class MaterialItem(Base):
    __tablename__ = "material_items"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    package_id: Mapped[str] = mapped_column(String, ForeignKey("material_packages.id"), index=True)
    logical_key: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String, index=True)
    format: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    source_path: Mapped[str | None] = mapped_column(String, nullable=True)
    preview_url: Mapped[str | None] = mapped_column(String, nullable=True)
    content_url: Mapped[str | None] = mapped_column(String, nullable=True)
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

职责：

- 表示素材包中的每个归一化文件
- 作为“原始证据层”
- 为 LLM 摘要、规则匹配和派生资产生成提供统一输入

### 6.3 扩展现有 `Asset`

当前 `assets` 表建议继续保留，但语义调整为“派生资产层”。

建议新增字段：

```python
package_id: Mapped[str | None]
source_item_id: Mapped[str | None]
logical_key: Mapped[str | None]
variant: Mapped[str | None]
render_role: Mapped[str | None]
```

含义如下：

- `package_id`：该派生资产来自哪个素材包版本
- `source_item_id`：该派生资产来自哪个原始素材条目
- `logical_key`：继承或派生自哪个逻辑键
- `variant`：例如 `svg` / `html` / `thumbnail` / `fullres` / `summary_json`
- `render_role`：例如 `chart` / `hero_image` / `table` / `thumbnail_grid`

### 6.4 新增 `SlideMaterialBinding`

建议新增表：`slide_material_bindings`

```python
class SlideMaterialBinding(Base):
    __tablename__ = "slide_material_bindings"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id"), index=True)
    package_id: Mapped[str] = mapped_column(String, ForeignKey("material_packages.id"), index=True)
    slide_no: Mapped[int] = mapped_column(Integer, index=True)
    slot_id: Mapped[str] = mapped_column(String, index=True)
    must_use_item_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    optional_item_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    derived_asset_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    evidence_snippets: Mapped[list | None] = mapped_column(JSON, nullable=True)
    coverage_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    missing_requirements: Mapped[list | None] = mapped_column(JSON, nullable=True)
    binding_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
```

职责：

- 记录每一页最终绑定了哪些素材
- 在 `Outline` 和 `Composer` 之间建立硬约束
- 为可追溯性、审查、重生成提供依赖依据

## 7. 逻辑键体系

### 7.1 设计目标

逻辑键体系的作用是把“蓝图中的需求”和“素材包中的文件”稳定映射起来。

设计要求：

- 可读
- 稳定
- 可扩展
- 能表达一对一、一对多、多变体关系

### 7.2 命名建议

建议采用点分层级命名：

```text
domain.topic.entity.variant
```

例如：

- `site.boundary.image`
- `site.poi.table`
- `site.poi.stats`
- `site.transport.external.image`
- `site.transport.hub.image`
- `site.transport.hub.table`
- `site.infrastructure.plan.image`
- `economy.city.chart.0`
- `economy.city.chart.1`
- `reference.case.1.source`
- `reference.case.1.analysis`
- `reference.case.1.thumbnail`
- `reference.case.1.images`
- `brief.design_outline`
- `brief.manus_prompt`
- `site.coordinate.text`

### 7.3 对 `test_material/project1` 的建议映射

示例映射如下：

- `场地四至分析_285.png` -> `site.boundary.image`
- `场地poi_285.xlsx` -> `site.poi.table`
- `外部交通_285.png` -> `site.transport.external.image`
- `枢纽站点_285.png` -> `site.transport.hub.image`
- `枢纽站点_POI_285.xlsx` -> `site.transport.hub.table`
- `周边基础设施建设规划_285.png` -> `site.infrastructure.plan.image`
- `经济背景 - 城市经济_chart_0_285.json/svg/html` -> `economy.city.chart.0`
- `参考案例4_archdaily.cn_285.md` -> `reference.case.4.source`
- `案例4_评价和分析_285.md` -> `reference.case.4.analysis`
- `参考案例4.png` -> `reference.case.4.thumbnail`
- `参考案例4-1.png` / `参考案例4-2.png` / `参考案例4-3.png` -> `reference.case.4.images`
- `设计建议书大纲_285.md` -> `brief.design_outline`
- `场地坐标_285.md` -> `site.coordinate.text`
- `manus提示词_285.md` -> `brief.manus_prompt`

## 8. 素材包归一化设计

### 8.1 目标

归一化层负责把素材包目录中的异构文件转成统一结构，以便系统稳定消费。

### 8.2 归一化输入

输入来源包括：

- 手机用户输入衍生出的结构化信息
- 后台自动抓取/生成的文件
- 用户上传文件
- 中间产物文件

### 8.3 归一化策略

#### 文本文件

对 `md` / `txt` / `html`：

- 抽取标题
- 抽取正文文本
- 抽取小节结构
- 生成摘要
- 存入 `text_content` 和 `metadata_json`

#### Excel / 表格文件

对 `xlsx` / `csv`：

- 抽取 sheet 列表
- 抽取表头
- 存储结构化表格数据
- 生成基础统计摘要
- 可额外生成常见维度聚合结果

#### 图表组文件

对同 basename 的 `json` / `svg` / `html`：

- 归并为一个逻辑图表组
- 统一逻辑键
- 在 `metadata_json` 中标明各变体位置
- 保留结构化数据源与视觉呈现变体

#### 图片文件

对 `png` / `jpg` / `jpeg`：

- 提取宽高、方向、主色
- 生成缩略图
- 进行 OCR
- 生成图像标签

### 8.4 Manifest 结构

建议在 `MaterialPackage.manifest_json` 中维护统一清单，例如：

```json
{
  "package_id": "pkg_285_v3",
  "version": 3,
  "items": [
    {
      "id": "mi_site_boundary",
      "logical_key": "site.boundary.image",
      "kind": "image",
      "format": "png",
      "title": "场地四至分析",
      "source_path": "test_material/project1/场地四至分析_285.png"
    },
    {
      "id": "mi_case4_source",
      "logical_key": "reference.case.4.source",
      "kind": "document",
      "format": "md",
      "title": "参考案例4 archdaily 原文"
    }
  ]
}
```

### 8.5 新增模块建议

建议新增：

- `tool/material/ingest.py`
- `tool/material/normalize.py`
- `tasks/material_package_tasks.py`

职责分别为：

- `ingest`：接收目录或上传集合，创建素材包
- `normalize`：按文件类型归一化并生成 `MaterialItem`
- `tasks`：以 Celery 任务形式驱动整个归一化流程

## 9. 派生资产生成设计

### 9.1 原则

并不是所有 `MaterialItem` 都适合被页面直接使用，因此需要生成派生资产层。

### 9.2 典型派生规则

#### POI 表格

输入：

- `site.poi.table`

输出：

- `site.poi.stats`
- `site.poi.chart`
- `site.poi.summary`

#### 图表组

输入：

- `economy.city.chart.0`

输出：

- `Asset(variant="svg", render_role="chart")`
- `Asset(variant="html", render_role="chart")`
- `Asset(variant="summary_json", render_role="chart_data")`

#### 参考案例

输入：

- `reference.case.N.source`
- `reference.case.N.analysis`
- `reference.case.N.images`
- `reference.case.N.thumbnail`

输出：

- `reference.case.N.card`
- `reference.case.N.insights`
- `reference.case.N.gallery`

#### 大纲与 manus

输入：

- `brief.design_outline`
- `brief.manus_prompt`

输出：

- `brief.design_outline.summary`
- `brief.manus_prompt.summary`

### 9.3 对现有 `asset_tasks.py` 的改造

当前 `tasks/asset_tasks.py` 只产出少量通用资产，应改为两类任务：

1. 素材包归一化任务
2. 派生资产生成任务

建议拆分为：

- `tasks/material_package_tasks.py`
- `tasks/derived_asset_tasks.py`

## 10. BriefDoc 改造

### 10.1 当前问题

当前 `BriefDoc` 主要基于项目 brief 和有限素材摘要生成，素材使用深度不足。

### 10.2 新职责

在素材包驱动架构下，`BriefDoc` 应承担：

- 对素材包内容进行全局叙事收束
- 总结当前项目最重要的证据、场地特征、案例方向、经济背景
- 为 `Outline` 提供页级叙事建议，而不是替代素材选择

### 10.3 输入调整

输入应改为：

- `ProjectBrief`
- `MaterialPackage.summary_json`
- 关键 `MaterialItem` 摘要
- 派生资产摘要
- 蓝图章节结构

### 10.4 输出调整

建议在 `BriefDoc` 输出中新增：

- `evidence_keys`
- `recommended_focus_keys`
- `storyline_segments`

以帮助后续 `Outline` 判断哪些章节应优先引用哪些素材域。

## 11. Outline 改造

### 11.1 当前问题

当前 `Outline` 可以生成页面结构，但素材只作为浅层参考信息。

### 11.2 新职责

在新架构中，`Outline` 负责：

- 根据 `PPT_BLUEPRINT` 确定页面结构
- 根据素材包覆盖率判断哪些页面可展开、哪些页面需要降级
- 输出每页的内容意图和素材需求

### 11.3 输入调整

输入建议包括：

- `ProjectBrief`
- `BriefDoc`
- `PPT_BLUEPRINT`
- `MaterialPackage.manifest_json`
- 素材覆盖率统计

### 11.4 输出调整

`OutlineSlideEntry` 建议新增：

- `required_input_keys`
- `optional_input_keys`
- `coverage_status`
- `recommended_binding_scope`

其中：

- `required_input_keys` 用于后续 `Binding`
- `coverage_status` 用于提示该页是否缺素材
- `recommended_binding_scope` 用于帮助 `Binding` 缩小选择范围

### 11.5 PageSlotGroup 的展开逻辑

组页不应固定死，而应参考素材包内容进行展开。

例如：

- 若 `reference.case.*` 存在 4 组完整案例，则可展开 4 页案例页
- 若仅存在 2 组完整案例，则仅展开 2 页或进入降级策略

## 12. 新增 Binding 层

### 12.1 作用

`Binding` 层是本次改造的核心。它位于 `Outline` 和 `Composer` 之间，负责把“页面语义需求”变成“具体素材绑定结果”。

### 12.2 输入

输入包括：

- `OutlineSlideEntry`
- `PageSlot.required_inputs`
- `MaterialPackage.manifest_json`
- 派生资产列表
- `BriefDoc` 中的叙事焦点信息

### 12.3 输出

输出为 `SlideMaterialBinding`

### 12.4 绑定规则

绑定时应执行以下逻辑：

1. 先满足蓝图定义的 `required_inputs`
2. 再挑选最适合的 `optional_inputs`
3. 若素材缺失，则记录 `missing_requirements`
4. 若素材候选过多，则按规则排序选择最佳候选

### 12.5 排序策略

素材候选排序建议参考：

- 逻辑键匹配程度
- 文件类型适配度
- 是否存在派生摘要
- 图像质量 / 分辨率
- 案例完整度
- 与 `BriefDoc` 叙事焦点的一致性

### 12.6 新增模块建议

建议新增：

- `agent/material_binding.py`
- `tool/material/resolver.py`
- `tasks/binding_tasks.py`

## 13. Composer 改造

### 13.1 当前问题

当前 `Composer` 会看到一批浅层素材摘要，但不对素材使用负责。

### 13.2 新输入

`Composer` 不再接收“全量素材摘要列表”，而是只接收当前页的：

- `OutlineSlideEntry`
- `SlideMaterialBinding`
- `VisualTheme`
- 页面上下文

### 13.3 强约束规则

Prompt 中必须明确要求：

1. 图表、图片、地图、案例卡片必须引用绑定资产
2. 文案应优先基于 `evidence_snippets`
3. 不得凭空制造页面关键结论
4. 若缺少关键素材，应选择降级布局，而非伪造内容

### 13.4 输出扩展

建议在 `LayoutSpec` 或 block 层加入：

- `source_refs`
- `evidence_refs`
- `binding_id`

例如：

```json
{
  "kind": "image",
  "asset_ref": "asset:ast_case4_thumbnail",
  "source_refs": ["mi_case4_thumbnail"],
  "binding_id": "bind_slide_22"
}
```

## 14. Render 改造

### 14.1 当前问题

当前渲染器只负责将 `asset:{id}` 替换成 URL，不区分图表、表格、图片的最佳消费方式。

### 14.2 目标

渲染器应根据资产类型与变体优先级进行最佳解析。

### 14.3 变体优先级建议

#### 图表

- 首选 `html`
- 次选 `svg`
- 再次选图片快照

#### 表格

- 首选 `structured_data -> HTML table`
- 次选富文本摘要
- 最后才使用图片

#### 图片

- 导出时优先 full-res
- 预览时可使用 thumbnail

### 14.4 表格和图表专用渲染器

建议在 `render/engine.py` 中引入：

- `render_chart_asset()`
- `render_table_asset()`
- `resolve_best_variant()`

## 15. Review 改造

### 15.1 新增审查维度

现有审查偏向布局和语义，应新增素材一致性审查。

### 15.2 新增规则示例

- 页面必需素材未使用
- 页面引用了未绑定素材
- 图表说明与结构化数据不一致
- 案例图片和案例文案不属于同一案例
- 结论段落没有证据来源

### 15.3 修复策略

部分问题可自动修复：

- 补齐遗漏的素材引用
- 调整错误的资产变体
- 因素材缺失切换布局

其余问题标记为：

- `repair_needed`
- `failed`
- `escalate_human`

## 16. API 改造

### 16.1 新增接口

建议新增：

- `POST /material-packages/ingest`
- `GET /material-packages/{id}`
- `GET /material-packages/{id}/manifest`
- `POST /material-packages/{id}/derive-assets`
- `GET /slides/{slide_no}/binding`
- `POST /slides/rebind`
- `POST /projects/{id}/regenerate-from-package`

### 16.2 现有接口调整

现有 `assets` 相关接口应区分：

- 原始素材浏览
- 派生资产浏览
- 页面绑定结果浏览

## 17. Celery 任务设计

推荐任务链路如下：

1. `ingest_material_package_task`
2. `normalize_material_items_task`
3. `derive_assets_task`
4. `generate_brief_doc_task`
5. `generate_outline_task`
6. `bind_slides_task`
7. `compose_slides_task`
8. `render_slides_task`
9. `review_slides_task`

### 17.1 增量更新任务

新增：

- `diff_material_package_task`
- `collect_impacted_slides_task`
- `rebind_impacted_slides_task`
- `recompose_impacted_slides_task`
- `rerender_impacted_slides_task`

## 18. 增量重生成设计

### 18.1 依赖链

需要建立以下依赖关系：

- `MaterialPackage -> MaterialItem`
- `MaterialItem -> Asset`
- `MaterialItem / Asset -> SlideMaterialBinding`
- `SlideMaterialBinding -> LayoutSpec`
- `LayoutSpec -> RenderedSlide`

### 18.2 差异检测

比较 `package_vN` 和 `package_vN+1` 时：

- 新增素材
- 删除素材
- 素材内容变化
- 素材逻辑键变化

### 18.3 受影响页面识别

若某个 `MaterialItem` 变化，则：

1. 找到引用它的 `SlideMaterialBinding`
2. 定位受影响的 slide
3. 只对这些 slide 重跑 `Binding -> Compose -> Render -> Review`

### 18.4 中间层是否重跑

建议策略：

- 若只是案例图替换，不重跑全量 `Outline`
- 若新增大量案例、地图或核心场地材料，可重跑 `Outline`
- 若只是局部表格更新，通常只需重跑相关页面

## 19. 向后兼容与迁移策略

### 19.1 双轨并行

迁移初期保留旧流程：

- 无素材包时：走旧 `Asset` 驱动链路
- 有素材包时：走新 `MaterialPackage` 驱动链路

### 19.2 逐步替换

建议按以下顺序逐步替换：

1. 先引入素材包对象和归一化层
2. 再将蓝图需求升级为逻辑键体系
3. 再引入 `Binding`
4. 最后升级 `Composer`、`Render`、`Review`

## 20. 测试方案

### 20.1 单元测试

应覆盖：

- 逻辑键映射
- 素材归一化
- 图表组归并
- 案例素材聚合
- 绑定规则排序
- 缺素材降级策略

### 20.2 集成测试

使用 `test_material/project1` 作为主测试夹具，验证：

- 素材包可完整归一化
- `manifest` 中关键逻辑键齐全
- 每个关键页面可获得绑定结果
- 输出的页面资源引用与素材包一致

### 20.3 回归测试

验证以下场景：

- 替换某案例图，仅对应案例页重生成
- 更新经济图表数据，仅经济相关页重生成
- 新增交通素材，仅交通分析页重生成

## 21. 与 `test_material/project1` 的映射样例

以下为示意性映射：

```text
test_material/project1/
  场地四至分析_285.png                   -> site.boundary.image
  场地poi_285.xlsx                       -> site.poi.table
  外部交通_285.png                       -> site.transport.external.image
  枢纽站点_285.png                       -> site.transport.hub.image
  枢纽站点_POI_285.xlsx                  -> site.transport.hub.table
  周边基础设施建设规划_285.png           -> site.infrastructure.plan.image
  参考案例4_archdaily.cn_285.md          -> reference.case.4.source
  案例4_评价和分析_285.md                -> reference.case.4.analysis
  参考案例4.png                          -> reference.case.4.thumbnail
  参考案例4-1.png                        -> reference.case.4.images
  参考案例4-2.png                        -> reference.case.4.images
  参考案例4-3.png                        -> reference.case.4.images
  经济背景 - 城市经济_chart_0_285.json   -> economy.city.chart.0
  经济背景 - 城市经济_chart_0_285.svg    -> economy.city.chart.0
  经济背景 - 城市经济_chart_0_285.html   -> economy.city.chart.0
  设计建议书大纲_285.md                  -> brief.design_outline
  场地坐标_285.md                        -> site.coordinate.text
  manus提示词_285.md                     -> brief.manus_prompt
```

### 21.1 页面绑定示例

假设某一页为“交通分析页”，其绑定结果可能如下：

```json
{
  "slide_no": 16,
  "slot_id": "site-traffic-analysis",
  "must_use_item_ids": [
    "mi_transport_external",
    "mi_hub_map"
  ],
  "optional_item_ids": [
    "mi_hub_poi_table"
  ],
  "derived_asset_ids": [
    "ast_transport_external_image",
    "ast_hub_map_image",
    "ast_hub_poi_summary"
  ],
  "missing_requirements": [],
  "coverage_score": 1.0
}
```

## 22. 推荐落地顺序

建议按以下阶段实施：

### 阶段 1：素材包对象化

- 新增 `MaterialPackage` 和 `MaterialItem`
- 接入 `test_material/project1` 完成归一化
- 生成 `manifest`

### 阶段 2：蓝图逻辑键化

- 改造 `PageSlot.required_inputs`
- 将蓝图页需求与素材逻辑键对齐

### 阶段 3：引入 Binding 层

- 新增 `SlideMaterialBinding`
- 打通 `Outline -> Binding -> Composer`

### 阶段 4：渲染与审查升级

- 引入最佳变体选择
- 增加素材一致性审查

### 阶段 5：增量重生成

- 建立依赖追踪
- 实现 package diff 和局部重生成

## 23. 本次建议涉及的主要文件

建议新增文件：

- `db/models/material_package.py`
- `db/models/material_item.py`
- `db/models/slide_material_binding.py`
- `schema/material_package.py`
- `agent/material_binding.py`
- `tasks/material_package_tasks.py`
- `tasks/derived_asset_tasks.py`
- `tasks/binding_tasks.py`
- `tasks/incremental_regen_tasks.py`
- `tool/material/ingest.py`
- `tool/material/normalize.py`
- `tool/material/resolver.py`

建议修改文件：

- `config/ppt_blueprint.py`
- `schema/page_slot.py`
- `db/models/asset.py`
- `schema/asset.py`
- `agent/brief_doc.py`
- `agent/outline.py`
- `agent/composer.py`
- `render/engine.py`
- `agent/critic.py`
- `tool/review/layout_lint.py`
- `api/routers/assets.py`

## 24. 验收标准

本次改造完成后，应达到以下验收标准：

1. 每个项目可以生成带版本号的 `MaterialPackage`
2. 每个素材包都可归一化出稳定的 `MaterialItem` 清单
3. 蓝图页需求可通过逻辑键与素材包稳定匹配
4. 每个页面在生成前都有 `SlideMaterialBinding`
5. 页面中的图表、图片、文字结论可追溯到素材包来源
6. 替换或新增素材后，系统可只重跑受影响页面
7. 使用 `test_material/project1` 时，可稳定生成与素材包强绑定的 PPT

## 25. 结论

本次改造的关键不在于“给 LLM 更多素材”，而在于将素材包升级为整个 PPT 流程的基础数据层，并在 `Outline` 和 `Composer` 之间加入明确的页面素材绑定层。

只要完成以下三个核心步骤，系统就会从“素材参考型 PPT 生成器”升级为“素材驱动型 PPT 生成器”：

1. 建立 `MaterialPackage + MaterialItem` 体系
2. 将蓝图需求改造成逻辑键驱动
3. 在页面生成前引入 `SlideMaterialBinding`

在此基础上，渲染、审查、增量重生成等能力都可以自然建立，最终让素材包真正成为页面图表、图片和文字内容的共同来源。
