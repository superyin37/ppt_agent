# 04. FastAPI 接口定义

> 最后更新：2026-04-10

---

## 4.1 统一响应格式

```python
# api/response.py
from typing import TypeVar, Generic, Optional
from pydantic import BaseModel

T = TypeVar("T")

class APIResponse(BaseModel, Generic[T]):
    success: bool = True
    data: Optional[T] = None
    error: Optional[str] = None
    error_code: Optional[str] = None

class PagedResponse(BaseModel, Generic[T]):
    success: bool = True
    data: list[T] = []
    total: int = 0
    page: int = 1
    page_size: int = 20
```

---

## 4.2 业务异常类

```python
# api/exceptions.py
class AppError(Exception):
    error_code: str
    message: str
    http_status: int
    detail: dict
    retryable: bool

# === 用户侧错误（4xx）===
ProjectNotFoundError       # 404  PROJECT_NOT_FOUND
BriefIncompleteError       # 422  BRIEF_INCOMPLETE
InvalidStatusTransitionError # 409 INVALID_STATUS_TRANSITION
CaseNotFoundError          # 404  CASE_NOT_FOUND
SelectionTooFewError       # 422  SELECTION_TOO_FEW
OutlineNotConfirmedError   # 409  OUTLINE_NOT_CONFIRMED
RepairLimitExceededError   # 409  REPAIR_LIMIT_EXCEEDED
InvalidGeoJSONError        # 422  INVALID_GEOJSON

# === 系统侧错误（5xx）===
LLMParseError              # 502  LLM_PARSE_FAILED       retryable
LLMRateLimitError          # 503  LLM_RATE_LIMITED       retryable
RenderTimeoutError         # 504  RENDER_TIMEOUT         retryable
OSSUploadError             # 500  OSS_UPLOAD_FAILED      retryable
GeocodeFailedError         # 502  GEOCODE_FAILED
```

---

## 4.3 路由注册

```python
# main.py
app = FastAPI(title="PPT Agent API", version="0.1.0")

app.include_router(projects.router,           prefix="/projects",  tags=["projects"])
app.include_router(sites.router,              prefix="/projects",  tags=["sites"])
app.include_router(references.router,         prefix="/projects",  tags=["references"])
app.include_router(assets.router,             prefix="/projects",  tags=["assets"])
app.include_router(material_packages.router,  prefix="/projects",  tags=["material-packages"])
app.include_router(outlines.router,           prefix="/projects",  tags=["outlines"])
app.include_router(slides.router,             prefix="/projects",  tags=["slides"])
app.include_router(render.router,             prefix="/projects",  tags=["render"])
app.include_router(exports.router,            prefix="/projects",  tags=["exports"])

# 静态文件挂载
app.mount("/slides-output", StaticFiles(...))    # 渲染截图
app.mount("/export-output", StaticFiles(...))    # 导出 PDF
app.mount("/app",           StaticFiles(...))    # 前端 SPA

# 健康检查
GET /health → {"status": "ok", "version": "0.1.0"}
```

---

## 4.4 项目接口（`api/routers/projects.py`）

### GET /projects
列出所有项目，按创建时间倒序。

**Response 200** `APIResponse[list[ProjectRead]]`

---

### POST /projects
创建新项目。

**Request Body** `ProjectCreate`
```json
{ "name": "天津博物馆概念方案" }
```

**Response 201** `APIResponse[ProjectRead]`
```json
{
  "success": true,
  "data": {
    "id": "uuid",
    "name": "天津博物馆概念方案",
    "status": "INIT",
    "created_at": "2026-04-10T10:00:00Z"
  }
}
```

---

### GET /projects/{project_id}
获取项目详情。

**Response 200** `APIResponse[ProjectRead]`

---

### PATCH /projects/{project_id}/brief
多轮对话式项目信息采集。每次调用通过 Intake Agent 将新输入与已有 brief 合并。

**实现**：`async` 路由 → `run_intake(project_id, raw_text, db)`

**Request Body** `ProjectBriefInput`
```json
{
  "raw_text": "我们的项目是天津主城区一个约12000平米的博物馆，甲方是天津文化集团，风格偏现代简约"
}
```

**Response 200** `APIResponse[dict]`
```json
{
  "success": true,
  "data": {
    "brief": {
      "building_type": "museum",
      "client_name": "天津文化集团",
      "style_preferences": ["modern", "minimal"],
      "gross_floor_area": 12000,
      "site_area": null,
      "far": null,
      "site_address": null,
      "province": null,
      "city": "天津",
      "district": null,
      "missing_fields": ["site_area_or_far"],
      "is_complete": false
    },
    "follow_up": {
      "question": "请问用地面积大约是多少平米？或者您知道容积率是多少吗？",
      "missing_fields": ["site_area"],
      "is_final_confirmation": false
    }
  }
}
```

