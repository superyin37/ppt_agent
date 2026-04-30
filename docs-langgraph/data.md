---
title: 数据模型与输入契约
audience: 第一次读项目的开发者 / 维护者
read_time: 10 分钟
prerequisites: glossary.md
last_verified_against: f083adb
---

# 数据模型与输入契约

> **读完这篇，你应该能回答：**
> - 输入文件如何被索引成语义键？
> - `ProjectState`、reducer、`SlideSpec` 分别承担什么职责？
> - `parse_outline` 当前是否调用 LLM？
> - `SlideSpec.data` 为什么是常见 bug 来源？

> **关联文档：**
> - 上一篇：[pipeline.md](pipeline.md)
> - 下一篇：[templates.md](templates.md)
> - 术语：[glossary.md](glossary.md)

PPT-Maker 的核心数据流是：

```text
输入文件
  -> AssetIndex
  -> UserInput / SiteCoords / DesignOutline / POIData
  -> ProjectState
  -> SlideSpec
  -> Jinja2 component
```

本文解释这些数据结构，以及节点之间如何通过 `ProjectState` 合并结果。

## 输入目录

每个项目 case 一个目录：

```text
data/case_<id>/
```

示例：

```text
data/case_688/
  用户输入_688.md
  场地坐标_688.md
  设计建议书大纲_688.md
  场地poi_688.xlsx
  GDP及其增速_688.png
  参考案例1_详情_688.md
  参考案例1_缩略图_1_688.png
```

## 语义键索引

实现：[ppt_maker/assets.py](../ppt_maker/assets.py)

文件名会去掉末尾 `_<id>` 或 `_<id>_<n>`，剩余部分作为语义键：

```python
_SUFFIX_RE = re.compile(r"_\d+(?:_\d+)?$")
```

| 文件 | 语义键 | 桶 |
|---|---|---|
| `设计建议书大纲_688.md` | `设计建议书大纲` | `docs` |
| `GDP及其增速_688.png` | `GDP及其增速` | `images` |
| `场地poi_688.xlsx` | `场地poi` | `xlsx` |
| `参考案例1_缩略图_1_688.png` | `参考案例1_缩略图` | `images` |

扫描结果是 `AssetIndex`：

```python
class AssetIndex(BaseModel):
    project_id: str
    case_dir: str
    images: dict[str, str]
    docs: dict[str, str]
    xlsx: dict[str, str]
```

节点不直接猜路径，而是通过 `assets.images["GDP及其增速"]` 这种语义键访问文件。

## 必需和可选输入

| 输入 | 语义键 | 用途 | 缺失后果 |
|---|---|---|---|
| 用户输入 | `用户输入` | 封面元信息、设计任务书 | 字段为空 |
| 坐标 | `场地坐标` | 区位和地址信息 | 坐标为空 |
| 设计大纲 | `设计建议书大纲` | 多数页面内容来源 | 大量页面缺失或占位 |
| POI 表 | `场地poi` | 第 18、21 页和部分区位分析 | POI 页空表或占位 |
| 统计图 PNG | 多个图片语义键 | 经济/区位/场地图页 | 对应图片缺失 |
| 参考案例 md/png | `参考案例N_*` | 第 23-25 页 | 案例页内容变少 |

## `用户输入` 格式

由 [ppt_maker/nodes/load.py](../ppt_maker/nodes/load.py) 解析：

```markdown
| 建筑类型   | 住宅           |
| 总建筑面积 | 200000 m²      |
| 用地面积   | 128795 m²      |
| 容积率     | 1.55           |
| 设计风格   | 极简           |
```

生成：

```python
class UserInput(BaseModel):
    building_type: str = ""
    total_gfa_sqm: float = 0.0
    site_area_sqm: float = 0.0
    far: float = 0.0
    design_style: str = ""
```

## `场地坐标` 格式

```markdown
经度: 117.123
纬度: 39.456
地址: 天津市红桥区...
省份: 天津
```

生成：

```python
class SiteCoords(BaseModel):
    lng: float = 0.0
    lat: float = 0.0
    address: str = ""
    province: str = ""
```

## `设计建议书大纲`

由 [ppt_maker/nodes/outline.py](../ppt_maker/nodes/outline.py) 解析为 `DesignOutline`：

```python
class DesignOutline(BaseModel):
    project_title: str
    policies: list[Policy]
    industry_policies: list[IndustryPolicy]
    upper_plans: list[UpperPlan]
    cultural_features: list[CulturalFeature]
    economy_summary: dict[str, str]
    location_analysis: LocationAnalysis
    reference_cases: list[ReferenceCase]
    design_strategies: list[DesignStrategy]
    concept_schemes: list[ConceptSchemeSeed]
```

