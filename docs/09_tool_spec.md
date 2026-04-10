# 09. Tool / Skill 接口规范

最后更新：2026-04-10

---

## 9.1 Tool 设计约定

所有 Tool 遵循以下规范：
- 纯函数，无副作用（DB 写入在 Agent 层完成，`material_pipeline` 除外——它直接操作 DB Session）
- 明确的输入/输出 Pydantic 模型
- 超时时间显式声明
- 错误类型枚举化，不抛出裸 Exception

```python
# tool/_base.py
from pydantic import BaseModel
from typing import TypeVar, Generic

I = TypeVar("I", bound=BaseModel)
O = TypeVar("O", bound=BaseModel)

class ToolError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False):
        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(message)
```

---

## 9.2 共享基础设施

### OSS 上传客户端

| 项目 | 值 |
|---|---|
| 文件 | `tool/_oss_client.py` |
| 依赖 | `config.settings`；可选 `oss2`（阿里云 OSS） |

Provider 选择逻辑：
- `settings.oss_endpoint` 为空 → mock（写入 `/tmp/ppt_agent_assets/`，返回 `file://` 路径）
- `settings.oss_endpoint` 有值 → 调用阿里云 `oss2` SDK

```python
def upload_bytes(data: bytes, key: str, content_type: str = "image/png") -> str:
    """上传字节流到 OSS（或 mock 文件系统），返回可访问 URL。"""
```

### AMap REST 客户端

| 项目 | 值 |
|---|---|
| 文件 | `tool/site/_amap_client.py` |
| 依赖 | `httpx`、`config.settings` |
| timeout | 10s |

所有场地分析 Tool 共用此模块发起高德地图 HTTP 请求。

```python
async def amap_get(endpoint: str, params: dict) -> dict:
    """
    发起 GET 请求到高德 REST API。
    API 级错误或 HTTP 异常均抛出 ToolError。
    错误类型：AMAP_TIMEOUT / AMAP_HTTP_ERROR / AMAP_NETWORK_ERROR / AMAP_API_ERROR / API_LIMIT_EXCEEDED
    """
```

---

## 9.3 项目输入类 Tool (`tool/input/`)

### extract_project_brief

| 项目 | 值 |
|---|---|
| 文件 | `tool/input/extract_brief.py` |
| 类型 | async |
| timeout | 30s（LLM 调用） |
| model | FAST_MODEL |

从自然语言中提取 `ProjectBriefData`，支持多轮对话（将新提取字段合并到已有 brief）。自动在"三指标中有两个"时调用 `compute_far_metrics` 补齐第三个。

```python
class ExtractBriefInput(BaseModel):
    raw_text: str
    existing_brief: Optional[dict] = None

class ExtractBriefOutput(BaseModel):
    extracted: ProjectBriefData
    missing_fields: list[str]
    is_complete: bool
    follow_up: Optional[str] = None
    confirmation_summary: Optional[str] = None

async def extract_project_brief(input: ExtractBriefInput) -> ExtractBriefOutput: ...
```

---

### validate_project_brief

| 项目 | 值 |
|---|---|
| 文件 | `tool/input/validate_brief.py` |
| 类型 | sync |
| timeout | 1s（纯本地校验，无 LLM） |

校验 `ProjectBriefData` 完整性：必填字段检查、三指标至少两项、建筑面积异常值警告、容积率范围警告。

```python
class ValidateBriefInput(BaseModel):
    brief: ProjectBriefData

class ValidateBriefOutput(BaseModel):
    is_valid: bool
    errors: list[str]       # 字段级错误
    warnings: list[str]     # 非阻断性警告

def validate_project_brief(input: ValidateBriefInput) -> ValidateBriefOutput: ...
```

---

### compute_far_metrics

| 项目 | 值 |
|---|---|
| 文件 | `tool/input/compute_far.py` |
| 类型 | sync |
| timeout | 0.1s |

根据建筑面积、用地面积、容积率三者中的任意两个计算第三个。不足两个时抛出 `ToolError("INSUFFICIENT_METRICS")`。

```python
class ComputeFARInput(BaseModel):
    gross_floor_area: Optional[float] = None
    site_area: Optional[float] = None
    far: Optional[float] = None

class ComputeFAROutput(BaseModel):
    gross_floor_area: float
    site_area: float
    far: float
    computed_field: str     # 哪个字段是计算得出的

def compute_far_metrics(input: ComputeFARInput) -> ComputeFAROutput: ...
```

