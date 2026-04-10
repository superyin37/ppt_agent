---
tags: [schema, layout, pydantic]
source: schema/visual_theme.py (line 82-190)
---

# LayoutPrimitive — 11 种布局原语

> 每个原语描述「空间如何划分」，由 [[agents/ComposerAgent]] 选择，被 `render/engine.py` 的 `_render_layout()` 渲染为 HTML。

---

## 1. `full-bleed` — 全屏单区

适用：封面、章节过渡页、氛围大图页

```python
class FullBleedLayout(BaseModel):
    primitive:         Literal["full-bleed"]
    content_anchor:    Literal["center", "bottom-left", "top-left", "bottom-center"]
    use_overlay:       bool
    overlay_direction: Literal["top", "bottom", "left", "radial"] | None
    background_type:   Literal["image", "color", "gradient"]
```

**区域 ID：** `background`（背景）、`content`（文字内容）

---

## 2. `split-h` — 左右分割

适用：图文并列、案例介绍、分析页

```python
class SplitHLayout(BaseModel):
    primitive:           Literal["split-h"]
    left_ratio:          int    # 左右合计 10，如 6
    right_ratio:         int    # 如 4
    left_content_type:   Literal["text", "image", "chart", "map", "mixed"]
    right_content_type:  Literal["text", "image", "chart", "map", "mixed"]
    divider:             Literal["none", "line", "gap"]
    dominant_side:       Literal["left", "right"]
```

**区域 ID：** `left`、`right`

---

## 3. `split-v` — 上下分割

适用：大图 + 说明条

```python
class SplitVLayout(BaseModel):
    primitive:            Literal["split-v"]
    top_ratio:            int    # 上下合计 10，如 7
    bottom_ratio:         int    # 如 3
    top_content_type:     Literal["text", "image", "chart", "map", "mixed"]
    bottom_content_type:  Literal["text", "image", "chart", "map", "mixed"]
    bottom_style:         Literal["info-strip", "normal"]
```

**区域 ID：** `top`、`bottom`

---

## 4. `single-column` — 单列居中

适用：纯文字页、定位声明页

```python
class SingleColumnLayout(BaseModel):
    primitive:       Literal["single-column"]
    max_width_ratio: float   # 内容区宽度占比，如 0.6
    v_align:         Literal["top", "center", "bottom"]
    has_pull_quote:  bool
```

**区域 ID：** `content`

---

## 5. `grid` — 多列网格

适用：KPI 展示、多案例并排

```python
class GridLayout(BaseModel):
    primitive:         Literal["grid"]
    columns:           int    # 1~4
    rows:              int    # 1~3
    cell_content_type: Literal["image", "text", "kpi-card", "case-card", "mixed"]
    has_header_row:    bool
    gap_size:          Literal["tight", "normal", "loose"]
```

**区域 ID：** `cell-{row}-{col}`（如 `cell-0-0`）、`header`（若有标题行）

---

## 6. `hero-strip` — 大图横条

适用：场地大图 + 指标条

```python
class HeroStripLayout(BaseModel):
    primitive:           Literal["hero-strip"]
    hero_position:       Literal["top", "left"]
    hero_ratio:          float  # 主视觉占比，如 0.7
    hero_content_type:   Literal["image", "chart", "map"]
    strip_content_type:  Literal["text", "kpi-cards", "bullet-list"]
    strip_use_primary_bg: bool
```

**区域 ID：** `hero`、`strip`

---

## 7. `sidebar` — 侧边栏

适用：注释 + 主内容并排

```python
class SidebarLayout(BaseModel):
    primitive:             Literal["sidebar"]
    sidebar_position:      Literal["left", "right"]
    sidebar_ratio:         float  # 侧栏宽度比例，如 0.28
    main_content_type:     Literal["text", "image", "chart", "map", "mixed"]
    sidebar_content_type:  Literal["text", "kpi-cards", "image-list", "annotation-list"]
    sidebar_use_surface_bg: bool
```

**区域 ID：** `main`、`sidebar`

---

## 8. `triptych` — 三联

适用：三案例并排、三策略对比

```python
class TriptychLayout(BaseModel):
    primitive:          Literal["triptych"]
    equal_width:        bool
    col_content_types:  list[Literal["text", "image", "chart", "kpi-card", "case-card"]]  # 长度 3
    has_unified_header: bool
    use_column_dividers: bool
```

**区域 ID：** `col-0`、`col-1`、`col-2`、`header`（若有）

---

## 9. `overlay-mosaic` — 覆盖拼贴

适用：场地地图 + 数据浮层

```python
class OverlayMosaicLayout(BaseModel):
    primitive:         Literal["overlay-mosaic"]
    background_type:   Literal["image", "map"]
    panel_count:       int    # 1~5
    panel_arrangement: Literal["corners", "left-stack", "bottom-row", "scatter"]
    panel_content_type: Literal["kpi", "text-annotation", "legend", "mixed"]
    panel_opacity:     float  # 0.7~1.0
```

**区域 ID：** `background`、`panel-0`…`panel-N`

---

## 10. `timeline` — 时间线

适用：发展历程、项目进度

```python
class TimelineLayout(BaseModel):
    primitive:          Literal["timeline"]
    direction:          Literal["horizontal", "vertical"]
    node_count:         int    # 3~7
    node_content:       Literal["text-only", "text-image", "text-kpi"]
    line_style:         Literal["solid", "dashed", "dotted"]
    show_progress_state: bool
```

**区域 ID：** `node-0`…`node-N`

---

## 11. `asymmetric` — 不对称自定义

适用：复杂创意版式

```python
class AsymmetricLayout(BaseModel):
    primitive: Literal["asymmetric"]
    regions:   list[AsymmetricRegion]

class AsymmetricRegion(BaseModel):
    region_id:    str
    x:            float   # 相对坐标 0.0~1.0
    y:            float
    width:        float
    height:       float
    content_type: Literal["text", "image", "chart", "accent-shape", "empty"]
    z_index:      int = 0
```

---

## 渲染引擎映射

```python
# render/engine.py → _render_layout()
{
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
```

## 相关

- [[schemas/LayoutSpec]]
- [[agents/ComposerAgent]]
- `render/engine.py`
