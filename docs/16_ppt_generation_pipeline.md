# PPT 生成流程全集成文档

> 本文档描述 PPT Agent 的完整生成流程设计，整合以下两套体系：
> 1. **内容结构**：基于 `prompts/manus.md` 的 40 页蓝图，结构化为 `PageSlot` 系统
> 2. **视觉系统**：基于 `docs/visual_design_system.md` 的 VisualTheme + 布局原语体系
>
> **重要更新**：项目已引入"素材包驱动"的主流程路径。用户通过本地素材包
> （MaterialPackage）提供全部输入素材，替代了原先的逐项数据采集（POI/交通/经济/
> 地图/网搜）环节。本文档同时保留两条路径的说明。
>
> 最后更新：2026-04-25
>
> **2026-04-25 视觉升级口径**：ADR-006 已提出将 Composer v3 HTML 模式统一为产品主流程，structured 模式保留为 fallback/debug。本文档中的 LayoutSpec 说明仍作为 v2 结构化模式参考。

---

## 一、整体流程概览

### 路径 A — 素材包驱动（当前主路径）

```
本地素材文件夹
  ↓
[ 素材包摄入 ]
  扫描 + 分类 → MaterialItem → Asset → ProjectBrief（自动提取）
  ↓
[ Brief Doc Agent ]
  输入：MaterialPackage + MaterialItem + ProjectBrief
  输出：BriefDoc（叙事框架 + 章节结构，结构化 JSON）
  ↓
[ Outline Agent ]
  输入：BriefDoc + PPT_BLUEPRINT + MaterialPackage
  输出：Outline（OutlineSpec = 每页 slot / title / directive / asset_keys）
       + 素材覆盖率分析
  ↓
[ 用户确认大纲 ]
  ↓
[ 素材绑定 ]
  每页 OutlineSlideEntry → SlideMaterialBinding（绑定具体素材与资产）
  ↓
[ Composer Agent（逐页并发）]
  输入：OutlineSlideEntry + SlideMaterialBinding + VisualTheme
  输出：Slide（主流程：HTML/body_html；fallback/debug：LayoutSpec）
  ↓
[ 渲染器 ]
  VisualTheme → 动态 CSS
  HTML 直出或 LayoutSpec 渲染 → 完整 HTML
  Playwright 截图 → PNG
  ↓
[ Review Agent（可选）]
  审查 + 修复（rule / semantic 两层）
  ↓
导出 PDF
```

### 路径 B — 旧路径（案例推荐 + 数据采集，仍可用）

```
用户输入基本项目信息
  ↓
[ Intake Agent ]
  简报提取 → ProjectBriefData 存入 DB
  ↓
[ 前端：案例推荐与选择 ]
  POST /projects/{id}/references/recommend
  用户确认选择 → POST /projects/{id}/references/confirm
  → 生成 PreferenceSummary（dominant_styles / narrative_hint）
  ↓
[ Visual Theme Agent ]
  输入：BuildingType + 风格偏好 + PreferenceSummary
  输出：VisualTheme → 存入 visual_themes 表
  ↓
[ Brief Doc Agent ]
  整合数据 → 结构化 BriefDoc JSON
  ↓
（后续 Outline → Composer → 渲染 → PDF 流程与路径 A 相同）
```

> **注意**：路径 B 中曾设计的并发 Celery 数据采集任务（POI 检索、交通分析、经济
> 图表、地图截图、网络政策搜索）在素材包路径下由用户直接提供素材替代，不再是
> 主流程的必经步骤。

---

## 二、PageSlot 系统

### 2.1 设计原则

`PageSlot` 是 manus.md 的结构化表示。每个 PageSlot 描述：
- 本页/本组的**内容任务**（要做什么）
- 所需的**输入资产**（来自哪里）— 通过 `InputRequirement` 描述
- **生成方式**（LLM 文本 / 图表 / Nanobanana 图像 / 资产引用 / 网络搜索）
- **页数范围**（固定或浮动）

### 2.2 Schema