---

### geocode_address

| 项目 | 值 |
|---|---|
| 文件 | `tool/input/geocode.py` |
| 类型 | async |
| timeout | 5s（高德地图 API 调用） |
| 错误类型 | ADDRESS_NOT_FOUND / NETWORK_ERROR |

调用高德地图地理编码 API，将地址文本转换为经纬度坐标，附带格式化地址和省市区信息。置信度从高德返回的 `level` 字段推算。

```python
class GeocodeInput(BaseModel):
    address: str
    city: Optional[str] = None

class GeocodeOutput(BaseModel):
    longitude: float
    latitude: float
    formatted_address: str
    province: str
    city: str
    district: str
    confidence: float   # 0~1

async def geocode_address(input: GeocodeInput) -> GeocodeOutput: ...
```

---

### normalize_polygon

| 项目 | 值 |
|---|---|
| 文件 | `tool/input/normalize_polygon.py` |
| 类型 | sync |
| timeout | 0.1s（纯本地计算） |

验证并标准化 GeoJSON Polygon（确保闭环），使用 Shoelface 公式计算面积（平面近似）和 Haversine 球面周长，返回质心坐标。

```python
class NormalizePolygonInput(BaseModel):
    geojson: dict   # GeoJSON Polygon

class NormalizePolygonOutput(BaseModel):
    geojson: dict
    area_sqm: float
    perimeter_m: float
    centroid_lng: float
    centroid_lat: float

def normalize_polygon(input: NormalizePolygonInput) -> NormalizePolygonOutput: ...
```

---

## 9.4 场地分析类 Tool (`tool/site/`)

### poi_retrieval

| 项目 | 值 |
|---|---|
| 文件 | `tool/site/poi_retrieval.py` |
| 类型 | async |
| timeout | 10s |
| 外部依赖 | 高德 `/v3/place/around` API |

按分类（教育/医疗/商业/交通/文化/公园）检索指定坐标周边 POI。API Key 未配置时返回 mock 数据。

```python
class POIRetrievalInput(BaseModel):
    longitude: float
    latitude: float
    radius_meters: int = 1000
    categories: list[str] = ["教育", "医疗", "商业", "交通", "文化", "公园"]

class POIItem(BaseModel):
    name: str
    category: str
    distance_meters: float
    longitude: float
    latitude: float

class POIRetrievalOutput(BaseModel):
    pois: list[POIItem]
    summary: str            # "周边1km内有3所学校、2个地铁站..."
    by_category: dict[str, list[POIItem]] = {}

async def poi_retrieval(input: POIRetrievalInput) -> POIRetrievalOutput: ...
```

---

### mobility_analysis

| 项目 | 值 |
|---|---|
| 文件 | `tool/site/mobility_analysis.py` |
| 类型 | async |
| timeout | 15s |
| 外部依赖 | 高德 `/v3/place/around` API（type 150200 地铁 / 150300 公交） |

分析场地交通可达性：最近地铁站（距离 + 线路）、公交线路数量、交通便利性评分（0~100）。API Key 未配置时返回 mock 数据。

```python
class MobilityAnalysisInput(BaseModel):
    longitude: float
    latitude: float
    radius_meters: int = 1500

class MetroStation(BaseModel):
    name: str
    distance_meters: float
    lines: list[str] = []

class BusLine(BaseModel):
    name: str
    stop_name: str
    distance_meters: float

class MobilityAnalysisOutput(BaseModel):
    metro_stations: list[MetroStation]
    bus_lines: list[BusLine]
    traffic_score: int          # 0-100
    summary: str

async def mobility_analysis(input: MobilityAnalysisInput) -> MobilityAnalysisOutput: ...
```

---

## 9.5 参考案例类 Tool (`tool/reference/`)

### Embedding 生成

| 项目 | 值 |
|---|---|
| 文件 | `tool/reference/_embedding.py` |
| 类型 | async（`get_embedding`）/ sync（`get_embedding_sync`） |
| Provider | mock（默认）/ openai / voyage / qwen |
| 向量维度 | 1536 |

多 Provider 支持的 embedding 生成。mock 模式通过文本 hash 生成确定性伪向量，无需 API Key，适合本地开发。

