"""
Render Engine v2 — 动态视觉主题 + 布局原语

替代旧版固定 tokens.css + Jinja2 模板方案。
流程：
  VisualTheme → generate_theme_css() → CSS 变量
  LayoutSpec  → _render_layout()     → HTML body
  合并         → render_slide_html()  → 完整 HTML（Playwright-ready）

详见 docs/visual_design_system.md
"""
from __future__ import annotations

import logging
import math
from typing import Optional

from schema.visual_theme import (
    VisualTheme,
    LayoutSpec,
    ContentBlock,
    RegionBinding,
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
)
from render.html_sanitizer import sanitize_slide_html

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# CSS 生成
# ─────────────────────────────────────────────

_RADIUS_MAP = {"none": "0", "small": "4px", "medium": "12px", "large": "24px"}
_TEXTURE_CSS = {
    "flat": "",
    "subtle-grain": (
        "background-image: url(\"data:image/svg+xml,%3Csvg viewBox='0 0 200 200' "
        "xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence "
        "type='fractalNoise' baseFrequency='0.65' numOctaves='3' stitchTiles='stitch'/"
        "%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' "
        "opacity='0.04'/%3E%3C/svg%3E\");"
    ),
    "linen": (
        "background-image: repeating-linear-gradient("
        "45deg, transparent, transparent 2px, rgba(0,0,0,0.015) 2px, rgba(0,0,0,0.015) 4px);"
    ),
    "concrete": (
        "background-image: url(\"data:image/svg+xml,%3Csvg viewBox='0 0 300 300' "
        "xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='c'%3E%3CfeTurbulence "
        "type='turbulence' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/"
        "%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23c)' "
        "opacity='0.05'/%3E%3C/svg%3E\");"
    ),
}


# 1920×1080 画布上各级字号的绝对下限（px）
_TYPE_FLOOR = {
    "display": 56,
    "h1":      40,
    "h2":      32,
    "h3":      24,
    "body":    20,
    "caption": 16,
    "label":   12,
}


def _compute_type_scale(base: int, ratio: float) -> dict[str, int]:
    raw = {
        "display": round(base * ratio ** 4),
        "h1":      round(base * ratio ** 3),
        "h2":      round(base * ratio ** 2),
        "h3":      round(base * ratio ** 1),
        "body":    base,
        "caption": round(base * ratio ** -1),
        "label":   round(base * ratio ** -2),
    }
    return {k: max(v, _TYPE_FLOOR[k]) for k, v in raw.items()}


