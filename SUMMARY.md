# PPT Agent — 项目总结文档

> AI 驱动的建筑方案 PPT 自动生成系统
> 架构：模块化单体 | FastAPI + Celery + LangGraph
> 状态：全部 8 个阶段编码完成，117 个单元测试通过

---

## 一、系统概述

PPT Agent 接收建筑项目需求（用地位置、建筑类型、面积指标等），自动生成一套完整的专业 PPT 汇报材料，输出 PDF 文件。全程由 AI Agent 驱动，支持人工审查干预。

**支持的建筑类型：** 博物馆、办公、住宅、商业、酒店、文化、教育、综合体（通过 `building_type` 动态注入，代码无硬编码限制）

---

## 二、技术栈

| 层次 | 技术 |
|------|------|
| Web 框架 | FastAPI 0.111 + Uvicorn |
| 任务队列 | Celery 5.4 + Redis 7 |
| Agent 编排 | LangGraph 0.1 |
| LLM | Anthropic Claude（Opus 4.6 强模型 / Haiku 4.5 快模型）|
| 数据库 | PostgreSQL 16 + pgvector（向量检索）|
| ORM | SQLAlchemy 2.0 + Alembic 迁移 |
| Schema 校验 | Pydantic v2 |
| HTML 渲染 | Jinja2 模板 + Design Token CSS |
| 截图/PDF | Playwright headless Chromium（含 Pillow/matplotlib fallback）|
| 对象存储 | Aliyun OSS（开发环境 `/tmp/` mock）|
| 地图/POI | 高德地图 API（无 key 时返回 mock 数据）|
| 图表生成 | matplotlib（bar / line / pie / radar）|
| 向量嵌入 | 支持 OpenAI / Voyage AI / mock（通过 `embedding_provider` 配置）|

---

## 三、项目结构

