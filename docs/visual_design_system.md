# 视觉设计系统设计文档

> 本文档描述 PPT Agent 新一代视觉生成逻辑，替代现有的固定 Design Token + 预制模板方案。
> 核心原则：每个项目的视觉设计从用户风格输入动态生成，而非从预设库中选取。

---

## 一、整体架构

### 1.1 设计分层

视觉系统分两层，完全独立：

```
第一层：VisualTheme（项目级，生成一次）
  ├── 色彩系统
  ├── 字体系统
  ├── 空间系统
  └── 装饰风格

第二层：LayoutSpec（页面级，每页生成一次）
  ├── 布局原语类型
  ├── 区域比例与分配
  └── 内容与区域的绑定关系
```

两层相互独立：LayoutSpec 只描述「空间怎么分」，VisualTheme 决定「视觉怎么表现」。渲染器将二者合并生成最终 HTML。

### 1.2 流程位置

```
简报确认
  ↓
案例选择 → 偏好摘要（dominant_styles / narrative_hint）
  ↓
[ Visual Theme Agent ]  ← 新增，生成 VisualTheme，保存至 DB
  ↓
大纲生成（每页带内容意图，不带模板名）
  ↓
Composer（每页生成 LayoutSpec + 内容块）
  ↓
渲染器（VisualTheme + LayoutSpec + 内容块 → HTML）
  ↓
Playwright 截图 → PDF
```

---

## 二、VisualTheme 规格

VisualTheme 在案例偏好确认后由 LLM 生成一次，作用于整个 PPT 的所有页面。

### 2.1 色彩系统

```python
class ColorSystem(BaseModel):
    # 主色调：品牌感最强的颜色，用于大面积色块、标题强调
    primary: str              # hex，如 "#1C3A5F"

    # 辅助色：与主色协调，用于次级元素、章节背景
    secondary: str            # hex，如 "#2D6A8F"

    # 强调色：高饱和，用于关键数据、高亮、标签
    accent: str               # hex，如 "#E8A020"

    # 页面背景色
    background: str           # hex，通常接近白色或极浅色

    # 卡片/面板背景色（比 background 略深或略浅）
    surface: str              # hex

    # 主要文字色
    text_primary: str         # hex，高对比度

    # 次要文字色（说明文字、注释）
    text_secondary: str       # hex，中对比度

    # 分隔线/边框色
    border: str               # hex，低对比度

    # 图片/深色背景上的叠加蒙层色（含透明度）
    overlay: str              # rgba，如 "rgba(0,0,0,0.55)"

    # 封面专属背景（可与 background 不同，用于封面全出血背景）
    cover_bg: str             # hex 或 CSS gradient 字符串
```

**色彩关系约束（由生成 prompt 保证）：**
- `primary` 与 `background` 对比度 ≥ 4.5:1（WCAG AA）
- `accent` 与 `background` 对比度 ≥ 3:1
- `secondary` 与 `primary` 不得过于相近（色相差 ≥ 15°）

### 2.2 字体系统

```python
class TypographySystem(BaseModel):
    # 标题字体族（中文优先，回退到系统字体）
    font_heading: str         # 如 "思源黑体" / "方正标雅宋" / "霞鹜文楷"

    # 正文字体族
    font_body: str            # 如 "思源宋体" / "思源黑体" / "方正仿宋"

    # 英文/数字专用字体（用于指标数值、英文标签）
    font_en: str              # 如 "Inter" / "DM Sans" / "Helvetica Neue"

    # 基础字号（正文）单位 px
    base_size: int            # 通常 18~22

    # 字阶比例（标题逐级放大的倍数）
    scale_ratio: float        # 如 1.25（Major Third）/ 1.333（Perfect Fourth）

    # 标题字重
    heading_weight: int       # 400 / 500 / 700

    # 正文字重
    body_weight: int          # 通常 400

    # 正文行高
    line_height_body: float   # 如 1.6

    # 标题行高
    line_height_heading: float  # 如 1.15

    # 字母间距修正（主要用于英文全大写标签）
    letter_spacing_label: str   # 如 "0.1em"
```

