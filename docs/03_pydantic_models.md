# 03. Pydantic 数据模型

> 最后更新：2026-04-10

> 所有模型基于 Pydantic v2，用于 API 请求/响应校验、LLM 结构化输出、Agent 内部传递。

---

## 3.1 通用基础模型

```python
# schema/common.py
from datetime import datetime
from uuid import UUID, uuid4
from pydantic import BaseModel, Field
from enum import Enum


class BaseSchema(BaseModel):
    model_config = {"from_attributes": True}


class ProjectStatus(str, Enum):
    INIT = "INIT"
    INTAKE_IN_PROGRESS = "INTAKE_IN_PROGRESS"
    INTAKE_CONFIRMED = "INTAKE_CONFIRMED"
    REFERENCE_SELECTION = "REFERENCE_SELECTION"
    ASSET_GENERATING = "ASSET_GENERATING"
    MATERIAL_READY = "MATERIAL_READY"
    OUTLINE_READY = "OUTLINE_READY"
    BINDING = "BINDING"
    SLIDE_PLANNING = "SLIDE_PLANNING"
    RENDERING = "RENDERING"
    REVIEWING = "REVIEWING"
    READY_FOR_EXPORT = "READY_FOR_EXPORT"
    EXPORTED = "EXPORTED"
    FAILED = "FAILED"


class SlideStatus(str, Enum):
    PENDING = "pending"
    SPEC_READY = "spec_ready"
    RENDERED = "rendered"
    REVIEW_PENDING = "review_pending"
    REVIEW_PASSED = "review_passed"
    REPAIR_NEEDED = "repair_needed"
    REPAIR_IN_PROGRESS = "repair_in_progress"
    READY = "ready"
    FAILED = "failed"


class AssetType(str, Enum):
    IMAGE = "image"
    CHART = "chart"
    MAP = "map"
    CASE_CARD = "case_card"
    CASE_COMPARISON = "case_comparison"
    TEXT_SUMMARY = "text_summary"
    KPI_TABLE = "kpi_table"
    OUTLINE = "outline"
    DOCUMENT = "document"


class ReviewSeverity(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    PASS = "PASS"


class ReviewDecision(str, Enum):
    PASS = "pass"
    REPAIR_REQUIRED = "repair_required"
    ESCALATE_HUMAN = "escalate_human"


class BuildingType(str, Enum):
    MUSEUM = "museum"
    OFFICE = "office"
    RESIDENTIAL = "residential"
    MIXED = "mixed"
    HOTEL = "hotel"
    COMMERCIAL = "commercial"
    CULTURAL = "cultural"
    EDUCATION = "education"


class LayoutTemplate(str, Enum):
    COVER_HERO = "cover-hero"
    OVERVIEW_KPI = "overview-kpi"
    MAP_LEFT_INSIGHT_RIGHT = "map-left-insight-right"
    TWO_CASE_COMPARE = "two-case-compare"
    GALLERY_QUAD = "gallery-quad"
    STRATEGY_DIAGRAM = "strategy-diagram"
    CHAPTER_DIVIDER = "chapter-divider"
    CHART_MAIN_TEXT_SIDE = "chart-main-text-side"
    MATRIX_SUMMARY = "matrix-summary"
```

---

## 3.2 项目模型