```python
def build_embedding_text(case: dict) -> str:
    """将案例字段拼接为 embedding 输入文本。"""

def build_query_text(brief: dict) -> str:
    """将 ProjectBriefData dict 转为检索文本。"""

async def get_embedding(text: str) -> list[float]:
    """生成 embedding 向量。Provider 通过 settings.embedding_provider 配置。"""

def get_embedding_sync(text: str) -> list[float]:
    """同步版本（供种子脚本使用）。"""
```

---

### search_cases（参考案例搜索）

| 项目 | 值 |
|---|---|
| 文件 | `tool/reference/search.py` |
| 类型 | sync（内部操作 DB Session） |
| timeout | 5s |

优先使用 pgvector 余弦相似度检索；向量搜索失败或未提供 embedding 时回退到 building_type + tag 过滤。

```python
class CaseSearchInput(BaseModel):
    building_type: str
    style_tags: list[str] = []
    feature_tags: list[str] = []
    scale_category: Optional[str] = None
    top_k: int = 10
    exclude_ids: list[str] = []
    query_embedding: Optional[list[float]] = None   # None -> tag-only search

class CaseSearchOutput(BaseModel):
    cases: list[ReferenceCase]
    search_vector: list[float] = []   # echo back for debugging
    used_vector_search: bool

def search_cases(input: CaseSearchInput, db: Session) -> CaseSearchOutput: ...
```

---

### rerank_cases（案例重排序）

| 项目 | 值 |
|---|---|
| 文件 | `tool/reference/rerank.py` |
| 类型 | async |
| timeout | 20s（LLM 调用） |
| model | FAST_MODEL |

LLM 驱动的案例重排序。将候选案例列表按与项目需求的匹配度重排，返回推荐理由。候选数量 <= top_k 时直接返回；LLM 失败时回退到原始顺序。

```python
class RerankInput(BaseModel):
    cases: list[ReferenceCase]
    brief: dict     # ProjectBriefData as dict
    top_k: int = 8

class RerankOutput(BaseModel):
    cases: list[ReferenceCase]
    recommendation_reason: str
    case_notes: dict[str, str] = {}

async def rerank_cases(input: RerankInput) -> RerankOutput: ...
```

---

### summarise_preferences（偏好总结）

| 项目 | 值 |
|---|---|
| 文件 | `tool/reference/preference_summary.py` |
| 类型 | async |
| timeout | 20s（LLM 调用） |
| model | FAST_MODEL |

分析用户选择的参考案例及勾选的标签，总结设计偏好，为大纲 Agent 提供叙事方向。LLM 失败时回退到标签频率统计。

```python
class PreferenceSummaryInput(BaseModel):
    selections: list[dict]  # [{case_id, case_title, selected_tags, selection_reason}]
    brief: dict

class PreferenceSummaryOutput(BaseModel):
    dominant_styles: list[str]
    dominant_features: list[str]
    narrative_hint: str
    design_keywords: list[str] = []

async def summarise_preferences(input: PreferenceSummaryInput) -> PreferenceSummaryOutput: ...
```

---

## 9.6 资产生成类 Tool (`tool/asset/`)

### chart_generation

| 项目 | 值 |
|---|---|
| 文件 | `tool/asset/chart_generation.py` |
| 类型 | sync |
| timeout | 10s（本地 matplotlib 渲染） |
| 依赖 | matplotlib；radar 图需 numpy |

支持 bar / line / pie / radar 四种图表类型，内置 4 套配色方案（primary / secondary / monochrome / warm）。line 图支持多系列格式。radar 点数不足 3 时自动降级为 bar 图。

```python
class ChartGenerationInput(BaseModel):
    chart_type: str             # bar / line / pie / radar
    title: str
    data: list[dict]            # [{label, value} | {x, y}]
    x_label: Optional[str] = None
    y_label: Optional[str] = None
    color_scheme: str = "primary"
    width_px: int = 800
    height_px: int = 500

class ChartGenerationOutput(BaseModel):
    image_bytes: bytes
    image_format: str = "png"
    data_json: dict

def chart_generation(input: ChartGenerationInput) -> ChartGenerationOutput: ...
```

---

### map_annotation

