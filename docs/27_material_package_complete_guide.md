# 素材包完整技术文档

> 来源文件：`tool/material_pipeline.py`、`tool/material_resolver.py`、`agent/material_binding.py`、`db/models/material_package.py`、`db/models/material_item.py`、`db/models/asset.py`、`db/models/slide_material_binding.py`、`api/routers/material_packages.py`

---

## 1. 概述

**素材包**（Material Package）是 PPT 生成流程的**唯一事实源**。整个生成链路从素材包摄入开始，后续所有 Agent（BriefDoc、Outline、MaterialBinding、Composer、VisualTheme）都直接或间接消费素材包中的内容。

核心设计原则：

- **单一事实源**：所有 Agent 只能消费一个明确版本的素材包，不再面向散落文件
- **先绑定后生成**：每个 PPT 页面在进入 Composer 前，必须先通过 MaterialBinding 明确其所需素材
- **原始素材与派生资产分层**：原始文件→`MaterialItem`→`Asset`，各层职责不同
- **内容可追溯**：每个页面的图、表、文案都可追溯到素材包中的具体来源文件
- **版本化增量更新**：素材包支持 `version` 字段，可对比版本差异进行增量重生成

---

## 2. 原始素材包的目录结构

素材包是一个**本地目录**，由后台服务根据用户输入自动生成，格式类似 `test_material/project1/`。

目录中包含以下类型的文件：

### 2.1 文件类型说明

| 扩展名 | 说明 | 处理方式 |
|--------|------|----------|
| `.png` `.jpg` `.jpeg` `.webp` `.svg` | 图片 | 直接作为 `preview_url` 和 `content_url` |
| `.md` `.txt` `.html` `.htm` | 文本文档 | 读取前 2000 字作为 `text_content` |
| `.json` | JSON 数据 | 读取为 `structured_data` + 文本摘录 |
| `.xlsx` `.csv` | 表格 | 提取 sheet 名、前 5 行作为 `structured_data` |
| 图表三件套 `_chart_N_.svg/json/html` | 图表 Bundle | 合并为一个 `chart_bundle` 条目 |

### 2.2 图表 Bundle（`chart_bundle`）特别说明

当文件名包含 `_chart_` 且扩展名为 `.svg`、`.json`、`.html` 时，三个文件会被合并为一个 `MaterialItem`：

```
(文件名格式) 经济背景 - 城市经济_chart_1_.svg
             经济背景 - 城市经济_chart_1_.json
             经济背景 - 城市经济_chart_1_.html
→ 合并成一个 kind=chart_bundle 的 MaterialItem
```

字段分配：
- `preview_url` → `.svg` 文件路径
- `content_url` → `.html` 文件路径（优先）
- `structured_data` → `.json` 文件解析结果
- `metadata_json.variants` → 各扩展名对应的文件路径

---

## 3. `logical_key`：逻辑标识体系

`logical_key` 是素材包的**语义索引**，格式为点分隔的层级路径。它是 Agent 查找素材时使用的唯一标识符。

### 3.1 完整 `logical_key` 映射表

