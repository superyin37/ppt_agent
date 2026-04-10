---
tags: [schema, binding, database]
source: db/models/slide_material_binding.py
---

# SlideMaterialBinding

> 每页幻灯片的素材绑定结果，是 [[agents/MaterialBindingAgent]] 的产出，[[agents/ComposerAgent]] 的关键输入。

## 数据库模型

```
表名: slide_material_bindings
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | |
| `project_id` | UUID FK | |
| `package_id` | UUID FK | 来源素材包 |
| `outline_id` | UUID FK | 来源大纲 |
| `slide_no` | int | 对应幻灯片页码（1-based） |
| `slot_id` | str | 对应 PageSlot.slot_id |
| `version` | int | 绑定版本（重绑定时递增） |
| `status` | str | `"ready"` / `"stale"` |
| `must_use_item_ids` | JSON array | 必须使用的 MaterialItem UUID 列表 |
| `optional_item_ids` | JSON array | 可选 MaterialItem UUID 列表 |
| `derived_asset_ids` | JSON array | **关键**：匹配到的 Asset UUID 列表 |
| `evidence_snippets` | JSON array | 文本证据摘录（前 200 字） |
| `coverage_score` | float | 0.0 – 1.0 |
| `missing_requirements` | JSON array | 未匹配的 logical_key 模式 |
| `binding_reason` | str | 绑定日志说明 |

## 核心字段说明

### `derived_asset_ids`

ComposerAgent 用此字段过滤 `<available_assets>`：

```python
# agent/composer.py
filtered_assets = [a for a in all_assets if str(a.id) in binding.derived_asset_ids]
```

确保 LLM 只看到与本页相关的资产，避免上下文污染。

### `coverage_score` 计算

```python
missing_count = len(patterns_without_match)
required_count = len(required_patterns) or 1
coverage_score = (required_count - missing_count) / required_count
```

| 分数 | 含义 |
|------|------|
| 1.0 | 所有必需素材均匹配 |
| 0.5~0.9 | 部分匹配 |
| 0.0~0.4 | 素材严重不足 |

### `evidence_snippets`

从匹配到的 MaterialItem 中提取文本摘录，注入 `<slide_material_binding>` 给 LLM，帮助生成相关文字内容：

```python
# tool/material_resolver.py → summarize_evidence()
snippets = [item.text_content[:200] for item in matched_items if item.text_content]
```

## JSON 示例

```json
{
  "slide_no": 12,
  "slot_id": "site-boundary",
  "status": "ready",
  "derived_asset_ids": [
    "550e8400-e29b-41d4-a716-446655440001",
    "550e8400-e29b-41d4-a716-446655440002"
  ],
  "evidence_snippets": [
    "本地块位于苏州工业园区，用地面积约 3.2 万平方米，容积率≤2.0...",
    "绿化率不低于 35%，建筑限高 60 米..."
  ],
  "coverage_score": 0.85,
  "missing_requirements": ["site.parking.layout"],
  "binding_reason": "Matched 3 items and 2 assets for slide 12"
}
```

## 相关

- [[agents/MaterialBindingAgent]]
- [[agents/ComposerAgent]]
- [[schemas/OutlineSlideEntry]]
- [[schemas/Asset]]
- [[tools/MaterialResolver]]