| 项目 | 值 |
|---|---|
| 文件 | `tool/asset/map_annotation.py` |
| 类型 | async |
| timeout | 15s（高德静态地图 API） |
| 错误类型 | AMAP_TIMEOUT / AMAP_MAP_ERROR |

通过高德静态地图 API 生成带标注的地图 PNG。最多 20 个标注点，标注标签最长 8 字符。支持 light / dark / satellite 地图样式。API Key 未配置时使用 matplotlib 生成占位图。

```python
class AnnotationItem(BaseModel):
    longitude: float
    latitude: float
    label: str = ""
    color: str = "blue"         # red / blue / green / yellow / purple
    icon: Optional[str] = None

class MapAnnotationInput(BaseModel):
    center_lng: float
    center_lat: float
    zoom: int = 14
    width_px: int = 800
    height_px: int = 600
    annotations: list[AnnotationItem] = []
    map_style: str = "light"    # light / dark / satellite

class MapAnnotationOutput(BaseModel):
    image_bytes: bytes
    image_format: str = "png"

async def map_annotation(input: MapAnnotationInput) -> MapAnnotationOutput: ...
```

---

## 9.7 幻灯片辅助 Tool (`tool/slide/`)

### check_content_density

| 项目 | 值 |
|---|---|
| 文件 | `tool/slide/content_fit.py` |
| 类型 | sync |
| timeout | 0.1s（纯本地计算） |

检查单页幻灯片内容密度是否在约束范围内。统计文字字数、图片数、bullet 条数，与 `SlideSpec.constraints` 上限比对，输出密度等级（low / medium / high / overflow）和改进建议。

```python
class ContentDensityResult(BaseModel):
    density_level: str          # low / medium / high / overflow
    total_text_chars: int
    total_images: int
    total_bullets: int
    exceeds_text_limit: bool
    exceeds_image_limit: bool
    exceeds_bullet_limit: bool
    recommendations: list[str]

def check_content_density(spec: SlideSpec) -> ContentDensityResult: ...
```

---

## 9.8 审查类 Tool (`tool/review/`)

### layout_lint

| 项目 | 值 |
|---|---|
| 文件 | `tool/review/layout_lint.py` |
| 类型 | sync |
| timeout | 0.1s（纯规则检查） |
| 适配 | 同时支持新版 `LayoutSpec` 和旧版 `SlideSpec` |

纯规则驱动的版面检查。检测规则包括：

| 规则码 | 说明 |
|---|---|
| TEXT_OVERFLOW | heading 超 40 字 / 正文超 300 字 |
| BULLET_OVERFLOW | bullet 超 5 条 |
| MISSING_REQUIRED_BLOCK | cover-hero 缺 hero_image / full-bleed 缺图片 |
| GRID_UNDERFILLED | grid 单元填充不足 |
| TIMELINE_UNDERFILLED | timeline 节点数不足 |
| IMAGE_COUNT_EXCEEDED | 视觉 block 超 4 个 |
| EMPTY_SLIDE | 页面无有效内容 |
| TITLE_TOO_LONG | 标题超 25 字 |
| KEY_MESSAGE_MISSING | key_message 为空 |
| VISUAL_SOURCE_MISSING | 视觉 block 无 source_refs |
| HEADING_MISSING | 缺少标题/副标题 block |
| NO_REGION_BINDINGS | 无内容区域 |
| EXCESSIVE_DENSITY | 全页文字超 900 字 |

```python
class LayoutLintOutput(BaseModel):
    issues: list[ReviewIssue]
    pass_count: int
    fail_count: int

def layout_lint(spec: LayoutSpec | SlideSpec) -> LayoutLintOutput: ...
```

---

### execute_repair / build_repair_plan_from_issues

| 项目 | 值 |
|---|---|
| 文件 | `tool/review/repair_plan.py` |
| 类型 | sync |
| 适配 | 同时支持新版 `LayoutSpec` 和旧版 `SlideSpec` |

根据审查报告自动执行可修复的修复动作。可自动执行的动作类型：

| action_type | 效果 |
|---|---|
| truncate_text | 截断 block 文本到上限并追加"..." |
| truncate_bullets | 截断 bullet 列表到上限 |
| truncate_title | 截断标题 |
| remove_extra_images | 移除多余图片 block |
| fill_footer_defaults | 委托给调用方填充 |
| replace_client_name | 替换错误的客户名 |