```python
# schema/page_slot.py

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from uuid import UUID
from enum import Enum


class GenerationMethod(str, Enum):
    LLM_TEXT        = "llm_text"        # LLM 生成文字内容
    CHART           = "chart"           # 图表生成
    NANOBANANA      = "nanobanana"      # Nanobanana 生成图像（规划中，尚未实现）
    ASSET_REF       = "asset_ref"       # 引用已有资产（素材包图片/图表等）
    WEB_SEARCH      = "web_search"      # 联网搜索内容（规划中，尚未实现）
    COMPOSITE       = "composite"       # 多种方式组合


class InputRequirement(BaseModel):
    """结构化的输入需求描述，用于素材包路径下的自动匹配。"""
    logical_key_pattern: str            # 匹配素材的正则模式
    required: bool = True
    consume_as: str = "auto"            # 消费方式
    min_count: int = 1
    max_count: int = 1
    preferred_variant: Optional[str] = None
    fallback_policy: str = "allow-empty"


class PageSlot(BaseModel):
    slot_id: str                        # 唯一标识，如 "cover", "toc", "policy"
    title: str                          # 槽位名称，用于调试和日志
    chapter: str                        # 所属章节

    # 页数控制
    page_count_min: int = 1
    page_count_max: int = 1             # min == max 时为固定页数
    page_count_hint: str = ""           # 调节规则说明

    # 内容任务描述（传给 Composer 的指令）
    content_task: str

    # 所需输入资产 — 支持字符串或 InputRequirement
    # 字符串会自动转换为 InputRequirement(logical_key_pattern=字符串)
    required_inputs: list[InputRequirement] = Field(default_factory=list)

    # 生成方式
    generation_methods: list[GenerationMethod] = Field(
        default_factory=lambda: [GenerationMethod.LLM_TEXT]
    )

    # 布局偏好提示（供 Composer 参考，最终由 LLM 决定）
    layout_hint: str = ""

    # 特殊页面标记
    is_chapter_divider: bool = False
    is_cover: bool = False

    @field_validator("required_inputs", mode="before")
    @classmethod
    def _normalize_required_inputs(cls, value):
        """兼容旧写法：将字符串自动转为 InputRequirement。"""
        if value is None:
            return []
        return [_to_requirement(item) for item in value]

    @property
    def required_input_keys(self) -> list[str]:
        """返回所有 logical_key_pattern，用于素材匹配。"""
        return [req.logical_key_pattern for req in self.required_inputs]


class PageSlotGroup(BaseModel):
    """可变页数的槽位组（如参考案例部分）"""
    group_id: str
    slot_template: PageSlot             # 单个模板（组内所有页面共用）
    repeat_count_min: int = 1
    repeat_count_max: int = 5
    repeat_hint: str = ""               # 如 "按用户选择的案例数量"


class SlotAssignment(BaseModel):
    """Outline Agent 的输出：每个槽位的实际内容指令"""
    slot_id: str
    slide_no: int                       # 实际页码（单页）
    section: str                        # 所属章节
    title: str                          # 页面标题
    content_directive: str              # 针对本项目的具体内容指令
    asset_keys: list[str] = Field(default_factory=list)
    layout_hint: str = ""               # 布局建议
    is_cover: bool = False
    is_chapter_divider: bool = False
    estimated_content_density: str = "medium"  # compact / medium / spacious


class SlotAssignmentList(BaseModel):
    project_id: UUID
    deck_title: str
    total_pages: int
    assignments: list[SlotAssignment]
    visual_theme_id: Optional[UUID] = None
```

> **与旧版差异**：
> - `PageSlotGroup.slots` 改为 `slot_template`（单模板，非列表）
> - `SlotAssignment` 不再有 `actual_page_count` / `page_numbers`，改为单个 `slide_no`
> - 新增 `InputRequirement` 系统，`required_inputs` 类型从 `list[str]` 变为 `list[InputRequirement]`（通过 validator 兼容字符串写法）

---

## 三、完整 PageSlot 蓝图（对应 manus.md 40 页）