```
ppt_agent/
├── main.py                    # FastAPI 入口，挂载所有路由
├── docker-compose.yml         # api + worker + renderer + db + redis + flower
├── pyproject.toml             # Poetry 依赖
│
├── config/
│   ├── settings.py            # Pydantic Settings，统一读取 .env
│   └── llm.py                 # LLM 调用封装（call_llm_structured / call_llm_with_limit / call_llm_multimodal）
│
├── schema/                    # Pydantic 数据模型（API 层与 Agent 层共用）
│   ├── common.py              # 枚举：ProjectStatus / SlideStatus / LayoutTemplate 等
│   ├── project.py             # ProjectBriefData, ProjectRead
│   ├── slide.py               # SlideSpec, BlockContent, SlideConstraints
│   ├── outline.py             # OutlineSpec, OutlineSlideEntry
│   ├── review.py              # ReviewReport, ReviewIssue, RepairAction
│   ├── reference.py           # ReferenceCase, CaseSearchOutput
│   ├── asset.py               # AssetRead
│   └── site.py                # SitePoint, SitePolygon
│
├── db/
│   ├── base.py                # SQLAlchemy Base
│   ├── session.py             # SessionLocal + get_db_context() 上下文管理器
│   └── models/                # ORM 模型（projects / briefs / outlines / slides /
│                              #           reviews / assets / sites / references / jobs）
│
├── alembic/                   # 数据库迁移（含 pgvector extension + embedding 列）
│
├── api/
│   ├── middleware.py          # 全局异常处理，统一错误响应
│   ├── response.py            # APIResponse[T] 泛型响应封装
│   ├── exceptions.py          # 业务异常类
│   └── routers/
│       ├── projects.py        # POST /projects, GET, PATCH /brief, POST /confirm-brief
│       ├── sites.py           # POST /site/point, /site/polygon
│       ├── references.py      # GET /references/recommend, POST /references/select
│       ├── assets.py          # POST /assets/generate, GET /assets
│       ├── outlines.py        # POST /outline/generate, GET /outline, POST /outline/confirm
│       ├── slides.py          # GET /slides, GET /slides/{id}
│       ├── render.py          # POST /render, /review, /repair
│       └── exports.py         # POST /export
│
├── agent/                     # Agent 逻辑层
│   ├── intake.py              # Intake Agent：自然语言 → ProjectBriefData（多轮对话）
│   ├── reference.py           # Reference Agent：向量检索 + 重排序 + 偏好摘要
│   ├── outline.py             # Outline Agent：brief + 资产 → OutlineSpec（强模型）
│   ├── composer.py            # Composer Agent：per-slide 快模型，asyncio.gather 并发
│   ├── critic.py              # Critic Agent：3 层审查 + 自动修复
│   └── graph.py               # LangGraph StateGraph：5 节点完整流水线
│
├── tool/                      # 纯函数工具层（无外部状态）
│   ├── input/
│   │   ├── compute_far.py     # 容积率 / 建蔽率计算
│   │   ├── validate_brief.py  # 项目简报字段校验
│   │   ├── extract_brief.py   # 从 LLM 输出提取结构化 brief
│   │   ├── geocode.py         # 高德地理编码
│   │   └── normalize_polygon.py # 用地红线坐标归一化
│   ├── reference/
│   │   ├── search.py          # pgvector 向量检索 + tag 过滤
│   │   ├── rerank.py          # 案例重排序
│   │   ├── preference_summary.py # 偏好摘要生成
│   │   └── _embedding.py      # 嵌入向量生成（多 provider）
│   ├── site/
│   │   ├── _amap_client.py    # 高德 REST API 统一客户端
│   │   ├── poi_retrieval.py   # POI 周边检索
│   │   └── mobility_analysis.py # 交通可达性分析
│   ├── asset/
│   │   ├── chart_generation.py # matplotlib 图表（bar/line/pie/radar，4 配色）
│   │   └── map_annotation.py  # 高德静态地图 + 标注
│   ├── review/
│   │   ├── layout_lint.py     # 规则审查（R001–R015，9 条规则，纯本地）
│   │   ├── semantic_check.py  # 语义一致性审查（S001/S004–S007，快模型）
│   │   └── repair_plan.py     # 修复执行器
│   ├── slide/
│   │   └── content_fit.py     # 内容密度约束检查
│   └── _oss_client.py         # OSS 上传（mock / Aliyun）
│
├── render/
│   ├── engine.py              # Jinja2 渲染引擎，SlideSpec → 自包含 HTML
│   ├── exporter.py            # Playwright 截图 + PDF 编译（含 fallback）
│   └── templates/             # 9 套 HTML 模板
│       ├── base.html          # 基础模板（Design Token CSS 内联）
│       ├── cover_hero.html    # 封面-大图
│       ├── overview_kpi.html  # 概览-KPI 卡片
│       ├── chapter_divider.html # 章节分割页
│       ├── map_left_insight_right.html # 地图+洞察
│       ├── two_case_compare.html # 双案例对比
│       ├── chart_main_text_side.html # 图表+文字
│       ├── gallery_quad.html  # 四宫格图集
│       ├── strategy_diagram.html # 策略图示
│       └── matrix_summary.html # 矩阵/表格
│
├── tasks/                     # Celery 异步任务
│   ├── celery_app.py          # Celery 配置（3 队列：default / render / export）
│   ├── asset_tasks.py         # 资产生成（chord 并发：场地 + 图表 + 案例卡）
│   ├── outline_tasks.py       # 大纲生成 + 页面合成
│   ├── render_tasks.py        # HTML 渲染 + 截图 + OSS 上传
│   ├── review_tasks.py        # 3 层审查 + 自动修复（max 3 次）
│   └── export_tasks.py        # PDF 编译 + OSS 上传
│
├── scripts/
│   └── seed_cases.py          # 案例库初始化脚本（读取 seed_cases.json）
│
└── tests/unit/                # 117 个单元测试（全部通过）
    ├── test_compute_far.py
    ├── test_validate_brief.py
    ├── test_extract_brief.py
    ├── test_layout_lint.py
    ├── test_repair_plan.py
    ├── test_content_fit.py
    ├── test_reference_tools.py
    ├── test_phase6_tools.py
    ├── test_render_engine.py
    └── test_critic.py
```

---

## 四、完整业务流程

```
用户输入自然语言需求
        │
        ▼
[Intake Agent]  ──→  多轮对话补全字段  ──→  ProjectBriefData 确认
        │
        ▼
[Reference Agent]  ──→  pgvector 向量检索  ──→  案例推荐 + 用户选择 + 偏好摘要
        │
        ▼
[Asset Tasks - Celery chord 并发]
  ├── POI 检索 + 交通分析  ──→  场地资产
  ├── matplotlib 图表生成  ──→  图表资产
  └── 案例卡生成          ──→  案例对比资产
        │
        ▼
[Outline Agent]  ──→  Claude Opus（强模型）  ──→  OutlineSpec（8-12 页规划）
        │  用户确认
        ▼
[Composer Agent]  ──→  asyncio.gather 并发（快模型 per-slide）  ──→  SlideSpec × N
        │
        ▼
[Render Tasks]  ──→  Jinja2 HTML  ──→  Playwright PNG  ──→  OSS 存储
        │
        ▼
[Critic Agent - 3 层审查]
  ├── Layer 1: layout_lint（规则，无 LLM，自动修复）
  ├── Layer 2: semantic_check（快模型，语义一致性）
  └── Layer 3: vision review（多模态 LLM，仅有截图时启用）
        │
        ├── PASS  ──→  READY_FOR_EXPORT
        ├── REPAIR_REQUIRED  ──→  自动修复后重试（最多 3 次）
        └── ESCALATE_HUMAN  ──→  标记失败，等待人工干预
        │
        ▼
[Export Task]  ──→  PNG 列表  ──→  compile_pdf  ──→  OSS  ──→  PDF URL
```