| 文件名前缀 / 正则 | `logical_key` | 含义 |
|---|---|---|
| `参考案例N_图片_M_*` | `reference.case.N.images` | 第 N 个参考案例的图片集 |
| `参考案例N_缩略图*` | `reference.case.N.thumbnail` | 第 N 个参考案例缩略图 |
| `参考案例N_archdaily*` | `reference.case.N.source` | 第 N 个参考案例原始来源文档 |
| `案例N_评价和分析*` | `reference.case.N.analysis` | 第 N 个参考案例评价分析文档 |
| `经济背景 - 城市经济_chart_N_*` | `economy.city.chart.N` | 城市经济图表 |
| `经济背景 - 产业发展_chart_N_*` | `economy.industry.chart.N` | 产业发展图表 |
| `经济背景 - 消费水平_chart_N_*` | `economy.consumption.chart.N` | 消费水平图表 |
| `场地四至分析*` | `site.boundary.image` | 场地四至分析图 |
| `场地poi*` | `site.poi.table` | 场地 POI 数据表 |
| `场地坐标*` | `site.coordinate.text` | 场地坐标文本 |
| `外部交通站点_POI*` | `site.transport.station.table` | 外部交通站点 POI 表 |
| `外部交通站点*` | `site.transport.station.image` | 外部交通站点图 |
| `外部交通_POI*` | `site.transport.external.table` | 外部交通 POI 表 |
| `外部交通*` | `site.transport.external.image` | 外部交通图 |
| `枢纽站点_POI*` | `site.transport.hub.table` | 枢纽站点 POI 表 |
| `枢纽站点*` | `site.transport.hub.image` | 枢纽站点图 |
| `周边基础设施建设规划_POI*` | `site.infrastructure.plan.table` | 基础设施规划 POI 表 |
| `周边基础设施建设规划*` | `site.infrastructure.plan.image` | 基础设施规划图 |
| `区域开发情况_POI*` | `site.development.table` | 区域开发情况 POI 表 |
| `区域开发情况*` | `site.development.image` | 区域开发情况图 |
| `附近同类型产品分析_POI*` | `site.competitor.table` | 竞品分析 POI 表 |
| `附近同类型产品分析*` | `site.competitor.image` | 竞品分析图 |
| `设计建议书大纲*` | `brief.design_outline` | 设计建议书大纲文本（**关键材料**） |
| `manus提示词*` | `brief.manus_prompt` | Manus 提示词 |
| 其他文件 | `misc.{ext}.{stem}` | 兜底分类 |

### 3.2 `logical_key` 前缀分类

```
reference.*   — 参考案例（图片、缩略图、分析文档）
economy.*     — 经济背景图表（城市、产业、消费）
site.*        — 场地分析（边界、POI、交通、竞品）
brief.*       — 设计文档（设计建议书大纲、提示词）
misc.*        — 未识别文件（兜底）
```

---

## 4. 处理流程：`ingest_local_material_package()`

**入口函数**：`tool/material_pipeline.py :: ingest_local_material_package(project_id, local_path, db)`

**触发方式**：POST `/api/projects/{project_id}/material-packages/ingest-local`

### 4.1 完整处理步骤

```
1. 验证目录存在
2. 查询当前最大 version，新包 version = max_version + 1（首次为 1）
3. 创建 MaterialPackage 记录，status="ingesting"
4. 扫描目录所有文件：
   ├── _group_chart_variants()  → 拆分出 chart_bundle 组 和 普通文件
   ├── 普通文件：每个文件调用 _build_item_payload() → 创建 MaterialItem
   └── Chart Bundle：合并多个变体文件 → 创建一个 MaterialItem
5. build_manifest(items)  → 构建 manifest_json（按 logical_key 聚合）
6. build_summary(items)   → 构建 summary_json（统计信息 + 文本摘要）
7. source_hash = SHA256(所有 item.source_hash 排序后拼接)
8. package.status = "ready"
9. derive_assets_from_items()  → 从 MaterialItem 派生 Asset 记录
10. ensure_project_brief_from_package()  → 自动生成 ProjectBrief
11. project.status = "MATERIAL_READY"
```

### 4.2 `_build_item_payload()` 详解

将单个文件（或 chart bundle）转化为 `MaterialItem` 的字段字典：

```python
{
    "logical_key": "...",          # 由 infer_logical_key() 推断
    "kind": "image|document|spreadsheet|chart_bundle|binary",
    "format": "png|md|xlsx|bundle|...",
    "title": path.stem,
    "source_path": "/绝对路径/文件名.ext",
    "preview_url": "file:///绝对路径/文件名.ext",  # 图片/SVG
    "content_url": "file:///绝对路径/文件名.ext",  # HTML/文本/内容
    "text_content": "前2000字...",               # 文本文件
    "structured_data": {...},                    # JSON/XLSX解析结果
    "tags": ["reference"],                       # logical_key 第一段
    "source_hash": "sha256(文件名+文件大小)",
    "metadata_json": {"basename": "...", "file_name": "..."}
}
```

---

## 5. 数据库模型详解