```python
# config/ppt_blueprint.py

from schema.page_slot import PageSlot, PageSlotGroup, GenerationMethod

M = GenerationMethod  # 简写

PPT_BLUEPRINT: list[PageSlot | PageSlotGroup] = [

    # ── 封面 ──────────────────────────────────────────────────────────────
    PageSlot(
        slot_id="cover",
        title="封面",
        chapter="封面",
        content_task=(
            "生成封面。① 生成汇报标题、slogan（一句话点题）、英文翻译。"
            "② 调用 Nanobanana 生成项目 logo：简洁抽象线条画，与整体 PPT 风格统一。"
            "标题应简洁有力，英文翻译字面准确且有设计感。"
        ),
        required_inputs=["brief_doc", "project_name"],
        generation_methods=[M.NANOBANANA, M.LLM_TEXT],
        layout_hint="full-bleed 或 split 封面，呼应 CoverStyle.layout_mood",
        is_cover=True,
    ),

    # ── 目录 ──────────────────────────────────────────────────────────────
    PageSlot(
        slot_id="toc",
        title="目录",
        chapter="目录",
        content_task=(
            "生成目录页。① 调用 Nanobanana 生成目录插画：高度抽象概括设计意向，"
            "与设计主题呼应，具有艺术感。② 生成目录标题列表（章节名 + 页码）。"
        ),
        required_inputs=["brief_doc"],
        generation_methods=[M.NANOBANANA, M.LLM_TEXT],
        layout_hint="split-h：左侧大插画，右侧目录列表",
    ),

    # ── 第一章：背景研究 ──────────────────────────────────────────────────
    PageSlot(
        slot_id="chapter-1-divider",
        title="背景研究",
        chapter="背景研究",
        content_task="章节过渡页。标题：背景研究，英文翻译：Background Research。",
        generation_methods=[M.LLM_TEXT],
        layout_hint="full-bleed，章节编号 + 中英文标题",
        is_chapter_divider=True,
    ),

    PageSlotGroup(
        group_id="policy-pages",
        slot_template=PageSlot(
            slot_id="policy",
            title="政策分析",
            chapter="背景研究",
            content_task=(
                "分析设计建议书大纲中相关政策信息，筛选时效性强、与项目匹配度高的政策条目。"
                "每条提供：政策名称、发布时间、核心要点、与项目的关联说明。"
                "提供政策来源网页链接。内容按发布时间倒序排列。"
            ),
            required_inputs=["brief_doc", "web_search_policy"],
            generation_methods=[M.LLM_TEXT, M.WEB_SEARCH],
            layout_hint="sidebar 或 single-column：政策条目列表 + 来源链接",
        ),
        repeat_count_min=2, repeat_count_max=2,
        repeat_hint="固定 2 页政策内容",
    ),

    PageSlot(
        slot_id="policy-impact",
        title="政策影响分析",
        chapter="背景研究",
        content_task=(
            "统筹政策分析内容，分析这些政策对项目的综合影响。"
            "绘制政策影响可视化图表（影响矩阵、雷达图或分类气泡图）。"
            "图表需清晰标注政策名称与影响维度（用地、业态、指标、运营等）。"
        ),
        required_inputs=["brief_doc"],
        generation_methods=[M.LLM_TEXT, M.CHART],
        layout_hint="split-h 或 hero-strip：大图表 + 文字分析",
    ),

    PageSlot(
        slot_id="upper-planning",
        title="上位规划分析",
        chapter="背景研究",
        content_task=(
            "分析设计建议书大纲中的上位规划信息（城市总规、控规、专项规划等）。"
            "注意规划时效性及与项目的匹配程度。"
            "分析上位规划对项目的影响并绘制对比表格（规划名称 / 核心要求 / 对项目影响）。"
            "提供规划文件来源链接。"
        ),
        required_inputs=["brief_doc", "web_search_planning"],
        generation_methods=[M.LLM_TEXT, M.WEB_SEARCH, M.CHART],
        layout_hint="sidebar：规划对比表格 + 文字说明 + 链接注释",
    ),

    PageSlot(
        slot_id="transport-map",
        title="交通与基础设施",
        chapter="背景研究",
        content_task=(
            "展示三张地图资产：枢纽站点分布图、外部交通站点图、周边基础设施建设规划图。"
            "标注各图的关键交通节点及其距离项目的步行/车行时间。"
        ),
        required_inputs=["map_hub_stations", "map_transport_nodes", "map_infra_plan"],
        generation_methods=[M.ASSET_REF],
        layout_hint="triptych：三图并排，下方简要说明条",
    ),

    PageSlot(
        slot_id="cultural-analysis",
        title="文化特征分析",
        chapter="背景研究",
        content_task=(
            "分析设计建议书大纲中的文化特征信息（历史文脉、地域文化、人文特色）。"
            "提炼核心文化意向词（3~5 个），阐述对项目设计的影响。"
            "调用 Nanobanana 生成描述本地文化的插画（风格与 VisualTheme 协调）。"
        ),
        required_inputs=["brief_doc"],
        generation_methods=[M.LLM_TEXT, M.NANOBANANA],
        layout_hint="split-h：左侧文化分析，右侧 Nanobanana 文化插画",
    ),

    PageSlotGroup(
        group_id="economic-pages",
        slot_template=PageSlot(
            slot_id="economic",
            title="经济背景分析",
            chapter="背景研究",
            content_task=(
                "展示城市经济图表资产（GDP 及增速、常驻人口及增速、城镇化率、"
                "第三产业发展情况及增速、产业结构、消费品零售总额、城镇居民人均收支）。"
                "简要分析数据，总结城市经济背景及对项目的机遇与挑战。"
            ),
            required_inputs=[
                "chart_gdp", "chart_population", "chart_urbanization",
                "chart_tertiary", "chart_industry_structure",
                "chart_retail", "chart_income_expense",
            ],
            generation_methods=[M.ASSET_REF, M.LLM_TEXT],
            layout_hint="grid 2×3 或 3×2：图表卡片 + 底部文字总结",
        ),
        repeat_count_min=3, repeat_count_max=3,
        repeat_hint="固定 3 页经济数据",
    ),

    # ── 第二章：场地分析 ──────────────────────────────────────────────────
    PageSlot(
        slot_id="chapter-2-divider",
        title="场地分析",
        chapter="场地分析",
        content_task="章节过渡页。标题：场地分析，英文翻译：Site Analysis。",
        generation_methods=[M.LLM_TEXT],
        layout_hint="full-bleed 章节页",
        is_chapter_divider=True,
    ),

    PageSlotGroup(
        group_id="site-location-pages",
        slot_template=PageSlot(
            slot_id="site-location",
            title="场地区位与四至分析",
            chapter="场地分析",
            content_task=(
                "展示场地区位地图资产（周边基础设施规划、外部交通站点、枢纽站点、场地四至）。"
                "进行项目四至分析：地块优劣势、区位优势、设计注意事项（简洁条目式）。"
            ),
            required_inputs=["map_site_boundary", "map_transport_nodes", "map_hub_stations"],
            generation_methods=[M.ASSET_REF, M.LLM_TEXT],
            layout_hint="overlay-mosaic：大地图 + 浮动分析标注面板",
        ),
        repeat_count_min=4, repeat_count_max=4,
        repeat_hint="固定 4 页场地区位内容",
    ),

    PageSlot(
        slot_id="poi-analysis",
        title="场地 POI 业态分析",
        chapter="场地分析",
        content_task=(
            "分析场地 POI 数据，分析周边业态情况（餐饮、零售、文化、教育、交通等类型占比）。"
            "绘制业态可视化图表（饼图、环形图或气泡图）。"
            "提出 3~5 条设计注意事项（精简条目式）。"
        ),
        required_inputs=["poi_data"],
        generation_methods=[M.CHART, M.LLM_TEXT],
        layout_hint="split-h：左 POI 分类图表，右文字分析 + 注意事项",
    ),

    PageSlot(
        slot_id="site-summary",
        title="场地综合分析",
        chapter="场地分析",
        content_task=(
            "总结场地所有分析内容，从宏观（城市/区域）和微观（地块/周边）两个视角综合分析。"
            "以 SWOT 矩阵或结构化要点形式提出设计注意事项。"
        ),
        required_inputs=["brief_doc", "poi_data"],
        generation_methods=[M.LLM_TEXT, M.CHART],
        layout_hint="sidebar 或 single-column：SWOT 矩阵或分析框",
    ),

    # ── 第三章：竞品分析 ──────────────────────────────────────────────────
    PageSlot(
        slot_id="chapter-3-divider",
        title="竞品分析",
        chapter="竞品分析",
        content_task="章节过渡页。标题：竞品分析，英文翻译：Competitive Analysis。",
        generation_methods=[M.LLM_TEXT],
        layout_hint="full-bleed 章节页",
        is_chapter_divider=True,
    ),

    PageSlot(
        slot_id="competitor-local",
        title="本地竞品分析",
        chapter="竞品分析",
        content_task=(
            "基于场地 POI 数据和场地坐标，分析附近同类或相关产品（竞品项目）。"
            "绘制竞品对比表格（名称、距离、规模、特色、竞争关系）。"
            "给出 2~3 条对本项目的启示。"
        ),
        required_inputs=["poi_data", "site_coordinate"],
        generation_methods=[M.LLM_TEXT, M.CHART],
        layout_hint="sidebar 或 grid：表格为主，配文字分析",
    ),

    PageSlot(
        slot_id="competitor-web",
        title="行业竞品搜索分析",
        chapter="竞品分析",
        content_task=(
            "联网搜索同类或相关产品（国内外标杆案例），分析特点、定位、市场表现。"
            "绘制对比表格（项目名称、地区、规模、特色亮点、对本项目的启示）。"
        ),
        required_inputs=["web_search_competitors"],
        generation_methods=[M.WEB_SEARCH, M.LLM_TEXT, M.CHART],
        layout_hint="sidebar 或 grid：对比表格为主",
    ),

    # ── 第四章：参考案例 ──────────────────────────────────────────────────
    PageSlotGroup(
        group_id="reference-case-pages",
        slot_template=PageSlot(
            slot_id="reference-case",
            title="参考案例",
            chapter="参考案例",
            content_task=(
                "展示参考案例缩略图。分析案例核心特点（设计理念、空间特色、材质策略、建成效果）。"
                "基于设计建议书大纲，提出该案例对待建项目的具体启示（2~4 条）。"
            ),
            required_inputs=["case_thumbnail", "brief_doc", "case_meta"],
            generation_methods=[M.ASSET_REF, M.LLM_TEXT],
            layout_hint="split-h：左案例大图，右分析文字 + 启示条目",
        ),
        repeat_count_min=2, repeat_count_max=5,
        repeat_hint="按用户选择的参考案例数量 1:1，最少 2 页，最多 5 页",
    ),

    # ── 第五章：项目定位 ──────────────────────────────────────────────────
    PageSlot(
        slot_id="project-positioning",
        title="项目定位",
        chapter="项目定位",
        content_task=(
            "综合前述所有分析，总结概括项目定位（一句话定位 + 展开说明）。"
            "从社会价值（城市贡献、文化价值、公共性）和经济价值（商业潜力、运营模式）分别说明。"
        ),
        required_inputs=["brief_doc"],
        generation_methods=[M.LLM_TEXT],
        layout_hint="single-column 或 split-v：大字定位标语 + 下方价值说明",
    ),

    # ── 第六章：设计策略 ──────────────────────────────────────────────────
    PageSlot(
        slot_id="chapter-4-divider",
        title="设计策略",
        chapter="设计策略",
        content_task="章节过渡页。标题：设计策略，英文翻译：Design Strategy。",
        generation_methods=[M.LLM_TEXT],
        layout_hint="full-bleed 章节页",
        is_chapter_divider=True,
    ),

    PageSlot(
        slot_id="design-strategies",
        title="设计策略",
        chapter="设计策略",
        content_task=(
            "分析设计建议书大纲中的设计策略内容。"
            "既有概括性的策略标题（每条一句话），又有详细分项说明。"
            "设计策略需与场地分析、文化分析、项目定位形成逻辑呼应（3~5 条策略）。"
        ),
        required_inputs=["brief_doc"],
        generation_methods=[M.LLM_TEXT],
        layout_hint="triptych 或 grid：多策略并排，每条含标题 + 说明",
    ),

    # ── 第七章：概念方案 ──────────────────────────────────────────────────
    PageSlotGroup(
        group_id="concept-proposal-pages",
        slot_template=PageSlot(
            slot_id="concept-intro",
            title="概念方案介绍",
            chapter="概念方案",
            content_task=(
                "生成概念方案介绍页（3 个方案之一）。"
                "包含：方案名称、一句设计理念（≤20字）、一段理念解析（100~150字）、"
                "两张支撑图（资产引用或分析示意图）。"
            ),
            required_inputs=["brief_doc"],
            generation_methods=[M.LLM_TEXT],
            layout_hint="split-h 或 hero-strip：理念大字 + 图",
        ),
        repeat_count_min=3, repeat_count_max=3,
        repeat_hint="固定 3 个概念方案",
    ),

    PageSlotGroup(
        group_id="concept-aerial-pages",
        slot_template=PageSlot(
            slot_id="concept-aerial",
            title="概念方案鸟瞰图",
            chapter="概念方案",
            content_task=(
                "调用 Nanobanana 生成该概念方案的精致建筑渲染鸟瞰图。"
                "要求：精致的建筑渲染表现图，展现建筑体量和场地关系。"
                "图片下方添加简短图注（≤30字）。"
            ),
            required_inputs=["brief_doc", "concept_description"],
            generation_methods=[M.NANOBANANA],
            layout_hint="full-bleed 或 split-v：大鸟瞰图 + 底部图注条",
        ),
        repeat_count_min=3, repeat_count_max=3,
        repeat_hint="固定 3 个概念方案各一张鸟瞰图",
    ),

    PageSlotGroup(
        group_id="concept-perspective-pages",
        slot_template=PageSlot(
            slot_id="concept-perspective",
            title="概念方案人视图",
            chapter="概念方案",
            content_task=(
                "调用 Nanobanana 生成室外人视图和室内人视图各一张（共两张）。"
                "要求：精致建筑摄影风格，光影真实，构图美感强。"
                "图片旁添加设计亮点注释（2~3 条，每条≤25字）。"
            ),
            required_inputs=["brief_doc", "concept_description"],
            generation_methods=[M.NANOBANANA, M.LLM_TEXT],
            layout_hint="split-h 或 triptych：两张效果图 + 注释文字",
        ),
        repeat_count_min=3, repeat_count_max=3,
        repeat_hint="固定 3 个概念方案各两张人视图",
    ),

    # ── 第八章：深化比选 ──────────────────────────────────────────────────
    PageSlot(
        slot_id="material-economic",
        title="材质分析与经济技术指标",
        chapter="深化比选",
        content_task=(
            "生成三个概念方案各自的材质分析（外立面、内装、景观，各方案 2~3 条）。"
            "生成三个概念方案各自的经济技术指标（用地面积、总建筑面积、容积率、"
            "建筑密度、绿化率、建筑高度、停车位）。"
            "以三列对比表格呈现差异，清晰标注各方案优劣。"
        ),
        required_inputs=["brief_doc", "project_brief_data"],
        generation_methods=[M.LLM_TEXT, M.CHART],
        layout_hint="triptych 或 grid：三方案对比表格，上方材质样板",
    ),

    # ── 第九章：设计任务书 ──────────────────────────────────────────────────
    PageSlot(
        slot_id="design-brief-doc",
        title="设计任务书",
        chapter="设计任务书",
        content_task=(
            "基于所有前述内容，拟定正式设计任务书。"
            "包含：项目概述、设计目标、功能需求（分类列表）、"
            "技术要求、时间节点、注意事项。语言正式规范，结构清晰。"
        ),
        required_inputs=["brief_doc", "project_brief_data"],
        generation_methods=[M.LLM_TEXT],
        layout_hint="single-column 或 sidebar：正式文档排版",
    ),

    # ── 结尾 ──────────────────────────────────────────────────────────────
    PageSlot(
        slot_id="closing",
        title="结尾",
        chapter="结尾",
        content_task=(
            "生成结尾章节。包含感谢语、团队/机构标识占位、联系方式占位。"
            "视觉上呼应封面风格，形成整体感。"
        ),
        required_inputs=["project_name", "client_name"],
        generation_methods=[M.LLM_TEXT],
        layout_hint="full-bleed 或 centered：与封面风格呼应",
        is_chapter_divider=True,
    ),
]
```