def generate_theme_css(theme: VisualTheme) -> str:
    """根据 VisualTheme 动态生成 CSS 变量块，替代固定 tokens.css。"""
    c = theme.colors
    t = theme.typography
    s = theme.spacing
    d = theme.decoration

    sizes = _compute_type_scale(t.base_size, t.scale_ratio)
    radius = _RADIUS_MAP[d.border_radius]
    texture = _TEXTURE_CSS.get(d.background_texture, "")

    return f""":root {{
  /* ── 色彩系统 ── */
  --color-primary:        {c.primary};
  --color-secondary:      {c.secondary};
  --color-accent:         {c.accent};
  --color-bg:             {c.background};
  --color-surface:        {c.surface};
  --color-text-primary:   {c.text_primary};
  --color-text-secondary: {c.text_secondary};
  --color-border:         {c.border};
  --color-overlay:        {c.overlay};
  --color-cover-bg:       {c.cover_bg};

  /* ── 字体系统 ── */
  --font-heading: "{t.font_heading}", "PingFang SC", "Microsoft YaHei", sans-serif;
  --font-body:    "{t.font_body}", "PingFang SC", "Microsoft YaHei", sans-serif;
  --font-en:      "{t.font_en}", "Helvetica Neue", Arial, sans-serif;

  /* ── 字阶 ── */
  --text-display: {sizes["display"]}px;
  --text-h1:      {sizes["h1"]}px;
  --text-h2:      {sizes["h2"]}px;
  --text-h3:      {sizes["h3"]}px;
  --text-body:    {sizes["body"]}px;
  --text-caption: {sizes["caption"]}px;
  --text-label:   {sizes["label"]}px;

  /* ── 字重 / 行高 ── */
  --font-weight-heading: {t.heading_weight};
  --font-weight-body:    {t.body_weight};
  --line-height-body:    {t.line_height_body};
  --line-height-heading: {t.line_height_heading};
  --letter-spacing-label:{t.letter_spacing_label};

  /* ── 空间系统 ── */
  --safe-margin:   {s.safe_margin}px;
  --section-gap:   {s.section_gap}px;
  --element-gap:   {s.element_gap}px;
  --base-unit:     {s.base_unit}px;

  /* ── 装饰 ── */
  --border-radius: {radius};

  /* ── 幻灯片尺寸 ── */
  --slide-width:  1920px;
  --slide-height: 1080px;
}}

/* ── 全局 Reset ── */
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

body {{
  width: var(--slide-width);
  height: var(--slide-height);
  overflow: hidden;
  background-color: var(--color-bg);
  {texture}
  color: var(--color-text-primary);
  font-family: var(--font-body);
  font-size: var(--text-body);
  line-height: var(--line-height-body);
  font-weight: var(--font-weight-body);
}}

img {{ display: block; width: 100%; height: 100%; object-fit: cover; }}

.slide-root {{
  width: var(--slide-width);
  height: var(--slide-height);
  position: relative;
  overflow: hidden;
}}

/* ── 通用内容块样式 ── */
.block-heading {{
  font-family: var(--font-heading);
  font-size: var(--text-h1);
  font-weight: var(--font-weight-heading);
  line-height: var(--line-height-heading);
  color: var(--color-text-primary);
}}
.block-subheading {{
  font-family: var(--font-heading);
  font-size: var(--text-h2);
  font-weight: var(--font-weight-heading);
  line-height: var(--line-height-heading);
  color: var(--color-text-primary);
}}
.block-body-text {{
  font-size: var(--text-body);
  line-height: var(--line-height-body);
  color: var(--color-text-primary);
}}
.block-bullet-list {{ list-style: none; }}
.block-bullet-list li {{ padding: 6px 0; padding-left: 1.2em; position: relative; }}
.block-bullet-list li::before {{
  content: "";
  position: absolute;
  left: 0; top: 0.65em;
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--color-accent);
}}
.block-kpi-value {{
  font-family: var(--font-en);
  font-size: var(--text-display);
  font-weight: 700;
  color: var(--color-primary);
  line-height: 1;
}}
.block-caption {{
  font-size: var(--text-caption);
  color: var(--color-text-secondary);
  line-height: 1.4;
}}
.block-label {{
  font-family: var(--font-en);
  font-size: var(--text-label);
  letter-spacing: var(--letter-spacing-label);
  text-transform: uppercase;
  color: var(--color-text-secondary);
}}
.block-quote {{
  font-family: var(--font-heading);
  font-size: var(--text-h2);
  font-style: italic;
  color: var(--color-primary);
  border-left: 4px solid var(--color-accent);
  padding-left: 1em;
}}

/* emphasis 修饰 */
.emphasis-highlight {{ color: var(--color-accent); }}
.emphasis-muted {{ color: var(--color-text-secondary); opacity: 0.7; }}

/* ── 分隔线 ── */
.divider-hairline {{ border: none; border-top: 0.5px solid var(--color-border); }}
.divider-thin     {{ border: none; border-top: 1px solid var(--color-border); }}
.divider-medium   {{ border: none; border-top: 2px solid var(--color-accent); }}

/* ── 表面色背景 ── */
.surface-bg {{ background-color: var(--color-surface); }}
.primary-bg {{ background-color: var(--color-primary); color: #fff; }}
.accent-bg  {{ background-color: var(--color-accent); color: #fff; }}
"""


# ─────────────────────────────────────────────
# 内容块 HTML 渲染
# ─────────────────────────────────────────────

def _render_block(block: ContentBlock) -> str:
    """将单个 ContentBlock 渲染为 HTML 片段。"""
    em_cls = f" emphasis-{block.emphasis}" if block.emphasis != "normal" else ""
    c = block.content

    if block.content_type == "heading":
        return f'<h1 class="block-heading{em_cls}">{c or ""}</h1>'

    elif block.content_type == "subheading":
        return f'<h2 class="block-subheading{em_cls}">{c or ""}</h2>'

    elif block.content_type == "body-text":
        # 支持换行
        text = (c or "").replace("\n", "<br>")
        return f'<p class="block-body-text{em_cls}">{text}</p>'

    elif block.content_type == "bullet-list":
        items = c if isinstance(c, list) else [c or ""]
        lis = "".join(f"<li>{item}</li>" for item in items)
        return f'<ul class="block-bullet-list{em_cls}">{lis}</ul>'

    elif block.content_type == "kpi-value":
        return f'<div class="block-kpi-value{em_cls}">{c or ""}</div>'

    elif block.content_type == "image":
        url = c or ""
        if url and not url.startswith("asset:"):
            return f'<div class="block-image" style="width:100%;height:100%;"><img src="{url}" alt="" /></div>'
        return '<div class="block-image" style="background:#e8e8e8;width:100%;height:100%;display:flex;align-items:center;justify-content:center;color:#999;font-size:14px;">图片加载中</div>'

    elif block.content_type == "chart":
        url = c or ""
        if url:
            return f'<div class="block-chart" style="width:100%;height:100%;"><img src="{url}" alt="chart" style="object-fit:contain;" /></div>'
        return '<div class="block-chart" style="background:#f0f0f0;width:100%;height:100%;"></div>'

    elif block.content_type == "map":
        url = c or ""
        if url:
            return f'<div class="block-map" style="width:100%;height:100%;"><img src="{url}" alt="map" /></div>'
        return '<div class="block-map" style="background:#e8eff7;width:100%;height:100%;"></div>'

    elif block.content_type == "table":
        # content 为 list[list[str]] 或 Markdown 表格字符串
        if isinstance(c, str):
            return f'<div class="block-table{em_cls}">{_markdown_table_to_html(c)}</div>'
        return f'<pre class="block-table{em_cls}">{c}</pre>'

    elif block.content_type == "quote":
        return f'<blockquote class="block-quote{em_cls}">{c or ""}</blockquote>'

    elif block.content_type == "caption":
        return f'<p class="block-caption{em_cls}">{c or ""}</p>'

    elif block.content_type == "label":
        return f'<span class="block-label{em_cls}">{c or ""}</span>'

    elif block.content_type == "accent-element":
        return '<div class="accent-element" style="width:40px;height:4px;background:var(--color-accent);border-radius:2px;"></div>'

    return f'<div class="block-unknown">{c or ""}</div>'


