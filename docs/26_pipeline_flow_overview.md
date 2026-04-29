# 26 — 素材包到 PDF 全流程说明

> 本文档详细说明 PPT Agent 从接收素材包到输出 PDF 的完整 9 阶段流水线。
> 每个阶段包含：触发方式、关键文件与函数、LLM 调用说明、数据模型产出、项目状态变更。
>
> **2026-04-25 更新**：ADR-006 计划将 Composer v3 HTML 模式统一为产品主流程。本文中 structured/LayoutSpec 内容保留为 fallback/debug 说明。

---

## 目录

1. [流程总览](#1-流程总览)
2. [阶段一：素材包摄入](#2-阶段一素材包摄入)
3. [阶段二：Brief 文档生成](#3-阶段二brief-文档生成)
4. [阶段三：大纲生成](#4-阶段三大纲生成)
5. [阶段四：大纲确认与素材绑定](#5-阶段四大纲确认与素材绑定)
6. [阶段五：幻灯片内容编排](#6-阶段五幻灯片内容编排)
7. [阶段六：视觉主题生成](#7-阶段六视觉主题生成)
8. [阶段七：渲染](#8-阶段七渲染)
9. [阶段八：审查与修复](#9-阶段八审查与修复)
10. [阶段九：PDF 导出](#10-阶段九pdf-导出)
11. [核心数据流总结](#11-核心数据流总结)
12. [项目状态生命周期](#12-项目状态生命周期)
13. [关键文件索引](#13-关键文件索引)

---

## 1. 流程总览

```
本地素材文件夹
  │
  ▼  ① ingest_local_material_package()
MaterialItem + Asset + ProjectBrief
  │
  ▼  ② generate_brief_doc()                     [LLM]
BriefDoc（叙事框架 + 章节结构）
  │
  ▼  ③ generate_outline()                        [LLM]
Outline（每页 slot / title / directive / asset_keys）
  │
  ▼  ④ bind_materials()
SlideMaterialBinding（每页绑定具体素材与资产）
  │
  ▼  ⑤ compose_all_slides()                      [LLM × N 页并发]
Slide（主流程 HTML/body_html；fallback LayoutSpec）
  │
  ▼  ⑥ generate_visual_theme()                   [LLM，可选]
VisualTheme（配色 / 字体 / 间距 / 装饰）
  │
  ▼  ⑦ render_slide_html() + screenshot_slides_batch()
PNG 截图（1920×1080）
  │
  ▼  ⑧ review_slides()                           [可选]
Review → Repair → 重新渲染
  │
  ▼  ⑨ compile_pdf()
PDF 文件
```

---

## 2. 阶段一：素材包摄入

### 触发

- **API：** `POST /projects/{project_id}/material-packages/ingest-local`
- **路由：** `api/routers/material_packages.py` — 第 20 行

### 核心函数

| 函数 | 文件 | 行号 | 职责 |
|------|------|------|------|
| `ingest_local_material_package()` | `tool/material_pipeline.py` | 507 | 流程总控：扫描、分类、入库 |
| 文件扫描与分组 | `tool/material_pipeline.py` | 529-545 | 扫描目录、按 basename 分组图表变体 |
| `_derive_assets()` | `tool/material_pipeline.py` | 399-504 | MaterialItem → Asset 派生 |
| `_extract_project_brief()` | `tool/material_pipeline.py` | 257-339 | 从大纲文档提取项目元信息 |

### 处理流程

**Step 1 — 文件扫描与分类**

扫描指定本地目录下所有文件，将图表变体（JSON、SVG、HTML）按 basename 分组。通过正则模式推断每个文件的 `logical_key`：

```
文件名示例                          → logical_key
参考案例1_图片_1_xxx.jpg           → reference.case.1.images
场地分析_红线图.png                → site.boundary.image
经济指标_城市GDP.xlsx              → economy.city.chart.1
```

**Step 2 — 创建 MaterialItem**

每个文件生成一条数据库记录：

| 字段 | 说明 |
|------|------|
| `logical_key` | 层级化标识符，用于后续素材匹配 |
| `kind` | image / chart_bundle / spreadsheet / document / binary |
| `text_content` | 文本文件前 2000 字符摘录 |
| `structured_data` | JSON 内容 或 XLSX sheet 预览 |
| `preview_url` / `content_url` | 本地 `file://` URI |

**Step 3 — 资产派生**

每条 MaterialItem 自动派生为 Asset 记录，映射规则：

| MaterialItem kind | Asset Type | 备注 |
|-------------------|------------|------|
| image（site.* 前缀） | `MAP` | 场地类图片 |
| image（其他） | `IMAGE` | 一般图片 |
| chart_bundle | `CHART` | 图表 |
| spreadsheet | `KPI_TABLE` | 指标表格 |
| document | `TEXT_SUMMARY` | 文本摘要 |
| 参考案例聚合 | `CASE_CARD` | 多张图片 + 分析文本 + 来源 |

Asset 模型定义：`db/models/asset.py`

**Step 4 — 自动提取 ProjectBrief**

从素材包中的 `设计建议书大纲` 文档通过正则提取：

- 地理信息：`city`、`province`、`district`、`site_address`
- 建筑类型：关键词匹配（办公 / 住宅 / 酒店 / 商业综合体等）
- 风格偏好：`style_preferences`（现代 / 极简 / 生态 / 科技等）
- 容积率：`far`（数值提取）

### 产出数据模型

| 模型 | 文件 | 说明 |
|------|------|------|
| `MaterialPackage` | `db/models/material_package.py` | `manifest_json`（按条目分组的 logical_keys）、`summary_json`（计数与摘要）、`source_hash` |
| `MaterialItem` × N | 同上 | 每个文件的元数据 + 逻辑键 |
| `Asset` × N | `db/models/asset.py` | 派生资产，含 `asset_type`、`image_url`、`render_role` |
| `ProjectBrief` | — | 项目级元信息 |

### 状态变更

```
Project.status → MATERIAL_READY
```

---

## 3. 阶段二：Brief 文档生成

### 触发

- **API：** `POST /projects/{project_id}/material-packages/{package_id}/regenerate`
- **路由：** `api/routers/material_packages.py` — 第 80 行
- **异步：** 调用 `_outline_worker()` — `api/routers/outlines.py` 第 33 行

### 核心函数

| 函数 | 文件 | 行号 |
|------|------|------|
| `generate_brief_doc()` | `agent/brief_doc.py` | 46 |

### LLM 调用

**输入：**
- System Prompt：模板化注入 building_type、project_name、city、style_preferences
- User Message：素材清单摘要、manifest items、文本摘录

**输出 Schema — `_BriefDocLLMOutput`：**

```json
{
  "brief_title": "演示文稿标题",
  "executive_summary": "200 字项目概述",
  "chapters": [
    {
      "chapter_id": "ch01",
      "title": "章节标题",
      "key_findings": "核心发现",
      "narrative_direction": "叙事方向"
    }
  ],
  "positioning_statement": "差异化价值定位",
  "design_principles": ["方向1", "方向2", "方向3"],
  "recommended_emphasis": {
    "policy_focus": "...",
    "site_advantage": "...",
    "competitive_edge": "...",
    "case_inspiration": "..."
  },
  "narrative_arc": "整体叙事走向"
}
```

### 产出

- `BriefDoc` 记录：`outline_json`（章节结构）+ `narrative_arc_json`（叙事弧线）

---

## 4. 阶段三：大纲生成

### 核心函数

| 函数 | 文件 | 行号 |
|------|------|------|
| `generate_outline()` | `agent/outline.py` | 169 |
| 覆盖率分析 | `agent/outline.py` | 147-166 |
| `expand_requirement()` | `tool/material_resolver.py` | 35 |

### 输入组装

1. 加载 `ProjectBrief`、`BriefDoc`、`MaterialPackage`、`MaterialItem`
2. 加载 PPT 蓝图模板库 — `config/ppt_blueprint.py`（11 种布局原语 + 可重复组）
3. 统计参考案例数量（2-5 个）

### LLM 调用

**System Prompt：** `prompts/outline_system_v2.md`
- 注入 building_type、client_name、city 上下文
- 注入 BriefDoc 的 narrative_arc + positioning_statement

**User Message 包含：**

| XML 标签 | 内容 |
|----------|------|
| `<project_brief>` | building_type / client_name / city / style_preferences |
| `<brief_doc>` | 叙事指导 |
| `<blueprint>` | 40-60 个可用页面模板及其 required_inputs |
| `<reference_count>` | 2-5 个案例页 |
| `<material_package>` | 素材包摘要 + manifest |
| `<material_snippets>` | 素材文本摘录 |

**输出 Schema — `_OutlineLLMOutput`：**

```json
{
  "deck_title": "最终演示标题",
  "total_pages": 35,
  "assignments": [
    {
      "slot_id": "brief-doc-site",
      "slide_no": 5,
      "section": "场地分析",
      "title": "区位与交通",
      "content_directive": "展示场地红线范围与周边交通网络...",
      "asset_keys": ["site.boundary.image", "site.traffic.chart"],
      "layout_hint": "split-h, 左图右文",
      "is_cover": false,
      "is_chapter_divider": false,
      "estimated_content_density": "medium"
    }
  ]
}
```

### 覆盖率分析

在大纲生成后，对每页执行素材覆盖率检查：

1. 通过 `material_resolver.py` 将 `required_input_keys` 展开为正则匹配模式
2. 检查 MaterialItem 是否有匹配项
3. 标记覆盖状态：`complete` / `partial` / `missing`

### 产出

| 字段 | 说明 |
|------|------|
| `spec_json` | `OutlineSpec` — 完整页面规划数组 |
| `coverage_json` | 每页素材覆盖率 |
| `slot_binding_hints_json` | 每页所需输入 + 推荐匹配范围 |
| `deck_title` | 演示文稿标题 |
| `theme` | 从 building_type 推导 |
| `total_pages` | 总页数 |

### 状态变更

```
Outline.status → draft
Project.status → OUTLINE_READY（等待用户确认）
```

---

## 5. 阶段四：大纲确认与素材绑定

### 触发

- **API：** `POST /projects/{project_id}/outline/confirm`
- **路由：** `api/routers/outlines.py` — 第 189 行
- 确认后自动启动 `_compose_render_worker()` 后台线程

### 核心函数

| 函数 | 文件 | 行号 |
|------|------|------|
| `bind_materials()` | `agent/material_binding.py` | 92 |
| `expand_requirement()` | `tool/material_resolver.py` | 35 |
| `find_matching_items()` | `agent/material_binding.py` | — |
| `find_matching_assets()` | `agent/material_binding.py` | — |

### 逐页绑定逻辑

对 Outline 中的每个 `OutlineSlideEntry`：

1. 将 `required_input_keys` 展开为正则模式
2. 查找匹配的 `MaterialItem`（按 logical_key 正则匹配）
3. 查找匹配的 `Asset`（按 logical_key 正则匹配）
4. 计算覆盖率分数：`coverage_score = (required - missing) / required`

### 产出 — `SlideMaterialBinding`（每页一条）

| 字段 | 类型 | 说明 |
|------|------|------|
| `must_use_item_ids` | UUID[] | 匹配到的 MaterialItem ID |
| `derived_asset_ids` | UUID[] | 匹配到的 Asset ID |
| `evidence_snippets` | string[] | 文本证据摘录 |
| `coverage_score` | float | 0.0 – 1.0 |
| `missing_requirements` | string[] | 未匹配的模式 |

### 状态变更

```
Project.status → BINDING
```

---

## 6. 阶段五：幻灯片内容编排（Compose）

### 触发

大纲确认后由 `_compose_render_worker()` 自动执行 — `api/routers/outlines.py` 第 46 行

### 核心函数

| 函数 | 文件 | 行号 | 职责 |
|------|------|------|------|
| `compose_all_slides()` | `agent/composer.py` | 492 | 并发编排所有页面 |
| `_compose_slide_structured()` | `agent/composer.py` | 351 | 结构化模式（v2） |
| `_compose_slide_html()` | `agent/composer.py` | 381 | HTML 直出模式（v3，ADR-006 主流程） |
| `_html_fallback()` | `agent/composer.py` | 438 | HTML 降级模式 |
| `_fallback_layout_spec()` | `agent/composer.py` | 228 | LLM 失败时的兜底布局 |

### 输入

- `Outline`：页面规划
- `VisualTheme`（或默认主题）：视觉参数
- `ProjectBrief`：项目上下文
- 全部 `Asset` 记录：构建 asset_summary 列表
- 每页的 `SlideMaterialBinding`：绑定信息

### LLM 调用 — HTML 模式（v3，目标主流程）

**System Prompt：** `prompts/composer_system_v3.md`

**User Message 与 v2 共用核心上下文：**

| XML 标签 | 内容 |
|----------|------|
| `<visual_theme>` | style_keywords / cover_layout_mood / density / color_fill / generation_hint |
| `<outline_entry>` | 当前页需求 |
| `<project_brief>` | 项目上下文 |
| `<slide_material_binding>` | binding_id / derived_asset_ids / evidence_snippets / missing_requirements |
| `<available_assets>` | 已过滤的资产摘要（仅绑定中的 derived_asset_ids） |

**输出 Schema — `_ComposerHTMLOutput`：**

```json
{
  "slide_no": 5,
  "body_html": "<div class=\"slide-root\">...</div>",
  "asset_refs": ["asset:550e8400-e29b-41d4-a716-446655440000"],
  "content_summary": "区位交通分析页，左侧地图主视觉，右侧关键结论"
}
```

ADR-006 后,主流程应显式传 `ComposerMode.HTML`。HTML 模式允许 Composer 直接使用 CSS Grid/Flexbox/SVG、满版图、几何色块和浮层注释来增强视觉设计。

### LLM 调用 — 结构化模式（v2 fallback/debug）

**System Prompt：** `prompts/composer_system_v2.md`

**User Message：**

| XML 标签 | 内容 |
|----------|------|
| `<visual_theme>` | style_keywords / cover_layout_mood / density / color_fill / generation_hint |
| `<outline_entry>` | 当前页需求 |
| `<project_brief>` | 项目上下文 |
| `<slide_material_binding>` | binding_id / derived_asset_ids / evidence_snippets / missing_requirements |
| `<available_assets>` | 已过滤的资产摘要（仅绑定中的 derived_asset_ids） |

**输出 Schema — `_ComposerLLMOutput`：**

```json
{
  "slide_no": 5,
  "section": "场地分析",
  "title": "区位与交通",
  "is_cover": false,
  "is_chapter_divider": false,
  "primitive_type": "split-h",
  "primitive_params": { "ratio": "6:4" },
  "region_bindings": [
    {
      "region_id": "left",
      "blocks": [
        {
          "block_id": "visual",
          "content_type": "image",
          "content": "asset:550e8400-e29b-41d4-a716-446655440000",
          "emphasis": "normal"
        }
      ]
    },
    {
      "region_id": "right",
      "blocks": [
        {
          "block_id": "title",
          "content_type": "heading",
          "content": "区位优势分析",
          "emphasis": "highlight"
        },
        {
          "block_id": "body",
          "content_type": "bullet-list",
          "content": ["地铁 3 号线直达", "距市中心 15 分钟"],
          "emphasis": "normal"
        }
      ]
    }
  ],
  "visual_focus": "left"
}
```

**11 种布局原语（primitive_type）：**

| 原语 | 说明 |
|------|------|
| `full-bleed` | 全幅背景图 + 文字叠加 |
| `split-h` | 水平两栏 |
| `split-v` | 垂直两栏 |
| `single-column` | 单列居中 |
| `grid` | 多列网格 |
| `hero-strip` | 大图横条 |
| `sidebar` | 侧边栏 |
| `triptych` | 三联 |
| `overlay-mosaic` | 覆盖拼贴 |
| `timeline` | 时间线 |
| `asymmetric` | 不对称 |

**13 种内容块类型（content_type）：**

heading / body-text / image / chart / map / table / kpi-value / bullet-list / quote / caption / icon-label / tag-cloud / divider

### LLM 输出转换

LLM 的 `_ComposerLLMOutput` 被转换为 `LayoutSpec`（定义于 `schema/visual_theme.py`）：
- 解析 primitive_type + params → `LayoutPrimitive` 对象
- 映射 ContentBlocks → RegionBindings
- 注入资产引用和证据摘录
- 校验失败时降级为 single-column 布局

### 容错机制

- LLM 调用失败 → `_fallback_layout_spec()`：生成 single-column 兜底布局
- HTML 模式失败 → `_html_fallback()`：最小化 HTML 输出
- 保证每一页都可渲染，不会阻塞后续流程

### 产出 — `Slide`（每页一条）

| 字段 | 说明 |
|------|------|
| `spec_json` | LayoutSpec JSON（结构化）或 `{html_mode: true, body_html: "..."}` |
| `source_refs_json` | 引用的 Asset ID 列表 |
| `evidence_refs_json` | 文本证据摘录 |
| `slide_no` / `section` / `title` | 页面基本信息 |
| `purpose` / `key_message` | 内容语义 |

### 状态变更

```
Slide.status → spec_ready
Project.status → SLIDE_PLANNING
```

---

## 7. 阶段六：视觉主题生成（可选）

### 核心函数

| 函数 | 文件 | 行号 |
|------|------|------|
| `generate_visual_theme()` | `agent/visual_theme.py` | 46 |

### LLM 调用

**System Prompt：** `prompts/visual_theme_system.md`

**输入：** building_type、client_name、style_preferences、案例分析中的 dominant_styles

**输出 — `VisualTheme`**（定义于 `schema/visual_theme.py` 第 70 行）：

```json
{
  "colors": {
    "primary": "#1A365D",
    "secondary": "#2D3748",
    "accent": "#ED8936",
    "background": "#FFFFFF",
    "surface": "#F7FAFC",
    "text_primary": "#1A202C",
    "text_secondary": "#718096",
    "border": "#E2E8F0",
    "overlay": "rgba(0,0,0,0.6)",
    "cover_bg": "#1A365D"
  },
  "typography": {
    "font_heading": "思源黑体",
    "font_body": "思源宋体",
    "font_en": "Inter",
    "base_size": 24,
    "scale_ratio": 1.333,
    "heading_weight": 700,
    "body_weight": 400,
    "line_height_body": 1.6,
    "line_height_heading": 1.2,
    "letter_spacing_label": "0.05em"
  },
  "spacing": {
    "base_unit": 8,
    "safe_margin": 60,
    "section_gap": 40,
    "element_gap": 16,
    "density": "normal"
  },
  "decoration": {
    "use_divider_lines": true,
    "divider_weight": 1,
    "color_fill_usage": "accent-blocks",
    "border_radius": 4,
    "image_treatment": "rounded",
    "accent_shape": "line",
    "background_texture": "none"
  },
  "cover": {
    "layout_mood": "bold-dark",
    "title_on_dark": true,
    "show_brief_metrics": true
  },
  "style_keywords": ["现代", "专业", "沉稳"],
  "generation_prompt_hint": "..."
}
```

---

## 8. 阶段七：渲染（HTML → PNG）

### 核心函数

| 函数 | 文件 | 职责 |
|------|------|------|
| `render_slide_html()` | `render/engine.py` | 单页 HTML 生成 |
| `generate_theme_css()` | `render/engine.py` | VisualTheme → CSS 变量 |
| `_render_layout()` | `render/engine.py` | 按 primitive_type 选择布局渲染 |
| `_render_block()` | `render/engine.py` | 渲染单个 ContentBlock |
| `screenshot_slides_batch()` | `render/exporter.py` (line 81) | 批量截图 |

### HTML 生成流程

对每个 Slide：

1. **CSS 生成** — `generate_theme_css()` 将 VisualTheme 转为 CSS 自定义属性
2. **模式分支**：
   - HTML 模式：`render_slide_html_direct()` sanitize `body_html`,替换 `asset:{id}`,注入 theme CSS
   - structured 模式：`render_slide_html()` 调用 `_render_layout()` 根据 `primitive_type` 生成 HTML 结构
3. **structured 布局渲染** — `_render_layout()` 支持：
   - `full-bleed`：背景图 + 文字覆盖层
   - `split-h`：左右两区域 flex 布局
   - `grid`：CSS Grid 多列
   - 其他共 11 种布局（见阶段五表格）
4. **内容块渲染** — structured 模式下 `_render_block()` 处理每个 ContentBlock：

   | content_type | HTML 输出 |
   |-------------|-----------|
   | heading | `<h1 class="block-heading">` |
   | body-text | `<p class="block-body-text">` |
   | image | `<img src="...">` |
   | chart | `<img src="...">` |
   | table | `<table>` 或 markdown → HTML |
   | bullet-list | `<ul><li>` + accent 圆点 |
   | kpi-value | 大号数字展示 |

5. **资产注入** — 将 `asset:uuid` 引用解析为实际的 `image_url`
6. **输出** — 完整 HTML 页面，视口 1920×1080

### 截图批处理

**技术栈：** Playwright Chromium headless

```
Playwright Browser (单实例)
  ├── Tab 1 → slide_01.html → screenshot → slide_01.png
  ├── Tab 2 → slide_02.html → screenshot → slide_02.png
  ├── Tab 3 → slide_03.html → screenshot → slide_03.png
  └── Tab 4 → slide_04.html → screenshot → slide_04.png
  ... (最多 4 并发)
```

**流程：** HTML 写入临时文件 → `file://` 导航 → 截图 PNG（1920×1080）

**输出路径：** `tmp/e2e_output/slides/slide_01.png`、`slide_02.png`、...

### 数据更新

- `Slide.html_content` ← HTML 内容（上限 65535 字符）
- `Slide.screenshot_url` ← PNG 路径
- `Slide.status` → `rendered`

### 状态变更

```
Project.status → REVIEWING
```

---

## 9. 阶段八：审查与修复（可选）

### 触发

- **API：** `POST /projects/{project_id}/review`
- **路由：** `api/routers/render.py` — 第 50 行
- **Celery 任务：** `review_slides` — `tasks/review_tasks.py`

### 审查层

| 层 | 名称 | 检查内容 |
|----|------|---------|
| `rule` | 布局规则 | 文字溢出、图片宽高比、间距合规 |
| `semantic` | 内容语义 | 信息清晰度、视觉层次、一致性 |
| `vision` | 截图视觉缺陷 | 杂乱、模糊、文字压背景、空白浪费 |
| `design_advisor` | 设计评分 | 配色、排版、布局、视觉焦点、完成度 |

### 修复流程

```
发现问题
  → 标记 Slide.status = REPAIR_NEEDED
  → HTML 模式:recompose_slide_html() 改写 body_html
  → structured 模式:修复 LayoutSpec
  → 重新调用 render + screenshot()
  → 再次 review
```

ADR-006 后,Design Advisor 低分也可触发返工:例如 `overall_score < 7.0`、`focal_point < 6.5`、重点页出现 `D012`。审查规则详见 `docs/11_review_rules.md` 和 `docs/23_vision_review_v2_design_advisor.md`。

---

## 10. 阶段九：PDF 导出

### 触发

- **API：** `POST /projects/{project_id}/export`
- **路由：** `api/routers/exports.py` — 第 80 行
- **后台线程：** `_export_worker()` — 第 23 行

### 核心函数

| 函数 | 文件 | 行号 |
|------|------|------|
| `_export_worker()` | `api/routers/exports.py` | 23 |
| `compile_pdf()` | `render/exporter.py` | 126 |

### 处理流程

```
1. 按 slide_no 顺序加载所有 Slide
2. 每页获取 PNG:
   ├── 优先: 从磁盘读取已有 PNG (tmp/e2e_output/slides/slide_XX.png)
   └── 降级: 调用 screenshot_slide() 即时生成

3. 拼合 PDF:
   ├── 主路径 (Playwright):
   │     所有 PNG → data:image/png;base64 URL
   │     → 嵌入 HTML (每张图一页, page-break-after: always)
   │     → Playwright page.pdf() → PDF bytes
   │
   └── 降级路径 (Pillow PIL):
         纯 Python 拼接 PNG → PDF

4. 保存: tmp/e2e_output/export/{project_id}.pdf
```

### 状态变更

```
Project.status → EXPORTED
```

---

## 11. 核心数据流总结

### 数据模型链路

```
本地文件
  ↓
MaterialItem          文件目录（logical_key + kind + 内容摘录）
  ↓
Asset                 派生资产（asset_type + image_url + render_role）
  ↓
SlideMaterialBinding  素材绑定（每页 → 具体资产 ID + 证据文本）
  ↓
Slide.spec_json       布局规格（LayoutSpec: primitive + regions + blocks）
  ↓
Slide.html_content    渲染 HTML
  ↓
Slide.screenshot_url  截图 PNG
  ↓
PDF                   最终输出
```

### 内容语义链路

```
ProjectBrief          项目元信息（类型 / 地点 / 风格）
  ↓
BriefDoc              叙事框架（章节 / 定位 / 设计原则）
  ↓
Outline               页面结构（slot / title / directive / asset_keys）
  ↓
Slide                 内容编排（布局 + 文本 + 资产引用）
```

---

## 12. 项目状态生命周期

```
INIT
  → MATERIAL_READY      素材包摄入完成
  → OUTLINE_READY       大纲生成完成（等待用户确认）
  → BINDING             素材绑定中
  → SLIDE_PLANNING      幻灯片编排中
  → ASSET_GENERATING    内容生成中
  → REVIEWING           审查中
  → RENDERING           最终渲染中
  → EXPORTED            PDF 就绪
```

---

## 13. 关键文件索引

### 入口与路由

| 文件 | 职责 |
|------|------|
| `main.py` | FastAPI 服务入口，注册 8 个 Router |
| `api/routers/material_packages.py` | 素材包 API |
| `api/routers/outlines.py` | 大纲 API + compose_render 工作线程 |
| `api/routers/render.py` | 渲染与审查 API |
| `api/routers/exports.py` | PDF 导出 API |

### Agent（LLM 调用层）

| 文件 | 职责 |
|------|------|
| `agent/brief_doc.py` | Brief 文档生成 |
| `agent/outline.py` | 大纲生成 |
| `agent/material_binding.py` | 素材绑定 |
| `agent/composer.py` | 幻灯片内容编排 |
| `agent/visual_theme.py` | 视觉主题生成 |

### 工具与管道

| 文件 | 职责 |
|------|------|
| `tool/material_pipeline.py` | 素材包摄入全流程 |
| `tool/material_resolver.py` | logical_key 匹配与展开 |

### 渲染与导出

| 文件 | 职责 |
|------|------|
| `render/engine.py` | LayoutSpec → HTML 渲染引擎 |
| `render/exporter.py` | Playwright 截图 + PDF 编译 |

### 数据模型与配置

| 文件 | 职责 |
|------|------|
| `db/models/material_package.py` | MaterialPackage / MaterialItem 模型 |
| `db/models/asset.py` | Asset 模型 |
| `schema/visual_theme.py` | VisualTheme / LayoutSpec / LayoutPrimitive |
| `config/ppt_blueprint.py` | PPT 蓝图模板库（11 种布局原语） |
| `config/settings.py` | 数据库 / LLM / OSS 配置 |
| `config/llm.py` | LLM 客户端配置 |

### Prompt 模板

| 文件 | 用途 |
|------|------|
| `prompts/outline_system_v2.md` | 大纲生成 System Prompt |
| `prompts/composer_system_v2.md` | 内容编排 System Prompt |
| `prompts/visual_theme_system.md` | 视觉主题 System Prompt |

### 异步任务

| 文件 | 职责 |
|------|------|
| `tasks/review_tasks.py` | Celery 审查任务 |