### 3.3 页数统计

| 章节 | 固定页数 | 浮动区间 |
|------|---------|---------|
| 封面 + 目录 | 2 | — |
| 背景研究（政策×2 + 影响 + 上位 + 交通 + 文化 + 经济×3 + 章节页×1） | 11 | — |
| 场地分析（场地×4 + POI + 综合 + 章节页×1） | 7 | — |
| 竞品分析（本地 + 网搜 + 章节页×1） | 3 | — |
| 参考案例 | — | 2~5 |
| 项目定位 | 1 | — |
| 设计策略（策略 + 章节页×1） | 2 | — |
| 概念方案（介绍×3 + 鸟瞰×3 + 人视×3） | 9 | — |
| 深化比选 | 1 | — |
| 设计任务书 | 1 | — |
| 结尾 | 1 | — |
| **合计** | **38** | **+0~3** |

> 最终页数范围：**38~41 页**（manus.md 描述约 40 页，完全吻合）
> 实际页数由 `get_total_page_range()` 函数动态计算。

---

## 四、核心模块说明

### 4.1 Brief Doc Agent（`agent/brief_doc.py`）

**职责**：整合素材包数据或旧路径采集数据，生成结构化叙事框架（JSON）。

**输入**：
- 素材包路径：`MaterialPackage` + `MaterialItem`（素材清单摘要 + 文本摘录）
- 旧路径：`Asset` 列表（POI、交通、经济等资产摘要）
- 两条路径均需要 `ProjectBrief`（building_type、city、style_preferences）

