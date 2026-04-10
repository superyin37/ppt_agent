---
tags: [agent, material-binding, no-llm]
source: agent/material_binding.py
---

# MaterialBindingAgent

> **阶段四**：无 LLM 调用的纯逻辑 Agent，将大纲每页所需资产与实际 MaterialItem / Asset 进行正则匹配绑定。

## 触发时机

```
POST /projects/{project_id}/outline/confirm
→ api/routers/outlines.py line 189
→ _compose_render_worker()
  → bind_outline_slides()  ← 本 Agent（在 compose 之前）
```

## 核心函数

```python
# agent/material_binding.py
def bind_outline_slides(
    project_id: UUID,
    outline_id: UUID,
    db: Session,
) -> list[SlideMaterialBinding]

# 内部：对每页调用
def _build_binding(
    project_id, outline_id, package_id,
    entry: OutlineSlideEntry,
    items: list[MaterialItem],
    assets: list[Asset],
    existing_version: int = 0,
) -> SlideMaterialBinding
```

## 绑定逻辑（逐页）

```
1. _collect_required_patterns(entry)
   ├── 优先：entry.required_input_keys（来自 LLM 的 asset_keys）
   └── 降级：从 PPT_BLUEPRINT 中找对应 slot 的 required_inputs

2. expand_requirement(key)  →  正则模式列表
   （via tool/material_resolver.py）

3. find_matching_items(patterns, all_items)
   → 用 logical_key 前缀匹配 MaterialItem

4. find_matching_assets(patterns, all_assets)
   → 用 logical_key 前缀匹配 Asset

5. 计算 coverage_score：
   (required_count - missing_count) / required_count
```

## 正则匹配规则

```python
# tool/material_resolver.py
def find_matching_items(patterns, items):
    for pattern in patterns:
        prefix = pattern.rstrip("*")
        for item in items:
            if item.logical_key and item.logical_key.startswith(prefix):
                yield item
```

## 产出 — `SlideMaterialBinding`（每页一条）

```python
class SlideMaterialBinding:
    project_id: UUID
    package_id: UUID
    outline_id: UUID
    slide_no: int
    slot_id: str
    version: int
    status: str                   # "ready"
    must_use_item_ids: list[str]  # 匹配到的 MaterialItem UUID
    optional_item_ids: list[str]
    derived_asset_ids: list[str]  # 匹配到的 Asset UUID
    evidence_snippets: list[str]  # 文本证据摘录（前 200 字）
    coverage_score: float         # 0.0 – 1.0
    missing_requirements: list[str]  # 未匹配的模式
    binding_reason: str           # 日志说明
```

`derived_asset_ids` 被 [[agents/ComposerAgent]] 用于构建 `<available_assets>` 消息。

## 状态变更

```
Project.status → BINDING
```

## 相关

- [[stages/04-素材绑定]]
- [[schemas/SlideMaterialBinding]]
- [[schemas/OutlineSlideEntry]]
- [[tools/MaterialResolver]]
- [[schemas/MaterialPackage]]