```python
def execute_repair(
    spec: LayoutSpec | SlideSpec,
    report: ReviewReport,
) -> tuple[LayoutSpec | SlideSpec, list[str]]:
    """执行修复计划，返回修复后的 spec 和操作日志。"""

def build_repair_plan_from_issues(issues: list[Any]) -> list[RepairAction]:
    """从 ReviewIssue 列表中生成可自动执行的 RepairAction 列表。"""
```

---

### semantic_check

| 项目 | 值 |
|---|---|
| 文件 | `tool/review/semantic_check.py` |
| 类型 | async |
| timeout | 30s（LLM 调用） |
| model | CRITIC_MODEL（失败时回退 FAST_MODEL） |
| 适配 | 同时支持新版 `LayoutSpec` 和旧版 `SlideSpec` |

LLM 驱动的语义一致性检查。校验幻灯片内容与项目信息的匹配度。检测类别：

| 规则码 | 说明 |
|---|---|
| S001 | METRIC_INCONSISTENCY — 指标数据不一致 |
| S004 | UNSUPPORTED_CLAIM — 无依据的声明 |
| S005 | STYLE_TERM_WRONG — 风格术语错误 |
| S006 | MISSING_KEY_MESSAGE_SUPPORT — 核心论点缺乏支撑 |
| S007 | CLIENT_NAME_WRONG — 客户名称错误（可自动修复） |

```python
class SemanticCheckInput(BaseModel):
    spec: LayoutSpec | SlideSpec
    brief: dict

class SemanticCheckOutput(BaseModel):
    issues: list[ReviewIssue] = []
    repair_actions: list[RepairAction] = []

async def semantic_check(input: SemanticCheckInput) -> SemanticCheckOutput: ...
```

---

## 9.9 素材管道 Tool (`tool/material_pipeline.py`)

### ingest_local_material_package

| 项目 | 值 |
|---|---|
| 文件 | `tool/material_pipeline.py` |
| 类型 | sync（直接操作 DB Session） |
| 注意 | 此 Tool 非纯函数，直接写入 MaterialPackage / MaterialItem / Asset / ProjectBrief |

素材包完整摄入管道。扫描本地目录，按文件名规则推断 `logical_key`，分组经济图表变体，将所有文件注册为 `MaterialItem`，派生 `Asset`（图表/图片/表格/文本/案例卡片），并自动从素材中提取 `ProjectBrief`。

**入口函数：**

```python
def ingest_local_material_package(
    project_id,
    local_path: str,
    db: Session,
) -> MaterialPackage:
    """
    扫描 local_path 目录，生成 MaterialPackage + MaterialItem + Asset + ProjectBrief。
    目录不存在时抛出 ValueError。
    """
```

**关键内部函数：**

```python
def infer_logical_key(path: Path) -> str:
    """
    根据文件名推断逻辑键。
    匹配规则：参考案例图片/缩略图/source/analysis、经济背景图表、
    场地分析系列（四至/POI/交通/基建/竞品等）、设计建议书大纲。
    未匹配时返回 misc.{ext}.{stem}。
    """

def derive_assets_from_items(
    project_id, package_id,
    items: list[MaterialItem],
    db: Session,
) -> list[Asset]:
    """
    从 MaterialItem 列表派生 Asset 记录。
    chart_bundle -> CHART, image -> MAP|IMAGE, spreadsheet -> KPI_TABLE,
    document -> TEXT_SUMMARY。
    额外将同一参考案例的缩略图/source/analysis/images 聚合为 CASE_CARD Asset。
    """

def ensure_project_brief_from_package(
    project_id, project_name: str,
    summary_json: dict, db: Session,
    items: list[MaterialItem] | None = None,
) -> ProjectBrief:
    """
    若项目尚无 ProjectBrief，则从素材包中自动提取并创建。
    从设计建议书大纲中提取城市/省份/区县/地址/建筑类型/风格/容积率。
    """

def build_manifest(items: list[MaterialItem]) -> dict:
    """按 logical_key 分组，生成素材包清单 JSON。"""

def build_summary(items: list[MaterialItem]) -> dict:
    """统计素材包摘要：条目数、logical_key 分布、案例数、图表数、证据片段。"""
```

---

## 9.10 素材解析 Tool (`tool/material_resolver.py`)

### expand_requirement / find_matching_items / find_matching_assets