**LLM 输出 Schema**：

```python
class _ChapterEntry(BaseModel):
    chapter_id: str
    title: str
    key_findings: list[str] = []
    narrative_direction: str = ""

class _RecommendedEmphasis(BaseModel):
    policy_focus: str = ""
    site_advantage: str = ""
    competitive_edge: str = ""
    case_inspiration: str = ""

class _BriefDocLLMOutput(BaseModel):
    brief_title: str                    # 演示文稿标题
    executive_summary: str              # 项目概述
    chapters: list[_ChapterEntry]       # 章节结构
    positioning_statement: str          # 差异化价值定位
    design_principles: list[str]        # 3~5 个设计方向
    recommended_emphasis: _RecommendedEmphasis
    narrative_arc: str                  # 整体叙事走向
```

**数据库存储**：`brief_docs` 表
- `outline_json`（JSONB）：`_BriefDocLLMOutput` 的完整结构化输出
- `slot_assignments_json`（JSONB，可选）：Outline Agent 产出的 SlotAssignment 数据
- `narrative_summary`（Text）：叙事摘要
- `material_summary_json`（JSONB）：素材包上下文摘要
- `evidence_keys_json`（JSONB）：引用的证据 key 列表
- `package_id`（UUID，可选）：关联的素材包 ID

**调用时机**：素材包摄入后或所有采集任务完成后，Outline Agent 之前。

> **与旧版差异**：不再输出 Markdown 全文（`brief_doc_markdown`），改为结构化 JSON。
> 不再有 `design_concepts` / `style_keywords` 等字段。`slot_assignments` 独立表
> 不存在，数据存储在 `brief_docs.slot_assignments_json` 字段中。

---

### 4.2 Nanobanana 图像生成工具