def _render_blocks(blocks: list[ContentBlock]) -> str:
    return "\n".join(_render_block(b) for b in blocks)


def _get_region_blocks(spec: LayoutSpec, region_id: str) -> list[ContentBlock]:
    for rb in spec.region_bindings:
        if rb.region_id == region_id:
            return rb.blocks
    return []


def _markdown_table_to_html(md: str) -> str:
    """简单 Markdown 表格 → HTML 表格（仅支持基础格式）。"""
    lines = [l.strip() for l in md.strip().splitlines() if l.strip()]
    rows = [l.strip("|").split("|") for l in lines if not l.startswith("|--") and not l.startswith("|:-")]
    if not rows:
        return f"<pre>{md}</pre>"
    html = '<table style="width:100%;border-collapse:collapse;font-size:var(--text-caption);">'
    for i, row in enumerate(rows):
        html += "<tr>"
        tag = "th" if i == 0 else "td"
        style = 'style="padding:8px 12px;border:1px solid var(--color-border);' + (
            'background:var(--color-surface);font-weight:600;"' if i == 0 else '"'
        )
        for cell in row:
            html += f"<{tag} {style}>{cell.strip()}</{tag}>"
        html += "</tr>"
    html += "</table>"
    return html


# ─────────────────────────────────────────────
# 布局原语渲染
# ─────────────────────────────────────────────

def _render_full_bleed(spec: LayoutSpec, theme: VisualTheme) -> str:
    p = spec.primitive
    assert isinstance(p, FullBleedLayout)

    # 背景
    if p.background_type == "image":
        bg_blocks = _get_region_blocks(spec, "background")
        bg_img = ""
        if bg_blocks:
            url = bg_blocks[0].content or ""
            if url:
                bg_img = f'<img src="{url}" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;z-index:0;" />'
    elif p.background_type == "gradient":
        bg_img = f'<div style="position:absolute;inset:0;background:{theme.colors.cover_bg};z-index:0;"></div>'
    else:
        bg_img = f'<div style="position:absolute;inset:0;background:{theme.colors.cover_bg};z-index:0;"></div>'

    # 蒙层
    overlay_html = ""
    if p.use_overlay:
        direction_map = {
            "bottom": "to bottom",
            "top": "to top",
            "left": "to left",
            "radial": "radial-gradient",
        }
        if p.overlay_direction == "radial":
            overlay_style = f"background:radial-gradient(ellipse at center, transparent 30%, {theme.colors.overlay} 100%)"
        else:
            direction = direction_map.get(p.overlay_direction or "bottom", "to bottom")
            overlay_style = f"background:linear-gradient({direction}, transparent 0%, {theme.colors.overlay} 100%)"
        overlay_html = f'<div style="position:absolute;inset:0;{overlay_style};z-index:1;"></div>'

    # 内容区定位（章节分隔页强制居中）
    effective_anchor = "center" if spec.is_chapter_divider else p.content_anchor
    anchor_style_map = {
        "center":        "top:50%;left:50%;transform:translate(-50%,-50%);text-align:center;",
        "bottom-left":   "bottom:var(--safe-margin);left:var(--safe-margin);",
        "top-left":      "top:var(--safe-margin);left:var(--safe-margin);",
        "bottom-center": "bottom:var(--safe-margin);left:50%;transform:translateX(-50%);text-align:center;",
    }
    anchor_style = anchor_style_map.get(effective_anchor, "top:50%;left:50%;transform:translate(-50%,-50%);")

    content_blocks = _get_region_blocks(spec, "content")
    content_html = _render_blocks(content_blocks)

    return f"""
<div class="layout-full-bleed slide-root" style="position:relative;">
  {bg_img}
  {overlay_html}
  <div style="position:absolute;{anchor_style}z-index:2;max-width:70%;padding:var(--safe-margin);">
    {content_html}
  </div>
</div>"""


