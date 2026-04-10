---
tags: [schema, asset, database]
source: db/models/asset.py, schema/common.py
---

# Asset

> 从 MaterialItem 派生的渲染用资产，直接被 [[agents/ComposerAgent]] 和渲染引擎引用。

## 数据库模型

```
表名: assets
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | |
| `project_id` | UUID FK | |
| `package_id` | UUID FK | 来源素材包 |
| `source_item_id` | UUID FK | 来源 MaterialItem（nullable） |
| `asset_type` | str | 资产类型（AssetType 枚举，见下文） |
| `subtype` | str | 细分类型（如 `"map"`, `"kpi"` 等） |
| `logical_key` | str | 与 MaterialItem 一致的 logical_key |
| `title` | str | 资产标题 |
| `image_url` | str | `file://` 路径，渲染引擎直接使用 |
| `render_role` | str | `"primary"` / `"secondary"` / `"thumbnail"` |
| `data_json` | JSON | 表格数据、KPI 数值等结构化内容 |
| `summary` | str | 资产用途摘要（发送给 LLM） |
| `meta_json` | JSON | 额外元信息 |

## AssetType 枚举

详见 [[enums/AssetType]]

| 值 | 说明 |
|----|------|
| `IMAGE` | 一般图片（照片、效果图） |
| `CHART` | 图表（来自 chart_bundle） |
| `MAP` | 场地图（site.* 前缀图片） |
| `CASE_CARD` | 参考案例卡片（多图 + 分析文本 + 来源） |
| `CASE_COMPARISON` | 竞品对比 |
| `TEXT_SUMMARY` | 文本摘要（来自 document） |
| `KPI_TABLE` | 指标表格（来自 spreadsheet） |
| `OUTLINE` | 大纲文档 |
| `DOCUMENT` | 其他文档 |

## `image_url` 格式

```
file:///D:/projects/PPT_Agent/test_material/场地分析/红线图.png
```

Playwright 渲染时通过 `file://` 协议加载本地文件。

## 被 ComposerAgent 消费的格式

在 `<available_assets>` XML 中，每条 Asset 序列化为：

```json
{
  "id": "550e8400-...",
  "type": "MAP",
  "title": "场地红线图",
  "image_url": "file:///...",
  "summary": "苏州项目用地红线范围，显示地块形状与边界条件",
  "logical_key": "site.boundary.image"
}
```

LLM 在 `region_bindings` 中通过 `"asset:550e8400-..."` 格式引用，渲染引擎再解析为 `image_url`。

## 相关

- [[schemas/MaterialPackage]]
- [[enums/AssetType]]
- [[agents/ComposerAgent]]
- [[schemas/SlideMaterialBinding]]
