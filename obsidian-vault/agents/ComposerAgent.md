---
tags: [agent, llm, composer, layout]
source: agent/composer.py
model: STRONG_MODEL
---

# ComposerAgent

> **阶段五**：将大纲条目扩展为完整的 `LayoutSpec`（版式规格），支持 v2 结构化模式和 v3 HTML 直出模式。

## 操作模式

```python
class ComposerMode(str, Enum):
    STRUCTURED = "structured"   # v2: 输出 LayoutSpec JSON（默认）
    HTML       = "html"         # v3: 输出 body_html（直接 HTML）
```

## 触发时机

```
POST /projects/{project_id}/outline/confirm
→ api/routers/outlines.py line 189
→ _compose_render_worker() line 46（后台线程）
  → bind_materials()     ← MaterialBindingAgent
  → generate_visual_theme()
  → compose_all_slides() ← 本 Agent（并发 N 页）
  → render & screenshot
```

## 核心函数

```python
# agent/composer.py line 492
async def compose_all_slides(
    project_id: UUID,
    outline_id: UUID,
    db: Session,
    mode: ComposerMode = ComposerMode.STRUCTURED,
) -> list[Slide]

# agent/composer.py line 351（v2 结构化路径）
async def _compose_slide_structured(
    entry: OutlineSlideEntry,
    theme: VisualTheme,
    brief: ProjectBrief,
    assets: list[Asset],
    binding: SlideMaterialBinding,
) -> LayoutSpec

# agent/composer.py line 438（HTML 降级路径）
async def _html_fallback(...) -> dict
```

## 并发策略

```python
# compose_all_slides() 内部
tasks = [_compose_slide_structured(entry, ...) for entry in slides]
results = await asyncio.gather(*tasks, return_exceptions=True)
```

每页独立并发调用 LLM，N 页同时处理。

## System Prompt

文件：`prompts/composer_system_v2.md`（→ [[prompts/ComposerSystemV2]]）
v3 文件：`prompts/composer_system_v3.md`
修复文件：`prompts/composer_repair.md`

## User Message XML 结构

```xml
<visual_theme>
  style_keywords, cover_layout_mood, density,
  color_fill, generation_hint
</visual_theme>

<outline_entry>
  slide_no, section, title, content_directive,
  layout_hint, is_cover, is_chapter_divider,
  estimated_content_density
</outline_entry>

<project_brief>
  building_type, client_name, city
</project_brief>

<slide_material_binding>
  binding_id, derived_asset_ids,
  evidence_snippets, missing_requirements
</slide_material_binding>

<available_assets>
  // 仅包含 binding.derived_asset_ids 中的资产
  [{ "id": "uuid", "type": "IMAGE", "title": "...",
     "image_url": "file://...", "summary": "..." }]
</available_assets>
```

## 输出 Schema — `_ComposerLLMOutput`（v2）

```python
class _ComposerLLMOutput(BaseModel):
    slide_no: int
    section: str
    title: str
    is_cover: bool = False
    is_chapter_divider: bool = False
    primitive_type: str          # 11 种布局原语之一
    primitive_params: dict       # 对应布局的参数
    region_bindings: list[_RegionLLM]
    visual_focus: str            # 视觉重心区域 ID

class _RegionLLM(BaseModel):
    region_id: str               # 如 "left", "right", "content"
    blocks: list[_BlockLLM]

class _BlockLLM(BaseModel):
    block_id: str
    content_type: str            # 13 种内容块类型（见下表）
    content: str | list[str] | None
    emphasis: str                # "normal" / "highlight" / "muted"
```

## 13 种内容块类型（content_type）

| 类型 | 说明 | HTML 产出 |
|------|------|-----------|
| `heading` | 标题 | `<h1 class="block-heading">` |
| `body-text` | 正文段落 | `<p class="block-body-text">` |
| `image` | 图片 | `<img src="asset:uuid">` |
| `chart` | 图表（PNG/SVG） | `<img src="asset:uuid">` |
| `map` | 场地图 | `<img src="asset:uuid">` |
| `table` | 表格 | `<table>` 或 markdown → HTML |
| `kpi-value` | 大号数字展示 | `.kpi-value` + `.kpi-label` |
| `bullet-list` | 要点列表 | `<ul><li>` + accent 圆点 |
| `quote` | 引用块 | `<blockquote>` |
| `caption` | 说明文字 | `<p class="caption">` |
| `icon-label` | 图标 + 标签 | `.icon-label-pair` |
| `tag-cloud` | 关键词标签云 | `.tag` badges |
| `divider` | 分隔线 | `<hr>` |

## 资产引用格式

LLM 输出中使用 `"asset:uuid"` 格式引用资产：
```json
{ "content_type": "image", "content": "asset:550e8400-e29b-41d4-a716-446655440000" }
```
渲染引擎（`render/engine.py`）在 `_render_block()` 中将其解析为实际 `image_url`。

## 容错机制

```
LLM 调用失败
  → _fallback_layout_spec()  -> single-column 兜底布局
  
HTML 模式失败
  → _html_fallback()         -> 最小化 HTML 输出
```

## 产出 — `Slide` ORM（每页一条）

| 字段 | 说明 |
|------|------|
| `spec_json` | `LayoutSpec` JSON（结构化）或 `{html_mode:true, body_html:"..."}` |
| `source_refs_json` | 引用的 Asset ID 列表 |
| `evidence_refs_json` | 文本证据摘录 |
| `slide_no` / `section` / `title` | 页面基本信息 |
| `status` | `spec_ready` |

## 状态变更

```
Slide.status  → spec_ready
Project.status → SLIDE_PLANNING
```

## 相关

- [[stages/05-幻灯片编排]]
- [[prompts/ComposerSystemV2]]
- [[schemas/LayoutSpec]]
- [[schemas/LayoutPrimitive]]
- [[schemas/SlideMaterialBinding]]
- [[schemas/Slide]]
- [[agents/VisualThemeAgent]]