def _render_split_h(spec: LayoutSpec, theme: VisualTheme) -> str:
    p = spec.primitive
    assert isinstance(p, SplitHLayout)

    left_pct = p.left_ratio / (p.left_ratio + p.right_ratio) * 100
    right_pct = 100 - left_pct

    divider_css = ""
    if p.divider == "line":
        divider_css = f"border-right:1px solid {theme.colors.border};"
    elif p.divider == "gap":
        divider_css = f"margin-right:var(--section-gap);"

    left_blocks = _get_region_blocks(spec, "left")
    right_blocks = _get_region_blocks(spec, "right")

    padding = "var(--safe-margin)"

    return f"""
<div class="layout-split-h slide-root" style="display:flex;width:100%;height:100%;">
  <div class="region-left" style="width:{left_pct:.1f}%;height:100%;overflow:hidden;{divider_css}padding:{padding};display:flex;flex-direction:column;justify-content:center;gap:var(--element-gap);">
    {_render_blocks(left_blocks)}
  </div>
  <div class="region-right" style="width:{right_pct:.1f}%;height:100%;overflow:hidden;padding:{padding};display:flex;flex-direction:column;justify-content:center;gap:var(--element-gap);">
    {_render_blocks(right_blocks)}
  </div>
</div>"""


def _render_split_v(spec: LayoutSpec, theme: VisualTheme) -> str:
    p = spec.primitive
    assert isinstance(p, SplitVLayout)

    top_pct = p.top_ratio / (p.top_ratio + p.bottom_ratio) * 100
    bottom_pct = 100 - top_pct

    top_blocks = _get_region_blocks(spec, "top")
    bottom_blocks = _get_region_blocks(spec, "bottom")

    bottom_style = ""
    if p.bottom_style == "info-strip":
        bottom_style = f"background:{theme.colors.primary};color:#fff;"

    return f"""
<div class="layout-split-v slide-root" style="display:flex;flex-direction:column;width:100%;height:100%;">
  <div class="region-top" style="height:{top_pct:.1f}%;overflow:hidden;padding:var(--safe-margin);display:flex;flex-direction:column;justify-content:center;gap:var(--element-gap);">
    {_render_blocks(top_blocks)}
  </div>
  <div class="region-bottom" style="height:{bottom_pct:.1f}%;overflow:hidden;padding:var(--safe-margin);display:flex;flex-direction:column;justify-content:center;gap:var(--element-gap);{bottom_style}">
    {_render_blocks(bottom_blocks)}
  </div>
</div>"""


def _render_single_column(spec: LayoutSpec, theme: VisualTheme) -> str:
    p = spec.primitive
    assert isinstance(p, SingleColumnLayout)

    max_w = f"{p.max_width_ratio * 100:.0f}%"
    v_align_map = {"top": "flex-start", "center": "center", "bottom": "flex-end"}
    v_align = v_align_map.get(p.v_align, "center")

    content_blocks = _get_region_blocks(spec, "content")
    pull_quote_html = ""
    if p.has_pull_quote:
        pq_blocks = _get_region_blocks(spec, "pull-quote")
        if pq_blocks:
            pull_quote_html = f'<div style="margin-bottom:var(--section-gap);">{_render_blocks(pq_blocks)}</div>'

    return f"""
<div class="layout-single-column slide-root" style="
  display:flex;flex-direction:column;align-items:center;justify-content:{v_align};
  width:100%;height:100%;padding:var(--safe-margin);">
  <div style="width:{max_w};max-width:{max_w};">
    {pull_quote_html}
    <div style="display:flex;flex-direction:column;gap:var(--element-gap);">
      {_render_blocks(content_blocks)}
    </div>
  </div>
</div>"""