**由 scale_ratio 推导的字阶：**

```
display  = base_size × scale_ratio⁴
h1       = base_size × scale_ratio³
h2       = base_size × scale_ratio²
h3       = base_size × scale_ratio¹
body     = base_size
caption  = base_size × scale_ratio⁻¹
label    = base_size × scale_ratio⁻²
```

### 2.3 空间系统

```python
class SpacingSystem(BaseModel):
    # 基础间距单位（px），所有间距为此的倍数
    base_unit: int            # 通常 8

    # 页面安全边距（四周留白）
    safe_margin: int          # 如 64 / 80 / 96

    # 内容区域间距（两个主要内容块之间）
    section_gap: int          # 如 40 / 48

    # 元素间距（同一内容区内的元素间隔）
    element_gap: int          # 如 16 / 24

    # 空间密度感
    density: Literal["compact", "normal", "spacious"]
    # compact  → 信息密度高，适合数据密集型汇报
    # normal   → 标准建筑汇报
    # spacious → 留白充足，适合概念性/艺术性方案
```

### 2.4 装饰风格

```python
class DecorationStyle(BaseModel):
    # 是否使用装饰线（章节标题下方、区域分隔）
    use_divider_lines: bool

    # 装饰线粗细
    divider_weight: Literal["hairline", "thin", "medium"]
    # hairline = 0.5px / thin = 1px / medium = 2px

    # 色块使用方式
    color_fill_usage: Literal["none", "subtle", "bold"]
    # none   → 纯白底，靠字色和图区分层次
    # subtle → 浅色面板背景（surface 色），柔和分区
    # bold   → 大面积 primary/secondary 色块，视觉张力强

    # 圆角风格
    border_radius: Literal["none", "small", "medium", "large"]
    # none=0 / small=4px / medium=12px / large=24px

    # 图片处理方式
    image_treatment: Literal["natural", "duotone", "desaturated", "framed"]
    # natural      → 原色呈现
    # duotone      → 双色调（主色 + 亮色叠加）
    # desaturated  → 去饱和（配合彩色文字区域）
    # framed       → 加边框/内边距，像装裱的画

    # 强调图形元素（用于封面、章节页的装饰性几何）
    accent_shape: Literal["none", "line", "dot", "block", "circle"]
    # none   → 无装饰几何
    # line   → 细长竖线/横线
    # dot    → 圆点阵列或单点
    # block  → 矩形色块
    # circle → 圆形装饰

    # 背景纹理
    background_texture: Literal["flat", "subtle-grain", "linen", "concrete"]
    # flat          → 纯色，无纹理
    # subtle-grain  → 极轻微噪点，增加质感
    # linen / concrete → 材质感纹理（SVG data URI）
```

### 2.5 封面专项

```python
class CoverStyle(BaseModel):
    # 封面版式基调
    layout_mood: Literal["full-bleed", "split", "centered", "editorial"]
    # full-bleed → 背景图满铺，文字叠加（建筑效果图类项目）
    # split      → 左右分割，一侧底色一侧图
    # centered   → 居中排版，简洁大气
    # editorial  → 杂志风，图文穿插不对称

    # 标题文字颜色方案
    title_on_dark: bool       # True = 白字（深色背景），False = 深字（浅色背景）

    # 是否显示项目指标摘要（面积、容积率等）
    show_brief_metrics: bool
```

### 2.6 完整 VisualTheme Schema

```python
class VisualTheme(BaseModel):
    project_id: UUID

    # 五个子系统
    colors: ColorSystem
    typography: TypographySystem
    spacing: SpacingSystem
    decoration: DecorationStyle
    cover: CoverStyle

    # 生成时的风格关键词（用于调试和审查）
    style_keywords: list[str]      # 如 ["水墨留白", "现代简约", "江南意境"]
    generation_prompt_hint: str    # LLM 生成时使用的核心指令摘要
```

