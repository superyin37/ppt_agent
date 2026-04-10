---
tags: [schema, material, pydantic, database]
source: db/models/material_package.py, db/models/material_item.py
---

# MaterialPackage & MaterialItem

> 素材包的数据库模型，由[[stages/01-素材包摄入]]中的 `ingest_local_material_package()` 创建。

---

## MaterialPackage

```
表名: material_packages
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | |
| `project_id` | UUID FK | 所属项目 |
| `version` | int | 版本号，支持多次上传 |
| `status` | str | `"pending"` / `"ready"` / `"failed"` |
| `source_hash` | str | 素材目录内容哈希（防重复摄入） |
| `manifest_json` | JSON | 按条目分组的 logical_keys 映射 |
| `summary_json` | JSON | 各类型计数与摘要 |
| `meta_json` | JSON | 额外元信息 |
| `created_at` | datetime | |

### `manifest_json` 结构示例

```json
{
  "policy": ["policy.national.1", "policy.city.2"],
  "site": ["site.boundary.image", "site.traffic.chart.1"],
  "economy": ["economy.city.chart.1", "economy.far"],
  "reference": ["reference.case.1.images", "reference.case.2.images"],
  "brief": ["brief.outline.text"]
}
```

### `summary_json` 结构示例

```json
{
  "total_items": 24,
  "by_kind": {
    "image": 12,
    "chart_bundle": 5,
    "spreadsheet": 3,
    "document": 4
  },
  "reference_case_count": 3
}
```

---

## MaterialItem

```
表名: material_items
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | |
| `package_id` | UUID FK | 所属 MaterialPackage |
| `project_id` | UUID FK | 所属项目 |
| `logical_key` | str | 层级化标识符（见下文） |
| `kind` | str | 文件类型（见下表） |
| `title` | str | 文件名或推断标题 |
| `source_path` | str | 磁盘路径 |
| `content_url` | str | `file://` URI |
| `preview_url` | str | 预览图 `file://` URI |
| `text_content` | str | 文本文件前 2000 字符 |
| `structured_data` | JSON | JSON 内容 或 XLSX sheet 预览 |
| `meta_json` | JSON | 额外元数据 |

### `kind` 枚举值

| kind | 说明 | 示例文件 |
|------|------|---------|
| `image` | 图片文件 | `.jpg`, `.png`, `.svg` |
| `chart_bundle` | 图表变体组（JSON + SVG + HTML） | `GDP统计_*.json` |
| `spreadsheet` | 表格数据 | `.xlsx`, `.csv` |
| `document` | 文本文档 | `.txt`, `.md`, `.docx` |
| `binary` | 其他二进制 | `.pdf`, `.pptx` |

### `logical_key` 命名规则

通过正则模式从文件名推断：

| 文件名示例 | logical_key |
|-----------|-------------|
| `参考案例1_图片_1_xxx.jpg` | `reference.case.1.images` |
| `场地分析_红线图.png` | `site.boundary.image` |
| `经济指标_城市GDP.xlsx` | `economy.city.chart.1` |
| `政策文件_国土规划.txt` | `policy.national.1` |
| `设计建议书大纲.txt` | `brief.outline.text` |

层级结构：`{domain}.{subdomain}.{type}.{index}`

常用前缀：`site.*`, `economy.*`, `policy.*`, `reference.*`, `brief.*`, `competition.*`

---

## MaterialItem → Asset 派生关系

| MaterialItem kind | prefix | Asset Type | [[schemas/Asset]] |
|-------------------|--------|------------|---------|
| `image`（site.* 前缀） | `site.*` | `MAP` | 场地类图片 |
| `image`（其他） | | `IMAGE` | 一般图片 |
| `chart_bundle` | | `CHART` | 图表 |
| `spreadsheet` | | `KPI_TABLE` | 指标表格 |
| `document` | | `TEXT_SUMMARY` | 文本摘要 |
| 参考案例聚合 | `reference.*` | `CASE_CARD` | 多图 + 分析 + 来源 |

派生逻辑在 `tool/material_pipeline.py` 的 `_derive_assets()` 中实现。

---

## 相关

- [[stages/01-素材包摄入]]
- [[tools/MaterialPipeline]]
- [[schemas/Asset]]
- [[agents/MaterialBindingAgent]]
