# 10. HTML 渲染引擎与模板规范

> 最后更新：2026-04-10

本文档涵盖两套渲染体系：

| 体系 | 入口 | 状态 |
|------|------|------|
| **新版** — VisualTheme + LayoutSpec + 动态 CSS | `render/engine.py` → `render_slide_html()` / `render_slide_html_direct()` | **当前主路径** |
| **旧版** — tokens.css + SlideSpec + Jinja2 模板 | 原 `render/templates/*.html` | 保留供参考/回退 |

---

# 第一部分：新版渲染系统（当前主路径）

## 1.1 架构总览

```
VisualTheme ──→ generate_theme_css() ──→ CSS 变量（替代静态 tokens.css）
LayoutSpec  ──→ _render_layout()     ──→ HTML body（布局原语分发）
合并         ──→ render_slide_html()  ──→ 完整 HTML（Playwright-ready）
```

核心文件：

| 文件 | 职责 |
|------|------|
| `schema/visual_theme.py` | VisualTheme、LayoutSpec、ContentBlock、11 种布局原语的 Pydantic 定义 |
| `render/engine.py` | CSS 生成、内容块渲染、布局原语渲染、主入口函数 |
| `render/html_sanitizer.py` | HTML 直出模式的安全清洗（去除 script、事件处理器等） |

关键类型关系：

```
VisualTheme
  ├── ColorSystem        (10 色槽)
  ├── TypographySystem   (字体 + 字阶 + 字重 + 行高)
  ├── SpacingSystem      (安全边距 + 间距密度)
  ├── DecorationStyle    (圆角 / 纹理 / 填色策略)
  └── CoverStyle         (封面布局语气)

LayoutSpec (每张幻灯片一个)
  ├── primitive: LayoutPrimitive  (11 选 1，discriminated union)
  ├── region_bindings: list[RegionBinding]
  │     └── blocks: list[ContentBlock]  (13 种 content_type)
  ├── visual_focus: str
  ├── is_cover / is_chapter_divider
  └── slide_no, section, title, ...
```

---

## 1.2 动态 CSS 生成 — `generate_theme_css()`

取代旧版固定的 `tokens.css`。根据 `VisualTheme` 实时计算所有 CSS 变量。

### 字阶计算

字阶由 `base_size`（正文基础字号）和 `scale_ratio`（比例因子）按幂级数推导，
并受每级绝对下限约束：

```python
# render/engine.py

_TYPE_FLOOR = {
    "display": 56, "h1": 40, "h2": 32, "h3": 24,
    "body": 20, "caption": 16, "label": 12,
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
```

### 圆角与纹理映射

```python
_RADIUS_MAP = {"none": "0", "small": "4px", "medium": "12px", "large": "24px"}

_TEXTURE_CSS = {
    "flat": "",
    "subtle-grain": "background-image: url(\"data:image/svg+xml,...\");",  # fractalNoise SVG
    "linen":        "background-image: repeating-linear-gradient(45deg, ...);",
    "concrete":     "background-image: url(\"data:image/svg+xml,...\");",  # turbulence SVG
}
```

### 生成的 CSS 变量全集

`generate_theme_css(theme)` 输出一个完整的 `<style>` 块，包含以下变量组：

