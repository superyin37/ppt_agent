# PPT Agent 项目说明文档

> 更新时间：2026-04-15
> 依据：`pyproject.toml`、`architecture.md`、`SUMMARY.md`、`main.py`、`docker-compose.yml` 以及 `agent/`、`tool/`、`tasks/`、`schema/`、`render/`、`frontend/` 等实际源码目录。

---

## 一、项目定位

PPT Agent 是一个面向**建筑方案汇报场景**的 AI 内容生产系统。它以本地素材包（MaterialPackage）为事实源，通过多 Agent 流水线，将建筑策划材料逐步加工为可追踪、可重试、可审查的生成结果，最终稳定输出 PDF。

核心产物链路：

```
MaterialPackage → BriefDoc → OutlineSpec → SlideMaterialBinding
               → VisualTheme → LayoutSpec → HTML → PNG → PDF
```

`LayoutSpec` 是当前页面级核心协议，`PDF` 是当前稳定交付产物；`PPTX` 仍属规划方向。

---

## 二、技术栈总览

### 2.1 运行时 & 语言

| 项 | 版本/说明 |
|---|---|
| Python | 3.11+ |
| 包管理 | Poetry（`pyproject.toml`） |
| 容器化 | Docker + docker-compose（api / worker / renderer / flower / db / redis） |

### 2.2 Web / API 层

| 框架 | 版本 | 用途 |
|---|---|---|
| **FastAPI** | ^0.111 | HTTP API、OpenAPI 文档、依赖注入 |
| **Uvicorn** | ^0.30（standard extras） | ASGI 服务器 |
| **Pydantic** | ^2.7 | API / Agent / 存储三层共用的 Schema 校验 |
| **pydantic-settings** | ^2.2 | `.env` 读取、统一配置 |
| **Jinja2** | ^3.1 | HTML 模板渲染 |
| **httpx** | ^0.27 | 异步 HTTP 客户端 / 测试客户端 |

FastAPI 入口：[main.py](main.py)，挂载路由 `projects / sites / references / assets / material-packages / outlines / slides / render / exports`，并挂载静态目录 `/slides-output`、`/export-output`、`/app`（前端 SPA）。

### 2.3 数据与存储层

| 组件 | 版本 | 说明 |
|---|---|---|
| **PostgreSQL** | 16（`pgvector/pgvector:pg16` 镜像） | 主数据库 |
| **pgvector** | ^0.3 | 参考案例向量检索 |
| **SQLAlchemy** | ^2.0 | ORM（`db/base.py`、`db/session.py`、`db/models/`） |
| **Alembic** | ^1.13 | 迁移；包含 pgvector extension 与 embedding 列 |
| **psycopg2-binary** | ^2.9 | PG 驱动 |
| **Aliyun OSS** | —— | 对象存储；本地开发 fallback 到 `/tmp/` mock（`tool/_oss_client.py`） |

### 2.4 任务编排层

| 组件 | 版本 | 用途 |
|---|---|---|
| **Celery** | ^5.4（含 redis extras） | 异步任务队列，3 队列：`default` / `render` / `export` |
| **Redis** | 7-alpine | Celery broker + result backend |
| **Flower** | ^2.0 | Celery 监控面板（5555 端口） |

任务模块：[tasks/celery_app.py](tasks/celery_app.py)、`asset_tasks.py`、`outline_tasks.py`、`render_tasks.py`、`review_tasks.py`、`export_tasks.py`。

当前实际编排分布在 FastAPI 路由的后台线程 + Celery tasks 中，**不存在单独的 Orchestrator Agent 进程**。

### 2.5 LLM / Agent 层

| 组件 | 版本 | 用途 |
|---|---|---|
| **LangChain** | ^0.2 | LLM 封装基础设施 |
| **LangGraph** | ^0.1 | Agent 流程图（保留中，当前主链路非强依赖） |
| **langchain-anthropic** | ^0.1 | LangChain 的 Anthropic 集成 |
| **anthropic** | ^0.28 | Claude 官方 SDK |
| **openai** | >=1.30 | 备用 / embedding 供应商 |

模型策略（见 `config/llm.py`）：

| 场景 | 模型 |
|---|---|
| Outline 生成 | `claude-opus-4-6`（强模型，叙事结构质量） |
| Composer 页面合成 | `claude-haiku-4-5`（快模型，per-slide 并发） |
| 语义审查 / 视觉审查 / Intake | `claude-haiku-4-5` |

