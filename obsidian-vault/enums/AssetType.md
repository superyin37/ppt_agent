---
tags: [enum, asset-type]
source: schema/common.py
---

# AssetType 枚举

> 资产类型，存于 `assets.asset_type` 字段，由 Material 派生。

## 定义

```python
class AssetType(str, Enum):
    IMAGE           = "image"
    CHART           = "chart"
    MAP             = "map"
    CASE_CARD       = "case_card"
    CASE_COMPARISON = "case_comparison"
    TEXT_SUMMARY    = "text_summary"
    KPI_TABLE       = "kpi_table"
    OUTLINE         = "outline"
    DOCUMENT        = "document"
```

## 各类型说明

| 值 | 说明 | 来源 MaterialItem kind | 渲染方式 |
|----|------|----------------------|---------|
| `IMAGE` | 一般图片（照片/效果图） | `image`（非 site.* 前缀） | `<img>` |
| `CHART` | 图表 | `chart_bundle` | `<img>` 或 SVG 内联 |
| `MAP` | 场地图/地图 | `image`（含 site.* 前缀） | `<img class="map-asset">` |
| `CASE_CARD` | 参考案例卡片 | 多张 `reference.*` images 聚合 | Grid 展示 |
| `CASE_COMPARISON` | 竞品对比 | `competition.*` 聚合 | 对比表格 |
| `TEXT_SUMMARY` | 文本摘要 | `document` | 文本引用 |
| `KPI_TABLE` | 指标表格 | `spreadsheet` | `<table>` |
| `OUTLINE` | 大纲文档 | `brief.outline.text` | 文本解析 |
| `DOCUMENT` | 其他文档 | 其他 `document` | 文本引用 |

## 在 LayoutSpec 中的对应

`content_type` → 常用 AssetType：

| content_type | 常用 AssetType |
|-------------|---------------|
| `image` | IMAGE |
| `chart` | CHART |
| `map` | MAP |
| `case-card` 区域 | CASE_CARD |
| `kpi-value` | KPI_TABLE |

## 相关

- [[schemas/Asset]]
- [[schemas/MaterialPackage]]
- [[agents/MaterialBindingAgent]]