> **状态：规划中，尚未实现。**
>
> `GenerationMethod.NANOBANANA` 定义于 `schema/page_slot.py` 枚举中，蓝图中多处
> 引用（封面 logo、目录插画、文化插画、鸟瞰图、人视图），但 `tool/image_gen/nanobanana.py`
> 尚未创建。当前流程中 Composer Agent 会在 content_task 中看到 Nanobanana 相关指令，
> 但实际以 LLM 生成的文字占位内容替代。
>
> **预期文件**：`tool/image_gen/nanobanana.py`
> **预期配置**：`config/settings.py` 中的 `running_hub_key`

---

### 4.3 网络搜索工具

> **状态：规划中，尚未实现。**
>
> `GenerationMethod.WEB_SEARCH` 定义于枚举中，蓝图的政策分析、上位规划、行业竞品
> 页面引用，但 `tool/search/web_search.py` 尚未创建。当前流程中这些页面的内容由
> LLM 基于素材包中的文本材料生成，不涉及实际联网搜索。

---

### 4.4 Outline Agent（`agent/outline.py`）

**职责**：
1. 读取 `PPT_BLUEPRINT`（PageSlot 列表）
2. 读取 `BriefDoc` 和 `MaterialPackage`（素材包路径）或 `Asset`（旧路径）
3. 对每个 `PageSlot`/`PageSlotGroup`，生成 `SlotAssignment`（实际页码 + 具体内容指令）
4. 输出 `OutlineSpec`（含最终页码分配）并执行素材覆盖率分析

**输出存储**：`outlines` 表
- `spec_json`（JSONB）：`OutlineSpec`（SlotAssignment 数组）
- `coverage_json`（JSONB）：每页素材覆盖率（complete / partial / missing）
- `slot_binding_hints_json`（JSONB）：每页所需输入 + 推荐匹配范围
- `deck_title`、`theme`、`total_pages`

**素材覆盖率分析**（素材包路径特有）：
- 通过 `tool/material_resolver.py` 的 `expand_requirement()` 将 required_input_keys 展开为正则匹配模式
- `find_matching_items()` 检查 MaterialItem 是否有匹配项
- 标记每页覆盖状态：`complete` / `partial` / `missing`

**页数决策规则**：
```python
# Outline Agent 决策参考
- reference-case-pages: repeat_count = len(selected_cases)，clip 到 [2, 5]
- policy-pages: 固定 2 页
- economic-pages: 固定 3 页
- site-location-pages: 固定 4 页
- concept-proposal-pages: 固定 3 组（intro + aerial + perspective）
```

---

### 4.5 Composer Agent（`agent/composer.py`）

**职责**：逐页生成 HTML 模式的 `body_html`，或在 fallback/debug 场景生成 `LayoutSpec`（结构化模式）。

**两种工作模式**：

```python
class ComposerMode(str, enum.Enum):
    STRUCTURED = "structured"   # v2: 输出 LayoutSpec JSON
    HTML = "html"               # v3: 输出 body_html
```

**当前产品口径（ADR-006）**：
- 主流程应显式使用 `ComposerMode.HTML`
- `structured` 保留为稳定回退、调试和结构化测试路径
- 若代码入口未显式传 mode,需检查是否仍落回 `ComposerMode.STRUCTURED`
- HTML 模式输出存储为 `{"html_mode": true, "body_html": "...", "asset_refs": [...]}`

**输入**：
- `OutlineSlideEntry`：当前页的大纲条目
- `SlideMaterialBinding`：素材绑定信息（derived_asset_ids、evidence_snippets）
- `VisualTheme`：视觉参数
- 已过滤的 `Asset` 列表：仅包含绑定中的资产

**HTML 模式设计规则**：
- Composer v3 直接输出 `<div class="slide-root">...</div>` 内部页面结构
- 必须使用 VisualTheme 注入的 CSS 变量,如 `var(--color-primary)`、`var(--text-h1)`、`var(--safe-margin)`
- 允许使用 CSS Grid/Flexbox/SVG 做非对称构图、满版图、强色块和注释层
- 图片只使用 `asset:{id}` 引用,由渲染器替换为真实 URL
- 设计目标从“信息排版”升级为“有明确视觉焦点的建筑汇报页面”

**LayoutSpec 生成规则（structured fallback/debug）**：
- `is_cover=True` → 使用 `CoverStyle.layout_mood` 对应的原语
- `is_chapter_divider=True` → 强制 `full-bleed`，`density=spacious`
- 其余页面：Composer LLM 根据 `layout_hint` + `VisualTheme` 自由选择最合适的原语

**容错**：
- `_fallback_layout_spec()`：LLM 失败时生成 single-column 兜底布局
- `_html_fallback()`：HTML 模式失败时的最小化输出
- 保证每一页都可渲染，不阻塞后续流程

> **与旧版差异**：Composer 不再按 `GenerationMethod` 分发任务（不调用 Nanobanana、
> matplotlib 或 web_search）。它只负责调用 LLM 生成 LayoutSpec / HTML，将 `asset:uuid`
> 引用嵌入内容块。资产的实际生成由上游（素材包摄入或资产采集任务）完成。

---

## 五、Visual Theme Agent 接入

详细规格见 `docs/visual_design_system.md` 第五节。以下是接入流程关键点：

### 5.1 触发位置