### 5.1 `MaterialPackage`（表：`material_packages`）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | 主键 |
| `project_id` | UUID FK → projects | 所属项目 |
| `version` | Integer | 同一项目下递增版本号（从 1 开始） |
| `status` | String(50) | `ingesting` → `ready` |
| `source_hash` | String(128) | 所有 item source_hash 的 SHA256 聚合值，用于版本比对 |
| `manifest_json` | JSONB | 素材清单，按 logical_key 聚合（见 5.1.1） |
| `summary_json` | JSONB | 素材统计摘要（见 5.1.2） |
| `created_from` | JSONB | 来源描述，如 `{"type": "local_directory", "local_path": "..."}` |
| `created_at` | DateTime | 创建时间 |
| `updated_at` | DateTime | 更新时间 |

**5.1.1 `manifest_json` 结构**

```json
{
  "logical_keys": ["brief.design_outline", "economy.city.chart.1", "..."],
  "items": [
    {
      "logical_key": "economy.city.chart.1",
      "entries": [
        {
          "id": "uuid",
          "kind": "chart_bundle",
          "format": "bundle",
          "title": "经济背景 - 城市经济_chart_1_",
          "source_path": "/abs/path/file.svg",
          "preview_url": "file:///abs/path/file.svg",
          "content_url": "file:///abs/path/file.html"
        }
      ]
    }
  ]
}
```

**5.1.2 `summary_json` 结构**

```json
{
  "item_count": 42,
  "logical_key_counts": {
    "economy.city.chart.1": 1,
    "reference.case.1.thumbnail": 1,
    "site.boundary.image": 1
  },
  "evidence_snippets": [
    {
      "logical_key": "brief.design_outline",
      "title": "设计建议书大纲",
      "snippet": "武汉市江汉区...（前240字）"
    }
  ],
  "case_count": 3,
  "chart_count": 6
}
```

### 5.2 `MaterialItem`（表：`material_items`）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | 主键 |
| `package_id` | UUID FK → material_packages | 所属素材包 |
| `logical_key` | String(255) **indexed** | 语义索引（见第 3 节） |
| `kind` | String(50) **indexed** | `image` / `document` / `spreadsheet` / `chart_bundle` / `binary` |
| `format` | String(50) **indexed** | 文件格式，如 `png` `md` `xlsx` `bundle` |
| `title` | String(500) | 文件 stem 名 |
| `source_path` | Text | 原始文件绝对路径 |
| `preview_url` | String(1000) | `file://` URI，用于图片预览 |
| `content_url` | String(1000) | `file://` URI，用于内容访问 |
| `text_content` | Text | 文本文件前 2000 字 |
| `structured_data` | JSONB | JSON/XLSX 解析结果 |
| `tags` | JSONB | `[logical_key 第一段]` |
| `source_hash` | String(128) | SHA256(文件名 + 文件大小) |
| `metadata_json` | JSONB | `{"basename": ..., "file_name": ...}` 或 chart variants 路径 |
| `created_at` | DateTime | 创建时间 |
| `updated_at` | DateTime | 更新时间 |

### 5.3 `Asset`（表：`assets`）

Asset 是从 MaterialItem **派生**的渲染就绪资产，是 Composer 直接消费的层。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | 主键 |
| `project_id` | UUID | 所属项目 |
| `package_id` | UUID | 来源素材包（**可为 null，表示非素材包来源**） |
| `source_item_id` | UUID | 来源 MaterialItem ID |
| `logical_key` | String(255) **indexed** | 继承自 MaterialItem |
| `asset_type` | String(100) | 枚举值（见 5.3.1） |
| `subtype` | String(100) | 细分类型，通常等于 `kind` |
| `title` | String(500) | 资产标题 |
| `image_url` | String(1000) | `file://` URI，图片展示用 |
| `data_json` | JSONB | 结构化数据（图表数据、表格数据等） |
| `config_json` | JSONB | 渲染配置（preview_url / content_url / source_path 等） |
| `summary` | Text | 文本摘要（前 500 字） |
| `render_role` | String(100) | `image` / `chart` / `table` / `summary` / `case_card` |
| `is_primary` | Boolean | 该 logical_key 下的主要资产（always true for package-derived） |
| `status` | String(50) | `ready` |
| `source_info` | JSONB | `{"material_item_id": "...", "logical_key": "..."}` |
| `variant` | String(50) | 格式变体，如 `bundle` `png` |
| `version` | Integer | 版本号 |
| `created_at` | DateTime | 创建时间 |
| `updated_at` | DateTime | 更新时间 |