```css
:root {
  /* ── 色彩系统（来自 ColorSystem） ── */
  --color-primary:        ...;
  --color-secondary:      ...;
  --color-accent:         ...;
  --color-bg:             ...;
  --color-surface:        ...;
  --color-text-primary:   ...;
  --color-text-secondary: ...;
  --color-border:         ...;
  --color-overlay:        ...;
  --color-cover-bg:       ...;

  /* ── 字体系统（来自 TypographySystem） ── */
  --font-heading: "思源黑体", "PingFang SC", "Microsoft YaHei", sans-serif;
  --font-body:    "思源宋体", "PingFang SC", "Microsoft YaHei", sans-serif;
  --font-en:      "Inter", "Helvetica Neue", Arial, sans-serif;

  /* ── 字阶（由 _compute_type_scale 计算） ── */
  --text-display: ...px;
  --text-h1:      ...px;
  --text-h2:      ...px;
  --text-h3:      ...px;
  --text-body:    ...px;
  --text-caption: ...px;
  --text-label:   ...px;

  /* ── 字重 / 行高 ── */
  --font-weight-heading: ...;
  --font-weight-body:    ...;
  --line-height-body:    ...;
  --line-height-heading: ...;
  --letter-spacing-label:...;

  /* ── 空间系统（来自 SpacingSystem） ── */
  --safe-margin:   ...px;
  --section-gap:   ...px;
  --element-gap:   ...px;
  --base-unit:     ...px;

  /* ── 装饰 ── */
  --border-radius: ...;

  /* ── 幻灯片尺寸 ── */
  --slide-width:  1920px;
  --slide-height: 1080px;
}
```

此外还生成全局 Reset、`body` 基础样式、`.slide-root` 容器，以及全部内容块 class 的样式规则（见下节 1.3）。

---

## 1.3 内容块类型与渲染 — `_render_block()`

`ContentBlock.content_type` 共 13 种。每种由 `_render_block()` 映射为 HTML 片段。

| content_type | CSS class | 输出 HTML | 说明 |
|---|---|---|---|
| `heading` | `.block-heading` | `<h1>` | 主标题，使用 `--font-heading` / `--text-h1` |
| `subheading` | `.block-subheading` | `<h2>` | 副标题，`--text-h2` |
| `body-text` | `.block-body-text` | `<p>`（`\n` → `<br>`） | 正文段落 |
| `bullet-list` | `.block-bullet-list` | `<ul><li>...` | 圆点列表，accent 色圆点 |
| `kpi-value` | `.block-kpi-value` | `<div>` | 大数字指标，`--font-en` / `--text-display` / 700 |
| `image` | `.block-image` | `<div><img>` 或灰色占位 | `object-fit: cover`，`asset:` 引用懒解析 |
| `chart` | `.block-chart` | `<div><img>` | `object-fit: contain` |
| `map` | `.block-map` | `<div><img>` | 同 image 但带蓝底占位 |
| `table` | `.block-table` | `<table>` 或 `<pre>` | Markdown 表格自动转 HTML 表格 |
| `quote` | `.block-quote` | `<blockquote>` | 左侧 accent 色竖线 |
| `caption` | `.block-caption` | `<p>` | 小字注释，`--text-caption` / secondary 色 |
| `label` | `.block-label` | `<span>` | 全大写标签，`--font-en` / `--text-label` |
| `accent-element` | `.accent-element` | `<div>` | 40x4px accent 色装饰条 |

### emphasis 修饰

每个 ContentBlock 可设 `emphasis` 字段：

| 值 | 效果 |
|---|---|
| `normal` | 无额外 class |
| `highlight` | `.emphasis-highlight` — 使用 accent 色 |
| `muted` | `.emphasis-muted` — secondary 色 + 70% 透明度 |

### 生成的通用内容块样式（摘要）

```css
.block-heading {
  font-family: var(--font-heading);
  font-size: var(--text-h1);
  font-weight: var(--font-weight-heading);
  line-height: var(--line-height-heading);
  color: var(--color-text-primary);
}
.block-bullet-list li::before {
  /* accent 色圆点 */
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--color-accent);
}
.block-kpi-value {
  font-family: var(--font-en);
  font-size: var(--text-display);
  font-weight: 700;
  color: var(--color-primary);
}
.block-quote {
  font-family: var(--font-heading);
  font-size: var(--text-h2);
  font-style: italic;
  color: var(--color-primary);
  border-left: 4px solid var(--color-accent);
}

/* 分隔线 */
.divider-hairline { border-top: 0.5px solid var(--color-border); }
.divider-thin     { border-top: 1px solid var(--color-border); }
.divider-medium   { border-top: 2px solid var(--color-accent); }

/* 表面色背景 */
.surface-bg { background-color: var(--color-surface); }
.primary-bg { background-color: var(--color-primary); color: #fff; }
.accent-bg  { background-color: var(--color-accent); color: #fff; }
```

