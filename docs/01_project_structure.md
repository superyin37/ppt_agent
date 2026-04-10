# 01. 项目目录结构与环境规范

> 最后更新：2026-04-10

## 1.1 目录结构

```
ppt_agent/
├── alembic/                        # 数据库迁移
│   ├── versions/
│   └── env.py
├── api/                            # FastAPI 路由层
│   ├── __init__.py
│   ├── deps.py                     # 依赖注入（DB session）
│   ├── exceptions.py               # 业务异常类
│   ├── response.py                 # 统一响应格式
│   ├── middleware.py               # 全局异常处理、日志中间件
│   └── routers/
│       ├── projects.py             # 项目 CRUD
│       ├── sites.py                # 场地信息
│       ├── references.py           # 案例推荐/选择 + Visual Theme 触发
│       ├── assets.py               # 资产管理
│       ├── material_packages.py    # 素材包摄入 + BriefDoc 重生成
│       ├── outlines.py             # 大纲生成/确认 + compose_render 工作线程
│       ├── slides.py               # 幻灯片查询
│       ├── render.py               # 渲染 + 审查
│       └── exports.py              # PDF 导出
├── agent/                          # Agent 层（LLM 调用业务逻辑）
│   ├── __init__.py
│   ├── intake.py                   # Intake Agent — 项目信息采集
│   ├── reference.py                # Reference Agent — 案例推荐/偏好摘要
│   ├── brief_doc.py                # Brief Doc Agent — 设计建议书大纲
│   ├── visual_theme.py             # Visual Theme Agent — 视觉主题生成
│   ├── outline.py                  # Outline Agent — PPT 大纲
│   ├── material_binding.py         # Material Binding — 素材绑定（非 LLM）
│   ├── composer.py                 # Composer Agent — 幻灯片内容编排
│   └── critic.py                   # Critic Agent — 审查与修复
├── tool/                           # Tool / Skill 层
│   ├── __init__.py
│   ├── _base.py                    # Tool 基类（ToolError）
│   ├── _oss_client.py              # OSS 客户端封装
│   ├── material_pipeline.py        # 素材包摄入全流程
│   ├── material_resolver.py        # logical_key 匹配与展开
│   ├── input/
│   │   ├── extract_brief.py        # 自然语言 → ProjectBriefData
│   │   ├── validate_brief.py       # Brief 字段校验
│   │   ├── compute_far.py          # FAR / GFA / 用地面积互推
│   │   ├── geocode.py              # 高德地理编码
│   │   └── normalize_polygon.py    # 场地多边形标准化
│   ├── site/
│   │   ├── _amap_client.py         # 高德 API 统一封装
│   │   ├── poi_retrieval.py        # POI 检索
│   │   └── mobility_analysis.py    # 交通可达性分析
│   ├── reference/
│   │   ├── search.py               # pgvector 向量检索案例
│   │   ├── rerank.py               # 案例重排序
│   │   ├── preference_summary.py   # 选择偏好摘要
│   │   └── _embedding.py           # Embedding 生成
│   ├── asset/
│   │   ├── chart_generation.py     # 图表生成
│   │   └── map_annotation.py       # 地图标注
│   ├── slide/
│   │   └── content_fit.py          # 内容适配检查
│   └── review/
│       ├── layout_lint.py          # 规则审查（无 LLM）
│       ├── semantic_check.py       # 语义审查（LLM）
│       └── repair_plan.py          # 修复方案生成
├── schema/                         # Pydantic 数据模型
│   ├── __init__.py
│   ├── common.py                   # ProjectStatus / SlideStatus / AssetType / BuildingType 等枚举
│   ├── project.py                  # ProjectBriefData / ProjectRead 等
│   ├── site.py                     # SiteLocation / SitePolygon
│   ├── reference.py                # ReferenceCase / PreferenceSummary
│   ├── material_package.py         # MaterialPackageRead / MaterialItemRead
│   ├── asset.py                    # AssetRead
│   ├── page_slot.py                # PageSlot / PageSlotGroup / SlotAssignment / InputRequirement
│   ├── visual_theme.py             # VisualTheme / LayoutSpec / LayoutPrimitive / ContentBlock
│   ├── outline.py                  # OutlineSlideEntry / OutlineSpec
│   ├── slide.py                    # SlideRead
│   └── review.py                   # ReviewResult
├── db/                             # 数据库层
│   ├── __init__.py
│   ├── base.py                     # SQLAlchemy Base
│   ├── session.py                  # DB session 工厂
│   └── models/                     # ORM 模型
│       ├── __init__.py
│       ├── project.py              # Project / ProjectBrief
│       ├── site.py                 # SiteLocation / SitePolygon
│       ├── reference.py            # ReferenceCase / ProjectReferenceSelection
│       ├── material_package.py     # MaterialPackage
│       ├── material_item.py        # MaterialItem
│       ├── asset.py                # Asset
│       ├── brief_doc.py            # BriefDoc
│       ├── visual_theme.py         # VisualTheme ORM
│       ├── outline.py              # Outline
│       ├── slide.py                # Slide
│       ├── slide_material_binding.py  # SlideMaterialBinding
│       ├── review.py               # Review
│       └── job.py                  # Job（异步任务记录）
├── render/                         # 渲染引擎
│   ├── __init__.py
│   ├── engine.py                   # LayoutSpec → HTML 渲染（动态 CSS + 11 种布局原语）
│   ├── exporter.py                 # Playwright 截图 + PDF 编译
│   ├── html_sanitizer.py           # HTML 清理工具
│   ├── templates/                  # 旧版 HTML 模板（保留兼容）
│   │   ├── base.html
│   │   ├── cover_hero.html
│   │   ├── overview_kpi.html
│   │   ├── map_left_insight_right.html
│   │   ├── two_case_compare.html
│   │   ├── gallery_quad.html
│   │   ├── strategy_diagram.html
│   │   ├── chapter_divider.html
│   │   ├── chart_main_text_side.html
│   │   └── matrix_summary.html
│   └── design_system/
│       └── tokens.css              # 旧版静态 CSS Token（保留兼容）
├── tasks/                          # Celery 异步任务
│   ├── __init__.py
│   ├── celery_app.py               # Celery 配置
│   ├── asset_tasks.py              # 资产生成任务
│   ├── outline_tasks.py            # 大纲生成任务
│   ├── render_tasks.py             # 渲染任务
│   ├── review_tasks.py             # 审查任务
│   └── export_tasks.py             # 导出任务
├── prompts/                        # Prompt 模板文件
│   ├── intake_system.md            # Intake Agent
│   ├── brief_doc_system.md         # Brief Doc Agent
│   ├── visual_theme_system.md      # Visual Theme Agent
│   ├── outline_system_v2.md        # Outline Agent（主用）
│   ├── outline_system.md           # Outline Agent（旧版）
│   ├── outline.md                  # Outline 辅助
│   ├── composer_system_v2.md       # Composer v2（结构化 LayoutSpec）
│   ├── composer_system_v3.md       # Composer v3（HTML 直出）
│   ├── composer_repair.md          # Composer 修复
│   ├── vision_design_advisor.md    # Vision Review v2（多模态审查）
│   └── manus.md                    # 40 页 PPT 蓝图原文
├── config/                         # 配置管理
│   ├── __init__.py
│   ├── settings.py                 # Pydantic Settings（环境变量）
│   ├── llm.py                      # LLM 客户端（STRONG_MODEL / FAST_MODEL / 信号量限流）
│   └── ppt_blueprint.py            # PPT_BLUEPRINT 蓝图定义（PageSlot 列表）
├── scripts/                        # 运维 / 测试脚本
│   ├── seed_cases.py               # 案例库初始化
│   ├── seed_cases.json             # 种子案例数据
│   ├── e2e_test.py                 # 端到端测试（旧路径）
│   └── material_package_e2e.py     # 端到端测试（素材包路径）
├── tests/                          # 测试
│   ├── helpers/
│   │   └── theme_factory.py        # VisualTheme 测试工厂
│   ├── unit/
│   │   ├── test_compute_far.py
│   │   ├── test_validate_brief.py
│   │   ├── test_extract_brief.py
│   │   ├── test_layout_lint.py
│   │   ├── test_content_fit.py
│   │   ├── test_repair_plan.py
│   │   ├── test_critic.py
│   │   ├── test_render_engine.py
│   │   ├── test_material_pipeline.py
│   │   ├── test_reference_tools.py
│   │   └── test_phase6_tools.py
│   └── integration/
│       └── test_project_flow.py
├── frontend/                       # 轻量 SPA 前端
│   ├── index.html
│   ├── style.css
│   └── app.js
├── test_material/                  # 测试素材包
│   └── project1/                   # 示例项目素材
├── .env.example
├── docker-compose.yml
├── pyproject.toml
├── alembic.ini
└── main.py                         # FastAPI app 入口
```