大纲中比较重要的章节：

| 章节 | 解析目标 |
|---|---|
| `政策分析` | `Policy[]` |
| `产业政策引导` | `IndustryPolicy[]` |
| `上位规划条件` | `UpperPlan[]` |
| `文化特征` | `CulturalFeature[]` |
| `经济背景 - 城市经济/产业发展/消费水平` | `economy_summary` |
| `区位分析`、`交通分析`、`场地四至分析` | `LocationAnalysis` |
| 参考案例相关段落和 sibling md | `ReferenceCase[]` |
| `设计策略` | `DesignStrategy[]` |
| `设计愿景`、`方案鸟瞰图`、`方案人视图` | `ConceptSchemeSeed[]` |

解析逻辑完全由正则、markdown 表格和编号项抽取完成，当前实现**零 LLM 调用**。关键 helper 包括 `_split_sections()`、`_parse_table()`、`_numbered_items()` 和 `_bold_field()`，入口是 [outline.py:285](../ppt_maker/nodes/outline.py#L285)。

`DoubaoClient` 虽然存在，但没有被 `parse_outline` 或其他节点调用；它是后续扩展预留。外部 AI 当前只出现在 RunningHub 图像生成，详见 [llm-and-external-services.md](llm-and-external-services.md)。

## POI Excel

由 [ppt_maker/nodes/poi.py](../ppt_maker/nodes/poi.py) 解析为：

```python
class POIData(BaseModel):
    infrastructure: list[POIRow]
    external_transit: list[POIRow]
    competitors: list[POIRow]
    hubs: list[POIRow]
    regional_dev: list[POIRow]
```

`POIRow` 字段：

```text
name / category / address / lng / lat / distance_m / tag
```

Excel sheet 名称需要匹配节点里的 `SHEET_MAP`。列名按语义取值，多余列会忽略。

## `ProjectState`

入口：[ppt_maker/state.py](../ppt_maker/state.py)

`ProjectState` 是 LangGraph 中流转的总状态。它分为四类字段。

### CLI 注入字段

| 字段 | 含义 |
|---|---|
| `project_id` | case id |
| `case_dir` | `data/case_<id>` |
| `output_dir` | `output/case_<id>` |
| `template` | 模板名 |
| `dry_run` | 是否跳过外部 API |

### 加载阶段字段

| 字段 | 写入节点 |
|---|---|
| `assets` | `load_assets` |
| `user_input` | `load_assets` |
| `site_coords` | `load_assets` |
| `outline` | `parse_outline` |
| `poi_data` | `poi_parser` |

这些字段没有 reducer，默认应只由一个节点写入。

### reducer 合并字段

| 字段 | reducer | 用途 |
|---|---|---|
| `slide_specs` | `merge_dict` | 多节点并行写页面 |
| `charts` | `merge_dict` | 图表路径 |
| `generated_images` | `merge_dict` | 生成图或占位图路径 |
| `search_cache` | `merge_dict` | Tavily 搜索结果 |
| `errors` | `operator.add` | 节点错误列表 |

`merge_dict` 是浅合并：右侧 key 覆盖左侧 key。正常情况下不同节点写不同页码，不会冲突。

### 终态字段

| 字段 | 写入节点 |
|---|---|
| `output_html` | `render_html` |

## `SlideSpec`

`SlideSpec` 是项目里最重要的中间格式：

```python
class SlideSpec(BaseModel):
    page: int
    component: ComponentKind
    title: str = ""
    subtitle_en: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None
```

字段含义：

| 字段 | 含义 |
|---|---|
| `page` | 页码，当前固定 1-40 |
| `component` | 使用哪个模板组件 |
| `title` | 页面标题 |
| `subtitle_en` | 英文副标题，可空 |
| `data` | 组件需要的结构化数据 |
| `notes` | 备注，可空 |

允许的 `component`：

```text
cover
toc
transition
policy_list
chart
table
image_grid
content_bullets
case_card
concept_scheme
ending
```

渲染时，`component="chart"` 会对应：

```text
templates/<template>/components/chart.html.j2
```

各组件的 `data` 形状见 [templates.md](templates.md)。

需要特别注意：`data` 是 `dict[str, Any]`，Pydantic 不校验内部字段。模板使用 `ChainableUndefined`，字段名写错或层级写错时通常只会渲染为空，不会抛异常。这是模板排查里最常见的问题之一，具体见 [templates.md](templates.md) 和 [debugging.md](debugging.md)。