def _render_grid(spec: LayoutSpec, theme: VisualTheme) -> str:
    p = spec.primitive
    assert isinstance(p, GridLayout)

    gap_map = {"tight": "8px", "normal": "var(--element-gap)", "loose": "var(--section-gap)"}
    gap = gap_map[p.gap_size]

    header_html = ""
    if p.has_header_row:
        header_blocks = _get_region_blocks(spec, "header")
        header_html = f'<div style="grid-column:1/-1;padding-bottom:{gap};">{_render_blocks(header_blocks)}</div>'

    cells_html = ""
    for r in range(p.rows):
        for c in range(p.columns):
            cell_id = f"cell-{r}-{c}"
            cell_blocks = _get_region_blocks(spec, cell_id)
            cell_bg = f"background:{theme.colors.surface};" if theme.decoration.color_fill_usage != "none" else ""
            cells_html += (
                f'<div class="grid-cell" style="overflow:hidden;border-radius:var(--border-radius);'
                f'{cell_bg}padding:var(--element-gap);display:flex;flex-direction:column;gap:8px;">'
                f'{_render_blocks(cell_blocks)}'
                f'</div>'
            )

    return f"""
<div class="layout-grid slide-root" style="
  display:grid;
  grid-template-columns:repeat({p.columns}, 1fr);
  grid-template-rows:{'auto ' if p.has_header_row else ''}repeat({p.rows}, 1fr);
  gap:{gap};
  padding:var(--safe-margin);
  width:100%;height:100%;">
  {header_html}
  {cells_html}
</div>"""


def _render_hero_strip(spec: LayoutSpec, theme: VisualTheme) -> str:
    p = spec.primitive
    assert isinstance(p, HeroStripLayout)

    hero_pct = p.hero_ratio * 100
    strip_pct = 100 - hero_pct

    hero_blocks = _get_region_blocks(spec, "hero")
    strip_blocks = _get_region_blocks(spec, "strip")

    strip_bg = f"background:{theme.colors.primary};color:#fff;" if p.strip_use_primary_bg else ""

    if p.hero_position == "top":
        return f"""
<div class="layout-hero-strip slide-root" style="display:flex;flex-direction:column;width:100%;height:100%;">
  <div class="region-hero" style="height:{hero_pct:.0f}%;overflow:hidden;">
    {_render_blocks(hero_blocks)}
  </div>
  <div class="region-strip" style="height:{strip_pct:.0f}%;padding:var(--element-gap) var(--safe-margin);
    display:flex;align-items:center;gap:var(--section-gap);{strip_bg}">
    {_render_blocks(strip_blocks)}
  </div>
</div>"""
    else:  # left
        return f"""
<div class="layout-hero-strip slide-root" style="display:flex;width:100%;height:100%;">
  <div class="region-hero" style="width:{hero_pct:.0f}%;overflow:hidden;">
    {_render_blocks(hero_blocks)}
  </div>
  <div class="region-strip" style="width:{strip_pct:.0f}%;padding:var(--safe-margin);
    display:flex;flex-direction:column;justify-content:center;gap:var(--element-gap);{strip_bg}">
    {_render_blocks(strip_blocks)}
  </div>
</div>"""


def _render_sidebar(spec: LayoutSpec, theme: VisualTheme) -> str:
    p = spec.primitive
    assert isinstance(p, SidebarLayout)

    sidebar_pct = p.sidebar_ratio * 100
    main_pct = 100 - sidebar_pct
    sidebar_bg = f"background:{theme.colors.surface};" if p.sidebar_use_surface_bg else ""

    main_blocks = _get_region_blocks(spec, "main")
    sidebar_blocks = _get_region_blocks(spec, "sidebar")

    sidebar_div = (
        f'<div class="region-sidebar" style="width:{sidebar_pct:.0f}%;height:100%;'
        f'overflow:hidden;padding:var(--safe-margin);{sidebar_bg}'
        f'display:flex;flex-direction:column;gap:var(--element-gap);">'
        f'{_render_blocks(sidebar_blocks)}</div>'
    )
    main_div = (
        f'<div class="region-main" style="width:{main_pct:.0f}%;height:100%;'
        f'overflow:hidden;padding:var(--safe-margin);'
        f'display:flex;flex-direction:column;gap:var(--element-gap);">'
        f'{_render_blocks(main_blocks)}</div>'
    )

    if p.sidebar_position == "left":
        return f'<div class="layout-sidebar slide-root" style="display:flex;width:100%;height:100%;">{sidebar_div}{main_div}</div>'
    else:
        return f'<div class="layout-sidebar slide-root" style="display:flex;width:100%;height:100%;">{main_div}{sidebar_div}</div>'