---

## 三、布局原语规格

布局原语描述「页面空间如何划分」，不含任何视觉信息。共定义 **11 种**，覆盖建筑汇报的常见页面类型。

### 原语列表

| 编号 | 原语名 | 描述 | 典型用途 |
|------|--------|------|---------|
| 1 | `full-bleed` | 单一全屏区域，无内部分割 | 封面、章节过渡页、氛围页 |
| 2 | `split-h` | 左右分割，比例可配置 | 图文并列、区位分析、案例介绍 |
| 3 | `split-v` | 上下分割，比例可配置 | 大图 + 说明条、标题 + 内容区 |
| 4 | `single-column` | 单列居中，两侧留白 | 文字为主的说明页、设计理念 |
| 5 | `grid` | N×M 均等网格 | 多图集、指标卡片组、案例对比 |
| 6 | `hero-strip` | 主视觉区（上/左大）+ 底部/侧边信息条 | 效果图展示 + 技术指标 |
| 7 | `sidebar` | 主内容区 + 窄侧栏（左或右） | 图表 + 文字注释、流程图 + 说明 |
| 8 | `triptych` | 三等分竖向并排 | 三方案对比、三阶段流程、三维度分析 |
| 9 | `overlay-mosaic` | 背景大图 + 多个浮动文字/数据面板叠加 | 场地分析、鸟瞰图标注 |
| 10 | `timeline` | 横向或纵向时间序列轨道 | 设计进度、建设周期、历史沿革 |
| 11 | `asymmetric` | 不对称自由分区（LLM 指定各区位置比例） | 创意封面、概念页、需要特殊强调的页 |

### 原语详细规格

#### `full-bleed`
```python
class FullBleedLayout(BaseModel):
    primitive: Literal["full-bleed"]

    # 内容区定位
    content_anchor: Literal[
        "center",           # 文字居中
        "bottom-left",      # 左下角（电影字幕式）
        "top-left",         # 左上角
        "bottom-center",    # 底部居中
    ]

    # 是否需要背景蒙层（背景图较亮时需要）
    use_overlay: bool
    overlay_direction: Literal["top", "bottom", "left", "radial"] | None

    # 背景内容类型
    background_type: Literal["image", "color", "gradient"]
```

#### `split-h`
```python
class SplitHLayout(BaseModel):
    primitive: Literal["split-h"]

    # 左右比例，合计 10
    left_ratio: int           # 如 6（左占 60%）
    right_ratio: int          # 如 4（右占 40%）

    # 各区域主要内容类型
    left_content_type: Literal["text", "image", "chart", "map", "mixed"]
    right_content_type: Literal["text", "image", "chart", "map", "mixed"]

    # 是否在中间加分隔线或间距
    divider: Literal["none", "line", "gap"]

    # 哪侧是视觉主导（影响标题放置逻辑）
    dominant_side: Literal["left", "right"]
```

#### `split-v`
```python
class SplitVLayout(BaseModel):
    primitive: Literal["split-v"]

    top_ratio: int            # 如 7（上占 70%）
    bottom_ratio: int         # 如 3（下占 30%）

    top_content_type: Literal["text", "image", "chart", "map", "mixed"]
    bottom_content_type: Literal["text", "image", "chart", "map", "mixed"]

    # 底部区域风格（信息条 or 普通内容区）
    bottom_style: Literal["info-strip", "normal"]
```

#### `single-column`
```python
class SingleColumnLayout(BaseModel):
    primitive: Literal["single-column"]

    # 内容最大宽度（相对于页面宽度的比例）
    max_width_ratio: float    # 如 0.6（内容区占页面宽度 60%）

    # 垂直对齐
    v_align: Literal["top", "center", "bottom"]

    # 是否有引言/大字号段落（类似杂志引言）
    has_pull_quote: bool
```

