---
date: 2026-05-01
status: Draft
owner: superxiaoyin
assignee: TBD
---

# Task Brief：Template Pack 渲染管线（Templates × VisualTheme 融合）

## 0. Progress Update（2026-05-04）

本 brief 的 PR-1 / PR-2 / PR-3 / PR-4a 已进入可跑状态，并完成一次 **41 页 real-LLM + RunningHub + template mode** 全量验证：

```text
output_dir: D:\projects\PPT_Agent\tmp\template_full_real_verify\run_20260504T094923Z
mode: real-llm
generate_visual_theme: ok
generate_outline: ok (41 pages)
concept_render: ok (initial total=9, generated=8, placeholders=1; 2026-05-05 strict retry generated=9, placeholders=0, reused=8)
compose_slides: ok (41 slides; template=40, html=1)
template_quality: ok (critical_issues=0)
render_and_review: ok (41 rendered)
export_pdf: ok (deck.pdf)
```

### 已解决的问题

- **任务提示词泄露**：`template_quality_report.json` 未发现 `[Material Package E2E]` / `调用 Nanobanana` / `联网搜索` 等 prompt marker；`slides_spec.json` 未再把任务说明当正文输出。
- **内容未参考素材/大纲**：`brief.design_outline` 现在优先从 `source_path` 读取完整 markdown，而不是仅使用 Asset.summary 的前 500 字；文化页、场地综合页、项目定位页已能从大纲对应章节抽取内容。
- **政策页重复**：`policy-1 / policy-2` 按真实条目分页，不再在第二页回退第一页内容。
- **经济/场地资产串页**：`economic-1/2/3`、`site-location-1..4`、`poi-analysis` 已按 raw slot id 和 logical_key 选择素材；经济三页分别使用城市经济、产业发展、消费水平图表。
- **POI chart 物化**：当 `site.poi.table` 的 `data_json.preview_rows` 缺失时，Composer 会从资产 `source_path` 只读解析 XLSX 预览行，再生成 chart PNG。
- **概念效果图接入**：`concept-aerial-*` 使用 `concept_scheme`；`concept-perspective-*` 使用 `image_grid` 展示 ext/int 两张图。真实验证中 8/9 张图来自 RunningHub 并进入 slide。
- **字号与模板密度第一轮调整**：全局字号、`policy_list`、`content_bullets`、`image_grid`、`table` 已上调；Chrome 截图和 PDF 在全量 E2E 中正常产出。

### 当前仍未达标

- **视觉密度仍不足**：真实 vision review 仍有 28/41 页 P2，主要为 `V007` 大面积留白；地图页另有 `V001/V004` 图内标注拥挤、文字压复杂背景。
- **`competitor-web` 仍是 HTML 模式**：Slide 22 是 `mode=html`，因为联网搜索和 TABLE 模板接入尚未完成；这不是 generic fallback，template quality 没有 critical issue。
- **概念大图文字可读性**：Slide 31/34/37 的 `concept_scheme` 文案叠在复杂背景上，review 报 `V004`。

### 关键实测抽查

- Slide 4/5：政策 1/2 与 2/2 已拆分为不同政策条目。
- Slide 9：文化特征来自大纲“武当飞檐曲线 / 车城齿轮元素 / 山城肌理线条”。
- Slide 10/11/12：分别绑定城市经济、产业发展、消费水平 chart。
- Slide 14/15/16/17：分别绑定场地四至、外部交通、枢纽/基础设施、区域开发相关资产。
- Slide 18：`site.poi.table` 已物化为 `tmp\chart_materialized\slide_18_46b652385c.png`。
- Slide 27：项目定位来自大纲“综合定位 / 客群定位 / 功能配比”等。
- Slide 31/34/37：鸟瞰图均来自 RunningHub asset。
- Slide 32/35：外/内人视图均来自 RunningHub asset。
- Slide 38：外人视图和内人视图均来自 RunningHub；2026-05-05 已重渲染该页并重建 `deck.pdf`。

## 1. Goal

把 [d:\projects\liuzong\PPT-maker\templates\minimalist_architecture\](../../../../liuzong/PPT-maker/templates/minimalist_architecture/) 这一套已经成熟的、theme-token 驱动的 11 组件 Jinja2 模板，作为 Composer 的**第三种产出模式（template mode）**接入主链路，覆盖 manus.md 40 页中约 90% 可模板化的页面；少数关键创意页继续走现有 v3 (html_free) / v2 (layout_spec) 路径。

**完成标志**：

- `scripts/material_package_e2e.py test_material/project1 --real-llm` 跑全量时，蓝图中标了 `template_component` 的页（≥ 30 页）由 Jinja2 模板渲染，剩余页由 v3 兜底，PDF 仍能完整产出且视觉一致。
- 第七章 9 页（concept-aerial / ext / int × 3 方案）由 `concept_scheme` 模板直接消费 `concept_render` 已落地的 9 个 `Asset`，零新增数据装配代码。
- 项目主题色 / 字体 / 章节口音色由 `agent/visual_theme.py` 一次生成，全局应用于 11 个模板组件，且与 BriefDoc 大纲调性匹配（不是写死）。

---

## 2. Context

### 2.1 现状摘要