**5.3.1 `asset_type` 枚举值（`schema/common.py :: AssetType`）**

| MaterialItem.kind | MaterialItem.logical_key 前缀 | → Asset.asset_type | render_role |
|---|---|---|---|
| `chart_bundle` | 任意 | `chart` | `chart` |
| `image` | `site.*` | `map` | `image` |
| `image` | 其他 | `image` | `image` |
| `spreadsheet` | 任意 | `kpi_table` | `table` |
| `document` | 任意 | `text_summary` | `summary` |
| 参考案例综合（合成） | `reference.case.N.*` | `case_card` | `case_card` |

**参考案例的特殊处理**：`reference.case.N.thumbnail + source + analysis + images` 会被额外合并成一个 `asset_type=case_card` 的 Asset，`logical_key` 为 `reference.case.N.card`，`data_json` 包含各关联 item 的 ID。

### 5.4 `SlideMaterialBinding`（表：`slide_material_bindings`）

素材绑定结果，记录每个 PPT 页面与素材包中哪些资产绑定。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | 主键 |
| `project_id` | UUID FK → projects | 所属项目 |
| `package_id` | UUID FK → material_packages | 关联素材包 |
| `outline_id` | UUID FK → outlines | 关联大纲（nullable） |
| `slide_id` | UUID FK → slides | 关联页面（nullable，渲染后回填） |
| `slide_no` | Integer **indexed** | 幻灯片序号 |
| `slot_id` | String(100) **indexed** | PPT_BLUEPRINT 中的槽位 ID |
| `version` | Integer | 绑定版本（每次重新绑定递增） |
| `status` | String(50) | `ready` |
| `must_use_item_ids` | JSONB | 必须使用的 MaterialItem UUID 列表 |
| `optional_item_ids` | JSONB | 可选使用的 MaterialItem UUID 列表（目前恒为 `[]`） |
| `derived_asset_ids` | JSONB | **ComposerAgent 直接使用的** Asset UUID 列表 |
| `evidence_snippets` | JSONB | 匹配到的文本证据摘要（每条最多 240 字） |
| `coverage_score` | Float | 覆盖率分数：`(required_count - missing_count) / required_count` |
| `missing_requirements` | JSONB | 未匹配到的 logical_key 模式列表 |
| `binding_reason` | Text | 人读描述："Matched X items and Y assets for slide N" |
| `created_at` | DateTime | 创建时间 |
| `updated_at` | DateTime | 更新时间 |

---

## 6. 素材绑定：`MaterialBindingAgent`

**文件**：`agent/material_binding.py`

### 6.1 入口函数

```python
bind_outline_slides(project_id: UUID, outline_id: UUID, db: Session) → list[SlideMaterialBinding]
```

**完整执行流程**：

```
1. 加载 Outline（spec_json → OutlineSpec）
2. 加载该 project 最新版 MaterialPackage
3. 加载该 Package 下所有 MaterialItem 和 Asset
4. 删除该 outline 下已有的所有旧绑定记录
5. 对 OutlineSpec.slides 中每条 OutlineSlideEntry：
   a. _collect_required_patterns(entry) → 获取该页所需的 logical_key 模式列表
   b. find_matching_items(patterns, items) → 匹配 MaterialItem
   c. find_matching_assets(patterns, assets) → 匹配 Asset
   d. 计算缺失 patterns → coverage_score
   e. 创建 SlideMaterialBinding 记录
6. 返回所有绑定结果列表
```

### 6.2 需求模式收集：`_collect_required_patterns(entry)`

优先使用 `OutlineSlideEntry.required_input_keys`（Outline LLM 输出的字段），若为空则 fallback 到 `PPT_BLUEPRINT` 中该 slot 的 `required_inputs`。

最终调用 `expand_requirement()` 将高层语义键展开为具体的 `logical_key` 模式列表（见第 7 节）。

### 6.3 `coverage_score` 计算

```
coverage_score = (required_count - missing_count) / required_count
```

- `required_count`：需求的 pattern 总数（至少为 1）
- `missing_count`：在 `MaterialItem.logical_key` 中找不到匹配的 pattern 数量
- 结果保留 4 位小数，范围 `[0.0, 1.0]`