#### `grid`
```python
class GridLayout(BaseModel):
    primitive: Literal["grid"]

    columns: int              # 列数，1~4
    rows: int                 # 行数，1~3

    # 单元格内容类型（所有格相同或混合）
    cell_content_type: Literal["image", "text", "kpi-card", "case-card", "mixed"]

    # 是否有统一的标题行（在网格上方）
    has_header_row: bool

    # 网格间距大小
    gap_size: Literal["tight", "normal", "loose"]
```

#### `hero-strip`
```python
class HeroStripLayout(BaseModel):
    primitive: Literal["hero-strip"]

    # 主视觉区在哪侧
    hero_position: Literal["top", "left"]

    # 主视觉区占比
    hero_ratio: float         # 如 0.7（主视觉占 70%）

    hero_content_type: Literal["image", "chart", "map"]
    strip_content_type: Literal["text", "kpi-cards", "bullet-list"]

    # 信息条背景是否使用 primary 色
    strip_use_primary_bg: bool
```

#### `sidebar`
```python
class SidebarLayout(BaseModel):
    primitive: Literal["sidebar"]

    # 侧栏位置
    sidebar_position: Literal["left", "right"]

    # 侧栏宽度比例
    sidebar_ratio: float      # 如 0.28（侧栏占 28%）

    main_content_type: Literal["text", "image", "chart", "map", "mixed"]
    sidebar_content_type: Literal["text", "kpi-cards", "image-list", "annotation-list"]

    # 侧栏是否有独立背景色
    sidebar_use_surface_bg: bool
```

#### `triptych`
```python
class TriptychLayout(BaseModel):
    primitive: Literal["triptych"]

    # 三列是否等宽
    equal_width: bool

    # 各列内容类型
    col_content_types: list[
        Literal["text", "image", "chart", "kpi-card", "case-card"]
    ]                         # 长度必须为 3

    # 是否有统一标题（在三列上方）
    has_unified_header: bool

    # 列间是否有分隔线
    use_column_dividers: bool
```

#### `overlay-mosaic`
```python
class OverlayMosaicLayout(BaseModel):
    primitive: Literal["overlay-mosaic"]

    # 背景内容类型
    background_type: Literal["image", "map"]

    # 浮动面板数量（1~5）
    panel_count: int

    # 面板布局倾向
    panel_arrangement: Literal[
        "corners",          # 四角分布
        "left-stack",       # 左侧垂直堆叠
        "bottom-row",       # 底部一排
        "scatter",          # 自由散布（LLM 决定大致位置）
    ]

    panel_content_type: Literal["kpi", "text-annotation", "legend", "mixed"]

    # 面板透明度
    panel_opacity: float      # 0.7 ~ 1.0
```

#### `timeline`
```python
class TimelineLayout(BaseModel):
    primitive: Literal["timeline"]

    # 时间轴方向
    direction: Literal["horizontal", "vertical"]

    # 节点数量
    node_count: int           # 3~7

    # 节点内容类型
    node_content: Literal["text-only", "text-image", "text-kpi"]

    # 时间轴线风格
    line_style: Literal["solid", "dashed", "dotted"]

    # 是否标注当前进度节点（当前/完成/未来）
    show_progress_state: bool
```

#### `asymmetric`
```python
class AsymmetricLayout(BaseModel):
    primitive: Literal["asymmetric"]

    # LLM 自定义的区域描述（2~4 个区域）
    regions: list[AsymmetricRegion]

class AsymmetricRegion(BaseModel):
    region_id: str
    # 位置和尺寸（以页面宽高为 1 的相对坐标）
    x: float                  # 0.0 ~ 1.0
    y: float                  # 0.0 ~ 1.0
    width: float              # 0.0 ~ 1.0
    height: float             # 0.0 ~ 1.0
    content_type: Literal["text", "image", "chart", "accent-shape", "empty"]
    z_index: int              # 层叠顺序（允许区域重叠）
```