def _render_triptych(spec: LayoutSpec, theme: VisualTheme) -> str:
    p = spec.primitive
    assert isinstance(p, TriptychLayout)

    col_w = "33.333%" if p.equal_width else "33.333%"
    divider_style = f"border-right:1px solid {theme.colors.border};" if p.use_column_dividers else ""

    header_html = ""
    if p.has_unified_header:
        header_blocks = _get_region_blocks(spec, "header")
        header_html = (
            f'<div style="grid-column:1/-1;padding-bottom:var(--element-gap);">'
            f'{_render_blocks(header_blocks)}</div>'
        )

    cols_html = ""
    for i in range(3):
        col_blocks = _get_region_blocks(spec, f"col-{i}")
        is_last = (i == 2)
        border = "" if is_last else divider_style
        cols_html += (
            f'<div style="overflow:hidden;padding:0 var(--element-gap);'
            f'{border}display:flex;flex-direction:column;gap:var(--element-gap);">'
            f'{_render_blocks(col_blocks)}</div>'
        )

    return f"""
<div class="layout-triptych slide-root" style="
  display:grid;
  grid-template-columns:repeat(3, 1fr);
  {'grid-template-rows:auto 1fr;' if p.has_unified_header else ''}
  gap:0;
  padding:var(--safe-margin);
  width:100%;height:100%;">
  {header_html}
  {cols_html}
</div>"""


def _render_overlay_mosaic(spec: LayoutSpec, theme: VisualTheme) -> str:
    p = spec.primitive
    assert isinstance(p, OverlayMosaicLayout)

    bg_blocks = _get_region_blocks(spec, "background")
    bg_html = _render_blocks(bg_blocks) if bg_blocks else (
        f'<div style="width:100%;height:100%;background:{theme.colors.surface};"></div>'
    )

    # 面板位置预设
    arrangement_positions = {
        "corners": [
            "top:5%;left:4%;",
            "top:5%;right:4%;",
            "bottom:5%;left:4%;",
            "bottom:5%;right:4%;",
            "top:50%;left:50%;transform:translate(-50%,-50%);",
        ],
        "left-stack": [
            "top:5%;left:4%;", "top:30%;left:4%;", "top:55%;left:4%;",
            "top:80%;left:4%;", "top:5%;left:4%;",
        ],
        "bottom-row": [
            "bottom:4%;left:4%;", "bottom:4%;left:24%;", "bottom:4%;left:44%;",
            "bottom:4%;left:64%;", "bottom:4%;left:84%;",
        ],
        "scatter": [
            "top:8%;left:6%;", "top:8%;right:6%;", "bottom:10%;left:6%;",
            "bottom:10%;right:6%;", "top:45%;left:50%;transform:translate(-50%,-50%);",
        ],
    }
    positions = arrangement_positions.get(p.panel_arrangement, arrangement_positions["corners"])

    panels_html = ""
    for i in range(p.panel_count):
        panel_blocks = _get_region_blocks(spec, f"panel-{i}")
        pos = positions[i % len(positions)]
        panels_html += (
            f'<div style="position:absolute;{pos}z-index:2;min-width:200px;max-width:340px;'
            f'background:rgba(255,255,255,{p.panel_opacity});'
            f'border-radius:var(--border-radius);padding:var(--element-gap);'
            f'box-shadow:0 4px 20px rgba(0,0,0,0.12);">'
            f'{_render_blocks(panel_blocks)}</div>'
        )

    return f"""
<div class="layout-overlay-mosaic slide-root" style="position:relative;width:100%;height:100%;">
  <div style="position:absolute;inset:0;z-index:0;">{bg_html}</div>
  {panels_html}
</div>"""


def _render_timeline(spec: LayoutSpec, theme: VisualTheme) -> str:
    p = spec.primitive
    assert isinstance(p, TimelineLayout)

    line_style_map = {"solid": "solid", "dashed": "dashed", "dotted": "dotted"}
    ls = line_style_map[p.line_style]

    nodes_html = ""
    node_size = 16

    if p.direction == "horizontal":
        for i in range(p.node_count):
            node_blocks = _get_region_blocks(spec, f"node-{i}")
            nodes_html += f"""
<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:var(--element-gap);">
  <div style="width:{node_size}px;height:{node_size}px;border-radius:50%;
    background:{theme.colors.accent};border:3px solid {theme.colors.primary};"></div>
  <div style="text-align:center;">{_render_blocks(node_blocks)}</div>
</div>"""

        return f"""
<div class="layout-timeline slide-root" style="padding:var(--safe-margin);width:100%;height:100%;
  display:flex;flex-direction:column;justify-content:center;">
  <div style="display:flex;align-items:flex-start;position:relative;">
    <div style="position:absolute;top:{node_size // 2}px;left:0;right:0;
      border-top:2px {ls} {theme.colors.primary};z-index:0;"></div>
    {nodes_html}
  </div>
</div>"""
    else:  # vertical
        for i in range(p.node_count):
            node_blocks = _get_region_blocks(spec, f"node-{i}")
            nodes_html += f"""
<div style="display:flex;align-items:flex-start;gap:var(--section-gap);">
  <div style="flex-shrink:0;display:flex;flex-direction:column;align-items:center;">
    <div style="width:{node_size}px;height:{node_size}px;border-radius:50%;
      background:{theme.colors.accent};border:3px solid {theme.colors.primary};"></div>
    {"" if i == p.node_count - 1 else f'<div style="width:2px;flex:1;min-height:40px;border-left:2px {ls} {theme.colors.border};"></div>'}
  </div>
  <div>{_render_blocks(node_blocks)}</div>
</div>"""

        return f"""
<div class="layout-timeline slide-root" style="padding:var(--safe-margin);width:100%;height:100%;
  overflow:hidden;">
  <div style="display:flex;flex-direction:column;gap:var(--element-gap);">
    {nodes_html}
  </div>
</div>"""


