---
tags: [tool, material, pipeline]
source: tool/material_pipeline.py
---

# MaterialPipeline 工具

> 素材包摄入全流程工具函数集，位于 `tool/material_pipeline.py`（507行）。

## 主函数

### `ingest_local_material_package()`

```python
# line 507
async def ingest_local_material_package(
    local_path: str,
    project_id: UUID,
    db: Session,
) -> MaterialPackage
```

**流程总控**，依次调用以下函数完成完整摄入。

---

## 文件扫描与分类（line 529-545）

```python
def _scan_directory(local_path: str) -> list[FileEntry]:
    # 扫描所有文件
    # 按 basename 分组图表变体（同名的 .json + .svg + .html）
    # 推断每个文件的 logical_key
```

### logical_key 推断正则（示例）

```python
PATTERN_MAP = [
    (r'参考案例(\d+)_图片', 'reference.case.{1}.images'),
    (r'场地分析_红线图',     'site.boundary.image'),
    (r'场地分析_交通',       'site.traffic.chart.1'),
    (r'经济指标_城市GDP',    'economy.city.chart.1'),
    (r'政策.*国家|国土',     'policy.national.1'),
    (r'政策.*城市|市级',     'policy.city.1'),
    (r'设计建议书大纲',      'brief.outline.text'),
    (r'竞品分析',            'competition.local.1'),
]
```

---

## `_derive_assets()` — MaterialItem → Asset 派生

```python
# line 399-504
def _derive_assets(
    items: list[MaterialItem],
    project_id: UUID,
    package_id: UUID,
) -> list[Asset]
```

### 派生规则

```python
# 场地图片
if item.kind == "image" and item.logical_key.startswith("site."):
    asset_type = AssetType.MAP

# 参考案例聚合
elif item.logical_key.startswith("reference.case."):
    # 同一案例的多张图片聚合为一个 CASE_CARD
    asset_type = AssetType.CASE_CARD
    # data_json 包含所有图片 URL 列表 + 分析文本

# 图表
elif item.kind == "chart_bundle":
    asset_type = AssetType.CHART
    # image_url 优先 SVG，降级 PNG/HTML

# 表格
elif item.kind == "spreadsheet":
    asset_type = AssetType.KPI_TABLE

# 文本文档
elif item.kind == "document":
    asset_type = AssetType.TEXT_SUMMARY

# 其他图片
else:
    asset_type = AssetType.IMAGE
```

---

## `_extract_project_brief()` — 大纲文档提取

```python
# line 257-339
def _extract_project_brief(
    brief_item: MaterialItem,
    project_id: UUID,
) -> ProjectBrief
```

从 `brief.outline.text` 类型的文档中提取：

| 字段 | 提取方式 |
|------|---------|
| `city` | `re.search(r'城市[：:]?\s*(\w+市|\w+区)', text)` |
| `province` | `re.search(r'省份[：:]?\s*(\w+省|\w+市)', text)` |
| `far` | `re.search(r'容积率\s*[≤≥<=]\s*(\d+\.?\d*)', text)` |
| `building_type` | 关键词匹配字典 |
| `style_preferences` | 正则匹配风格关键词列表 |

---

## `source_hash` 计算

```python
# 基于目录内容哈希，防止重复摄入
import hashlib
source_hash = hashlib.md5(
    "".join(sorted(all_file_paths))
).hexdigest()
```

如新摄入的 hash 与已有 MaterialPackage 相同，跳过重复处理。

## 相关

- [[stages/01-素材包摄入]]
- [[schemas/MaterialPackage]]
- [[schemas/Asset]]
- [[schemas/ProjectBrief]]
- [[tools/MaterialResolver]]
