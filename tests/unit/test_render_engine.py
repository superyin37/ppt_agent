"""
Unit tests for render engine v2.
Tests: CSS generation, all 11 layout primitives, asset resolution, footer, chapter divider.
"""
import pytest
from uuid import uuid4

from schema.visual_theme import (
    VisualTheme, ColorSystem, TypographySystem, SpacingSystem,
    DecorationStyle, CoverStyle,
    LayoutSpec, ContentBlock, RegionBinding,
    FullBleedLayout, SplitHLayout, SplitVLayout, SingleColumnLayout,
    GridLayout, HeroStripLayout, SidebarLayout, TriptychLayout,
    OverlayMosaicLayout, TimelineLayout, AsymmetricLayout, AsymmetricRegion,
)
from render.engine import generate_theme_css, render_slide_html, _resolve_asset_refs


# ─── 测试 fixture ───────────────────────────────────────────────────────────

@pytest.fixture
def theme():
    return VisualTheme(
        project_id=uuid4(),
        colors=ColorSystem(
            primary="#1C3A5F", secondary="#2D6A8F", accent="#E8A020",
            background="#F8F6F1", surface="#EDEAE3",
            text_primary="#1C1C1C", text_secondary="#6B6B6B",
            border="#D4D0C8", overlay="rgba(0,0,0,0.55)",
            cover_bg="linear-gradient(135deg, #1C3A5F 0%, #2D6A8F 100%)",
        ),
        typography=TypographySystem(
            font_heading="思源黑体", font_body="思源宋体", font_en="Inter",
            base_size=20, scale_ratio=1.25, heading_weight=700, body_weight=400,
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
        generation_prompt_hint="以冷静克制的蓝灰色系呈现博物馆的学术气质",
    )


def _blocks(*pairs) -> list[ContentBlock]:
    """pairs: (block_id, content_type, content)"""
    return [ContentBlock(block_id=p[0], content_type=p[1], content=p[2]) for p in pairs]


def _spec(slide_no: int, primitive, bindings: list[RegionBinding], **kw) -> LayoutSpec:
    return LayoutSpec(slide_no=slide_no, primitive=primitive, region_bindings=bindings,
                      visual_focus="content", **kw)


# ─── CSS 生成 ───────────────────────────────────────────────────────────────

def test_css_contains_color_vars(theme):
    css = generate_theme_css(theme)
    assert "--color-primary" in css
    assert "--color-accent" in css
    assert "--color-bg" in css
    assert "#1C3A5F" in css


def test_css_contains_font_vars(theme):
    css = generate_theme_css(theme)
    assert "--font-heading" in css
    assert "思源黑体" in css
    assert "--font-en" in css


def test_css_type_scale_computed(theme):
    css = generate_theme_css(theme)
    # base=20, ratio=1.25 → h1 = round(20 * 1.25^3) = 39
    assert "--text-h1:" in css
    assert "39px" in css


def test_css_border_radius(theme):
    css = generate_theme_css(theme)
    assert "--border-radius: 4px" in css


# ─── 布局原语渲染 ────────────────────────────────────────────────────────────

def _assert_valid_html(html: str):
    assert isinstance(html, str)
    assert len(html) > 200
    assert "<!DOCTYPE html>" in html
    assert "</html>" in html
    assert "<style>" in html


def test_full_bleed(theme):
    spec = _spec(1, FullBleedLayout(
        primitive="full-bleed", content_anchor="bottom-left",
        use_overlay=True, overlay_direction="bottom", background_type="color",
    ), [RegionBinding(region_id="content", blocks=_blocks(
        ("h", "heading", "项目标题"),
        ("s", "subheading", "副标题"),
    ))], is_cover=True)
    html = render_slide_html(spec, theme)
    _assert_valid_html(html)
    assert "项目标题" in html
    assert "副标题" in html


def test_split_h(theme):
    spec = _spec(2, SplitHLayout(
        primitive="split-h", left_ratio=6, right_ratio=4,
        left_content_type="image", right_content_type="text",
        divider="line", dominant_side="left",
    ), [
        RegionBinding(region_id="left", blocks=_blocks(("img", "image", "https://example.com/img.jpg"))),
        RegionBinding(region_id="right", blocks=_blocks(("h", "heading", "分析标题"), ("b", "body-text", "分析内容"))),
    ])
    html = render_slide_html(spec, theme)
    _assert_valid_html(html)
    assert "example.com/img.jpg" in html
    assert "分析标题" in html


def test_split_v(theme):
    spec = _spec(3, SplitVLayout(
        primitive="split-v", top_ratio=7, bottom_ratio=3,
        top_content_type="image", bottom_content_type="text",
        bottom_style="info-strip",
    ), [
        RegionBinding(region_id="top", blocks=_blocks(("img", "image", ""))),
        RegionBinding(region_id="bottom", blocks=_blocks(("cap", "caption", "图注说明"))),
    ])
    html = render_slide_html(spec, theme)
    _assert_valid_html(html)
    assert "图注说明" in html


def test_single_column(theme):
    spec = _spec(4, SingleColumnLayout(
        primitive="single-column", max_width_ratio=0.65, v_align="center", has_pull_quote=True,
    ), [
        RegionBinding(region_id="pull-quote", blocks=_blocks(("q", "quote", "设计即生活的凝练"))),
        RegionBinding(region_id="content", blocks=_blocks(("b", "body-text", "正文内容段落。"))),
    ])
    html = render_slide_html(spec, theme)
    _assert_valid_html(html)
    assert "设计即生活的凝练" in html
    assert "正文内容段落" in html


def test_grid(theme):
    spec = _spec(5, GridLayout(
        primitive="grid", columns=3, rows=2, cell_content_type="kpi-card",
        has_header_row=True, gap_size="normal",
    ), [
        RegionBinding(region_id="header", blocks=_blocks(("h", "heading", "经济指标"))),
        RegionBinding(region_id="cell-0-0", blocks=_blocks(("v", "kpi-value", "10万㎡"))),
        RegionBinding(region_id="cell-0-1", blocks=_blocks(("v", "kpi-value", "2.5"))),
        RegionBinding(region_id="cell-0-2", blocks=_blocks(("v", "kpi-value", "35%"))),
    ])
    html = render_slide_html(spec, theme)
    _assert_valid_html(html)
    assert "经济指标" in html
    assert "10万㎡" in html


def test_hero_strip(theme):
    spec = _spec(6, HeroStripLayout(
        primitive="hero-strip", hero_position="top", hero_ratio=0.72,
        hero_content_type="image", strip_content_type="kpi-cards",
        strip_use_primary_bg=True,
    ), [
        RegionBinding(region_id="hero", blocks=_blocks(("img", "image", "https://example.com/render.jpg"))),
        RegionBinding(region_id="strip", blocks=_blocks(
            ("k1", "kpi-value", "10万㎡"), ("k2", "kpi-value", "2.5"),
        )),
    ])
    html = render_slide_html(spec, theme)
    _assert_valid_html(html)
    assert "render.jpg" in html


def test_sidebar(theme):
    spec = _spec(7, SidebarLayout(
        primitive="sidebar", sidebar_position="right", sidebar_ratio=0.28,
        main_content_type="chart", sidebar_content_type="annotation-list",
        sidebar_use_surface_bg=True,
    ), [
        RegionBinding(region_id="main", blocks=_blocks(("c", "chart", ""))),
        RegionBinding(region_id="sidebar", blocks=_blocks(
            ("a1", "body-text", "注释一"), ("a2", "body-text", "注释二"),
        )),
    ])
    html = render_slide_html(spec, theme)
    _assert_valid_html(html)
    assert "注释一" in html


def test_triptych(theme):
    spec = _spec(8, TriptychLayout(
        primitive="triptych", equal_width=True,
        col_content_types=["text", "image", "text"],
        has_unified_header=True, use_column_dividers=True,
    ), [
        RegionBinding(region_id="header", blocks=_blocks(("h", "heading", "三方案对比"))),
        RegionBinding(region_id="col-0", blocks=_blocks(("t0", "body-text", "方案一说明"))),
        RegionBinding(region_id="col-1", blocks=_blocks(("i1", "image", ""))),
        RegionBinding(region_id="col-2", blocks=_blocks(("t2", "body-text", "方案三说明"))),
    ])
    html = render_slide_html(spec, theme)
    _assert_valid_html(html)
    assert "三方案对比" in html
    assert "方案一说明" in html


def test_overlay_mosaic(theme):
    spec = _spec(9, OverlayMosaicLayout(
        primitive="overlay-mosaic", background_type="map",
        panel_count=3, panel_arrangement="left-stack",
        panel_content_type="text-annotation", panel_opacity=0.9,
    ), [
        RegionBinding(region_id="background", blocks=_blocks(("bg", "map", "https://example.com/map.jpg"))),
        RegionBinding(region_id="panel-0", blocks=_blocks(("p0", "body-text", "场地分析要点一"))),
        RegionBinding(region_id="panel-1", blocks=_blocks(("p1", "body-text", "场地分析要点二"))),
        RegionBinding(region_id="panel-2", blocks=_blocks(("p2", "body-text", "场地分析要点三"))),
    ])
    html = render_slide_html(spec, theme)
    _assert_valid_html(html)
    assert "场地分析要点一" in html


def test_timeline(theme):
    spec = _spec(10, TimelineLayout(
        primitive="timeline", direction="horizontal", node_count=4,
        node_content="text-only", line_style="solid", show_progress_state=False,
    ), [
        RegionBinding(region_id=f"node-{i}", blocks=_blocks((f"n{i}", "body-text", f"阶段{i+1}")))
        for i in range(4)
    ])
    html = render_slide_html(spec, theme)
    _assert_valid_html(html)
    assert "阶段1" in html
    assert "阶段4" in html


def test_asymmetric(theme):
    spec = _spec(11, AsymmetricLayout(
        primitive="asymmetric",
        regions=[
            AsymmetricRegion(region_id="r1", x=0.0, y=0.0, width=0.6, height=0.7, content_type="image", z_index=0),
            AsymmetricRegion(region_id="r2", x=0.62, y=0.05, width=0.35, height=0.45, content_type="text", z_index=1),
        ],
    ), [
        RegionBinding(region_id="r1", blocks=_blocks(("img", "image", "https://example.com/bg.jpg"))),
        RegionBinding(region_id="r2", blocks=_blocks(("h", "heading", "非对称标题"))),
    ])
    html = render_slide_html(spec, theme)
    _assert_valid_html(html)
    assert "非对称标题" in html


# ─── 特殊页面 ────────────────────────────────────────────────────────────────

def test_chapter_divider_gets_dark_bg(theme):
    spec = _spec(13, FullBleedLayout(
        primitive="full-bleed", content_anchor="center",
        use_overlay=False, background_type="color",
    ), [
        RegionBinding(region_id="content", blocks=_blocks(
            ("h", "heading", "场地分析"),
            ("sub", "subheading", "Site Analysis"),
        )),
    ], is_chapter_divider=True)
    html = render_slide_html(spec, theme)
    _assert_valid_html(html)
    assert "场地分析" in html
    assert theme.colors.primary in html     # 章节页应使用 primary 色作背景


def test_cover_no_footer(theme):
    spec = _spec(1, FullBleedLayout(
        primitive="full-bleed", content_anchor="bottom-left",
        use_overlay=True, overlay_direction="bottom", background_type="gradient",
    ), [
        RegionBinding(region_id="content", blocks=_blocks(("h", "heading", "项目名称"))),
    ], is_cover=True)
    html = render_slide_html(spec, theme, deck_meta={"deck_title": "汇报", "total_slides": 40})
    # 封面不应该有页脚
    assert "position:fixed;bottom:0" not in html


# ─── 资产解析 ────────────────────────────────────────────────────────────────

def test_asset_ref_resolved(theme):
    spec = _spec(5, SingleColumnLayout(
        primitive="single-column", max_width_ratio=0.8, v_align="center", has_pull_quote=False,
    ), [
        RegionBinding(region_id="content", blocks=[
            ContentBlock(block_id="chart", content_type="chart", content="asset:chart-abc123"),
        ]),
    ])
    assets = {"chart-abc123": {"image_url": "https://oss.example.com/chart_abc.png"}}
    html = render_slide_html(spec, theme, assets=assets)
    assert "oss.example.com/chart_abc.png" in html


def test_chart_prefers_preview_variant_from_config(theme):
    spec = _spec(5, SingleColumnLayout(
        primitive="single-column", max_width_ratio=0.8, v_align="center", has_pull_quote=False,
    ), [
        RegionBinding(region_id="content", blocks=[
            ContentBlock(block_id="chart", content_type="chart", content="asset:chart-1"),
        ]),
    ])
    assets = {
        "chart-1": {
            "image_url": "https://oss.example.com/chart_fallback.png",
            "config_json": {
                "preview_url": "file:///tmp/chart_preview.svg",
                "content_url": "file:///tmp/chart_interactive.html",
            },
        }
    }
    html = render_slide_html(spec, theme, assets=assets)
    assert "chart_preview.svg" in html
    assert "chart_interactive.html" not in html


def test_table_asset_ref_renders_markdown_table(theme):
    spec = _spec(5, SingleColumnLayout(
        primitive="single-column", max_width_ratio=0.8, v_align="center", has_pull_quote=False,
    ), [
        RegionBinding(region_id="content", blocks=[
            ContentBlock(block_id="table", content_type="table", content="asset:table-1"),
        ]),
    ])
    assets = {
        "table-1": {
            "data_json": {
                "preview_rows": [
                    {
                        "sheet": "Sheet1",
                        "rows": [
                            ["类别", "数量"],
                            ["交通", 12],
                            ["商业", 8],
                        ],
                    }
                ]
            }
        }
    }
    html = render_slide_html(spec, theme, assets=assets)
    assert "<table" in html
    assert "交通" in html
    assert "12" in html


def test_asset_ref_missing_keeps_placeholder(theme):
    spec = _spec(5, SingleColumnLayout(
        primitive="single-column", max_width_ratio=0.8, v_align="center", has_pull_quote=False,
    ), [
        RegionBinding(region_id="content", blocks=[
            ContentBlock(block_id="img", content_type="image", content="asset:missing-key"),
        ]),
    ])
    html = render_slide_html(spec, theme, assets={})
    assert "图片加载中" in html


# ─── 页脚 ────────────────────────────────────────────────────────────────────

def test_footer_shows_deck_meta(theme):
    spec = _spec(3, SingleColumnLayout(
        primitive="single-column", max_width_ratio=0.7, v_align="center", has_pull_quote=False,
    ), [
        RegionBinding(region_id="content", blocks=_blocks(("b", "body-text", "内容"))),
    ])
    html = render_slide_html(spec, theme, deck_meta={
        "deck_title": "苏州博物馆设计方案",
        "client_name": "苏州市文化局",
        "total_slides": 40,
    })
    assert "苏州博物馆设计方案" in html
    assert "苏州市文化局" in html
    assert "3 / 40" in html


# ─── 内容块类型 ───────────────────────────────────────────────────────────────

def test_bullet_list_renders_items(theme):
    spec = _spec(2, SingleColumnLayout(
        primitive="single-column", max_width_ratio=0.7, v_align="center", has_pull_quote=False,
    ), [
        RegionBinding(region_id="content", blocks=[
            ContentBlock(block_id="bl", content_type="bullet-list",
                         content=["地铁站距离350m", "周边3所学校", "商业配套完善"]),
        ]),
    ])
    html = render_slide_html(spec, theme)
    assert "地铁站距离350m" in html
    assert "周边3所学校" in html
    assert "商业配套完善" in html


def test_table_renders(theme):
    md_table = """| 项目 | 数值 |
|------|------|
| 面积 | 10万㎡ |
| 容积率 | 2.5 |"""
    spec = _spec(2, SingleColumnLayout(
        primitive="single-column", max_width_ratio=0.8, v_align="top", has_pull_quote=False,
    ), [
        RegionBinding(region_id="content", blocks=[
            ContentBlock(block_id="tbl", content_type="table", content=md_table),
        ]),
    ])
    html = render_slide_html(spec, theme)
    assert "10万㎡" in html
    assert "容积率" in html