---

## 1.4 布局原语 — 11 种

所有布局原语定义在 `schema/visual_theme.py` 中，由 `LayoutPrimitive` 联合类型统一，通过 `primitive` 字段做 discriminator 分发。

每种原语定义了**区域划分方式**及其配置参数，实际内容通过 `LayoutSpec.region_bindings` 将 `ContentBlock` 列表绑定到各区域。

### 一览表

| 原语 | 区域 (region_id) | 主要参数 | 典型用途 |
|---|---|---|---|
| `full-bleed` | `background`, `content` | `content_anchor`, `use_overlay`, `overlay_direction`, `background_type` | 封面、章节隔页、全屏图文 |
| `split-h` | `left`, `right` | `left_ratio:right_ratio`（合计 10）, `divider` | 图文对照、地图+洞察 |
| `split-v` | `top`, `bottom` | `top_ratio:bottom_ratio`, `bottom_style` | 图表+说明、hero+info-strip |
| `single-column` | `content`, `pull-quote`(可选) | `max_width_ratio`, `v_align`, `has_pull_quote` | 纯文字页、引言页 |
| `grid` | `header`(可选), `cell-{r}-{c}` | `columns`(1-4), `rows`(1-3), `gap_size`, `has_header_row` | KPI 卡片、案例网格 |
| `hero-strip` | `hero`, `strip` | `hero_position`(top/left), `hero_ratio`, `strip_use_primary_bg` | 大图+底部/侧栏信息条 |
| `sidebar` | `main`, `sidebar` | `sidebar_position`(left/right), `sidebar_ratio`, `sidebar_use_surface_bg` | 主内容+侧栏注释 |
| `triptych` | `header`(可选), `col-0`, `col-1`, `col-2` | `equal_width`, `has_unified_header`, `use_column_dividers` | 三列并排对比 |
| `overlay-mosaic` | `background`, `panel-0`..`panel-{n}` | `panel_count`(1-5), `panel_arrangement`, `panel_opacity` | 地图/照片+浮动信息面板 |
| `timeline` | `node-0`..`node-{n}` | `direction`(horizontal/vertical), `node_count`(3-7), `line_style` | 时间轴、流程线 |
| `asymmetric` | 自定义 `region_id` 列表 | 每区域: `x, y, width, height`（相对坐标 0~1）, `z_index` | 自由定位，杂志风 |

### 各布局渲染细节

#### full-bleed — `_render_full_bleed()`

```
┌──────────────────────────────────┐
│  background (image/color/gradient)│
│  ┌─ overlay (可选渐变蒙层) ─────┐│
│  │                              ││
│  │  content (锚定于 anchor 点)  ││
│  │                              ││
│  └──────────────────────────────┘│
└──────────────────────────────────┘
```

- `background_type`: `image` | `color` | `gradient`
- `content_anchor`: `center` | `bottom-left` | `top-left` | `bottom-center`
- `use_overlay` + `overlay_direction`: 生成 linear-gradient 或 radial-gradient 蒙层
- 若 `spec.is_chapter_divider` 为 True，强制 anchor 为 `center`
- 内容区 `max-width: 70%`，z-index 分层：背景 0 → 蒙层 1 → 内容 2

#### split-h — `_render_split_h()`

```
┌────────────┬──────────┐
│   left     │  right   │
│ (left_ratio│(right_   │
│   / 10)    │ ratio/10)│
└────────────┴──────────┘
```

- 比例以整数表示，如 `left_ratio=6, right_ratio=4` → 左 60% 右 40%
- `divider`: `none` | `line`（右边框线）| `gap`（section-gap 外边距）
- 两侧均 flexbox 纵向居中，gap 为 `--element-gap`

#### split-v — `_render_split_v()`

```
┌──────────────────────────────┐
│            top               │
│        (top_ratio)           │
├──────────────────────────────┤
│           bottom             │
│       (bottom_ratio)         │
└──────────────────────────────┘
```