def _render_asymmetric(spec: LayoutSpec, theme: VisualTheme) -> str:
    p = spec.primitive
    assert isinstance(p, AsymmetricLayout)

    regions_html = ""
    for region in p.regions:
        blocks = _get_region_blocks(spec, region.region_id)
        left_pct   = region.x * 100
        top_pct    = region.y * 100
        width_pct  = region.width * 100
        height_pct = region.height * 100

        regions_html += (
            f'<div style="position:absolute;left:{left_pct:.1f}%;top:{top_pct:.1f}%;'
            f'width:{width_pct:.1f}%;height:{height_pct:.1f}%;'
            f'z-index:{region.z_index};overflow:hidden;'
            f'padding:var(--element-gap);">'
            f'{_render_blocks(blocks)}</div>'
        )

    return f"""
<div class="layout-asymmetric slide-root" style="position:relative;width:100%;height:100%;">
  {regions_html}
</div>"""


# ─────────────────────────────────────────────
# 布局分发
# ─────────────────────────────────────────────

_LAYOUT_DISPATCH = {
    "full-bleed":     _render_full_bleed,
    "split-h":        _render_split_h,
    "split-v":        _render_split_v,
    "single-column":  _render_single_column,
    "grid":           _render_grid,
    "hero-strip":     _render_hero_strip,
    "sidebar":        _render_sidebar,
    "triptych":       _render_triptych,
    "overlay-mosaic": _render_overlay_mosaic,
    "timeline":       _render_timeline,
    "asymmetric":     _render_asymmetric,
}


def _render_layout(spec: LayoutSpec, theme: VisualTheme) -> str:
    primitive_type = spec.primitive.primitive
    fn = _LAYOUT_DISPATCH.get(primitive_type)
    if not fn:
        logger.warning(f"Unknown primitive '{primitive_type}', falling back to single-column")
        fn = _render_single_column
    return fn(spec, theme)


# ─────────────────────────────────────────────
# 页脚
# ─────────────────────────────────────────────

def _render_footer(spec: LayoutSpec, deck_meta: dict, theme: VisualTheme) -> str:
    if spec.is_cover or spec.is_chapter_divider:
        return ""
    client = deck_meta.get("client_name", "")
    deck_title = deck_meta.get("deck_title", "")
    total = deck_meta.get("total_slides", 0)
    slide_no = spec.slide_no

    return f"""
<div style="
  position:fixed;bottom:0;left:0;right:0;height:40px;
  display:flex;align-items:center;justify-content:space-between;
  padding:0 var(--safe-margin);
  border-top:1px solid {theme.colors.border};
  font-family:var(--font-en);font-size:var(--text-label);
  color:{theme.colors.text_secondary};
  background:{theme.colors.background};
  z-index:100;">
  <span>{client}</span>
  <span>{deck_title}</span>
  <span>{slide_no} / {total}</span>
</div>"""


# ─────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────

def render_slide_html(
    spec: LayoutSpec,
    theme: VisualTheme,
    assets: dict[str, dict] | None = None,
    deck_meta: dict | None = None,
) -> str:
    """
    将 LayoutSpec + VisualTheme 渲染为完整的自包含 HTML 页面。

    Args:
        spec:      幻灯片版式规格（布局原语 + 内容块绑定）
        theme:     项目级视觉主题
        assets:    asset_key → {image_url, ...} 的映射（可选）
        deck_meta: {deck_title, client_name, total_slides} 页脚信息（可选）

    Returns:
        完整 HTML 字符串，可直接传入 Playwright。
    """
    if assets is None:
        assets = {}
    if deck_meta is None:
        deck_meta = {}

    # 解析资产引用
    spec = _resolve_asset_refs(spec, assets)

    theme_css = generate_theme_css(theme)
    body_html = _render_layout(spec, theme)
    footer_html = _render_footer(spec, deck_meta, theme)

    # 章节页：增加特殊背景处理 + 放大字号 + 强制居中
    chapter_overlay = ""
    if spec.is_chapter_divider:
        chapter_overlay = f"""
<style>
.slide-root {{ background: {theme.colors.primary}; color: #fff; }}
.block-heading {{
  color: #fff !important;
  font-size: var(--text-display) !important;
  letter-spacing: -0.01em;
}}
.block-subheading, .block-body-text, .block-label, .block-caption {{
  color: rgba(255,255,255,0.75) !important;
  font-size: var(--text-h2) !important;
}}
.block-quote {{
  color: #fff !important;
  border-left-color: {theme.colors.accent};
  font-size: var(--text-h2) !important;
}}
</style>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=1920">
<style>
{theme_css}
</style>
{chapter_overlay}
</head>
<body>
{body_html}
{footer_html}
</body>
</html>"""