---

## 五、项目状态机

```
INIT
 → INTAKE_IN_PROGRESS  （brief 采集中）
 → INTAKE_CONFIRMED    （brief 已确认）
 → REFERENCE_SELECTION （案例选择中）
 → ASSET_GENERATING    （资产生成中）
 → OUTLINE_READY       （资产完成，等待大纲）
 → SLIDE_PLANNING      （大纲确认，页面合成中）
 → RENDERING           （渲染截图中）
 → REVIEWING           （审查中）
 → READY_FOR_EXPORT    （审查通过）
 → EXPORTED            （PDF 已生成）
 → FAILED              （不可恢复错误）
```

---

## 六、API 端点一览

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/projects` | 创建项目 |
| GET | `/projects/{id}` | 查询项目状态 |
| PATCH | `/projects/{id}/brief` | 更新项目简报（自然语言输入）|
| POST | `/projects/{id}/confirm-brief` | 确认简报，进入案例推荐 |
| POST | `/projects/{id}/site/point` | 上传场地坐标点 |
| POST | `/projects/{id}/site/polygon` | 上传用地红线 |
| GET | `/projects/{id}/references/recommend` | 获取推荐案例 |
| POST | `/projects/{id}/references/select` | 选择参考案例 |
| POST | `/projects/{id}/assets/generate` | 触发资产生成（异步）|
| GET | `/projects/{id}/assets` | 查询已生成资产 |
| POST | `/projects/{id}/outline/generate` | 触发大纲生成（异步）|
| GET | `/projects/{id}/outline` | 查询大纲 |
| POST | `/projects/{id}/outline/confirm` | 确认大纲，触发页面合成 |
| GET | `/projects/{id}/slides` | 查询所有页面 |
| POST | `/projects/{id}/render` | 触发渲染（异步）|
| POST | `/projects/{id}/review` | 触发审查（异步）|
| POST | `/projects/{id}/repair` | 触发修复（异步）|
| POST | `/projects/{id}/export` | 触发导出 PDF（异步）|
| GET | `/health` | 健康检查 |

---

## 七、审查规则体系

### Layer 1 — 规则审查（layout_lint，无 LLM）

| 规则码 | 名称 | 严重度 | 可自动修复 |
|--------|------|--------|-----------|
| R001 | TEXT_OVERFLOW | P1 | ✅ |
| R002 | BULLET_OVERFLOW | P1 | ✅ |
| R003 | MISSING_REQUIRED_BLOCK | P0 | ❌ |
| R005 | IMAGE_COUNT_EXCEEDED | P2 | ✅ |
| R006 | EMPTY_SLIDE | P0 | ❌ |
| R007 | TITLE_TOO_LONG | P2 | ✅ |
| R008 | KEY_MESSAGE_MISSING | P2 | ✅ |
| R009 | TEMPLATE_UNKNOWN | P0 | ✅ |
| R015 | EXCESSIVE_DENSITY | P1 | ✅ |

### Layer 2 — 语义审查（快模型）

| 规则码 | 名称 | 说明 |
|--------|------|------|
| S001 | METRIC_INCONSISTENCY | 面积/容积率与 brief 数值不符 |
| S004 | UNSUPPORTED_CLAIM | 无数据支撑的强断言（最高/第一）|
| S005 | STYLE_TERM_WRONG | 风格描述词与 style_preferences 相悖 |
| S006 | MISSING_KEY_MESSAGE_SUPPORT | key_message 无内容支撑 |
| S007 | CLIENT_NAME_WRONG | 甲方名称错误（可自动修复）|

### Layer 3 — 视觉审查（多模态 LLM，需截图）

| 规则码 | 名称 |
|--------|------|
| V001 | VISUAL_CLUTTER |
| V002 | IMAGE_BLURRY |
| V004 | TEXT_ON_BUSY_BG |
| V007 | BLANK_AREA_WASTE |

### 审查决策逻辑

```
有 P0 且不可自动修复  →  ESCALATE_HUMAN（人工干预）
有 P0/P1（可修复）   →  REPAIR_REQUIRED（最多重试 3 次）
仅 P2               →  REPAIR_REQUIRED
无问题              →  PASS
```

---

## 八、Celery 队列分配

| 队列 | Worker | 包含任务 |
|------|--------|----------|
| `default` | worker | asset_tasks, outline_tasks, review_tasks |
| `render` | renderer | render_tasks（安装 Playwright）|
| `export` | worker | export_tasks |

---

## 九、LLM 使用策略

| 场景 | 模型 | 原因 |
|------|------|------|
| 大纲生成 | `claude-opus-4-6`（强模型）| 叙事结构质量要求高 |
| 页面合成 | `claude-haiku-4-5`（快模型）| 大量 per-slide 并发调用 |
| 语义审查 | `claude-haiku-4-5`（快模型）| 轻量检查，时效性优先 |
| 视觉审查 | `claude-haiku-4-5`（快模型）| 多模态，输出量小 |
| Intake 对话 | `claude-haiku-4-5`（快模型）| 交互式，延迟敏感 |

所有 LLM 调用统一通过 `config/llm.py` 封装，支持：
- `call_llm_structured()` — Pydantic Schema 结构化输出
- `call_llm_with_limit()` — 带 token 限制的快速调用
- `call_llm_multimodal()` — 图文混合输入

---

## 十、测试覆盖

| 测试文件 | 覆盖内容 | 测试数 |
|----------|----------|--------|
| test_compute_far.py | 容积率/建蔽率计算 | 8 |
| test_validate_brief.py | 简报字段校验 | 9 |
| test_extract_brief.py | LLM 输出提取 | 8 |
| test_layout_lint.py | 9 条规则审查 | 18 |
| test_repair_plan.py | 修复执行器 | 10 |
| test_content_fit.py | 内容密度约束 | 7 |
| test_reference_tools.py | 向量检索 + 重排序 | 16 |
| test_phase6_tools.py | 场地/资产/OSS 工具 | 14 |
| test_render_engine.py | 9 套模板渲染 | 16 |
| test_critic.py | 审查 Agent + 语义检查 | 21 |
| **合计** | | **117 ✅** |

---

## 十一、启动方式

### 本地开发

```bash
# 1. 启动基础设施
docker-compose up db redis -d