- `bottom_style`: `normal` | `info-strip`（primary 色背景白字）

#### single-column — `_render_single_column()`

```
┌──────────────────────────────┐
│         (居中容器)            │
│   ┌──────────────────┐       │
│   │  pull-quote (可选)│       │
│   ├──────────────────┤       │
│   │  content blocks  │       │
│   └──────────────────┘       │
│     max_width_ratio          │
└──────────────────────────────┘
```

- `v_align`: `top` | `center` | `bottom`（flexbox 对齐）
- `max_width_ratio`: 内容区宽度占比，如 0.6 → 60%

#### grid — `_render_grid()`

```
┌──────────────────────────────┐  (has_header_row 时)
│  header (grid-column: 1/-1)  │
├─────────┬─────────┬──────────┤
│ cell-0-0│ cell-0-1│ cell-0-2 │
├─────────┼─────────┼──────────┤
│ cell-1-0│ cell-1-1│ cell-1-2 │
└─────────┴─────────┴──────────┘
```

- CSS Grid：`grid-template-columns: repeat(columns, 1fr)`
- `gap_size`: `tight` → 8px, `normal` → `--element-gap`, `loose` → `--section-gap`
- 单元格根据 `decoration.color_fill_usage` 决定是否使用 surface 背景色

#### hero-strip — `_render_hero_strip()`

`hero_position=top` 时上下分割，`hero_position=left` 时左右分割。

- `hero_ratio`: 主视觉占比（如 0.7）
- `strip_use_primary_bg`: strip 区域是否使用 primary 色背景

#### sidebar — `_render_sidebar()`

- `sidebar_position`: `left` | `right`
- `sidebar_ratio`: 侧栏宽度占比（如 0.28）
- `sidebar_use_surface_bg`: 侧栏是否使用 surface 背景色

#### triptych — `_render_triptych()`

三等宽列，可选统一 header 行和列间分隔线。区域 ID：`header`(可选)、`col-0`、`col-1`、`col-2`。

#### overlay-mosaic — `_render_overlay_mosaic()`

全屏背景 + 绝对定位浮动面板。

- `panel_arrangement` 预设位置方案：
  - `corners`: 四角 + 中心
  - `left-stack`: 左侧垂直排列
  - `bottom-row`: 底部水平排列
  - `scatter`: 分散布局
- 面板样式：半透明白底、圆角、阴影（`box-shadow: 0 4px 20px rgba(0,0,0,0.12)`）

#### timeline — `_render_timeline()`

水平或垂直时间轴。

- 节点：accent 色圆点 + primary 色边框（16px 圆）
- 连接线：`line_style` → `solid` | `dashed` | `dotted`，primary 色
- `node_count`: 3-7 个节点
- 区域 ID：`node-0` .. `node-{n-1}`

#### asymmetric — `_render_asymmetric()`

自由定位布局，每个区域由相对坐标 `(x, y, width, height)` 指定（0.0~1.0），支持 `z_index` 层叠。

```python
class AsymmetricRegion(BaseModel):
    region_id: str
    x: float       # 0.0~1.0
    y: float
    width: float
    height: float
    content_type: Literal["text", "image", "chart", "accent-shape", "empty"]
    z_index: int = 0
```

渲染为 `position: absolute` 的百分比定位 div。

---

## 1.5 布局分发 — `_render_layout()`

```python
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
```

未知布局原语自动回退到 `single-column`。

---

## 1.6 主入口 — `render_slide_html()`

LayoutSpec 模式：将结构化的 `LayoutSpec` + `VisualTheme` 渲染为完整 HTML 页面。

```python
def render_slide_html(
    spec: LayoutSpec,
    theme: VisualTheme,
    assets: dict[str, dict] | None = None,
    deck_meta: dict | None = None,
) -> str:
```

执行流程：