```python
# schema/project.py
from pydantic import Field, field_validator
from typing import Optional
from uuid import UUID
from datetime import datetime
from .common import BaseSchema, ProjectStatus, BuildingType


class ProjectCreate(BaseSchema):
    name: str = Field(..., min_length=1, max_length=255)


class ProjectRead(BaseSchema):
    id: UUID
    name: str
    status: ProjectStatus
    current_phase: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ProjectBriefInput(BaseSchema):
    raw_text: str = Field(..., description="用户原始输入文本")
    attachments: list[str] = Field(default=[], description="附件 URL 列表")


class ProjectBriefData(BaseSchema):
    building_type: Optional[BuildingType] = None
    client_name: Optional[str] = None
    style_preferences: list[str] = Field(default=[])
    special_requirements: Optional[str] = None

    gross_floor_area: Optional[float] = Field(None, gt=0, description="建筑面积（㎡）")
    site_area: Optional[float] = Field(None, gt=0, description="用地面积（㎡）")
    far: Optional[float] = Field(None, gt=0, description="容积率")

    site_address: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None

    missing_fields: list[str] = Field(default=[], description="当前缺失的必填字段")
    is_complete: bool = False

    @field_validator("far", mode="before")
    @classmethod
    def compute_far_if_missing(cls, v, info):
        if v is None:
            gfa = info.data.get("gross_floor_area")
            site = info.data.get("site_area")
            if gfa and site and site > 0:
                return round(gfa / site, 3)
        return v


class ProjectBriefRead(ProjectBriefData):
    id: UUID
    project_id: UUID
    version: int
    status: str
    created_at: datetime
    updated_at: datetime


class IntakeFollowUp(BaseSchema):
    question: str = Field(..., description="追问文本")
    missing_fields: list[str] = Field(..., description="本次追问针对的缺失字段")
    is_final_confirmation: bool = False
```

---

## 3.3 场地模型

```python
# schema/site.py
from pydantic import Field, model_validator
from typing import Optional
from uuid import UUID
from .common import BaseSchema


class SitePointInput(BaseSchema):
    longitude: float = Field(..., ge=-180, le=180)
    latitude: float = Field(..., ge=-90, le=90)


class SitePolygonInput(BaseSchema):
    geojson: dict = Field(..., description="GeoJSON Polygon 对象")

    @model_validator(mode="after")
    def validate_geojson_type(self):
        if self.geojson.get("type") != "Polygon":
            raise ValueError("geojson 必须为 Polygon 类型")
        return self


class SiteRead(BaseSchema):
    project_id: UUID
    longitude: Optional[float] = None
    latitude: Optional[float] = None
    address_resolved: Optional[str] = None
    geojson: Optional[dict] = None
    area_calculated: Optional[float] = None
```

---

## 3.4 案例模型

```python
# schema/reference.py
from pydantic import Field
from typing import Optional
from uuid import UUID
from .common import BaseSchema, BuildingType


class ReferenceCase(BaseSchema):
    id: UUID
    title: str
    architect: Optional[str] = None
    location: Optional[str] = None
    country: Optional[str] = None
    building_type: BuildingType
    style_tags: list[str] = []
    feature_tags: list[str] = []
    scale_category: Optional[str] = None
    gfa_sqm: Optional[float] = None
    year_completed: Optional[int] = None
    images: list[dict] = []
    summary: Optional[str] = None


class RecommendRequest(BaseSchema):
    project_id: UUID
    top_k: int = Field(default=8, ge=3, le=20)
    style_filter: list[str] = []
    feature_filter: list[str] = []


class RecommendResponse(BaseSchema):
    cases: list[ReferenceCase]
    recommendation_reason: str


class SelectionInput(BaseSchema):
    case_id: UUID
    selected_tags: list[str] = Field(..., min_length=1)
    selection_reason: Optional[str] = None


class SelectionBatchInput(BaseSchema):
    project_id: UUID
    selections: list[SelectionInput] = Field(..., min_length=1, max_length=5)


class PreferenceSummary(BaseSchema):
    dominant_styles: list[str]
    dominant_features: list[str]
    narrative_hint: str
```

---

## 3.5 资产模型