---

## 7. 素材解析器：`MaterialResolver`

**文件**：`tool/material_resolver.py`

### 7.1 别名扩展映射：`INPUT_ALIAS_PATTERNS`

将 Blueprint 中的高层输入键名（如 `"chart_gdp"`）展开为具体 `logical_key` 模式：

| 输入键 | 展开为 logical_key 模式 |
|--------|------------------------|
| `brief_doc` | `[]`（不需要素材包匹配） |
| `project_name` | `[]` |
| `web_search_*` | `[]` |
| `map_hub_stations` | `["site.transport.hub.image"]` |
| `map_transport_nodes` | `["site.transport.external.image", "site.transport.station.image"]` |
| `map_infra_plan` | `["site.infrastructure.plan.image"]` |
| `map_site_boundary` | `["site.boundary.image"]` |
| `poi_data` | `["site.poi.table", "site.poi.stats", "site.poi.summary"]` |
| `site_coordinate` | `["site.coordinate.text"]` |
| `case_thumbnail` | `["reference.case.*.thumbnail"]` |
| `case_meta` | `["reference.case.*.analysis", "reference.case.*.card", "reference.case.*.source"]` |
| `chart_gdp` | `["economy.city.chart.*"]` |
| `chart_population` | `["economy.city.chart.*"]` |
| `chart_urbanization` | `["economy.city.chart.*"]` |
| `chart_tertiary` | `["economy.industry.chart.*"]` |
| `chart_industry_structure` | `["economy.industry.chart.*"]` |
| `chart_retail` | `["economy.consumption.chart.*"]` |
| `chart_income_expense` | `["economy.consumption.chart.*"]` |

### 7.2 通配符匹配：`logical_key_matches(pattern, logical_key)`

`*` 在 pattern 中匹配**单个节点**（不含 `.`）：

```python
"reference.case.*.thumbnail"  ↔  "reference.case.3.thumbnail"  # ✅ 匹配
"economy.city.chart.*"        ↔  "economy.city.chart.1"         # ✅ 匹配
"site.boundary.image"         ↔  "site.boundary.image"          # ✅ 精确匹配
"reference.case.*.thumbnail"  ↔  "reference.case.3.images"      # ❌ 不匹配
```

实现：将 `*` 转为 `[^.]+` 正则，然后 `re.fullmatch`。

### 7.3 完整函数说明

| 函数 | 作用 |
|------|------|
| `expand_requirement(req)` | 将 `InputRequirement` 或字符串 key 展开为 logical_key 模式列表 |
| `logical_key_matches(pattern, key)` | 单次模式匹配（支持 `*` 通配） |
| `find_matching_items(patterns, items)` | 从 MaterialItem 列表中找出所有匹配 patterns 的条目 |
| `find_matching_assets(patterns, assets)` | 从 Asset 列表中找出所有匹配 patterns 的条目 |
| `summarize_evidence(items, max_items=5)` | 提取前 N 个匹配条目的文本摘要 |

---

## 8. 自动提取 `ProjectBrief`

**函数**：`tool/material_pipeline.py :: ensure_project_brief_from_package()`

摄入完成后自动从素材包内容提取结构化项目简报。**仅在 ProjectBrief 不存在时执行**。

### 8.1 信息提取逻辑

所有提取都基于 `brief.design_outline` 这个 MaterialItem 的 `text_content`（设计建议书大纲的文本内容）。

**城市/地址提取（`_extract_location()`）**：

```python
# 正则：匹配 "武汉市江汉区" 格式
re.search(r"([\u4e00-\u9fff]{2,6}[市州])([\u4e00-\u9fff]{1,6}[区县市旗])", text[:500])
# province 由城市名查表（内置 40+ 城市→省份映射）
# site_address 尝试提取更长的地址字符串
```

**建筑类型检测（`_detect_building_type()`）**：

在文本中统计各类关键词出现次数，取得分最高的类型：