1. **资产引用解析** — `_resolve_asset_refs(spec, assets)`：扫描所有 ContentBlock，将 `content` 中的 `"asset:{key}"` 替换为实际 URL
2. **CSS 生成** — `generate_theme_css(theme)`
3. **布局渲染** — `_render_layout(spec, theme)` → body HTML
4. **页脚渲染** — `_render_footer(spec, deck_meta, theme)`（封面和章节隔页跳过）
5. **章节隔页特殊处理** — 若 `spec.is_chapter_divider`，注入额外 `<style>` 覆盖 `.slide-root` 背景为 primary 色、所有文字为白色、标题放大到 display 级
6. **拼合** — 输出完整 `<!DOCTYPE html>` 页面

### 资产解析逻辑

```python
def _resolve_asset_content(content_type: str, asset: dict, fallback: str) -> str:
    config = asset.get("config_json") or {}
    if content_type == "chart":
        return config.get("preview_url") or asset.get("image_url") or config.get("content_url") or fallback
    if content_type == "table":
        return _table_asset_to_markdown(asset) or fallback
    return config.get("preview_url") or asset.get("image_url") or asset.get("url") or fallback
```

- **chart** 优先使用 `config_json.preview_url`，其次 `image_url`，再次 `config_json.content_url`
- **table** 从 `data_json.preview_rows` 提取前 5 行转 Markdown 表格
- **其他** 类型依次尝试 `preview_url` → `image_url` → `url`

### 页脚

非封面/非章节隔页显示三段式页脚：

```
┌─────────────────────────────────────────────────────┐
│ {client_name}     {deck_title}     {slide_no}/{total}│
└─────────────────────────────────────────────────────┘
```

固定在底部 40px 高度，`position: fixed`，1px 顶部边框。

---

## 1.7 HTML 直出模式 — `render_slide_html_direct()`

Composer v3 支持 LLM 直接生成 `<div class="slide-root">...</div>` HTML，跳过 LayoutSpec 结构化流程。

```python
def render_slide_html_direct(
    body_html: str,
    theme: VisualTheme,
    assets: dict[str, dict] | None = None,
    deck_meta: dict | None = None,
    slide_no: int = 0,
    total_slides: int = 0,
) -> str:
```

执行流程：

1. **HTML 安全清洗** — `sanitize_slide_html(body_html)`（见 1.8）
2. **资产引用替换** — 字符串级别的 `"asset:{key}"` → 实际 URL
3. **CSS 生成** — 同上，`generate_theme_css(theme)`
4. **页脚** — 简化版绝对定位页脚（`position: absolute; bottom: 20px`）
5. **拼合** — 输出完整 HTML 页面

该模式的 CSS 变量系统与 LayoutSpec 模式完全一致，LLM 生成的 HTML 可直接使用 `var(--color-primary)` 等变量。

---

## 1.8 HTML 安全清洗 — `sanitize_slide_html()`

`render/html_sanitizer.py` 在 HTML 直出模式中对 LLM 输出进行安全过滤。

**移除项：**
- `<script>` 标签及内容
- 事件处理属性（`onclick`, `onerror` 等）
- `javascript:` 协议 URL
- CSS `@import` 规则
- 外部 `url()` 引用（保留 `data:` 和 `asset:` 协议）
- `<iframe>`, `<object>`, `<embed>`, `<form>`, `<input>`, `<link>` 等危险标签
- `<meta http-equiv>` 标签

**保留项：**
- 所有视觉 HTML 元素（`<div>`, `<span>`, `<h1>`-`<h6>`, `<p>`, `<ul>`, `<li>` 等）
- `<style>` 块（已去除 `@import`）
- 内联 style 属性、CSS 变量 `var(--...)`
- `<svg>` 及所有 SVG 子元素
- `<img>`（安全 src）
- `data:` URI 和 `asset:` 引用

---

## 1.9 VisualTheme 数据结构参考

### ColorSystem（10 色槽）

```python
class ColorSystem(BaseModel):
    primary: str            # 主色，如 "#1C3A5F"
    secondary: str          # 辅助色
    accent: str             # 强调色（高饱和）
    background: str         # 页面背景
    surface: str            # 卡片/面板背景
    text_primary: str       # 主要文字色
    text_secondary: str     # 次要文字色
    border: str             # 分隔线/边框
    overlay: str            # 图片蒙层（rgba 字符串）
    cover_bg: str           # 封面专属背景（hex 或 CSS gradient）
```