```python
# schema/asset.py
from pydantic import Field
from typing import Optional
from uuid import UUID
from datetime import datetime
from .common import BaseSchema, AssetType


class AssetRead(BaseSchema):
    id: UUID
    project_id: UUID
    version: int
    status: str
    asset_type: AssetType
    subtype: Optional[str] = None
    title: Optional[str] = None
    data_json: Optional[dict] = None
    config_json: Optional[dict] = None
    image_url: Optional[str] = None
    summary: Optional[str] = None
    package_id: Optional[UUID] = None
    source_item_id: Optional[UUID] = None
    logical_key: Optional[str] = None
    variant: Optional[str] = None
    render_role: Optional[str] = None
    created_at: datetime


class ChartConfig(BaseSchema):
    chart_type: str              # bar / line / pie / radar / scatter
    title: str
    x_label: Optional[str] = None
    y_label: Optional[str] = None
    data: list[dict]
    color_scheme: str = "primary"
    width_px: int = 800
    height_px: int = 500


class MapAnnotationConfig(BaseSchema):
    center_lng: float
    center_lat: float
    zoom: int = 14
    annotations: list[dict]
    radius_meters: Optional[int] = None
```

---

## 3.6 素材包模型

```python
# schema/material_package.py
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import Field
from .common import BaseSchema


class LocalMaterialPackageIngestRequest(BaseSchema):
    local_path: str = Field(..., description="Local directory path for a material package")


class MaterialPackageRead(BaseSchema):
    id: UUID
    project_id: UUID
    version: int
    status: str
    source_hash: Optional[str] = None
    manifest_json: Optional[dict] = None
    summary_json: Optional[dict] = None
    created_from: Optional[dict] = None
    created_at: datetime
    updated_at: datetime


class MaterialItemRead(BaseSchema):
    id: UUID
    package_id: UUID
    logical_key: str
    kind: str
    format: str
    title: Optional[str] = None
    source_path: Optional[str] = None
    preview_url: Optional[str] = None
    content_url: Optional[str] = None
    text_content: Optional[str] = None
    structured_data: Optional[dict] = None
    metadata_json: Optional[dict] = None
    created_at: datetime


class SlideMaterialBindingRead(BaseSchema):
    id: UUID
    project_id: UUID
    package_id: UUID
    outline_id: Optional[UUID] = None
    slide_id: Optional[UUID] = None
    slide_no: int
    slot_id: str
    version: int
    status: str
    must_use_item_ids: Optional[list] = None
    optional_item_ids: Optional[list] = None
    derived_asset_ids: Optional[list] = None
    evidence_snippets: Optional[list] = None
    coverage_score: Optional[float] = None
    missing_requirements: Optional[list] = None
    binding_reason: Optional[str] = None
    created_at: datetime
```

---

## 3.7 页面槽位模型

```python
# schema/page_slot.py
from __future__ import annotations

import re
from enum import Enum
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


class GenerationMethod(str, Enum):
    LLM_TEXT = "llm_text"
    CHART = "chart"
    NANOBANANA = "nanobanana"
    ASSET_REF = "asset_ref"
    WEB_SEARCH = "web_search"
    COMPOSITE = "composite"


class InputRequirement(BaseModel):
    logical_key_pattern: str
    required: bool = True
    consume_as: str = "auto"
    min_count: int = 1
    max_count: int = 1
    preferred_variant: Optional[str] = None
    fallback_policy: str = "allow-empty"


def _to_requirement(value: str | dict | InputRequirement) -> InputRequirement:
    if isinstance(value, InputRequirement):
        return value
    if isinstance(value, str):
        return InputRequirement(logical_key_pattern=value)
    if isinstance(value, dict):
        return InputRequirement(**value)
    raise TypeError(f"Unsupported input requirement: {type(value)!r}")


class PageSlot(BaseModel):
    slot_id: str
    title: str
    chapter: str
    page_count_min: int = 1
    page_count_max: int = 1
    page_count_hint: str = ""
    content_task: str
    required_inputs: list[InputRequirement] = Field(default_factory=list)
    generation_methods: list[GenerationMethod] = Field(
        default_factory=lambda: [GenerationMethod.LLM_TEXT]
    )
    layout_hint: str = ""

    is_chapter_divider: bool = False
    is_cover: bool = False

    @field_validator("required_inputs", mode="before")
    @classmethod
    def _normalize_required_inputs(cls, value):
        if value is None:
            return []
        return [_to_requirement(item) for item in value]

    @property
    def required_input_keys(self) -> list[str]:
        return [req.logical_key_pattern for req in self.required_inputs]


class PageSlotGroup(BaseModel):
    group_id: str
    slot_template: PageSlot
    repeat_count_min: int = 1
    repeat_count_max: int = 5
    repeat_hint: str = ""


class SlotAssignment(BaseModel):
    slot_id: str
    slide_no: int
    section: str
    title: str
    content_directive: str
    asset_keys: list[str] = Field(default_factory=list)
    layout_hint: str = ""
    is_cover: bool = False
    is_chapter_divider: bool = False
    estimated_content_density: str = "medium"


class SlotAssignmentList(BaseModel):
    project_id: UUID
    deck_title: str
    total_pages: int
    assignments: list[SlotAssignment]
    visual_theme_id: Optional[UUID] = None


def normalize_slot_id(slot_id: str) -> str:
    """Map grouped slot ids like `reference-case-2` to template slot id."""
    return re.sub(r"-\d+$", "", slot_id)
```

