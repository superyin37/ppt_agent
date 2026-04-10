---
tags: [schema, visual-theme, pydantic]
source: schema/visual_theme.py
---

# VisualTheme Schema

> 项目级视觉主题，一次生成作用于全部幻灯片。由 [[agents/VisualThemeAgent]] 生成，被 [[agents/ComposerAgent]] 和 `render/engine.py` 消费。

## 完整结构

```python
class VisualTheme(BaseModel):
    project_id: UUID

    colors:     ColorSystem
    typography: TypographySystem
    spacing:    SpacingSystem
    decoration: DecorationStyle
    cover:      CoverStyle

    style_keywords: list[str]       # 如 ["水墨留白", "现代简约"]
    generation_prompt_hint: str     # LLM 生成时的核心指令摘要
```

---

## ColorSystem

```python
class ColorSystem(BaseModel):
    primary:        str   # 主色，hex，如 "#1C3A5F"
    secondary:      str   # 辅助色，hex
    accent:         str   # 强调色，高饱和，hex
    background:     str   # 页面背景，hex（避免纯白，推荐极浅色）
    surface:        str   # 卡片/面板背景，hex
    text_primary:   str   # 主要文字色，hex
    text_secondary: str   # 次要文字色，hex
    border:         str   # 分隔线/边框，hex
    overlay:        str   # 图片蒙层，rgba 字符串
    cover_bg:       str   # 封面专属背景，hex 或 CSS gradient
```

**对比度约束（WCAG AA）：**
- `primary` vs `background` ≥ 4.5:1
- `accent` vs `background` ≥ 3:1
- `secondary` vs `primary` 色相差 ≥ 15°

---

## TypographySystem

```python
class TypographySystem(BaseModel):
    font_heading:          str    # 如 "思源黑体"
    font_body:             str    # 如 "思源宋体"
    font_en:               str    # 如 "Inter"
    base_size:             int    # 正文字号 px，范围 20–28，推荐 22
    scale_ratio:           float  # 字阶比例，范围 1.2–1.5，推荐 1.333
    heading_weight:        int    # 标题字重，400/500/700
    body_weight:           int    # 正文字重，通常 400
    line_height_body:      float  # 正文行高，如 1.6
    line_height_heading:   float  # 标题行高，如 1.15
    letter_spacing_label:  str    # 标签字母间距，如 "0.1em"
```

**字型阶梯计算（`render/engine.py`）：**

`size_n = base_size × scale_ratio^n`

| 级别 | 示例（base=22, ratio=1.333） | 绝对下限 |
|------|--------------------------|---------|
| display | ≈ 58px | 56px |
| h1 | ≈ 44px | 40px |
| h2 | ≈ 33px | 32px |
| h3 | ≈ 29px | 24px |
| body | 22px | 20px |
| caption | ≈ 17px | 16px |
| label | ≈ 13px | 12px |

---

## SpacingSystem

```python
class SpacingSystem(BaseModel):
    base_unit:   int     # 基础间距单位 px，通常 8
    safe_margin: int     # 页面安全边距 px，如 64–96
    section_gap: int     # 主要内容块间距 px，如 40–48
    element_gap: int     # 元素间距 px，如 16–24
    density:     Literal["compact", "normal", "spacious"]
```

密度含义：
- `compact` — 数据密集型汇报（经济分析、技术指标）
- `normal` — 标准建筑设计汇报
- `spacious` — 概念性/艺术性强，留白充足

---

## DecorationStyle

```python
class DecorationStyle(BaseModel):
    use_divider_lines:   bool
    divider_weight:      Literal["hairline", "thin", "medium"]
    color_fill_usage:    Literal["none", "subtle", "bold"]
    border_radius:       Literal["none", "small", "medium", "large"]
    image_treatment:     Literal["natural", "duotone", "desaturated", "framed"]
    accent_shape:        Literal["none", "line", "dot", "block", "circle"]
    background_texture:  Literal["flat", "subtle-grain", "linen", "concrete"]
```

`border_radius` 映射 px：`none=0, small=4px, medium=12px, large=24px`

`background_texture` 在 `render/engine.py` 中通过内联 SVG 实现。

---

## CoverStyle

```python
class CoverStyle(BaseModel):
    layout_mood:        Literal["full-bleed", "split", "centered", "editorial"]
    title_on_dark:      bool    # True = 白字（深色背景）
    show_brief_metrics: bool    # 是否显示项目指标摘要
```

---

## JSON 示例

```json
{
  "project_id": "550e8400-...",
  "colors": {
    "primary": "#1A365D",
    "secondary": "#2D3748",
    "accent": "#ED8936",
    "background": "#FAFAF8",
    "surface": "#F7FAFC",
    "text_primary": "#1A202C",
    "text_secondary": "#718096",
    "border": "#E2E8F0",
    "overlay": "rgba(0,0,0,0.6)",
    "cover_bg": "linear-gradient(135deg, #1A365D 0%, #2D6A8F 100%)"
  },
  "typography": {
    "font_heading": "思源黑体",
    "font_body": "思源宋体",
    "font_en": "Inter",
    "base_size": 22,
    "scale_ratio": 1.333,
    "heading_weight": 700,
    "body_weight": 400,
    "line_height_body": 1.6,
    "line_height_heading": 1.15,
    "letter_spacing_label": "0.1em"
  },
  "style_keywords": ["现代", "专业", "沉稳"]
}
```

## 相关

- [[agents/VisualThemeAgent]]
- [[prompts/VisualThemeSystem]]
- [[schemas/LayoutSpec]]
- `render/engine.py` — `generate_theme_css()` 消费此 schema