---

## 1.2 环境规范

### Python 版本
```
Python 3.11+
```

### 关键依赖版本锁定

```toml
# pyproject.toml
[tool.poetry.dependencies]
python = "^3.11"
fastapi = "^0.111.0"
uvicorn = {extras = ["standard"], version = "^0.30.0"}
sqlalchemy = "^2.0.0"
alembic = "^1.13.0"
pydantic = "^2.7.0"
pydantic-settings = "^2.2.0"
celery = {extras = ["redis"], version = "^5.4.0"}
redis = "^5.0.0"
anthropic = "^0.30.0"
playwright = "^1.44.0"
httpx = "^0.27.0"
psycopg2-binary = "^2.9.0"
pgvector = "^0.3.0"
Pillow = "^10.0.0"
```

> **注意**：早期文档中的 `langchain`/`langgraph`/`langchain-anthropic`/`jinja2`/
> `python-pptx`/`sqlmodel` 依赖已不再是主流程必需。LLM 调用统一通过 `anthropic`
> SDK 的 `config/llm.py` 封装完成。

---

## 1.3 环境变量清单

```bash
# .env.example

# === 数据库 ===
DATABASE_URL=postgresql://user:password@localhost:5432/ppt_agent
REDIS_URL=redis://localhost:6379/0

# === LLM ===
OPENROUTER_API_KEY=sk-or-xxx        # OpenRouter API Key
LLM_STRONG_MODEL=...                # 复杂推理（Outline、Composer、Critic）
LLM_FAST_MODEL=...                  # 简单抽取、校验
LLM_BASE_URL=...                    # OpenRouter base URL

# === 地图 ===
AMAP_API_KEY=xxx                    # 高德地图 API Key
AMAP_SECRET=xxx

# === 对象存储 ===
OSS_ENDPOINT=https://oss-cn-hangzhou.aliyuncs.com
OSS_BUCKET=ppt-agent-assets
OSS_ACCESS_KEY=xxx
OSS_SECRET_KEY=xxx
OSS_BASE_URL=https://cdn.example.com

# === 向量检索 ===
EMBEDDING_MODEL=text-embedding-3-small
VECTOR_DIM=1536

# === 渲染 ===
PLAYWRIGHT_HEADLESS=true
SLIDE_WIDTH_PX=1920
SLIDE_HEIGHT_PX=1080

# === Celery ===
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# === 业务配置 ===
MAX_REPAIR_ATTEMPTS=3
MAX_SLIDES_PER_DECK=30
CASE_LIBRARY_MIN_SIZE=30
```

---

## 1.4 Docker Compose 服务编排

```yaml
# docker-compose.yml
version: "3.9"

services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: password
      POSTGRES_DB: ppt_agent
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  api:
    build: .
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
    env_file: .env
    ports:
      - "8000:8000"
    depends_on:
      - db
      - redis

  worker:
    build: .
    command: celery -A tasks.celery_app worker --loglevel=info -Q default,render,export
    env_file: .env
    depends_on:
      - db
      - redis

  flower:
    build: .
    command: celery -A tasks.celery_app flower --port=5555
    ports:
      - "5555:5555"
    depends_on:
      - redis

volumes:
  postgres_data:
```