---

## 3.8 大纲模型

```python
# schema/outline.py
from datetime import datetime
from typing import Optional
from uuid import UUID
from .common import BaseSchema, LayoutTemplate


class OutlineSlideEntry(BaseSchema):
    slot_id: str = ""
    slide_no: int
    section: str
    title: str
    purpose: str
    key_message: str
    required_assets: list[str] = []
    required_input_keys: list[str] = []
    optional_input_keys: list[str] = []
    coverage_status: str = "unknown"
    recommended_binding_scope: list[str] = []
    recommended_template: Optional[LayoutTemplate] = None
    layout_hint: str = ""
    estimated_content_density: str = "medium"
    is_cover: bool = False
    is_chapter_divider: bool = False


class OutlineSpec(BaseSchema):
    outline_id: Optional[str] = None
    project_id: UUID
    deck_title: str
    theme: str
    total_pages: int
    sections: list[str]
    slides: list[OutlineSlideEntry]


class OutlineRead(BaseSchema):
    id: UUID
    project_id: UUID
    version: int
    status: str
    deck_title: Optional[str] = None
    theme: Optional[str] = None
    total_pages: Optional[int] = None
    spec_json: dict
    coverage_json: Optional[dict] = None
    slot_binding_hints_json: Optional[dict] = None
    confirmed_at: Optional[datetime] = None
    created_at: datetime
```

---

## 3.9 页面模型

```python
# schema/slide.py
from datetime import datetime
from typing import Optional, Any
from uuid import UUID
from .common import BaseSchema, LayoutTemplate, SlideStatus


class BlockContent(BaseSchema):
    block_id: str
    block_type: str
    content: Any
    position: Optional[dict] = None
    style_overrides: dict = {}
    source_refs: list[str] = []
    evidence_refs: list[str] = []


class SlideConstraints(BaseSchema):
    max_text_chars: int = 200
    max_bullet_points: int = 5
    min_image_count: int = 0
    max_image_count: int = 4


class StyleTokens(BaseSchema):
    primary_color: str = "#1a1a2e"
    accent_color: str = "#e94560"
    background_color: str = "#ffffff"
    font_heading: str = "PingFang SC"
    font_body: str = "PingFang SC"
    font_size_heading: str = "36px"
    font_size_body: str = "18px"


class SlideSpec(BaseSchema):
    slide_id: Optional[str] = None
    project_id: UUID
    slide_no: int
    section: str
    title: str
    purpose: str
    key_message: str
    layout_template: LayoutTemplate
    blocks: list[BlockContent] = []
    constraints: SlideConstraints = SlideConstraints()
    style_tokens: StyleTokens = StyleTokens()
    review_status: str = "pending"
    asset_refs: list[str] = []


class SlideRead(BaseSchema):
    id: UUID
    project_id: UUID
    slide_no: int
    section: Optional[str] = None
    title: Optional[str] = None
    layout_template: Optional[str] = None
    status: SlideStatus
    binding_id: Optional[UUID] = None
    screenshot_url: Optional[str] = None
    repair_count: int
    spec_json: dict
    source_refs_json: Optional[list] = None
    evidence_refs_json: Optional[list] = None
    created_at: datetime
    updated_at: datetime
```

