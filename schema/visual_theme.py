"""
VisualTheme — 项目级视觉主题（生成一次，作用于全部幻灯片）
LayoutSpec  — 幻灯片级版式规格（每页生成一次）
布局原语    — 11 种抽象空间结构，描述「空间如何划分」

详见 docs/visual_design_system.md
"""
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
    col_content_types: list[Literal["text", "image", "chart", "kpi-card", "case-card"]]  # 长度 3
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
    content: Union[str, list[str], None] = None     # 文字内容 / asset URL / 条目列表
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