统一封装的调用入口：`call_llm_structured()`、`call_llm_with_limit()`、`call_llm_multimodal()`。

Embedding 供应商可配置：`mock` / `openai` / `voyage`（`EMBEDDING_PROVIDER`）。

### 2.6 渲染 / 导出层

| 组件 | 版本 | 用途 |
|---|---|---|
| **Playwright** | ^1.44 | Headless Chromium 截图、PDF 生成 |
| **python-pptx** | ^0.6.23 | 预留 PPTX 导出（当前非主线） |
| **Pillow / matplotlib** | matplotlib ^3.9 | 图表生成（bar/line/pie/radar）以及截图 fallback |
| **numpy** | ^1.26 | 图表 / 数据处理 |

渲染链路：[render/engine.py](render/engine.py)（Jinja2 模板 → 自包含 HTML）→ [render/exporter.py](render/exporter.py)（Playwright 截图 + PDF）。

### 2.7 外部服务

| 服务 | 用途 | Fallback |
|---|---|---|
| 高德地图 REST API | POI 检索、可达性分析、静态地图标注 | 无 `AMAP_API_KEY` 时返回 mock |
| Anthropic API | Claude 模型调用 | —— |
| OpenAI / Voyage | Embedding | `mock` 模式 |
| Aliyun OSS | 产物存储 | 本地 `/tmp/` |

### 2.8 测试

| 组件 | 版本 |
|---|---|
| pytest | ^8.0 |
| pytest-asyncio | ^0.23（`asyncio_mode = "auto"`） |
| pytest-cov | ^5.0 |

测试目录：`tests/unit/`（`SUMMARY.md` 记录 117 个单元测试）。

### 2.9 前端

前端是轻量 SPA，位于 [frontend/](frontend/)，仅三个文件：`index.html` + `app.js` + `style.css`，由 FastAPI 在 `/app` 挂载。**不是复杂编辑器**，职责是串联流程、查看状态与截图、触发审查与导出。

---

## 三、目录结构

```
ppt_agent/
├── main.py                  # FastAPI 入口
├── docker-compose.yml       # api + worker + renderer + flower + db + redis
├── pyproject.toml           # Poetry 依赖
├── Dockerfile
├── alembic.ini, alembic/    # 数据库迁移
│
├── config/                  # Settings / LLM 封装
├── schema/                  # Pydantic 模型（Project/Brief/Outline/Slide/
│                            #   MaterialPackage/VisualTheme/Review/Asset/Site/PageSlot）
├── db/                      # SQLAlchemy Base / Session / ORM models
│
├── api/
│   ├── middleware.py, response.py, exceptions.py
│   └── routers/             # projects, sites, references, assets,
│                            #   material_packages, outlines, slides, render, exports
│
├── agent/                   # Agent 逻辑层
│   ├── intake.py            # Intake（自然语言 → ProjectBriefData）
│   ├── reference.py         # Reference（向量检索 + 重排 + 偏好摘要）
│   ├── brief_doc.py         # BriefDoc（叙事主线）
│   ├── outline.py           # Outline（强模型 → OutlineSpec）
│   ├── material_binding.py  # 页级素材绑定（确定性匹配）
│   ├── visual_theme.py      # 项目级视觉主题
│   ├── composer.py          # 页级 LayoutSpec 生成（并发快模型）
│   └── critic.py            # 审查 + 修复建议
│
├── tool/                    # 纯函数工具层
│   ├── input/               # compute_far, validate_brief, extract_brief, geocode, normalize_polygon
│   ├── reference/           # search, rerank, preference_summary, _embedding
│   ├── site/                # _amap_client, poi_retrieval, mobility_analysis
│   ├── asset/               # chart_generation, map_annotation
│   ├── review/              # layout_lint, semantic_check, repair_plan
│   ├── slide/               # content_fit
│   ├── material_pipeline.py, material_resolver.py
│   └── _oss_client.py
│
├── render/
│   ├── engine.py            # Jinja2 → 自包含 HTML
│   ├── exporter.py          # Playwright 截图 + PDF（含 fallback）
│   └── templates/           # 9 套 HTML 模板
│
├── tasks/                   # Celery 异步任务
├── prompts/                 # Prompt 资源
├── scripts/                 # seed_cases 等运维脚本
├── frontend/                # 轻量 SPA
├── docs/, architecture.md, DEVLOG.md, SUMMARY.md
└── tests/unit/
```

---

## 四、核心数据模型