当 `is_complete=true` 时，返回 `confirmation_summary` + `validation_warnings` 代替 `follow_up`。

---

### POST /projects/{project_id}/confirm-brief
确认项目信息，推进状态机至 `INTAKE_CONFIRMED`。

**前置条件**：项目状态为 `INIT` 或 `INTAKE_IN_PROGRESS`，且 brief 无 missing\_fields。

**Response 200** `APIResponse[dict]`
```json
{ "success": true, "data": { "status": "INTAKE_CONFIRMED" } }
```

**错误**：
- `BriefIncompleteError (422)` — brief 仍有缺失字段
- `InvalidStatusTransitionError (409)` — 状态不允许

---

## 4.5 场地接口（`api/routers/sites.py`）

### POST /projects/{project_id}/site/point
提交场地点位。

**Request Body** `SitePointInput`
```json
{ "longitude": 117.19, "latitude": 39.13 }
```

**Response 200**
```json
{
  "success": true,
  "data": {
    "longitude": 117.19,
    "latitude": 39.13,
    "address_resolved": "天津市河西区...",
    "poi_name": null
  }
}
```

---

### POST /projects/{project_id}/site/polygon
提交地块范围。内部调用 `normalize_polygon()` 进行几何标准化。

**Request Body** `SitePolygonInput`
```json
{
  "geojson": {
    "type": "Polygon",
    "coordinates": [[[117.18, 39.12], [117.20, 39.12], ...]]
  }
}
```

**Response 200**
```json
{
  "success": true,
  "data": {
    "area_calculated": 10024.5,
    "perimeter": 403.2,
    "geojson": { ... },
    "version": 1
  }
}
```

---

### GET /projects/{project_id}/site
获取场地信息汇总（点位 + 多边形）。

**Response 200** `APIResponse[SiteRead]`

---

## 4.6 案例接口（`api/routers/references.py`）

### POST /projects/{project_id}/references/recommend
触发案例推荐（同步，内部调用向量检索 + 重排序）。

**实现**：`async` 路由 → `recommend_cases(project_id, db, top_k, style_filter)`

**Request Body** `RecommendRequest`
```json
{
  "top_k": 8,
  "style_filter": ["modern"]
}
```

**Response 200** `APIResponse[RecommendResponse]`

---

### POST /projects/{project_id}/references/select
用户提交案例选择结果。清除旧选择后按 rank 写入。
若当前状态为 `INTAKE_CONFIRMED`，自动推进到 `REFERENCE_SELECTION`。

**Request Body** `SelectionBatchInput`
```json
{
  "selections": [
    {
      "case_id": "uuid",
      "selected_tags": ["造型", "材质"],
      "selection_reason": "喜欢轻盈立面"
    }
  ]
}
```

---

### POST /projects/{project_id}/references/confirm
确认案例选择。三步操作：
1. 调用 `summarise_selection_preferences()` 生成偏好摘要
2. 调用 `generate_visual_theme()` 生成视觉主题（`await`，非 Celery）
3. 返回 `ConfirmReferencesResponse`（含 visual\_theme\_id / keywords / primary）

> Visual Theme 生成失败不阻断主流程，仅记录 error 日志。

**Response 200** `APIResponse[ConfirmReferencesResponse]`
```json
{
  "success": true,
  "data": {
    "dominant_styles": ["modern"],
    "dominant_features": ["facade"],
    "narrative_hint": "...",
    "visual_theme_id": "uuid",
    "visual_theme_keywords": ["modern", "cultural"],
    "visual_theme_primary": "#2C5F7C"
  }
}
```

---

### POST /projects/{project_id}/references/refresh
刷新推荐（排除已选案例，换一批）。

**实现**：读取已有 selections → 传入 `exclude_ids` → `recommend_cases()`

---

## 4.7 素材包接口（`api/routers/material_packages.py`）

> **主路径（Path A）新增接口**

### POST /projects/{project_id}/material-packages/ingest-local
摄入本地素材包目录。

**实现**：`ingest_local_material_package(project_id, local_path, db)` → 扫描文件 → 创建 MaterialPackage + MaterialItem → 派生 Asset → 提取 ProjectBrief

**Request Body** `LocalMaterialPackageIngestRequest`
```json
{ "local_path": "/data/materials/project1" }
```

**Response 200** `APIResponse[MaterialPackageRead]`

---

### GET /projects/{project_id}/material-packages/latest
获取最新版本的素材包。