---

## 四、LayoutSpec：每页生成的版式规格

Composer 为每张幻灯片生成 LayoutSpec，包含原语选择 + 内容分配。

```python
class ContentBlock(BaseModel):
    block_id: str
    content_type: Literal[
        "heading", "subheading", "body-text", "bullet-list",
        "kpi-value", "image", "chart", "map", "table",
        "quote", "caption", "label", "accent-element"
    ]
    content: str | list[str] | None   # 文字内容 / asset 引用
    emphasis: Literal["normal", "highlight", "muted"] = "normal"
    # highlight = 用 accent 色强调
    # muted     = 用 text_secondary 色弱化

class RegionBinding(BaseModel):
    region_id: str            # 对应原语中的区域 ID
    blocks: list[ContentBlock]

LayoutPrimitive = Union[
    FullBleedLayout, SplitHLayout, SplitVLayout,
    SingleColumnLayout, GridLayout, HeroStripLayout,
    SidebarLayout, TriptychLayout, OverlayMosaicLayout,
    TimelineLayout, AsymmetricLayout,
]

class LayoutSpec(BaseModel):
    slide_no: int
    primitive: LayoutPrimitive
    region_bindings: list[RegionBinding]

    # 这页的视觉重点（渲染器据此决定哪个区域优先获得视觉权重）
    visual_focus: str         # region_id

    # 是否是封面页（触发 CoverStyle 的特殊处理）
    is_cover: bool = False

    # 是否是章节过渡页（减少内容密度，增加留白）
    is_chapter_divider: bool = False
```

---

## 五、Visual Theme Agent

### 5.1 触发时机

案例偏好确认（`POST /projects/{id}/references/confirm`）完成后，在大纲生成之前自动触发。

### 5.2 输入

```python
class VisualThemeInput(BaseModel):
    building_type: str
    style_preferences: list[str]      # 来自简报
    preference_summary: PreferenceSummary  # 来自案例选择
    project_name: str
    client_name: str | None
```

`preference_summary` 中的 `dominant_styles`、`dominant_features`、`narrative_hint` 是最重要的输入，它们包含了用户从案例中选出的审美倾向。

### 5.3 Prompt 核心指令

```
你是一位专业的建筑展示设计师，需要为一个建筑方案汇报 PPT 设计完整的视觉主题。

项目信息：
- 建筑类型：{building_type}
- 风格偏好：{style_preferences}
- 案例审美倾向：{dominant_styles}
- 叙事基调：{narrative_hint}

请生成一套完整的视觉主题，要求：
1. 色彩系统必须协调统一，主色与建筑类型气质吻合
2. 字体选择要支持中文显示，风格与项目气质匹配
3. 装饰风格必须与色彩、字体形成整体一致的美学语言
4. 避免与常见建筑 PPT 模板雷同，体现项目个性

输出必须严格符合 VisualTheme JSON Schema，不要输出任何 JSON 以外的内容。
```

### 5.4 存储

`VisualTheme` 存储在数据库 `visual_themes` 表中，通过 `project_id` 关联。大纲生成和 Composer 均从 DB 读取。

---

## 六、渲染器新逻辑

### 6.1 CSS 生成

渲染器不再读取固定的 `tokens.css`，而是根据 `VisualTheme` 动态生成 CSS 变量：