---

## 3.10 审查模型

```python
# schema/review.py
from pydantic import Field
from typing import Optional
from uuid import UUID
from datetime import datetime
from .common import BaseSchema, ReviewSeverity, ReviewDecision


class ReviewIssue(BaseSchema):
    issue_id: str
    rule_code: str
    layer: str
    severity: ReviewSeverity
    message: str
    location: Optional[str] = None
    suggested_fix: str
    auto_fixable: bool = False


class RepairAction(BaseSchema):
    action_type: str
    target_block_id: Optional[str] = None
    params: dict = {}


class DesignDimension(BaseSchema):
    """单维度评分"""
    dimension: str          # "color" | "typography" | "layout" | "focal_point" | "polish"
    score: float            # 0.0 ~ 10.0
    comment: str            # 一句话评价


class DesignSuggestion(BaseSchema):
    """单条改善建议"""
    code: str               # "D001" ~ "D012"
    category: str           # "color" | "typography" | "layout" | "focal_point" | "polish"
    severity: str           # "critical" | "recommended" | "nice-to-have"
    message: str            # 人类可读描述
    css_hint: str = ""      # 可选：建议的 CSS 修改
    target_selector: str = ""  # 可选：目标 CSS 选择器


class DesignAdvice(BaseSchema):
    """设计顾问完整输出"""
    slide_no: int = 0
    dimensions: list[DesignDimension] = []
    overall_score: float = 0.0
    grade: str = "D"        # "A" | "B" | "C" | "D"
    suggestions: list[DesignSuggestion] = []
    one_liner: str = ""


class ReviewReport(BaseSchema):
    review_id: Optional[str] = None
    target_type: str
    target_id: UUID
    review_layer: str
    severity: ReviewSeverity
    issues: list[ReviewIssue] = []
    final_decision: ReviewDecision
    repair_plan: list[RepairAction] = []
    design_advice: Optional[DesignAdvice] = None


class ReviewRead(BaseSchema):
    id: UUID
    project_id: UUID
    target_type: str
    target_id: UUID
    review_layer: str
    severity: Optional[str] = None
    final_decision: Optional[str] = None
    issues_json: list[dict]
    repair_plan: Optional[dict] = None
    created_at: datetime
```

---

## 3.11 视觉主题与布局模型