```python
# api/routers/references.py
@router.post("/{project_id}/references/confirm")
async def confirm_references(project_id: UUID, db: Session = Depends(get_db)):
    # 1. 计算 PreferenceSummary
    summary = await summarise_selection_preferences(project_id=project_id, db=db)

    # 2. 读取 ProjectBrief
    brief = db.query(ProjectBrief).filter(...).first()

    # 3. 同步调用 Visual Theme Agent
    inp = VisualThemeInput(
        project_id=project_id,
        building_type=brief.building_type,
        style_preferences=brief.style_preferences or [],
        dominant_styles=summary.dominant_styles,
        dominant_features=summary.dominant_features,
        narrative_hint=summary.narrative_hint,
        project_name=project.name,
        client_name=brief.client_name,
    )
    theme_orm = await generate_visual_theme(inp=inp, db=db)

    # 4. 返回主题信息
    return {
        "theme_id": theme_orm.id,
        "style_keywords": theme_data.get("style_keywords", []),
        "primary_color": theme_data.get("colors", {}).get("primary", ""),
    }
```

> **注意**：实际代码为 `await` 同步调用，非 Celery `.delay()` 异步任务。

### 5.2 数据流

```
PreferenceSummary.dominant_styles
PreferenceSummary.narrative_hint
ProjectBriefData.style_preferences
ProjectBriefData.building_type
    ↓
[ Visual Theme Agent LLM ]
    ↓
VisualTheme（存入 visual_themes 表）
    ↓
─── 后续所有 PPT 生成步骤读取此主题 ───
```

### 5.3 前端展示（可选）

生成 VisualTheme 后，可向前端返回：
- `style_keywords`：显示给用户（"本次 PPT 将采用：水墨留白 · 现代简约 · 江南意境"）
- `colors.primary` / `colors.accent`：可视化显示主色方案
- 用户可选择「重新生成」触发新一轮 Visual Theme 生成

---

## 六、渲染器与视觉系统集成

渲染器完整逻辑见 `docs/visual_design_system.md` 第六节。以下补充与 PageSlot 体系的衔接：

### 6.1 封面渲染特殊处理

```python
def render_cover(layout_spec: LayoutSpec, theme: VisualTheme, assets: dict) -> str:
    cover_style = theme.cover

    # 根据 cover_style.layout_mood 选择基础原语
    mood_to_primitive = {
        "full-bleed": FullBleedLayout(...),
        "split": SplitHLayout(...),
        "centered": SingleColumnLayout(...),
        "editorial": AsymmetricLayout(...),
    }
    # 使用 cover_bg 颜色（可能是渐变）
```

### 6.2 章节过渡页渲染

```python
# 章节页强制 full-bleed + 大字 + 极简装饰
def render_chapter_divider(layout_spec: LayoutSpec, theme: VisualTheme, chapter_no: int) -> str:
    # 背景使用 primary 或 cover_bg
    # 显示：章节编号（超大字）+ 章节中文名 + 英文翻译
    # accent_shape 装饰元素
```

### 6.3 Nanobanana 图像与 VisualTheme 联动（规划中）

> 此功能依赖 Nanobanana 工具实现。当前 Composer 在 content_task 中包含 Nanobanana
> 指令，但实际以文字占位替代。待 `tool/image_gen/nanobanana.py` 实现后，Composer
> 将从 VisualTheme 提取风格信息注入图像生成 Prompt：

```python
def build_nanobanana_prompt(
    base_description: str,
    theme: VisualTheme,
    image_type: str,
) -> str:
    style_desc = ", ".join(theme.style_keywords)
    color_mood = f"color palette inspired by {theme.colors.primary} and {theme.colors.accent}"

    prefix_by_type = {
        "aerial-render": "Aerial architectural rendering, bird's eye view,",
        "street-render": "Architectural photography, eye-level street view,",
        "interior-render": "Interior architectural photography,",
        "illustration": "Abstract architectural illustration, ink wash style,",
        "logo": "Minimalist architectural logo, line drawing,",
    }

    return f"{prefix_by_type[image_type]} {base_description}, {style_desc}, {color_mood}, high quality, professional"
```

---

## 七、数据库变更汇总

### 核心表

```sql
-- 视觉主题
CREATE TABLE visual_themes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  UUID NOT NULL REFERENCES projects(id),
    version     INT NOT NULL DEFAULT 1,
    status      VARCHAR(50) NOT NULL DEFAULT 'draft',
    theme_json  JSONB NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- 设计建议书大纲（结构化 JSON，非 Markdown 全文）
CREATE TABLE brief_docs (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id              UUID NOT NULL REFERENCES projects(id),
    package_id              UUID,                          -- 关联素材包（可选）
    version                 INT NOT NULL DEFAULT 1,
    status                  VARCHAR(50) NOT NULL DEFAULT 'draft',
    outline_json            JSONB NOT NULL,                -- _BriefDocLLMOutput 结构化内容
    slot_assignments_json   JSONB,                         -- SlotAssignment 数据（内嵌）
    narrative_summary       TEXT,
    material_summary_json   JSONB,                         -- 素材包上下文摘要
    evidence_keys_json      JSONB,                         -- 引用的证据 key
    created_at              TIMESTAMPTZ DEFAULT now(),
    updated_at              TIMESTAMPTZ DEFAULT now()
);

-- 大纲
CREATE TABLE outlines (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id              UUID NOT NULL,
    package_id              UUID,                          -- 关联素材包（可选）
    version                 INT NOT NULL DEFAULT 1,
    status                  VARCHAR(50) NOT NULL DEFAULT 'draft',
    deck_title              VARCHAR(500),
    theme                   VARCHAR(100),
    total_pages             INT,
    spec_json               JSONB NOT NULL,                -- OutlineSpec
    coverage_json           JSONB,                         -- 素材覆盖率
    slot_binding_hints_json JSONB,                         -- 素材匹配提示
    confirmed_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ DEFAULT now(),
    updated_at              TIMESTAMPTZ DEFAULT now()
);

-- 素材包相关表（素材包路径专用）
-- material_packages, material_items, assets, slide_material_bindings
-- 详见 docs/20_material_package_integration.md
```