| 类型 | 关键词 |
|------|--------|
| `public` | 公厕、公共厕所、公共卫生间 |
| `cultural` | 文化、博物、展览、美术馆、图书馆 |
| `education` | 学校、教育、大学、中学、小学、幼儿园 |
| `office` | 办公、写字楼、总部、企业 |
| `residential` | 住宅、居住、公寓、小区、楼盘 |
| `commercial` | 商业、购物、商场、零售、商圈 |
| `hotel` | 酒店、宾馆、度假村、民宿 |
| `healthcare` | 医院、医疗、诊所、康养 |
| `sports` | 体育、运动、体育馆、球场 |
| `mixed` | 综合体、综合、混合（默认兜底） |

**容积率提取（`_extract_far()`）**：

```python
re.search(r"容积率[：:≤≥\s]*([0-9]+\.?[0-9]*)", text)
```

**风格偏好提取（`_extract_style_preferences()`）**：

从以下关键词列表中提取（最多 6 个，避免子串重复）：
`现代简约`、`现代`、`简约`、`中式`、`新中式`、`禅意`、`工业风`、`极简`、`参数化`、`自然`、`生态`、`科技`、`智慧`、`人文`、`传统`、`古典`、`地域`、`文化`、`绿色`、`可持续`

---

## 9. 在各 Agent 中的使用方式

### 9.1 BriefDocAgent（`agent/brief_doc.py`）

消费路径：**优先使用素材包路径，fallback 使用旧 Asset 路径**。

**素材包路径**（新）：
```python
package = 最新版 MaterialPackage
items = 所有 MaterialItem（按 package_id 查询）
message = _build_material_package_message(package, items)
# 内容：package.summary_json + manifest + 所有有 text_content 的条目摘要（前240字）
```

**传统路径**（旧，向后兼容）：
```python
assets = 所有 Asset（text_summary/kpi_table 类型）
message = _build_legacy_assets_message(assets)
```

发送给 LLM 的信息包含：
- `package.summary_json`（统计汇总）
- `package.manifest_json`（素材清单）
- 每个有文本内容的 MaterialItem 的 `logical_key + title + snippet(240字)`

### 9.2 OutlineAgent（`agent/outline.py`）

消费路径：通过在 User Message XML 中注入 `<material_package>` 块。

```xml
<material_package>
  <!-- package.summary_json 的 JSON 序列化 -->
  <!-- 包含：item_count, case_count, chart_count, evidence_snippets -->
</material_package>
```

Outline LLM 需要：
1. 对每个 slot 决策是否使用素材包中的内容
2. 在 `OutlineSlideEntry.required_input_keys` 中指定该页需要的输入键名（如 `"chart_gdp"`, `"case_thumbnail"`）

### 9.3 MaterialBindingAgent（`agent/material_binding.py`）

这是素材包与 PPT 页面连接的核心步骤（见第 6 节详解）。

- 查询最新版 MaterialPackage → MaterialItem × N + Asset × N
- 对每个 OutlineSlideEntry 执行 pattern 匹配
- 产出 SlideMaterialBinding（每页一条记录）

### 9.4 ComposerAgent（`agent/composer.py`）

消费路径：通过 `SlideMaterialBinding.derived_asset_ids` 获取预筛选的 Asset 列表。

```python
binding = 该页对应的 SlideMaterialBinding
asset_ids = binding.derived_asset_ids  # list[UUID str]
assets = [db.get(Asset, uid) for uid in asset_ids]
```

在 Composer 的 User Message 中，这些 Asset 被序列化为 `<available_assets>` XML 块：

```xml
<available_assets>
[
  {"id": "uuid", "type": "chart", "title": "城市经济走势", "image_url": "file:///..."},
  {"id": "uuid", "type": "map", "title": "场地四至分析", "image_url": "file:///..."},
  ...
]
</available_assets>
```

Composer 在生成 `LayoutSpec` 时通过 `"asset:uuid"` 格式引用这些资产：

```json
{
  "content_type": "image",
  "content": "asset:3f2a9b1c-..."
}
```

渲染时，Render Engine 会将 `"asset:uuid"` 解析为实际的 `image_url` 或 `config_json`。

### 9.5 VisualThemeAgent（`agent/visual_theme.py`）

不直接消费 MaterialItem，但消费由素材包自动提取的 `ProjectBrief`，其中 `building_type` 和 `style_preferences` 影响视觉主题的颜色和字体选择。

---

## 10. API 端点

**Router 文件**：`api/routers/material_packages.py`

