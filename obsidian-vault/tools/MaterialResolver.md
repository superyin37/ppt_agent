---
tags: [tool, material-resolver, regex]
source: tool/material_resolver.py
---

# MaterialResolver 工具

> logical_key 匹配与展开工具，是 [[agents/MaterialBindingAgent]] 的核心依赖。

## 函数索引

| 函数 | 说明 |
|------|------|
| `expand_requirement(key)` | logical_key 模式 → 正则模式列表 |
| `find_matching_items(patterns, items)` | 正则匹配 MaterialItem |
| `find_matching_assets(patterns, assets)` | 正则匹配 Asset |
| `summarize_evidence(items)` | 提取文本证据摘录 |

---

## `expand_requirement(key)` — 模式展开

```python
# tool/material_resolver.py line 35
def expand_requirement(key: str) -> list[str]:
    """
    将 logical_key 或通配符模式展开为多个可匹配前缀。
    
    示例：
    "site.*"               → ["site."]
    "reference.case.*"     → ["reference.case."]
    "brief_doc"            → ["brief.", "policy.", "economy."]  # 特殊展开
    "web_search_policy"    → ["policy."]
    """
```

### 特殊 key 展开规则

| 输入 key | 展开为 |
|---------|--------|
| `"brief_doc"` | `["brief.", "policy.", "economy.", "competition."]` |
| `"web_search_policy"` | `["policy."]` |
| `"site.*"` | `["site."]` |
| `"reference.*"` | `["reference."]` |
| `"project_name"` | `[]`（无需素材匹配） |

---

## `find_matching_items(patterns, items)` — 素材匹配

```python
# tool/material_resolver.py
def find_matching_items(
    patterns: list[str],
    items: list[MaterialItem],
) -> list[MaterialItem]:
    result = []
    seen = set()
    for pattern in patterns:
        prefix = pattern.rstrip("*")
        for item in items:
            if item.logical_key and item.logical_key.startswith(prefix):
                if item.id not in seen:
                    result.append(item)
                    seen.add(item.id)
    return result
```

---

## `find_matching_assets(patterns, assets)` — 资产匹配

同上，对 Asset 进行匹配，按 `logical_key` 前缀。

---

## `summarize_evidence(items)` — 证据摘录

```python
def summarize_evidence(items: list[MaterialItem]) -> list[str]:
    return [
        item.text_content[:200]
        for item in items
        if item.text_content
    ]
```

---

## logical_key 层级结构

```
{domain}
 ├── {subdomain}
 │    ├── {type}
 │    │    └── {index}
 │    └── ...
```

常用前缀：

| 前缀 | 对应内容 |
|------|---------|
| `site.` | 场地相关（地图、红线、交通） |
| `site.boundary.*` | 用地红线图 |
| `site.traffic.*` | 交通分析图 |
| `economy.*` | 经济数据（GDP、消费、指标） |
| `economy.far` | 容积率数值 |
| `policy.*` | 政策文件 |
| `policy.national.*` | 国家级政策 |
| `policy.city.*` | 城市级政策 |
| `reference.case.*` | 参考案例 |
| `reference.case.N.images` | 第 N 个案例的图片 |
| `competition.*` | 竞品分析 |
| `brief.*` | 设计建议书文档 |

## 相关

- [[agents/MaterialBindingAgent]]
- [[schemas/MaterialPackage]]
- [[schemas/SlideMaterialBinding]]
