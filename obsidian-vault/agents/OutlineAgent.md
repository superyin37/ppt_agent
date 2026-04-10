---
tags: [agent, llm, outline]
source: agent/outline.py
model: STRONG_MODEL
---

# OutlineAgent

> **阶段三**：基于 BriefDoc + PPT_BLUEPRINT，为每个 PageSlot 生成具体内容指令，产出完整大纲。

## 触发时机

```
POST /projects/{project_id}/material-packages/{package_id}/regenerate
→ _outline_worker() in api/routers/outlines.py line 33
  → generate_brief_doc()
  → generate_outline()   ← 本 Agent
```

## 核心函数

```python
# agent/outline.py line 169
async def generate_outline(project_id: UUID, db: Session) -> Outline
```

## 输入组装

### System Prompt

文件：`prompts/outline_system_v2.md`（→ [[prompts/OutlineSystemV2]]）

注入变量：
| 变量 | 来源字段 |
|------|---------|
| `{building_type}` | `ProjectBrief.building_type` |
| `{project_name}` / `{client_name}` | `ProjectBrief.client_name` |
| `{city}` / `{province}` | `ProjectBrief` |
| `{positioning_statement}` | `BriefDoc.outline_json["positioning_statement"]` |
| `{narrative_arc}` | `BriefDoc.outline_json["narrative_arc"]` |

### User Message XML 结构

```xml
<project_brief>
  building_type, client_name, city, style_preferences
</project_brief>

<brief_doc>
  narrative_arc, positioning_statement, chapters
</brief_doc>

<blueprint>
  // 40-60 个 PageSlot JSON 条目，含 required_inputs、layout_hint
  {"slot_id": "cover", "title": "封面", ...}
  {"slot_id": "policy-1", "title": "政策分析", ...}
  // PageSlotGroup 按 repeat_count 展开
</blueprint>

<reference_count>
  3                          // 2-5 个参考案例页
</reference_count>

<material_package>
  summary_json + manifest_json
</material_package>

<material_snippets>
  // 文本素材摘录（前 400 字符），按 logical_key 展示
</material_snippets>
```

### Blueprint 处理

蓝图定义：`config/ppt_blueprint.py` → [[tools/MaterialPipeline]]

| 蓝图类型 | 描述 |
|---------|------|
| `PageSlot` | 单页槽位，直接输出一条 assignment |
| `PageSlotGroup` | 可重复页组，按 `repeat_count_min~max` 展开 |

`reference-case-pages` 组使用实际参考案例数量（通过 `Asset` 表中 `CASE_CARD` 类型统计）。

## LLM 配置

```python
model = STRONG_MODEL
function = call_llm_with_limit
```

## 输出 Schema — `_OutlineLLMOutput`

```python
class _OutlineLLMOutput(BaseModel):
    deck_title: str                         # 最终演示标题
    total_pages: int                        # 总页数（约 35-40）
    assignments: list[_SlotAssignmentLLM]

class _SlotAssignmentLLM(BaseModel):
    slot_id: str                            # 来自 PPT_BLUEPRINT 的 slot_id
    slide_no: int                           # 1-based 连续编号
    section: str                            # 章节名称
    title: str                              # ≤15字，本页标题
    content_directive: str                  # ≤80字，项目专属内容指令
    asset_keys: list[str]                   # 所需资产 logical_key 列表
    layout_hint: str                        # 布局意图
    is_cover: bool
    is_chapter_divider: bool
    estimated_content_density: str          # low / medium / high
```

## 覆盖率分析（生成后执行）

函数：`agent/outline.py line 147-166`

```python
for entry in outline_spec.slides:
    patterns = expand_requirement(key)      # tool/material_resolver.py
    matched = find_matching_items(all_items, patterns)
    status = "complete" | "partial" | "missing"
```

## 产出 — `Outline` ORM

| 字段 | 内容 |
|------|------|
| `spec_json` | `OutlineSpec` 完整 JSON（含所有页面条目） |
| `coverage_json` | 每页素材覆盖率报告 |
| `slot_binding_hints_json` | 每页所需输入 + 推荐匹配范围 |
| `deck_title` | 演示文稿标题 |
| `theme` | 从 building_type 推导 |
| `total_pages` | 总页数 |
| `status` | `draft` |

## 状态变更

```
Outline.status → "draft"
Project.status → OUTLINE_READY  （等待用户确认）
```

## 相关

- [[stages/03-大纲生成]]
- [[prompts/OutlineSystemV2]]
- [[schemas/OutlineSlideEntry]]
- [[agents/BriefDocAgent]]
- [[agents/MaterialBindingAgent]]
- [[tools/MaterialResolver]]