> **与旧版差异**：
> - `brief_docs` 表不再有 `content`（TEXT）和 `concepts`（JSONB）字段
> - `slot_assignments` 独立表不存在，数据嵌入 `brief_docs.slot_assignments_json`
> - 新增 `package_id` 外键关联素材包
> - 新增 `material_items`、`material_packages`、`slide_material_bindings` 表

### 修改表

| 表 | 字段 | 变更 |
|-----|------|------|
| `slides` | `spec_json` | 内容类型由旧 SlideSpec 改为 LayoutSpec |
| `projects` | `visual_theme_id` | 新增，UUID 外键 |
| `projects` | `brief_doc_id` | 新增，UUID 外键 |

---

## 八、完整代码改动清单

### 新建文件

| 文件 | 说明 | 状态 |
|------|------|------|
| `schema/page_slot.py` | PageSlot / PageSlotGroup / SlotAssignment / InputRequirement Schema | ✅ 已实现 |
| `schema/visual_theme.py` | VisualTheme / LayoutSpec / 布局原语 Schema | ✅ 已实现 |
| `config/ppt_blueprint.py` | PPT_BLUEPRINT 完整蓝图 | ✅ 已实现 |
| `agent/brief_doc.py` | Brief Doc Agent | ✅ 已实现 |
| `agent/visual_theme.py` | Visual Theme Agent | ✅ 已实现 |
| `agent/material_binding.py` | 素材绑定 Agent | ✅ 已实现 |
| `tool/material_pipeline.py` | 素材包摄入管道 | ✅ 已实现 |
| `tool/material_resolver.py` | logical_key 匹配与展开 | ✅ 已实现 |
| `tool/image_gen/nanobanana.py` | Nanobanana 图像生成工具 | ❌ 未实现 |
| `tool/search/web_search.py` | 网络搜索工具 | ❌ 未实现 |
| `db/models/visual_theme.py` | VisualTheme ORM | ✅ 已实现 |
| `db/models/brief_doc.py` | BriefDoc ORM | ✅ 已实现 |
| `db/models/material_package.py` | MaterialPackage / MaterialItem ORM | ✅ 已实现 |
| `db/models/slide_material_binding.py` | SlideMaterialBinding ORM | ✅ 已实现 |
| `db/models/asset.py` | Asset ORM | ✅ 已实现 |
| `prompts/visual_theme_system.md` | Visual Theme Agent Prompt | ✅ 已实现 |
| `prompts/brief_doc_system.md` | Brief Doc Agent Prompt | ✅ 已实现 |
| `prompts/outline_system_v2.md` | Outline Agent Prompt（含 PageSlot 引导） | ✅ 已实现 |
| `prompts/composer_system_v2.md` | Composer v2 Prompt（LayoutSpec 输出） | ✅ 已实现 |
| `prompts/composer_system_v3.md` | Composer v3 Prompt（HTML 直出） | ✅ 已实现 |
| `prompts/composer_repair.md` | Composer 修复 Prompt | ✅ 已实现 |

### 重写文件

| 文件 | 说明 |
|------|------|
| `agent/outline.py` | 重构为支持素材包路径 + 覆盖率分析 |
| `agent/composer.py` | 重构为 LayoutSpec 生成（v2）+ HTML 直出（v3），不做 GenerationMethod 分发 |
| `render/engine.py` | 动态 CSS 生成 + 11 种布局原语渲染函数 |

### 保留文件（未按原计划废弃）

| 文件 | 说明 |
|------|------|
| `render/templates/*.html` | 9 个旧模板仍保留（base.html、cover_hero.html 等），作为兼容/降级方案 |
| `render/design_system/tokens.css` | 保留，`generate_theme_css()` 动态生成的 CSS 在新路径中替代此文件 |

### 修改文件

| 文件 | 改动 |
|------|------|
| `api/routers/references.py` | confirm 后同步触发 Visual Theme Agent（`await`，非 Celery） |
| `api/routers/material_packages.py` | 素材包摄入 + BriefDoc 重生成 API |
| `api/routers/outlines.py` | 大纲确认 + compose_render 工作线程 |
| `api/routers/exports.py` | PDF 导出 |
| `tasks/outline_tasks.py` | 加入 BriefDoc 生成步骤 |
| `tasks/asset_tasks.py` | 资产相关任务 |
| `schema/outline.py` | OutlineSlideEntry / OutlineSpec |

---

## 九、实施状态

| 阶段 | 内容 | 状态 |
|------|------|------|
| A | 数据模型（PageSlot / VisualTheme / InputRequirement） | ✅ 完成 |
| B | Visual Theme Agent | ✅ 完成 |
| C | Brief Doc Agent（结构化 JSON 输出） | ✅ 完成 |
| C' | 素材包摄入管道（MaterialPackage / MaterialItem / Asset） | ✅ 完成 |
| C'' | 素材绑定（SlideMaterialBinding） | ✅ 完成 |
| D | Outline + Composer 重构 | ✅ 完成 |
| E | 渲染器（动态 CSS + 11 种布局原语） | ✅ 完成 |
| F | 端到端集成测试 | ✅ 完成（test_output/ 下有多轮测试结果） |
| — | Nanobanana 图像生成工具 | ❌ 待实现 |
| — | 网络搜索工具 | ❌ 待实现 |
| — | Review Agent v2（vision 审查） | ✅ 完成（见 docs/23_vision_review_v2_design_advisor.md） |