```python
# schema/visual_theme.py
from __future__ import annotations

from typing import Literal, Union, Optional, Any
from uuid import UUID
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# VisualTheme 子系统
# ─────────────────────────────────────────────

class ColorSystem(BaseModel):
    primary: str            # 主色，hex，如 "#1C3A5F"
    secondary: str          # 辅助色，hex
    accent: str             # 强调色，高饱和，hex
    background: str         # 页面背景，hex
    surface: str            # 卡片/面板背景，hex
    text_primary: str       # 主要文字色，hex
    text_secondary: str     # 次要文字色，hex
    border: str             # 分隔线/边框，hex
    overlay: str            # 图片蒙层，rgba 字符串
    cover_bg: str           # 封面专属背景，hex 或 CSS gradient


class TypographySystem(BaseModel):
    font_heading: str           # 标题字体，如 "思源黑体"
    font_body: str              # 正文字体，如 "思源宋体"
    font_en: str                # 英文/数字字体，如 "Inter"
    base_size: int              # 正文基础字号（px），范围 20~28，推荐 22
    scale_ratio: float          # 字阶比例，范围 1.2~1.5，推荐 1.333
    heading_weight: int         # 标题字重，400 / 500 / 700
    body_weight: int            # 正文字重，通常 400
    line_height_body: float     # 正文行高，如 1.6
    line_height_heading: float  # 标题行高，如 1.15
    letter_spacing_label: str   # 标签字母间距，如 "0.1em"


class SpacingSystem(BaseModel):
    base_unit: int          # 基础间距单位（px），通常 8
    safe_margin: int        # 页面安全边距（px），如 64~96
    section_gap: int        # 主要内容块间距（px），如 40~48
    element_gap: int        # 元素间距（px），如 16~24
    density: Literal["compact", "normal", "spacious"]


class DecorationStyle(BaseModel):
    use_divider_lines: bool
    divider_weight: Literal["hairline", "thin", "medium"]
    color_fill_usage: Literal["none", "subtle", "bold"]
    border_radius: Literal["none", "small", "medium", "large"]
    image_treatment: Literal["natural", "duotone", "desaturated", "framed"]
    accent_shape: Literal["none", "line", "dot", "block", "circle"]
    background_texture: Literal["flat", "subtle-grain", "linen", "concrete"]


class CoverStyle(BaseModel):
    layout_mood: Literal["full-bleed", "split", "centered", "editorial"]
    title_on_dark: bool         # True = 白字（深色背景）
    show_brief_metrics: bool    # 是否显示项目指标摘要


class VisualTheme(BaseModel):
    project_id: UUID

    colors: ColorSystem
    typography: TypographySystem
    spacing: SpacingSystem
    decoration: DecorationStyle
    cover: CoverStyle

    style_keywords: list[str]       # 如 ["水墨留白", "现代简约"]
    generation_prompt_hint: str     # LLM 生成时的核心指令摘要


# ─────────────────────────────────────────────
# 布局原语（11 种）
# ─────────────────────────────────────────────

class FullBleedLayout(BaseModel):
    primitive: Literal["full-bleed"]
    content_anchor: Literal["center", "bottom-left", "top-left", "bottom-center"]
    use_overlay: bool
    overlay_direction: Optional[Literal["top", "bottom", "left", "radial"]] = None
    background_type: Literal["image", "color", "gradient"]


class SplitHLayout(BaseModel):
    primitive: Literal["split-h"]
    left_ratio: int             # 合计 10，如左 6 右 4
    right_ratio: int
    left_content_type: Literal["text", "image", "chart", "map", "mixed"]
    right_content_type: Literal["text", "image", "chart", "map", "mixed"]
    divider: Literal["none", "line", "gap"]
    dominant_side: Literal["left", "right"]


class SplitVLayout(BaseModel):
    primitive: Literal["split-v"]
    top_ratio: int
    bottom_ratio: int
    top_content_type: Literal["text", "image", "chart", "map", "mixed"]
    bottom_content_type: Literal["text", "image", "chart", "map", "mixed"]
    bottom_style: Literal["info-strip", "normal"]


class SingleColumnLayout(BaseModel):
    primitive: Literal["single-column"]
    max_width_ratio: float      # 内容区宽度占页面比例，如 0.6
    v_align: Literal["top", "center", "bottom"]
    has_pull_quote: bool


class GridLayout(BaseModel):
    primitive: Literal["grid"]
    columns: int                # 1~4
    rows: int                   # 1~3
    cell_content_type: Literal["image", "text", "kpi-card", "case-card", "mixed"]
    has_header_row: bool
    gap_size: Literal["tight", "normal", "loose"]


class HeroStripLayout(BaseModel):
    primitive: Literal["hero-strip"]
    hero_position: Literal["top", "left"]
    hero_ratio: float           # 主视觉占比，如 0.7
    hero_content_type: Literal["image", "chart", "map"]
    strip_content_type: Literal["text", "kpi-cards", "bullet-list"]
    strip_use_primary_bg: bool


class SidebarLayout(BaseModel):
    primitive: Literal["sidebar"]
    sidebar_position: Literal["left", "right"]
    sidebar_ratio: float        # 侧栏宽度比例，如 0.28
    main_content_type: Literal["text", "image", "chart", "map", "mixed"]
    sidebar_content_type: Literal["text", "kpi-cards", "image-list", "annotation-list"]
    sidebar_use_surface_bg: bool


class TriptychLayout(BaseModel):
    primitive: Literal["triptych"]
    equal_width: bool
    col_content_types: list[
        Literal["text", "image", "chart", "kpi-card", "case-card"]
    ]  # 长度 3
    has_unified_header: bool
    use_column_dividers: bool


class OverlayMosaicLayout(BaseModel):
    primitive: Literal["overlay-mosaic"]
    background_type: Literal["image", "map"]
    panel_count: int            # 1~5
    panel_arrangement: Literal["corners", "left-stack", "bottom-row", "scatter"]
    panel_content_type: Literal["kpi", "text-annotation", "legend", "mixed"]
    panel_opacity: float        # 0.7~1.0


class TimelineLayout(BaseModel):
    primitive: Literal["timeline"]
    direction: Literal["horizontal", "vertical"]
    node_count: int             # 3~7
    node_content: Literal["text-only", "text-image", "text-kpi"]
    line_style: Literal["solid", "dashed", "dotted"]
    show_progress_state: bool


class AsymmetricRegion(BaseModel):
    region_id: str
    x: float                    # 相对坐标 0.0~1.0
    y: float
    width: float
    height: float
    content_type: Literal["text", "image", "chart", "accent-shape", "empty"]
    z_index: int = 0


class AsymmetricLayout(BaseModel):
    primitive: Literal["asymmetric"]
    regions: list[AsymmetricRegion]


LayoutPrimitive = Union[
    FullBleedLayout,
    SplitHLayout,
    SplitVLayout,
    SingleColumnLayout,
    GridLayout,
    HeroStripLayout,
    SidebarLayout,
    TriptychLayout,
    OverlayMosaicLayout,
    TimelineLayout,
    AsymmetricLayout,
]


# ─────────────────────────────────────────────
# LayoutSpec — 幻灯片级版式规格
# ─────────────────────────────────────────────

class ContentBlock(BaseModel):
    block_id: str
    content_type: Literal[
        "heading", "subheading", "body-text", "bullet-list",
        "kpi-value", "image", "chart", "map", "table",
        "quote", "caption", "label", "accent-element",
    ]
    content: Union[str, list[str], None] = None
    emphasis: Literal["normal", "highlight", "muted"] = "normal"
    style_overrides: dict[str, Any] = {}
    source_refs: list[str] = []
    evidence_refs: list[str] = []


class RegionBinding(BaseModel):
    region_id: str
    blocks: list[ContentBlock]


class LayoutSpec(BaseModel):
    slide_no: int
    primitive: LayoutPrimitive = Field(..., discriminator="primitive")
    region_bindings: list[RegionBinding]
    visual_focus: str           # 视觉重点的 region_id
    is_cover: bool = False
    is_chapter_divider: bool = False

    # 页面元信息（渲染器页脚用）
    section: str = ""
    title: str = ""
    slot_id: str = ""           # 对应 PageSlot.slot_id，便于调试
    binding_id: str = ""
    source_refs: list[str] = []
    evidence_refs: list[str] = []


# ─────────────────────────────────────────────
# Visual Theme Agent I/O
# ─────────────────────────────────────────────

class VisualThemeInput(BaseModel):
    project_id: UUID
    building_type: str
    style_preferences: list[str]
    dominant_styles: list[str]      # 来自 PreferenceSummary
    dominant_features: list[str]
    narrative_hint: str
    project_name: str
    client_name: Optional[str] = None


class VisualThemeRead(BaseModel):
    """API 响应体"""
    id: UUID
    project_id: UUID
    version: int
    status: str
    style_keywords: list[str]
    colors_primary: str
    colors_accent: str
    theme_json: dict
```