- **Composer 双模式**已稳定（[ADR-004](../decisions/ADR-004-html-mode-vision-only.md)）：v3 直出 `body_html`（默认）/ v2 输出 `LayoutSpec` JSON 经 [render/engine.py:_render_layout](../../../render/engine.py) 渲染。
- **VisualTheme** 是项目级唯一主题真源（[schema/visual_theme.py:VisualTheme](../../../schema/visual_theme.py#L70-L89)），由 [agent/visual_theme.py:generate_visual_theme](../../../agent/visual_theme.py) LLM 生成；CSS 变量经 [render/engine.py:generate_theme_css](../../../render/engine.py#L92) 注入。
- **PPT_BLUEPRINT** ([config/ppt_blueprint.py](../../../config/ppt_blueprint.py)) 已把 manus.md 40 页代码化为 `PageSlot` 列表，含 `layout_hint`（自由字符串）和 `generation_methods`（`NANOBANANA / WEB_SEARCH` 部分未实装）。
- **concept_render** ([agent/concept_render.py](../../../agent/concept_render.py)) 已完成，9 个 Asset 的 `image_url / proposal.name / design_idea / view label` 字段恰好对齐 [concept_scheme.html.j2](../../../../liuzong/PPT-maker/templates/minimalist_architecture/components/concept_scheme.html.j2) 的 `data.image / scheme_name / view_label / idea / analysis` —— **零阻力对接**。
- **chart_generation** ([tool/asset/chart_generation.py](../../../tool/asset/chart_generation.py)) 已能用 matplotlib 把 `[{label, value}]` 渲染成 PNG，可作为"chart 物化"步骤的执行器。
- **MaterialItem.logical_key** 体系已稳定（见 [tool/material_pipeline.py](../../../tool/material_pipeline.py)），`site.boundary.image / economy.*.chart.{N} / reference.case.{N}.thumbnail` 等命名已就绪，模板组件可直接按 key 索引素材。

### 2.2 templates 现状

11 个组件已就绪：`cover / toc / transition / policy_list / chart / table / image_grid / content_bullets / case_card / concept_scheme / ending`。完整文件树见 [d:\projects\liuzong\PPT-maker\templates\minimalist_architecture\](../../../../liuzong/PPT-maker/templates/minimalist_architecture/)。

但**直接照抄会有 5 类问题**：

| # | 问题 | 例 |
|---|------|---|
| P1 | 总页数 / 章节数硬编码 | [_chrome.html.j2:13](../../../../liuzong/PPT-maker/templates/minimalist_architecture/components/_chrome.html.j2#L13) `/ 40`；[toc.html.j2:42](../../../../liuzong/PPT-maker/templates/minimalist_architecture/components/toc.html.j2#L42) 写死 4 个页码区间 |
| P2 | 双套主题系统冲突 | 模板有自己的 [theme.json](../../../../liuzong/PPT-maker/templates/minimalist_architecture/theme.json)，与 VisualTheme 不通名 |
| P3 | 内容长度无约束 | LLM 输出 `lede` 200 字会撑爆 [content_bullets.html.j2](../../../../liuzong/PPT-maker/templates/minimalist_architecture/components/content_bullets.html.j2) |
| P4 | chart 组件接口与现有素材形态不匹配 | [chart.html.j2:41](../../../../liuzong/PPT-maker/templates/minimalist_architecture/components/chart.html.j2#L41) 只吃 image path，但 `site.poi.table` 是 structured_data |
| P5 | 部分元数据写死 | [cover.html.j2:72](../../../../liuzong/PPT-maker/templates/minimalist_architecture/components/cover.html.j2#L72) `lbls = ['BUILDING','GROSS AREA','FAR']`；[ending.html.j2:62](../../../../liuzong/PPT-maker/templates/minimalist_architecture/components/ending.html.j2#L62) 写死 `2026` 和 `ARCHITECT AGENT` |

本 brief 解决这 5 类问题的同时，把模板挂进 Composer。

---

## 3. Out of Scope

- **不重写 v3 / v2 路径**。template mode 是**新增**的第三模式，旧路径不动。回退路径明确。
- **不引入 logo 图像生成、联网搜索**。`generation_methods=[NANOBANANA / WEB_SEARCH]` 的页继续按现状降级（占位 / 跳过）。
- **不做交互式 HTML 导出**。模板里的导航 JS（[base.html.j2:46-74](../../../../liuzong/PPT-maker/templates/minimalist_architecture/components/../base.html.j2#L46-L74)）默认禁用，PDF 渲染不需要。
- **不做模板可视化编辑器**。模板修改靠改文件 + git。
- **本期只做 1 个 pack（minimalist_architecture）**。第 2、3 个 pack 与"LLM 选 pack"机制列入下一轮 brief（占位字段先建好）。
- **不动 Critic / Review 路径**。template mode 的产物在 spec_json 里有明确 marker，Critic 按现有 vision-only 路径处理（[ADR-004](../decisions/ADR-004-html-mode-vision-only.md)）。

---

## 4. Constraints

### 架构

- Composer 出口扩为三模式：`template / html_free / layout_spec`。优先级：`template`（若 PageSlot.template_component 不空）→ `html_free`（默认）→ `layout_spec`（兜底）。
- **template mode 永远不让 LLM 产 HTML/CSS**，只产符合 `SlideData` schema 的结构化 JSON。
- **VisualTheme 是唯一主题真源**。模板 `theme.json` 删除；模板的 `var(--accent) / var(--ink)` 等改名为 `generate_theme_css` 已有的 `var(--color-accent) / var(--color-text-primary)` 等。
- **40 页不写死**。`total_pages / page_ranges / 章节数 / section_colors` 全部由 `SlidePlan` 装配产生并以 context 注入模板。
- **不新增 LLM 调用**。template mode 复用 Composer 现有的 per-slide LLM 调用，只把 prompt 的输出 schema 从 "body_html 字符串" 切到 "SlideData JSON"。

### 数据 / 长度

- 11 个 `SlideData` 子模型用 Pydantic v2，字段级 `max_length / min_length / max_items / min_items` 强约束。
- LLM 输出 → Pydantic 校验失败 → **重试一次**（prompt 中回填超长字段实际长度让 LLM 自己截）→ 仍失败 → 调 `truncate_to_schema(data, schema)` 兜底 + log warning。
- 长度上限的具体数值**不放代码默认值**，放在 `config/slide_data_limits.py` 单文件，便于设计师和工程师各自调整。

### 主题（你的第 3 / 5 点）

- VisualTheme 输入扩 `BriefDoc.outline_json`（章节 + recommended_emphasis），LLM 在生成 palette 时**显式说明每个章节的口音色映射**。
- VisualTheme 新增字段：
  - `section_colors: list[str]` —— 长度等于章节数，由 LLM 生成，模板 `data-section="0N"` 选择器动态匹配。
  - `template_pack: str = "minimalist_architecture"` —— 本期固定单值，预留扩展。
- "LLM 选 pack" 不在本期实现，但 schema 字段必须留好，避免下一轮 brief 时再改 ORM。

### 失败降级

- **任意模板渲染失败**（Jinja2 异常 / 校验失败 / 静态文件缺失）→ 自动回退到 `html_free` 模式重跑这一页 → 仍失败 → 占位灰底页（复用 [tool/image_gen/placeholder.py](../../../tool/image_gen/placeholder.py)）。
- **chart 物化失败**（matplotlib 异常 / 数据解析失败）→ chart 组件渲染占位灰格 + "图表生成失败" 文字，不阻塞整页。
- **任何降级路径**必须在 `Slide.error_message` 留痕，PDF 仍能产出。

### 环境

- 不新增 .env 配置。本改动是纯本地渲染管线扩展。
- 测试 fixture 放 `tests/fixtures/slide_data/` 下，每个组件一个 JSON（含合规与超长两份）。

---

## 5. Acceptance Criteria

### 必达

- [ ] **Templates 落库**：`templates/packs/minimalist_architecture/` 拷入项目内，11 组件 + base.j2 + viewport-base.css 完整；`theme.json` 已删除。
- [ ] **5 类硬编码已消**：page 总数 / 章节数 / 章节色 / 元数据标签 / 默认年份等全部从 context 注入。
- [ ] **CSS 变量已对齐 VisualTheme**：模板 CSS 不再出现 `var(--accent) / var(--ink) / var(--bg)` 等旧名；改为 `var(--color-accent) / var(--color-text-primary) / var(--color-bg)` 等 `generate_theme_css` 已产出的变量名。
- [ ] **schema 落地**：`schema/slide_data.py` 含 11 个 `*Data` 子模型 + 长度约束 + `SlideDataUnion` 判别；`schema/slide_plan.py` 含 `SlidePlan / SlidePlanSection / SlidePlanEntry`。
- [ ] **SlidePlan 装配 agent**：`agent/slide_plan.py` 纯函数，输入 `(Outline, ProjectBrief)` → 输出 `SlidePlan`，覆盖 `total_pages / sections[*].page_range / 每页的 component_type`。单测覆盖 30 页 / 38 页 / 41 页三种规模。
- [ ] **PageSlot 字段扩展**：`schema/page_slot.py` 加 `template_component: ComponentType | None`，[config/ppt_blueprint.py](../../../config/ppt_blueprint.py) 中所有 PageSlot 显式标注。
- [ ] **Composer template-mode**：[agent/composer.py](../../../agent/composer.py) 加 `compose_template_slide(entry, brief_doc, assets, theme)` 路径；优先级判断 + 失败回退到 html_free 路径已实现。
- [ ] **VisualTheme 扩展**：`section_colors` 和 `template_pack` 字段已加；DB 迁移 `006_visual_theme_section_colors.py` 已加；[agent/visual_theme.py](../../../agent/visual_theme.py) prompt 已更新让 LLM 看 BriefDoc 章节并产 section_colors。
- [ ] **Render 分支**：[render/engine.py](../../../render/engine.py) 加 `render_via_jinja(slide, plan, theme)`；按 `slide.spec_json["mode"] == "template"` 分发；其余路径不变。
- [ ] **chart 物化**：`agent/chart_materialize.py` 新建，把 `ChartData.chart_spec` 喂 [tool/asset/chart_generation.py](../../../tool/asset/chart_generation.py)，落 PNG 到 `Asset` 表，回填 `ChartData.chart_path`；color_scheme 取自 VisualTheme.colors。
- [ ] **concept_scheme 端到端**：`scripts/material_package_e2e.py` 第 29-37 页用 template mode 渲染 9 张 concept 图，PDF 中视觉与 v3 路径无回退。
- [ ] **回退验证**：故意把某 template 改坏 → 该页能优雅退到 html_free → PDF 仍能产出 + Slide.error_message 有记录。
- [ ] **测试**：
  - 单元：每个 SlideData schema 校验 + 截断兜底（22 个 case）
  - 单元：SlidePlan 装配（3 个 case）
  - 单元：chart_materialize（mock matplotlib，2 个 case）
  - 集成：每个组件 fixture → render → 截图（11 个 case）
  - E2E：smoke `--max-slides 5` 跑通 template mode

### 文档

- [ ] [GLOSSARY.md](../GLOSSARY.md) 加：`Template Pack / SlideData / SlidePlan / Component Type / Chart Materialize`
- [ ] [STATUS.md](../STATUS.md) "能跑什么" 加 template mode 渲染
- [ ] [TODO.md](../TODO.md) 加 P1 项："第 2、3 个 template_pack" 和 "LLM 选 pack 机制"
- [ ] [CHANGELOG.md](../CHANGELOG.md) 追加条目
- [ ] ADR-006 写定（见 [decisions/ADR-006-template-pack-rendering.md](../decisions/ADR-006-template-pack-rendering.md)）

---

## 6. Suggested Approach

### 6.1 总体流水

```
                                  ┌── template_component ≠ None ─→ template mode
                                  │     (LLM → SlideData JSON)
PPT_BLUEPRINT.PageSlot ───────────┤
                                  ├── default ───────────────────→ html_free (v3)
                                  │     (LLM → body_html)
                                  └── fallback ──────────────────→ layout_spec (v2)

Outline ─→ SlidePlan ─→ Composer ─→ Slide.spec_json ─→ render/engine.py ─→ HTML
            ↑                                            │
            └── total_pages, sections, page_ranges       ├─ mode=template → render_via_jinja
                                                         ├─ mode=html_free → 现有路径
                                                         └─ mode=layout_spec → 现有路径
                                                                ↓
                                                         Playwright → PNG → PDF
```

### 6.2 文件改动清单

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `templates/packs/minimalist_architecture/` | 新建（拷入 + 改造） | 11 组件 + base.j2 + viewport-base.css；删除 theme.json |
| `templates/packs/minimalist_architecture/base.html.j2` | 改 | CSS 变量改用 `--color-*`；接收 `theme_css / total_pages / interactive` 等 context |
| `templates/packs/minimalist_architecture/components/_chrome.html.j2` | 改 | `/ 40` → `/ {{ total_pages }}` |
| `templates/packs/minimalist_architecture/components/cover.html.j2` | 改 | meta 标签从 context 取；`year` 从 context |
| `templates/packs/minimalist_architecture/components/toc.html.j2` | 改 | `page_ranges` 从 entries 取 |
| `templates/packs/minimalist_architecture/components/ending.html.j2` | 改 | 署名 / 年份从 context |
| `templates/packs/minimalist_architecture/components/chart.html.j2` | 改 | 仍只接 `chart_path`，但 fallback 占位文案改为 "图表生成失败 / 待补充" 区分 |
| `templates/packs/minimalist_architecture/viewport-base.css` | 改 | section_colors 不再写死 4 个，改为模板循环生成 |
| `schema/slide_data.py` | 新建 | 11 个 `*Data` Pydantic 模型 + `SlideDataUnion` |
| `schema/slide_plan.py` | 新建 | `SlidePlan / SlidePlanSection / SlidePlanEntry` |
| `schema/page_slot.py` | 改 | 加 `template_component: ComponentType \| None` 字段 |
| `schema/visual_theme.py` | 改 | `VisualTheme` 加 `section_colors / template_pack` |
| `config/ppt_blueprint.py` | 改 | 41 个 PageSlot 全部标注 `template_component` |
| `config/slide_data_limits.py` | 新建 | 集中放各组件长度上限 |
| `agent/slide_plan.py` | 新建 | 纯函数：`(Outline, ProjectBrief) → SlidePlan` |
| `agent/composer.py` | 改 | 加 `compose_template_slide`；mode 判定 + 回退 |
| `agent/visual_theme.py` | 改 | 输入加 BriefDoc；prompt 加 section_colors 要求 |
| `agent/chart_materialize.py` | 新建 | `ChartData.chart_spec` → matplotlib → Asset 表 → 回填 `chart_path` |
| `render/engine.py` | 改 | 加 `render_via_jinja`；按 `mode` 分发 |
| `render/jinja_env.py` | 新建 | Jinja2 Environment 单例 + `embed_image` filter + 模板路径解析 |
| `db/migrations/006_visual_theme_section_colors.py` | 新建 | VisualTheme 加列 |
| `prompts/composer_template_mode.md` | 新建 | template mode 的 LLM 系统 prompt（含 schema） |
| `prompts/visual_theme_v2.md` | 改 | 加章节口音色生成要求 |
| `tests/unit/test_slide_data_schemas.py` | 新建 | 22 case |
| `tests/unit/test_slide_plan.py` | 新建 | 3 case |
| `tests/unit/test_chart_materialize.py` | 新建 | 2 case mock |
| `tests/integration/test_template_render.py` | 新建 | 11 组件 fixture → HTML |
| `tests/integration/test_composer_template_mode.py` | 新建 | 端到端 single slide |
| `scripts/material_package_e2e.py` | 改 | 默认 enable template mode；加 `--no-template-mode` 开关 |

### 6.3 SlideData schema 设计（11 组件）

放在 `schema/slide_data.py`。所有字段 `max_length / max_items` 默认值从 `config/slide_data_limits.py` 读取（这里给的是建议起点）。

```python
# config/slide_data_limits.py
LIMITS = {
    "cover": {"title": 24, "slogan": 80, "en": 60, "meta_lines": 3},
    "toc":   {"title": 24, "entry_label": 18, "entry_en": 40, "entries_max": 6},
    "transition": {"title": 18, "subtitle_en": 60, "sub": 40},
    "policy_list": {"policies_max": 5, "title": 40, "content": 120, "impact": 60},
    "chart": {"title": 28, "bullets_max": 4, "bullet": 80},
    "table": {"title": 28, "headers_max": 6, "rows_max": 8, "cell": 36, "note": 80},
    "image_grid": {"title": 28, "images_max": 4, "caption": 30, "footer_caption": 140},
    "content_bullets": {"title": 28, "lede": 140, "bullets_max": 6, "bullet_title": 18, "bullet_body": 90},
    "case_card": {"title": 28, "case_name": 32, "scale": 60, "highlights": 100, "inspiration": 100},
    "concept_scheme": {"scheme_name": 16, "view_label": 24, "idea": 40, "analysis": 220},
    "ending": {"title": 16, "en": 40, "tagline": 80},
}
```

```python
# schema/slide_data.py（节选）
from typing import Annotated, Literal, Union
from pydantic import BaseModel, Field, StringConstraints
from config.slide_data_limits import LIMITS as L

class CoverData(BaseModel):
    component_type: Literal["cover"] = "cover"
    title: Annotated[str, StringConstraints(max_length=L["cover"]["title"])]
    slogan: Annotated[str, StringConstraints(max_length=L["cover"]["slogan"])]
    en: Annotated[str, StringConstraints(max_length=L["cover"]["en"])]
    meta_lines: list["MetaLine"] = Field(max_length=L["cover"]["meta_lines"])
    logo_asset_id: UUID | None = None
    year: int

class ContentBulletsData(BaseModel):
    component_type: Literal["content_bullets"] = "content_bullets"
    title: str = Field(max_length=L["content_bullets"]["title"])
    lede: str | None = Field(default=None, max_length=L["content_bullets"]["lede"])
    bullets: list["Bullet"] = Field(min_length=3, max_length=L["content_bullets"]["bullets_max"])
    illustration_asset_id: UUID | None = None

class ChartData(BaseModel):
    component_type: Literal["chart"] = "chart"
    title: str = Field(max_length=L["chart"]["title"])
    bullets: list[str] = Field(min_length=1, max_length=L["chart"]["bullets_max"])
    # OneOf：上游已是图就给 path，否则给 spec 让 chart_materialize 物化
    chart_path: str | None = None
    chart_spec: ChartGenerationInput | None = None

# ... 其余 8 个略

SlideData = Annotated[
    Union[CoverData, TocData, TransitionData, PolicyListData, ChartData,
          TableData, ImageGridData, ContentBulletsData, CaseCardData,
          ConceptSchemeData, EndingData],
    Field(discriminator="component_type"),
]
```

**校验/截断兜底**（同文件）：

```python
def truncate_to_schema(data: dict, schema: type[BaseModel]) -> dict:
    """Pydantic 校验失败后的最后兜底：按字段约束硬截断。"""
    # 走每个 field 的 metadata 拿 max_length，超长就 [: max_length-1] + "…"
    # max_length 类的 list 字段超长就截断
    ...
```

### 6.4 SlidePlan 装配（`agent/slide_plan.py`）

纯函数，无 LLM 调用：

```python
def build_slide_plan(outline: Outline, brief: ProjectBrief) -> SlidePlan:
    """
    1. 读 outline.spec_json -> List[OutlineSlideEntry]
    2. 按 slot_id 查 PPT_BLUEPRINT 拿 template_component 和 chapter
    3. 计算 total_pages（== len(entries)）
    4. 按 chapter 聚合 sections，每个 section 计算 page_start / page_end
    5. 输出 SlidePlan(total_pages, sections, slides)
    """
```

`SlidePlan` 在渲染阶段作为全局 context 之一注入 base.html.j2，模板里直接 `{{ total_pages }} / {{ section_no }} / {{ section_en }}` 取值，无需任何模板内逻辑。

### 6.5 章节口音色（VisualTheme.section_colors）

[agent/visual_theme.py](../../../agent/visual_theme.py) 输入扩展为：

```python
class VisualThemeInput(BaseModel):
    # 现有字段 ...
    chapters: list[ChapterMeta]   # 来自 BriefDoc.outline_json.chapters
    recommended_emphasis: dict    # 来自 BriefDoc

class ChapterMeta(BaseModel):
    id: str
    title: str
    narrative_direction: str
```

LLM prompt 增加：

> 你需要为每个章节确定一个"口音色（accent color）"，作为该章 slide 顶部 3px 装饰条的颜色。口音色应：
> 1. 与主色 palette 协调（不引入新色相，限制在 palette 内或其低饱和邻近色）；
> 2. 反映该章调性（如政策章可冷蓝、场地章可大地色、方案章可主色饱和）；
> 3. 章节数为 N，输出长度为 N 的 hex 数组，按章节顺序排列。

输出 schema 加：

```python
class VisualThemeOutput(VisualTheme):
    section_colors: list[str] = Field(min_length=1, max_length=12)
    template_pack: Literal["minimalist_architecture"] = "minimalist_architecture"
```

DB 迁移 `006_visual_theme_section_colors.py` 给 `visual_themes.theme_json` 不需要改（JSONB），但显式加两个普通列方便查询：`section_colors_json TEXT`、`template_pack VARCHAR(64) DEFAULT 'minimalist_architecture'`。

### 6.6 Composer template-mode（核心改动）

[agent/composer.py](../../../agent/composer.py) 改造（伪代码）：

```python
async def compose_slide(entry, brief_doc, assets, theme, mode_override=None):
    blueprint_slot = lookup_slot(entry.slot_id)
    mode = mode_override or _decide_mode(blueprint_slot)

    if mode == "template":
        try:
            data = await _compose_template_slide(blueprint_slot, entry, brief_doc, assets, theme)
            return Slide(spec_json={"mode": "template", "component_type": data.component_type, "data": data.model_dump()})
        except (ValidationError, LLMOutputError) as exc:
            logger.warning("template mode failed for slide %s, falling back to html_free: %s", entry.slide_no, exc)
            mode = "html_free"

    if mode == "html_free":
        return await _compose_html_free_slide(entry, brief_doc, assets, theme)

    return await _compose_layout_spec_slide(entry, brief_doc, assets, theme)


def _decide_mode(slot: PageSlot) -> Literal["template", "html_free", "layout_spec"]:
    if slot.template_component is not None:
        return "template"
    return "html_free"   # v3 默认


async def _compose_template_slide(slot, entry, brief_doc, assets, theme):
    schema_cls = COMPONENT_SCHEMAS[slot.template_component]
    prompt = _build_template_prompt(slot, entry, brief_doc, assets, theme, schema_cls)
    raw = await call_llm_structured(prompt=prompt, schema=schema_cls)
    try:
        return schema_cls.model_validate(raw)
    except ValidationError:
        retry_prompt = _build_retry_prompt(prompt, raw, schema_cls)
        raw2 = await call_llm_structured(prompt=retry_prompt, schema=schema_cls)
        try:
            return schema_cls.model_validate(raw2)
        except ValidationError:
            return schema_cls.model_validate(truncate_to_schema(raw2, schema_cls))
```

`_compose_template_slide` 的 prompt 模板放 [prompts/composer_template_mode.md](../../../prompts/composer_template_mode.md)，注入：

- 当前页的 `content_directive`（来自 OutlineSlideEntry）
- 已绑定的 assets（按 logical_key 列出）
- 目标 schema 的 JSON Schema dump（含 max_length 等约束）
- BriefDoc 的局部上下文（与该页相关的章节）
- VisualTheme 的 keywords / mood（让文案语气与视觉一致）

### 6.7 chart 物化（`agent/chart_materialize.py`）

```python
async def materialize_charts_in_slide(slide_data: SlideData, project_id: UUID, theme: VisualTheme, db: Session) -> SlideData:
    """对 ChartData 类型的 slide_data，若 chart_path 为空且 chart_spec 非空，调 chart_generation 物化为 PNG，落 Asset，回填 chart_path。"""
    if not isinstance(slide_data, ChartData):
        return slide_data
    if slide_data.chart_path or not slide_data.chart_spec:
        return slide_data

    spec = slide_data.chart_spec.model_copy(update={"color_scheme": _theme_to_scheme(theme)})
    out = chart_generation(spec)
    asset_path = _persist_chart_png(out.image_bytes, project_id, slide_data)
    asset = Asset(... logical_key=f"chart.materialized.{slide_no}", image_url=str(asset_path) ...)
    db.add(asset)
    return slide_data.model_copy(update={"chart_path": str(asset_path)})
```

调用点：Composer 产出 SlideData 之后、入库 Slide 之前。

`_theme_to_scheme(theme)`：把 `VisualTheme.colors` 注册为一个新的 `COLOR_SCHEMES["theme"]` 临时项（5 色：primary / accent / secondary / text_secondary / border 的合理组合），传给 chart_generation。

### 6.8 渲染分支（`render/engine.py` + `render/jinja_env.py`）

```python
# render/jinja_env.py
def get_jinja_env(template_pack: str) -> Environment:
    pack_dir = Path("templates/packs") / template_pack
    env = Environment(loader=FileSystemLoader([pack_dir, pack_dir / "components"]),
                      autoescape=select_autoescape(["html"]))
    env.filters["embed_image"] = _embed_image_filter
    return env

def _embed_image_filter(asset_id_or_path: str | UUID) -> str:
    # UUID -> 查 Asset.image_url -> 转 file:// 或 base64
    # str (file path) -> 直接 file://
    ...

# render/engine.py
def render_via_jinja(slide: Slide, plan: SlidePlan, theme: VisualTheme) -> str:
    env = get_jinja_env(theme.template_pack)
    component = slide.spec_json["component_type"]
    data = slide.spec_json["data"]
    section = plan.section_for(slide.slide_no)
    ctx = {
        "page": slide.slide_no,
        "section": f"{section.no:02d}",
        "section_en": section.en,
        "project_title": plan.project_title,
        "title": data.get("title", slide.title),
        "subtitle_en": data.get("subtitle_en", ""),
        "data": data,
        "theme": theme.model_dump(),
        "theme_css": generate_theme_css(theme),
        "total_pages": plan.total_pages,
        "interactive": False,
    }
    return env.get_template(f"components/{component}.html.j2").render(**ctx)


def render_slide_html(slide, plan, theme) -> str:
    mode = (slide.spec_json or {}).get("mode")
    if mode == "template":
        return render_via_jinja(slide, plan, theme)
    if mode == "html_free" or "body_html" in (slide.spec_json or {}):
        return _render_html_free(slide, theme)
    return _render_layout_spec(slide, theme)   # 现有路径
```

### 6.9 模板的具体修改（对应 P1-P5）

#### P1：硬编码总页数 / 章节数

- [_chrome.html.j2:13](../../../../liuzong/PPT-maker/templates/minimalist_architecture/components/_chrome.html.j2#L13) `/ 40` → `/ {{ total_pages }}`
- [toc.html.j2:42-50](../../../../liuzong/PPT-maker/templates/minimalist_architecture/components/toc.html.j2#L42-L50) 删除 `page_ranges` 局部变量；entries 中每项加 `page_range` 字段，从 SlidePlan 计算
- [viewport-base.css:51-53](../../../../liuzong/PPT-maker/templates/minimalist_architecture/viewport-base.css#L51-L53) 把 `.slide[data-section="02"]::before` 等手写规则删除，改由 base.j2 在 `<style>` 块内根据 `theme.section_colors` 循环生成

#### P2：双套主题系统

- 删除 [theme.json](../../../../liuzong/PPT-maker/templates/minimalist_architecture/theme.json)
- [base.html.j2:8-31](../../../../liuzong/PPT-maker/templates/minimalist_architecture/base.html.j2#L8-L31) 整段 `:root` 删除，改为 `{{ theme_css|safe }}`
- 全局批量改名（在 11 个组件中）：

| 旧（templates 自定义） | 新（VisualTheme 已有） |
|------|------|
| `var(--accent)` | `var(--color-accent)` |
| `var(--ink)` | `var(--color-text-primary)` |
| `var(--muted)` | `var(--color-text-secondary)` |
| `var(--bg)` | `var(--color-bg)` |
| `var(--bg-deep)` | 用 `color-mix(in srgb, var(--color-bg), var(--color-text-primary) 6%)` 派生 |
| `var(--surface)` | `var(--color-surface)` |
| `var(--rule)` | `var(--color-border)` |
| `var(--rule-soft)` | 用 `color-mix(in srgb, var(--color-border), transparent 50%)` |
| `var(--accent-soft)` | 用 `color-mix(in srgb, var(--color-accent), transparent 70%)` |
| `var(--accent-warm)` | 暂保留为 `--color-accent`（不引入新色） |
| `var(--highlight)` | 用 `--color-accent`（去掉 highlight 概念） |
| `var(--font-display)` | `var(--font-heading)` |
| `var(--font-body)` | `var(--font-body)`（已同名） |
| `var(--font-en)` | `var(--font-en)`（已同名） |
| `var(--font-mono)` | 删除使用（policy_list 里只有 source URL 用过，改 `var(--font-en)`） |

`color-mix()` 在 Chromium ≥ 111 支持，Playwright 用的 chromium 版本远超此线，可放心用。

#### P3：内容长度无约束

通过 SlideData schema 在 Composer 出口拦截，模板内不做长度兜底（信任上游）。但保留：

- [content_bullets.html.j2:39](../../../../liuzong/PPT-maker/templates/minimalist_architecture/components/content_bullets.html.j2)：`max-height: 18vh; overflow: hidden;` 这类样式作为最后兜底，**不删**。
- [concept_scheme.html.j2:49](../../../../liuzong/PPT-maker/templates/minimalist_architecture/components/concept_scheme.html.j2#L49) 同理。

#### P4：chart 接口

模板**不改**接口，仍只接 `chart_path`。在 SlideData schema 里 `chart_path / chart_spec` 二选一，由 chart_materialize 在 render 前确保 `chart_path` 已就绪。这样模板保持纯净。

#### P5：写死的元数据 / 署名

- [cover.html.j2:72](../../../../liuzong/PPT-maker/templates/minimalist_architecture/components/cover.html.j2#L72) `lbls = ['BUILDING','GROSS AREA','FAR']` 改为 `data.meta_lines: list[{label, value}]`
- [cover.html.j2:84](../../../../liuzong/PPT-maker/templates/minimalist_architecture/components/cover.html.j2#L84) `PREPARED BY ARCHITECT · AGENT` 改为 `data.signature` 字段
- [ending.html.j2:60-62](../../../../liuzong/PPT-maker/templates/minimalist_architecture/components/ending.html.j2#L60-L62) `2026 / ARCHITECT AGENT` 改为 `{{ year }} / {{ signature }}` 取自 SlideData

### 6.10 manus 40 页 → component 映射（写入 [config/ppt_blueprint.py](../../../config/ppt_blueprint.py)）

| slot_id | template_component | 数据来源 |
|---|---|---|
| cover | cover | ProjectBrief + BriefDoc.brief_title |
| toc | toc | SlidePlan.sections |
| chapter-{1..4}-divider | transition | BriefDoc.chapters[i] |
| policy ×2 | policy_list | brief.design_outline + LLM |
| policy-impact | chart | LLM bullets + chart_spec(数据来自 LLM 整理) |
| upper-planning | table | brief.design_outline |
| transport-map | image_grid | site.transport.* + site.infrastructure.* |
| cultural-analysis | content_bullets | BriefDoc 文化部分 |
| economy-* ×3 | image_grid | economy.*.chart.{N}（已是图） |
| site-* ×4 | image_grid / content_bullets 混合 | site.boundary / site.development |
| poi-analysis | chart | site.poi.table.structured_data → chart_materialize |
| site-summary | content_bullets | LLM 综合 |
| competitor ×2 | table | site.competitor.* + LLM |
| reference-case ×3 | case_card | reference.case.{N}.thumbnail + .analysis |
| positioning | content_bullets | BriefDoc.positioning_statement |
| design-strategy | content_bullets | outline.recommended_emphasis |
| concept-aerial / ext / int ×3 | concept_scheme | concept.{N}.{view}（concept_render 已就绪）|
| material-economy | table | LLM |
| design-task | content_bullets | LLM |
| ending | ending | BriefDoc + LLM tagline |

蓝图中 `generation_methods=[NANOBANANA / WEB_SEARCH]` 但本期不实装的页：

- cover.logo / toc.illustration → 本期 `template_component=cover|toc` 但 `logo_asset_id / illustration_asset_id` 字段为 None，模板对 None 自动隐藏图片位（[cover.html.j2:60-63](../../../../liuzong/PPT-maker/templates/minimalist_architecture/components/cover.html.j2#L60-L63) 已有 `{% if data.logo %}` 判断）
- competitor 第二页（联网搜索）→ 若联网工具未实装，蓝图 `template_component=None`，回退 html_free + LLM 凭训练数据生成（与现状一致）

### 6.11 落地顺序（5 个 PR）

| PR | 内容 | 验收 | 风险 |
|----|------|------|------|
| **PR-1** | 拷模板 + 改造（P1/P2/P5）+ schema 落地 + slide_plan 装配 + jinja_env | 11 fixture → render → 截图人工 review | 低 |
| **PR-2** | Composer template-mode + render 分支 + 单元测试 | smoke 跑通 1 页（ending） | 中（涉及 Composer） |
| **PR-3** | concept_scheme 端到端：第 29-37 页用模板渲染 | E2E 9 张图正常呈现 | 低（数据已就绪） |
| **PR-4** | 其余组件按风险递增接入（image_grid → case_card → policy_list → content_bullets → table → chart） | E2E 30 页 template mode + 11 页兜底 | 中 |
| **PR-5** | VisualTheme 扩展（section_colors）+ visual_theme prompt v2 | 真实项目跑出符合大纲调性的章节色 | 中（依赖 LLM 输出稳定性） |

第 2、3 个 template_pack 和 "LLM 选 pack" 留下一轮 brief。

---

## 7. Relevant Files

### 主要改动

见第 6.2 节清单。

### 参考实现

- [agent/concept_render.py](../../../agent/concept_render.py) — 派生资产入 Asset 表 + 失败降级范式
- [render/engine.py:generate_theme_css](../../../render/engine.py#L92) — VisualTheme → CSS 变量（不动，被复用）
- [tool/asset/chart_generation.py](../../../tool/asset/chart_generation.py) — chart 物化的执行器（不动）
- [agent/composer.py](../../../agent/composer.py) — 改造对象，需保留双模式现有逻辑
- [agent/visual_theme.py](../../../agent/visual_theme.py) — prompt 扩展对象
- [config/ppt_blueprint.py](../../../config/ppt_blueprint.py) — 41 个 PageSlot 加字段
- [d:\projects\liuzong\PPT-maker\templates\minimalist_architecture\](../../../../liuzong/PPT-maker/templates/minimalist_architecture/) — 模板源（不动源目录，改造拷贝）

### 不要动

- [agent/critic.py](../../../agent/critic.py) — Critic 对 mode 透明，按现有 vision-only 路径处理
- [tasks/review_tasks.py](../../../tasks/review_tasks.py) — 审查回环不变
- [tasks/render_tasks.py](../../../tasks/render_tasks.py) — Celery 编排不变
- [tool/image_gen/runninghub.py](../../../tool/image_gen/runninghub.py) — 不增不删
- [agent/concept_render.py](../../../agent/concept_render.py) — 已经能直接对接 concept_scheme 模板，零改动

---

## 8. Questions / Risks

### 开工前要对齐

1. **`color-mix()` 兼容性**：Playwright 用的 chromium 通常 ≥ 120，肯定支持 `color-mix(in srgb, ...)`。但如果 PDF 还要二次过 wkhtmltopdf 之类的旧渲染器，需手工把 `color-mix` 用 SCSS 预编译成静态 hex —— 请确认渲染链路只走 chromium。
2. **Asset 表的 `logical_key` 唯一性**：`chart.materialized.{slide_no}` 要唯一，建议按 `chart.materialized.{slide_no}.{hash(spec)}` 落，避免重渲染冲突。
3. **VisualTheme 重新生成时 section_colors 是否一致**：当前 [agent/visual_theme.py](../../../agent/visual_theme.py) 在某些路径会重新调用 LLM 生成。如果 section_colors 每次跑不一样，PDF 之间会有差异。是否要 seed？建议加 `seed=hash(project_id)` 让 LLM 调用时确定性。
4. **章节数动态化的边界**：现实中章节数应在 4-6 之间。`section_colors` schema `min_length=1, max_length=12` 是否够？如果 outline 章节数 > 12 是异常，应直接 raise。

### 已知风险

1. **LLM 输出 SlideData 不稳定**：长度约束失败重试一次仍失败 → 截断兜底，但截断可能产生不通顺文本。监控指标：`schema_truncate_total`，超过 5% 需调 prompt 或上限。
2. **模板 + VisualTheme 视觉不协调**：模板是为偏冷的纸白底设计的，如果 VisualTheme 生成深色 / 高饱和 palette，部分组件可能丑（如 transition 的 `var(--ink)` 黑底改成深紫底可能很怪）。短期对策：模板里**只允许深 / 浅两个对比模式**，由 `theme.color_mode` 选择 base.j2 注入不同的兜底变量。长期对策：第 2、3 个 pack 分别针对 `dark / warm / mono` 调性。
3. **chart 物化失败率未知**：matplotlib 对中文字体依赖系统 fonts，开发机和容器表现可能不同。需在 chart_materialize 启动时探测一次中文字体可用性，缺则 log warning。
4. **回退路径触发频率**：如果 template mode 失败率高于 10%，说明 schema 设计或 prompt 不到位，要回头调 prompt 而不是放任回退。监控指标：`composer_template_fallback_total / composer_template_total`。
5. **测试覆盖成本**：11 组件 × 多 fixture × 跨 PR，整体 E2E 时间会膨胀。CI 跑 `--max-slides 5` smoke，本地手动跑全量。
6. **section_colors 与现有 generate_theme_css 的耦合**：[render/engine.py:generate_theme_css](../../../render/engine.py#L92) 当前不输出 section_colors。需在该函数末尾追加 `--section-color-{N}: {hex}` 段，base.j2 内循环生成 `.slide[data-section="0N"]::before` 选择器。

### 未来改进（不在本期范围）

- **第 2、3 个 template_pack**（editorial_warm / tech_mono），与 "LLM 选 pack" 机制
- **模板可视化预览工具**（独立小工具，给设计师看效果）
- **template-mode 下的局部 LLM 重写**：用户对某页不满意时，只重跑该页 SlideData 而非整个项目
- **Critic 对 SlideData 的语义校验**：除了 vision review，可对 SlideData 做规则校验（如 `policy_list` 里 source_url 域名白名单）
- **ImageGrid 自动选图**：当前从 logical_key 显式取，未来可由 LLM 在 asset pool 中选择最相关的 N 张

---

## 9. Updates

（开发过程中追加）
