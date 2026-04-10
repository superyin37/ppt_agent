"""
测试辅助：生成标准 VisualTheme 供测试使用，无需调用 LLM。
"""
from uuid import UUID
from schema.visual_theme import (
    VisualTheme, ColorSystem, TypographySystem,
    SpacingSystem, DecorationStyle, CoverStyle,
)


def make_default_theme(project_id: UUID | str | None = None) -> VisualTheme:
    from uuid import uuid4
    return VisualTheme(
        project_id=project_id or uuid4(),
        colors=ColorSystem(
            primary="#1C3A5F", secondary="#2D6A8F", accent="#E8A020",
            background="#F8F6F1", surface="#EDEAE3",
            text_primary="#1C1C1C", text_secondary="#6B6B6B",
            border="#D4D0C8", overlay="rgba(0,0,0,0.55)",
            cover_bg="linear-gradient(135deg, #1C3A5F 0%, #2D6A8F 100%)",
        ),
        typography=TypographySystem(
            font_heading="思源黑体", font_body="思源宋体", font_en="Inter",
            base_size=26, scale_ratio=1.3, heading_weight=700, body_weight=400,
            line_height_body=1.6, line_height_heading=1.15,
            letter_spacing_label="0.08em",
        ),
        spacing=SpacingSystem(base_unit=8, safe_margin=80, section_gap=48, element_gap=24, density="normal"),
        decoration=DecorationStyle(
            use_divider_lines=True, divider_weight="thin",
            color_fill_usage="subtle", border_radius="small",
            image_treatment="natural", accent_shape="line",
            background_texture="flat",
        ),
        cover=CoverStyle(layout_mood="split", title_on_dark=True, show_brief_metrics=True),
        style_keywords=["现代简约", "低调精致"],
        generation_prompt_hint="测试默认主题",
    )