```python
def generate_theme_css(theme: VisualTheme) -> str:
    c = theme.colors
    t = theme.typography
    s = theme.spacing

    # 计算字阶
    sizes = _compute_type_scale(t.base_size, t.scale_ratio)

    return f"""
    :root {{
      --color-primary:        {c.primary};
      --color-secondary:      {c.secondary};
      --color-accent:         {c.accent};
      --color-bg:             {c.background};
      --color-surface:        {c.surface};
      --color-text-primary:   {c.text_primary};
      --color-text-secondary: {c.text_secondary};
      --color-border:         {c.border};
      --color-overlay:        {c.overlay};

      --font-heading:   "{t.font_heading}", "PingFang SC", sans-serif;
      --font-body:      "{t.font_body}", "PingFang SC", sans-serif;
      --font-en:        "{t.font_en}", "Helvetica Neue", sans-serif;

      --text-display: {sizes['display']}px;
      --text-h1:      {sizes['h1']}px;
      --text-h2:      {sizes['h2']}px;
      --text-h3:      {sizes['h3']}px;
      --text-body:    {sizes['body']}px;
      --text-caption: {sizes['caption']}px;
      --text-label:   {sizes['label']}px;

      --font-weight-heading: {t.heading_weight};
      --line-height-body:    {t.line_height_body};
      --line-height-heading: {t.line_height_heading};

      --safe-margin:   {s.safe_margin}px;
      --section-gap:   {s.section_gap}px;
      --element-gap:   {s.element_gap}px;

      --border-radius: {_radius_value(d.border_radius)};

      --slide-width:  1920px;
      --slide-height: 1080px;
    }}
    """
```

### 6.2 HTML 生成

渲染器根据 `LayoutSpec.primitive` 类型分发到对应的布局渲染函数，将内容块填入各区域：

```python
def render_slide_html(
    layout_spec: LayoutSpec,
    theme: VisualTheme,
    deck_meta: dict,
) -> str:
    theme_css = generate_theme_css(theme)
    body_html = _render_layout(layout_spec, theme)
    return _wrap_in_base(theme_css, body_html, layout_spec, deck_meta)

def _render_layout(spec: LayoutSpec, theme: VisualTheme) -> str:
    dispatch = {
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
    fn = dispatch[spec.primitive.primitive]
    return fn(spec, theme)
```

每个 `_render_*` 函数生成该原语对应的 HTML 结构（flex/grid/absolute positioning），所有颜色、字体均通过 CSS 变量引用，不硬编码。

---

## 七、数据库变更

### 新增表：`visual_themes`

```sql
CREATE TABLE visual_themes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  UUID NOT NULL REFERENCES projects(id),
    version     INT NOT NULL DEFAULT 1,
    status      VARCHAR(50) NOT NULL DEFAULT 'draft',  -- draft / confirmed
    theme_json  JSONB NOT NULL,          -- 完整 VisualTheme 对象
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);
```

### slides 表变更

| 字段 | 变更 |
|------|------|
| `spec_json` | 内容由 `SlideSpec` 改为 `LayoutSpec` |
| `layout_template` | 废弃，删除 |

---

## 八、改动范围

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `schema/visual_theme.py` | 新建 | VisualTheme / LayoutSpec / 布局原语 Schema |
| `db/models/visual_theme.py` | 新建 | ORM 模型 |
| `alembic/versions/` | 新增迁移 | 添加 visual_themes 表，修改 slides 表 |
| `agent/visual_theme.py` | 新建 | Visual Theme Agent |
| `render/engine.py` | 重写 | 动态 CSS 生成 + 布局原语渲染 |
| `render/templates/` | 废弃 | 所有 .html 模板文件删除 |
| `render/design_system/tokens.css` | 废弃 | 由动态生成替代 |
| `agent/composer.py` | 修改 | 生成 LayoutSpec 替代旧 SlideSpec |
| `tasks/outline_tasks.py` | 修改 | compose 前先读取 VisualTheme |
| `api/routers/references.py` | 修改 | confirm 后触发 visual_theme 生成 |
| `prompts/visual_theme_system.md` | 新建 | Visual Theme Agent Prompt |
| `prompts/composer_system.md` | 修改 | 加入 VisualTheme 上下文和 LayoutSpec 输出要求 |