def _resolve_asset_refs(spec: LayoutSpec, assets: dict) -> LayoutSpec:
    """将 ContentBlock.content 中的 'asset:{key}' 替换为实际 URL。"""
    new_bindings = []
    for rb in spec.region_bindings:
        new_blocks = []
        for block in rb.blocks:
            if isinstance(block.content, str) and block.content.startswith("asset:"):
                key = block.content.removeprefix("asset:")
                asset = assets.get(key)
                if asset:
                    resolved = _resolve_asset_content(block.content_type, asset, block.content)
                    block = block.model_copy(update={"content": resolved})
            new_blocks.append(block)
        new_bindings.append(rb.model_copy(update={"blocks": new_blocks}))
    return spec.model_copy(update={"region_bindings": new_bindings})


def _resolve_asset_content(content_type: str, asset: dict, fallback: str) -> str:
    config = asset.get("config_json") or {}
    if content_type == "chart":
        return config.get("preview_url") or asset.get("image_url") or config.get("content_url") or fallback
    if content_type == "table":
        return _table_asset_to_markdown(asset) or fallback
    return config.get("preview_url") or asset.get("image_url") or asset.get("url") or fallback


def _table_asset_to_markdown(asset: dict) -> str:
    data = asset.get("data_json") or {}
    preview_rows = data.get("preview_rows") if isinstance(data, dict) else None
    if not preview_rows:
        return ""

    first_sheet = preview_rows[0]
    rows = [
        ["" if cell is None else str(cell) for cell in row]
        for row in (first_sheet.get("rows") or [])[:5]
    ]
    if not rows:
        return ""

    header = rows[0]
    body = rows[1:] if len(rows) > 1 else []
    header_line = "| " + " | ".join(header) + " |"
    divider_line = "| " + " | ".join(["---"] * len(header)) + " |"
    body_lines = ["| " + " | ".join(row) + " |" for row in body]
    return "\n".join([header_line, divider_line, *body_lines])


# ─────────────────────────────────────────────
# HTML 直出模式（Composer v3）
# ─────────────────────────────────────────────

def render_slide_html_direct(
    body_html: str,
    theme: VisualTheme,
    assets: dict[str, dict] | None = None,
    deck_meta: dict | None = None,
    slide_no: int = 0,
    total_slides: int = 0,
) -> str:
    """
    HTML 直出模式：LLM 生成的 body_html 经过清洗后，
    与 VisualTheme CSS 变量合并为完整 HTML 页面。

    Args:
        body_html:    LLM 输出的 <div class="slide-root">...</div> HTML
        theme:        项目级视觉主题（提供 CSS 变量）
        assets:       asset_key → {image_url, ...} 映射
        deck_meta:    {deck_title, client_name, total_slides}
        slide_no:     当前页码
        total_slides: 总页数

    Returns:
        完整 HTML 字符串，可直接传入 Playwright。
    """
    if assets is None:
        assets = {}
    if deck_meta is None:
        deck_meta = {}

    # 1. 清洗 HTML
    safe_html = sanitize_slide_html(body_html)

    # 2. 替换 asset: 引用
    for asset_key, asset_info in assets.items():
        placeholder = f"asset:{asset_key}"
        if placeholder in safe_html:
            url = (
                (asset_info.get("config_json") or {}).get("preview_url")
                or asset_info.get("image_url")
                or asset_info.get("url")
                or ""
            )
            safe_html = safe_html.replace(placeholder, url)

    # 3. 生成主题 CSS
    theme_css = generate_theme_css(theme)

    # 4. 页脚
    footer_html = ""
    if deck_meta.get("deck_title") or slide_no:
        footer_html = f"""
<div style="position:absolute;bottom:20px;left:var(--safe-margin);right:var(--safe-margin);
display:flex;justify-content:space-between;font-size:var(--text-caption);
color:var(--color-text-secondary);opacity:0.6;">
  <span>{deck_meta.get('deck_title', '')}</span>
  <span>{slide_no} / {total_slides or deck_meta.get('total_slides', '')}</span>
</div>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=1920">
<style>
{theme_css}
</style>
</head>
<body>
{safe_html}
{footer_html}
</body>
</html>"""