| 方法 | Path | 说明 |
|------|------|------|
| `POST` | `/api/projects/{project_id}/material-packages/ingest-local` | 摄入本地目录素材包 |
| `GET`  | `/api/projects/{project_id}/material-packages/latest` | 获取最新版 MaterialPackage |
| `GET`  | `/api/projects/{project_id}/material-packages/{package_id}/manifest` | 获取包的 manifest_json |
| `GET`  | `/api/projects/{project_id}/material-packages/{package_id}/items` | 列出包内所有 MaterialItem |
| `POST` | `/api/projects/{project_id}/material-packages/{package_id}/regenerate` | 基于已有素材包重新触发大纲生成流程 |

**`ingest-local` 请求体**：

```json
{
  "local_path": "/path/to/material/directory"
}
```

**`regenerate` 行为**：
- 设置 `project.status = "ASSET_GENERATING"`
- 在后台线程中启动 `_outline_worker`，走完整的 BriefDoc → Outline → Binding → Compose → Render 链路

---

## 11. 数据流全局示意

```
本地目录
  │
  ├─ 普通文件 (image/text/xlsx)
  └─ Chart Bundle (.svg+.json+.html)
          │
          ▼  ingest_local_material_package()
    MaterialPackage
      ├── manifest_json          ← 素材清单索引
      ├── summary_json           ← 统计摘要（传给 BriefDocAgent / OutlineAgent）
      └── source_hash            ← 版本比对指纹
          │
          ├─ MaterialItem × N   ← 每个文件/chart bundle 一条记录
          │     └── logical_key  ← 语义索引
          │
          └─ Asset × N          ← 从 MaterialItem 派生（渲染直用）
                └── asset_type   ← chart/map/image/kpi_table/text_summary/case_card
                    image_url    ← Composer 引用的图片路径

          │
          ▼  ensure_project_brief_from_package()
    ProjectBrief                 ← 自动提取 city/building_type/style_prefs/far
          │
          ├─ BriefDocAgent → BriefDoc
          │       └── 消费 MaterialPackage.summary_json + MaterialItem.text_content
          │
          ├─ OutlineAgent → OutlineSpec（含 required_input_keys）
          │       └── 消费 MaterialPackage.summary_json
          │
          ├─ MaterialBindingAgent → SlideMaterialBinding × N
          │       └── 消费 MaterialItem + Asset，按 logical_key 模式匹配
          │             derived_asset_ids → ComposerAgent 可用资产列表
          │
          └─ ComposerAgent → Slide.spec_json（含 "asset:uuid" 引用）
                  └── 消费 SlideMaterialBinding.derived_asset_ids → Asset
                        image_url 在渲染时被 Render Engine 解析
```

---

## 12. 版本化与增量更新

- 同一项目可以有多个版本的 MaterialPackage（`version` 字段递增）
- `source_hash` 基于所有文件的名称 + 大小计算，可用于判断素材包是否变化
- `SlideMaterialBinding.version` 在每次重新绑定时递增（保留历史记录）
- `regenerate` API 会基于现有素材包重新触发整条生成链路
- 当前系统不做自动差异比对，**每次 ingest 都会创建新的 MaterialPackage 版本**，旧版本不删除

---

## 13. 相关文件索引

| 文件 | 职责 |
|------|------|
| `tool/material_pipeline.py` | 摄入、解析、派生资产、提取 ProjectBrief |
| `tool/material_resolver.py` | logical_key 模式匹配、别名展开 |
| `agent/material_binding.py` | 大纲页与素材包的绑定 |
| `api/routers/material_packages.py` | HTTP API 入口 |
| `db/models/material_package.py` | MaterialPackage ORM 模型 |
| `db/models/material_item.py` | MaterialItem ORM 模型 |
| `db/models/asset.py` | Asset ORM 模型 |
| `db/models/slide_material_binding.py` | SlideMaterialBinding ORM 模型 |
| `schema/material_package.py` | Pydantic 读取 Schema |
| `schema/common.py` | AssetType、ProjectStatus 枚举 |
| `config/ppt_blueprint.py` | PPT_BLUEPRINT（slot required_inputs 定义） |
| `schema/page_slot.py` | InputRequirement 模型 |