**Response 200** `APIResponse[MaterialPackageRead]`

---

### GET /projects/{project_id}/material-packages/{package_id}/manifest
获取素材包 manifest（JSON 清单）。

**Response 200** `APIResponse[dict]`

---

### GET /projects/{project_id}/material-packages/{package_id}/items
列出素材包下所有 MaterialItem，按 logical\_key + created\_at 排序。

**Response 200** `APIResponse[list[MaterialItemRead]]`

---

### POST /projects/{project_id}/material-packages/{package_id}/regenerate
基于已摄入素材包重新生成 BriefDoc + Outline。

**实现**：
1. 设置项目状态 → `ASSET_GENERATING`
2. 启动后台线程 `_outline_worker(project_id)`:
   - `generate_brief_doc()` → BriefDoc
   - `generate_outline()` → Outline

**Response 202** `APIResponse[dict]`
```json
{
  "success": true,
  "data": { "queued": true, "package_id": "uuid", "status": "outline generation started" }
}
```

---

## 4.8 大纲接口（`api/routers/outlines.py`）

### POST /projects/{project_id}/outline/generate
生成 PPT 大纲（后台线程异步执行）。

**实现**：设置状态 → `ASSET_GENERATING` → 启动 `_outline_worker` 后台线程

**Response 202** `APIResponse[dict]`
```json
{ "success": true, "data": { "message": "outline generation started" } }
```

---

### GET /projects/{project_id}/outline
获取最新版大纲。

**Response 200** `APIResponse[OutlineRead]`

---

### POST /projects/{project_id}/outline/confirm
确认大纲，推进至 `SLIDE_PLANNING` 阶段。

**实现**：
1. Outline 状态 → `confirmed`，记录 `confirmed_at`
2. Project 状态 → `SLIDE_PLANNING`
3. 启动后台线程 `_compose_render_worker(project_id)`:
   - `bind_outline_slides()` — 素材绑定（状态 → `BINDING`）
   - `compose_all_slides()` — Composer 并发生成
   - `render_slide_html()` × N — HTML 渲染
   - `screenshot_slides_batch()` — Playwright 批量截图
   - 状态 → `REVIEWING`
   - `review_slides.delay()` — 触发 Celery 审查任务

**Response 200** `APIResponse[dict]`
```json
{ "success": true, "data": { "status": "SLIDE_PLANNING" } }
```

---

## 4.9 页面接口（`api/routers/slides.py`）

### POST /projects/{project_id}/slides/plan
触发页面规划（当前实现返回提示信息：页面在确认大纲后自动生成）。

---

### GET /projects/{project_id}/slides
获取所有页面列表。

**Response 200** `APIResponse[list[SlideRead]]`
```json
{
  "success": true,
  "data": [
    {
      "id": "uuid",
      "project_id": "uuid",
      "slide_no": 4,
      "section": "场地分析",
      "title": "周边文化资源分布",
      "layout_template": "split-h",
      "status": "rendered",
      "binding_id": "uuid",
      "screenshot_url": "/slides-output/slide_04.png",
      "repair_count": 0,
      "spec_json": { ... },
      "source_refs_json": [...],
      "evidence_refs_json": [...]
    }
  ]
}
```

---

### GET /projects/{project_id}/slides/{slide_no}
获取单页详情，含完整 LayoutSpec。

**Response 200** `APIResponse[SlideRead]`

---

### GET /projects/{project_id}/slides/{slide_no}/binding
获取单页素材绑定详情。

**Response 200** `APIResponse[SlideMaterialBindingRead]`

---

## 4.10 资产接口（`api/routers/assets.py`）

### POST /projects/{project_id}/assets/generate
触发全量资产生成（Celery 异步任务）。

**实现**：`generate_all_assets.delay(project_id)`

**Response 202** `APIResponse[dict]`
```json
{
  "success": true,
  "data": { "job_id": "celery-task-id", "status": "queued", "message": "资产生成任务已进入队列" }
}
```

---

### GET /projects/{project_id}/assets
获取资产列表，支持按 `asset_type` 和 `status` 过滤。

**Query Params**
- `asset_type`（可选）：过滤资产类型（IMAGE / CASE_CARD / KPI_TABLE / DOCUMENT 等）
- `status`（可选）：过滤状态

**Response 200** `APIResponse[list[AssetRead]]`

---

## 4.11 渲染与审查接口（`api/routers/render.py`）

### POST /projects/{project_id}/render
触发渲染（Celery 异步任务）。

**Request Body**（可选）
```json
{ "slide_nos": [1, 2, 3] }   // 留空则渲染全部
```

**Response 202** `APIResponse[dict]`

---