### 4.1 项目输入层
- `Project`、`ProjectBrief`
- `MaterialPackage`、`MaterialItem`（素材包事实源）

### 4.2 中间资产层
- `Asset`（派生资产：图表、地图、案例卡等）
- `BriefDoc`（叙事整理）
- `Outline` / `OutlineSpec`（页级提纲）
- `SlideMaterialBinding`（页级素材绑定）
- `VisualTheme`（项目级视觉主题）

### 4.3 页面与导出层
- `LayoutSpec`（页面协议，定义在 [schema/visual_theme.py](schema/visual_theme.py)）
- `Slide`（DB 侧记录，`spec_json` 存 LayoutSpec）
- `Review` 相关（`ReviewReport`、`ReviewIssue`、`RepairAction`）
- 导出产物：PNG、PDF

> 仓库中仍保留 `schema/slide.py::SlideSpec` 作为历史兼容模型，**当前渲染链路的核心协议是 LayoutSpec**，而不是旧版 SlideSpec。

---

## 五、项目状态机

```
INIT → INTAKE_IN_PROGRESS → INTAKE_CONFIRMED
     → REFERENCE_SELECTION → ASSET_GENERATING
     → MATERIAL_READY → OUTLINE_READY → BINDING
     → SLIDE_PLANNING → RENDERING → REVIEWING
     → READY_FOR_EXPORT → EXPORTED
     → FAILED
```

当前素材包主流程的关键节点：
`MATERIAL_READY → OUTLINE_READY → BINDING → SLIDE_PLANNING → REVIEWING → READY_FOR_EXPORT → EXPORTED`

---

## 六、审查体系（Critic）

| 层次 | 位置 | LLM | 代表规则 |
|---|---|---|---|
| L1 规则审查 | [tool/review/layout_lint.py](tool/review/layout_lint.py) | 否 | R001 TEXT_OVERFLOW、R002 BULLET_OVERFLOW、R003 MISSING_REQUIRED_BLOCK、R006 EMPTY_SLIDE、R015 EXCESSIVE_DENSITY 等 |
| L2 语义审查 | [tool/review/semantic_check.py](tool/review/semantic_check.py) | 快模型 | S001 METRIC_INCONSISTENCY、S004 UNSUPPORTED_CLAIM、S005 STYLE_TERM_WRONG、S007 CLIENT_NAME_WRONG 等 |
| L3 视觉审查 | Composer / Critic 多模态 LLM | 快模型（多模态） | V001 VISUAL_CLUTTER、V002 IMAGE_BLURRY、V004 TEXT_ON_BUSY_BG、V007 BLANK_AREA_WASTE |

决策：P0 不可修复 → ESCALATE_HUMAN；P0/P1 可修复 → REPAIR_REQUIRED（最多 3 次）；仅 P2 → REPAIR_REQUIRED；无问题 → PASS。

---

## 七、启动方式

### 本地开发
```bash
docker-compose up db redis -d
alembic upgrade head
python scripts/seed_cases.py              # 可选：导入案例库
uvicorn main:app --reload --port 8000
celery -A tasks.celery_app worker -Q default,export
celery -A tasks.celery_app worker -Q render   # Playwright 渲染 worker
```

### Docker 全量部署
```bash
docker-compose up --build
# API:    http://localhost:8000    (Docs: /docs)
# 前端:   http://localhost:8000/app
# Flower: http://localhost:5555
```

### 关键环境变量
```env
DATABASE_URL=postgresql://user:password@localhost:5432/ppt_agent
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
ANTHROPIC_API_KEY=sk-ant-...
AMAP_API_KEY=                # 留空 → mock
OSS_ENDPOINT=                # 留空 → /tmp/
EMBEDDING_PROVIDER=mock      # mock / openai / voyage
```

---

## 八、重要事实与边界

1. **素材包即事实源**：主流程从本地素材目录开始，而非自由对话。
2. **分布式编排**：流程控制分布在 API 路由后台线程 + Celery tasks，不存在单一 Orchestrator。
3. **PDF-first**：稳定交付是 PDF；PPTX 依赖 `python-pptx` 已装但**未形成闭环**。
4. **LayoutSpec 为主协议**：`SlideSpec` 仅历史兼容。
5. **前端是流程页而非编辑器**。
6. **VisualTheme** 在素材包脚本流中可显式生成，HTTP 主流程可能回退默认主题。
7. **审查闭环**：规则层 + 语义层已接入；视觉审查与自动修复仍在完善。