### TypographySystem

```python
class TypographySystem(BaseModel):
    font_heading: str           # 标题字体，如 "思源黑体"
    font_body: str              # 正文字体，如 "思源宋体"
    font_en: str                # 英文/数字字体，如 "Inter"
    base_size: int              # 正文基础字号（px），20~28，推荐 22
    scale_ratio: float          # 字阶比例，1.2~1.5，推荐 1.333
    heading_weight: int         # 标题字重：400 / 500 / 700
    body_weight: int            # 正文字重：通常 400
    line_height_body: float     # 正文行高，如 1.6
    line_height_heading: float  # 标题行高，如 1.15
    letter_spacing_label: str   # 标签字母间距，如 "0.1em"
```

### SpacingSystem

```python
class SpacingSystem(BaseModel):
    base_unit: int          # 基础间距单位（px），通常 8
    safe_margin: int        # 安全边距（px），64~96
    section_gap: int        # 主内容块间距（px），40~48
    element_gap: int        # 元素间距（px），16~24
    density: Literal["compact", "normal", "spacious"]
```

### DecorationStyle

```python
class DecorationStyle(BaseModel):
    use_divider_lines: bool
    divider_weight: Literal["hairline", "thin", "medium"]
    color_fill_usage: Literal["none", "subtle", "bold"]
    border_radius: Literal["none", "small", "medium", "large"]
    image_treatment: Literal["natural", "duotone", "desaturated", "framed"]
    accent_shape: Literal["none", "line", "dot", "block", "circle"]
    background_texture: Literal["flat", "subtle-grain", "linen", "concrete"]
```

### LayoutSpec

```python
class LayoutSpec(BaseModel):
    slide_no: int
    primitive: LayoutPrimitive = Field(..., discriminator="primitive")
    region_bindings: list[RegionBinding]
    visual_focus: str           # 视觉重点的 region_id
    is_cover: bool = False
    is_chapter_divider: bool = False
    section: str = ""
    title: str = ""
    slot_id: str = ""
    binding_id: str = ""
    source_refs: list[str] = []
    evidence_refs: list[str] = []
```

### ContentBlock

```python
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
```

---

---

# 第二部分：旧版渲染系统（保留供参考/回退）

> **注意：以下为旧版系统，已被第一部分的新版系统取代。保留此节是为了兼容回退和历史参考。**

## 2.1 设计系统 Token（静态 CSS）

旧版使用固定的 `render/design_system/tokens.css`，所有项目共用同一套硬编码变量：

```css
/* render/design_system/tokens.css */
:root {
  /* === 色彩系统 === */
  --color-primary:        #1a1a2e;
  --color-secondary:      #16213e;
  --color-accent:         #e94560;
  --color-accent-light:   #f5a623;
  --color-bg:             #ffffff;
  --color-bg-secondary:   #f8f8f8;
  --color-bg-dark:        #1a1a2e;
  --color-text-primary:   #1a1a2e;
  --color-text-secondary: #666666;
  --color-text-light:     #999999;
  --color-text-on-dark:   #ffffff;
  --color-border:         #e0e0e0;

  /* === 字体系统 === */
  --font-heading:   "思源黑体", "Source Han Sans", "PingFang SC", sans-serif;
  --font-body:      "思源宋体", "Source Han Serif", "Noto Serif SC", serif;
  --font-mono:      "JetBrains Mono", monospace;
  --font-en:        "Inter", "Helvetica Neue", sans-serif;

  /* === 字号系统（固定值） === */
  --text-display:   64px;
  --text-h1:        48px;
  --text-h2:        36px;
  --text-h3:        28px;
  --text-body:      20px;
  --text-caption:   16px;
  --text-small:     14px;

  /* === 间距系统（固定值） === */
  --space-xs:   8px;
  --space-sm:   16px;
  --space-md:   24px;
  --space-lg:   40px;
  --space-xl:   64px;
  --space-2xl:  96px;

  --slide-width:  1920px;
  --slide-height: 1080px;
  --grid-columns: 12;
  --grid-gutter:  24px;
  --safe-margin:  64px;

  --radius-sm:  4px;
  --radius-md:  8px;
  --radius-lg:  16px;

  --shadow-card: 0 4px 16px rgba(0,0,0,0.08);
  --shadow-float: 0 8px 32px rgba(0,0,0,0.16);
}
```