### POST /projects/{project_id}/review
触发审查（Celery 异步任务）。

**Request Body**
```json
{
  "layers": ["rule", "semantic"],   // 可选 "vision"（成本高）
  "slide_nos": []                   // 留空则审查全部
}
```

**Response 202** `APIResponse[dict]`

---

### POST /projects/{project_id}/repair
触发修复渲染（查找 `REPAIR_NEEDED` 状态的页面 → 重新渲染 → 重新审查）。

**Request Body**
```json
{
  "slide_nos": [4, 7],    // 留空则自动查找 REPAIR_NEEDED 页
  "force": false
}
```

**实现**：`render_slides_task.delay(project_id, slide_nos, review_after=True)`

**Response 202** `APIResponse[dict]`

---

## 4.12 导出接口（`api/routers/exports.py`）

### POST /projects/{project_id}/export
触发导出（后台线程异步执行）。

**实现**：
1. 项目状态暂置 → `RENDERING`（让前端轮询继续）
2. 启动 `_export_worker(project_id, export_type)` 后台线程:
   - 收集已渲染 PNG（优先本地文件，回退 HTML 重渲染）
   - `compile_pdf(png_bytes_list)` → PDF
   - 保存至 `tmp/e2e_output/export/{project_id}.pdf`
   - 项目状态 → `EXPORTED`

**Request Body**（可选）
```json
{ "export_type": "pdf" }   // pdf / pptx
```

**Response 202** `APIResponse[dict]`
```json
{ "success": true, "data": { "message": "导出中 (pdf)" } }
```

导出完成后，PDF 通过 `/export-output/{project_id}.pdf` 静态路由访问。

---

## 4.13 完整接口清单

| 方法 | 路径 | 路由文件 | 同步/异步 | 说明 |
|------|------|---------|----------|------|
| GET | /health | main.py | 同步 | 健康检查 |
| GET | /projects | projects.py | 同步 | 项目列表 |
| POST | /projects | projects.py | 同步 | 创建项目 |
| GET | /projects/{id} | projects.py | 同步 | 项目详情 |
| PATCH | /projects/{id}/brief | projects.py | async | 多轮采集 → Intake Agent |
| POST | /projects/{id}/confirm-brief | projects.py | 同步 | 确认 Brief |
| POST | /projects/{id}/site/point | sites.py | 同步 | 提交点位 |
| POST | /projects/{id}/site/polygon | sites.py | 同步 | 提交多边形 |
| GET | /projects/{id}/site | sites.py | 同步 | 场地汇总 |
| POST | /projects/{id}/references/recommend | references.py | async | 案例推荐 |
| POST | /projects/{id}/references/select | references.py | 同步 | 提交选择 |
| POST | /projects/{id}/references/confirm | references.py | async | 确认选择 + Visual Theme |
| POST | /projects/{id}/references/refresh | references.py | async | 刷新推荐 |
| POST | /projects/{id}/material-packages/ingest-local | material_packages.py | 同步 | 素材包摄入 |
| GET | /projects/{id}/material-packages/latest | material_packages.py | 同步 | 最新素材包 |
| GET | /projects/{id}/material-packages/{pkg}/manifest | material_packages.py | 同步 | 素材清单 |
| GET | /projects/{id}/material-packages/{pkg}/items | material_packages.py | 同步 | 素材条目 |
| POST | /projects/{id}/material-packages/{pkg}/regenerate | material_packages.py | 后台线程 | 重生成 BriefDoc+Outline |
| POST | /projects/{id}/outline/generate | outlines.py | 后台线程 | 生成大纲 |
| GET | /projects/{id}/outline | outlines.py | 同步 | 获取大纲 |
| POST | /projects/{id}/outline/confirm | outlines.py | 后台线程 | 确认大纲 → 全流程 |
| POST | /projects/{id}/slides/plan | slides.py | 同步 | 页面规划（提示） |
| GET | /projects/{id}/slides | slides.py | 同步 | 页面列表 |
| GET | /projects/{id}/slides/{no} | slides.py | 同步 | 页面详情 |
| GET | /projects/{id}/slides/{no}/binding | slides.py | 同步 | 素材绑定详情 |
| POST | /projects/{id}/assets/generate | assets.py | Celery | 资产生成 |
| GET | /projects/{id}/assets | assets.py | 同步 | 资产列表 |
| POST | /projects/{id}/render | render.py | Celery | 触发渲染 |
| POST | /projects/{id}/review | render.py | Celery | 触发审查 |
| POST | /projects/{id}/repair | render.py | Celery | 触发修复 |
| POST | /projects/{id}/export | exports.py | 后台线程 | 触发导出 |
