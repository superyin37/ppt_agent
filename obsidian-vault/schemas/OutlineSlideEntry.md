---
tags: [schema, outline, pydantic]
source: schema/outline.py
---

# OutlineSlideEntry & OutlineSpec

> 大纲的核心数据结构。由 [[agents/OutlineAgent]] 生成，存于 `Outline.spec_json`，每页一条 `OutlineSlideEntry`。

## OutlineSlideEntry

```python
class OutlineSlideEntry(BaseSchema):
    slot_id:                   str = ""          # 对应 PPT_BLUEPRINT 中的 slot_id
    slide_no:                  int               # 1-based 连续编号
    section:                   str               # 章节名称，如 "场地分析"
    title:                     str               # 页面标题（≤15字）
    purpose:                   str               # 页面目的（语义）
    key_message:               str               # 核心信息点
    required_assets:           list[str] = []    # (旧版) 所需资产列表
    required_input_keys:       list[str] = []    # logical_key 匹配模式列表（新版）
    optional_input_keys:       list[str] = []    # 可选资产
    coverage_status:           str = "unknown"   # complete / partial / missing
    recommended_binding_scope: list[str] = []    # 推荐匹配范围
    recommended_template:      Optional[LayoutTemplate] = None
    layout_hint:               str = ""          # 布局意图描述
    estimated_content_density: str = "medium"    # low / medium / high
    is_cover:                  bool = False
    is_chapter_divider:        bool = False
```

## OutlineSpec

```python
class OutlineSpec(BaseSchema):
    outline_id:  Optional[str] = None
    project_id:  UUID
    deck_title:  str           # 最终演示标题
    theme:       str           # 从 building_type 推导的主题词
    total_pages: int           # 总页数
    sections:    list[str]     # 章节名称列表
    slides:      list[OutlineSlideEntry]
```

## 字段详细说明

### `slot_id` — 蓝图槽位标识

格式：`{slot_id}` 或对于 PageSlotGroup 为 `{slot_id}-{index}`。

示例：`"cover"`, `"policy-1"`, `"policy-2"`, `"reference-case-1"`, `"reference-case-2"`

与 `config/ppt_blueprint.py` 中的 `PageSlot.slot_id` 对应。

### `required_input_keys` — 资产匹配模式

LLM 在 Outline 中指定所需素材，格式为 logical_key 前缀或通配符模式：

```json
["site.boundary.image", "site.traffic.*", "economy.city.chart.*"]
```

[[agents/MaterialBindingAgent]] 通过 [[tools/MaterialResolver]] 的 `expand_requirement()` 展开这些模式。

### `coverage_status` — 素材覆盖率状态

在 [[agents/OutlineAgent]] 生成大纲后立即由覆盖率分析填充：
- `complete` — 所有 required_input_keys 都找到匹配
- `partial` — 部分匹配
- `missing` — 无匹配

### `estimated_content_density`

影响 [[agents/ComposerAgent]] 的排版密度判断：
- `low` — 封面、章节过渡页
- `medium` — 常规分析页
- `high` — 数据密集型（经济数据、技术指标）

## JSON 示例

```json
{
  "outline_id": null,
  "project_id": "550e8400-...",
  "deck_title": "苏州博物馆改造方案策划建议书",
  "theme": "museum",
  "total_pages": 38,
  "sections": ["封面", "背景研究", "场地分析", "竞品分析", "参考案例", "项目定位", "设计策略"],
  "slides": [
    {
      "slot_id": "cover",
      "slide_no": 1,
      "section": "封面",
      "title": "苏州博物馆改造策划",
      "purpose": "项目整体形象展示",
      "key_message": "传承与创新的共生",
      "required_input_keys": [],
      "layout_hint": "full-bleed，封面大图",
      "is_cover": true,
      "is_chapter_divider": false,
      "estimated_content_density": "low"
    },
    {
      "slot_id": "site-boundary",
      "slide_no": 12,
      "section": "场地分析",
      "title": "用地红线与技术指标",
      "purpose": "展示地块法定控制条件",
      "key_message": "容积率≤2.0 约束下的设计空间",
      "required_input_keys": ["site.boundary.image", "economy.far"],
      "coverage_status": "complete",
      "layout_hint": "split-h: 左侧红线图，右侧指标表格",
      "estimated_content_density": "medium"
    }
  ]
}
```

## 相关

- [[agents/OutlineAgent]]
- [[agents/MaterialBindingAgent]]
- [[schemas/SlideMaterialBinding]]
- [[enums/ProjectStatus]]
- `schema/page_slot.py` — `PageSlot` 蓝图槽位定义