| 项目 | 值 |
|---|---|
| 文件 | `tool/material_resolver.py` |
| 类型 | sync |
| 依赖 | `schema.page_slot.InputRequirement`、`db.models.asset.Asset`、`db.models.material_item.MaterialItem` |

逻辑键匹配系统。将页面 slot 的抽象需求（如 `map_hub_stations`、`chart_gdp`）展开为具体的 `logical_key` 通配模式，然后在素材库中匹配对应的 MaterialItem 或 Asset。

**别名映射表（部分）：**

| 抽象需求 | 展开为 logical_key 模式 |
|---|---|
| `map_hub_stations` | `site.transport.hub.image` |
| `map_transport_nodes` | `site.transport.external.image`, `site.transport.station.image` |
| `poi_data` | `site.poi.table`, `site.poi.stats`, `site.poi.summary` |
| `case_thumbnail` | `reference.case.*.thumbnail` |
| `chart_gdp` | `economy.city.chart.*` |

```python
def expand_requirement(requirement: InputRequirement | str) -> list[str]:
    """将页面 slot 需求展开为 logical_key 通配模式列表。"""

def logical_key_matches(pattern: str, logical_key: str) -> bool:
    """判断 logical_key 是否匹配通配模式（* 匹配单段）。"""

def find_matching_items(
    patterns: Iterable[str],
    items: Iterable[MaterialItem],
) -> list[MaterialItem]:
    """在 MaterialItem 集合中查找匹配给定模式的条目。"""

def find_matching_assets(
    patterns: Iterable[str],
    assets: Iterable[Asset],
) -> list[Asset]:
    """在 Asset 集合中查找匹配给定模式的条目。"""

def summarize_evidence(
    items: list[MaterialItem],
    max_items: int = 5,
) -> list[str]:
    """提取素材条目的文本摘要片段（用于 LLM 上下文）。"""
```

---

## 9.11 Tool 总览

| # | 模块 | 函数 | sync/async | 外部依赖 | timeout |
|---|---|---|---|---|---|
| 1 | `tool/_oss_client.py` | `upload_bytes` | sync | oss2（可选） | — |
| 2 | `tool/site/_amap_client.py` | `amap_get` | async | 高德 API | 10s |
| 3 | `tool/input/extract_brief.py` | `extract_project_brief` | async | LLM | 30s |
| 4 | `tool/input/validate_brief.py` | `validate_project_brief` | sync | 无 | 1s |
| 5 | `tool/input/compute_far.py` | `compute_far_metrics` | sync | 无 | 0.1s |
| 6 | `tool/input/geocode.py` | `geocode_address` | async | 高德 API | 5s |
| 7 | `tool/input/normalize_polygon.py` | `normalize_polygon` | sync | 无 | 0.1s |
| 8 | `tool/site/poi_retrieval.py` | `poi_retrieval` | async | 高德 API | 10s |
| 9 | `tool/site/mobility_analysis.py` | `mobility_analysis` | async | 高德 API | 15s |
| 10 | `tool/reference/_embedding.py` | `get_embedding` | async | OpenAI/Voyage/Qwen（可选） | — |
| 11 | `tool/reference/search.py` | `search_cases` | sync | pgvector（可选） | 5s |
| 12 | `tool/reference/rerank.py` | `rerank_cases` | async | LLM | 20s |
| 13 | `tool/reference/preference_summary.py` | `summarise_preferences` | async | LLM | 20s |
| 14 | `tool/asset/chart_generation.py` | `chart_generation` | sync | matplotlib | 10s |
| 15 | `tool/asset/map_annotation.py` | `map_annotation` | async | 高德静态地图 API | 15s |
| 16 | `tool/slide/content_fit.py` | `check_content_density` | sync | 无 | 0.1s |
| 17 | `tool/review/layout_lint.py` | `layout_lint` | sync | 无 | 0.1s |
| 18 | `tool/review/repair_plan.py` | `execute_repair` | sync | 无 | — |
| 19 | `tool/review/semantic_check.py` | `semantic_check` | async | LLM | 30s |
| 20 | `tool/material_pipeline.py` | `ingest_local_material_package` | sync | DB Session | — |
| 21 | `tool/material_resolver.py` | `expand_requirement` / `find_matching_items` / `find_matching_assets` | sync | 无 | — |