**与新版的关键差异：**
- 所有变量为硬编码值，无法按项目自定义
- 无 `--color-surface` / `--color-overlay` / `--color-cover-bg`
- 字号为固定像素值，无字阶计算
- 间距使用离散 token（`--space-xs` ~ `--space-2xl`），而非语义化的 `--safe-margin` / `--section-gap` / `--element-gap`

---

## 2.2 页面基础模板（Jinja2）

旧版使用 Jinja2 模板继承机制，所有页面 extend `base.html`：

```html
<!-- render/templates/base.html -->
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=1920">
  <link rel="stylesheet" href="/design_system/tokens.css">
  <link rel="stylesheet" href="/design_system/typography.css">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      width: var(--slide-width);
      height: var(--slide-height);
      overflow: hidden;
      font-family: var(--font-body);
      background: var(--color-bg);
      color: var(--color-text-primary);
    }
    .slide {
      position: relative;
      width: var(--slide-width);
      height: var(--slide-height);
      padding: var(--safe-margin);
    }
    .slide-footer { ... }
    .section-tag { ... }
    .slide-title { ... }
    .key-message { ... }
  </style>
</head>
<body>
<div class="slide" style="--primary: {{ style_tokens.primary_color }};
                           --accent: {{ style_tokens.accent_color }};">
  {% block content %}{% endblock %}
  <div class="slide-footer">
    <span>{{ client_name }}</span>
    <span>{{ deck_title }}</span>
    <span>{{ slide_no }} / {{ total_slides }}</span>
  </div>
</div>
</body>
</html>
```

---

## 2.3 旧版模板列表

旧版使用 `TEMPLATE_MAP` 将模板名映射到 Jinja2 文件：

```python
TEMPLATE_MAP = {
    "cover-hero":              "cover_hero.html",
    "overview-kpi":            "overview_kpi.html",
    "map-left-insight-right":  "map_left_insight_right.html",
    "two-case-compare":        "two_case_compare.html",
    "gallery-quad":            "gallery_quad.html",
    "strategy-diagram":        "strategy_diagram.html",
    "chapter-divider":         "chapter_divider.html",
    "chart-main-text-side":    "chart_main_text_side.html",
    "matrix-summary":          "matrix_summary.html",
}
```

每个模板是针对特定页面类型的完整 HTML 布局——与新版使用 11 种通用布局原语的组合方式不同。

### 旧版渲染入口

```python
# 旧版 render/engine.py
def render_slide_html(spec: SlideSpec, assets: dict = {}) -> str:
    template_file = TEMPLATE_MAP.get(spec.layout_template.value)
    template = env.get_template(template_file)
    blocks_dict = {b.block_id: _resolve_block(b, assets) for b in spec.blocks}
    ctx = {
        "slide_no":     spec.slide_no,
        "section":      spec.section,
        "title":        spec.title,
        "key_message":  spec.key_message,
        "blocks":       blocks_dict,
        "style_tokens": spec.style_tokens.model_dump(),
    }
    return template.render(**ctx)
```

---

## 2.4 旧版内容密度约束

旧版通过 `slide_content_fit_tool` 在 Composer 生成 SlideSpec 后校验内容密度：

```python
DENSITY_RULES = {
    "low":    {"max_chars": 100, "max_bullets": 3, "max_images": 1},
    "medium": {"max_chars": 200, "max_bullets": 5, "max_images": 2},
    "high":   {"max_chars": 300, "max_bullets": 7, "max_images": 4},
}
```

超量内容会被截断并返回警告列表。