# 2. 建表
alembic upgrade head

# 3. 导入案例库（需先准备 scripts/seed_cases.json）
python scripts/seed_cases.py

# 4. 启动 API
uvicorn main:app --reload --port 8000

# 5. 启动 Worker（新终端）
celery -A tasks.celery_app worker --loglevel=info -Q default,export

# 6. 启动渲染 Worker（新终端）
celery -A tasks.celery_app worker --loglevel=info -Q render
```

### Docker 全量部署

```bash
docker-compose up --build
# API:    http://localhost:8000
# Docs:   http://localhost:8000/docs
# Flower: http://localhost:5555
```

### 环境变量（.env）

```env
DATABASE_URL=postgresql://user:password@localhost:5432/ppt_agent
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
ANTHROPIC_API_KEY=sk-ant-...
AMAP_API_KEY=                  # 留空则返回 mock 数据
OSS_ENDPOINT=                  # 留空则存到 /tmp/
EMBEDDING_PROVIDER=mock        # mock / openai / voyage
```

### 运行测试

```bash
pytest tests/unit/ -v
```

---

## 十二、待完成事项

- [ ] **端到端验证**：docker-compose 全量启动，手动走完整链路
- [ ] **集成测试**：`tests/integration/` 接 PostgreSQL 的 CRUD 测试
- [ ] **案例库数据**：填写 `scripts/seed_cases.json`，导入真实案例
- [ ] **Playwright 安装**：`playwright install chromium`（截图/PDF 当前走 fallback）
- [ ] **真实 LLM 验证**：配置 `ANTHROPIC_API_KEY`，调优 Prompt 输出质量
- [ ] **高德 API 接入**：配置 `AMAP_API_KEY`，验证 POI 和静态地图
- [ ] **OSS 配置**：配置 Aliyun OSS 参数，替换 `/tmp/` mock 存储
- [ ] **PPTX 导出**：`export_deck` 当前仅支持 PDF，`python-pptx` 已在依赖中
