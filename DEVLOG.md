# PPT Agent — 开发过程记录

> 记录从架构决策到端到端打通的完整开发历程，包括每个阶段的实现内容、遇到的问题及修复方案。

---

## 一、项目背景

**目标：** 构建一个面向建筑设计场景的 AI Agent 系统，接收自然语言项目需求，自动生成专业的建筑方案汇报 PPT，输出 PDF 文件。

**核心挑战：**
- 多 Agent 协作（Intake → Reference → Outline → Composer → Critic）
- 异步任务编排（Celery + Redis）
- 向量检索（pgvector）+ LLM 双路检索
- HTML 模板渲染 + Playwright 截图 → PDF 合并

---

## 二、架构决策

### 2.1 架构选型

初期评估了两个方向：

| 方案 | 优点 | 缺点 |
|------|------|------|
| 微服务架构 | 独立扩展 | 运维复杂，开发成本高 |
| **模块化单体** | 开发快，部署简单 | 水平扩展有限 |

**最终选择模块化单体**，原因：项目处于早期验证阶段，业务逻辑尚未稳定，单体更易于快速迭代。

### 2.2 关键技术选型

- **LLM 层**：Anthropic Claude（Opus 强模型用于大纲生成，Sonnet/Haiku 快模型用于其他步骤），支持通过 OpenRouter 透传
- **向量数据库**：PostgreSQL + pgvector 扩展，避免引入额外中间件
- **任务队列**：Celery + Redis，支持多队列（default / outline / render / export）
- **Agent 编排**：LangGraph StateGraph，5 节点有向图，支持修复循环
- **渲染**：Jinja2 模板 → HTML → Playwright headless Chromium → PDF

### 2.3 建筑类型设计决策

所有建筑类型（museum / office / cultural / education 等）在代码层面**不做硬编码限制**：
- `building_type` 在所有模型中均为枚举/参数
- Prompt 中 `{building_type}` 通过 f-string 动态注入
- 案例库通过 `building_type` 字段过滤，天然支持多类型

---

## 三、编码阶段

### Phase 1 — 基础地基

**实现内容：**
- `pyproject.toml`：Poetry 依赖管理
- `docker-compose.yml`：api + worker + renderer + db + redis
- `config/settings.py`：Pydantic Settings，统一读取 `.env`
- `main.py`：FastAPI 入口，全局中间件
- `db/`：SQLAlchemy Base、Session 工厂、Alembic 迁移

**问题：JSONB 默认值语法错误**

Alembic 迁移文件中：
```python
# 错误写法（SQLAlchemy 会生成 DEFAULT '''[]'''，PostgreSQL 拒绝）
sa.Column("style_preferences", JSONB, server_default="'[]'")

# 正确写法
sa.Column("style_preferences", JSONB, server_default=sa.text("'[]'"))
```
影响字段：`style_preferences`、`missing_fields`、`conversation_history`、`style_tags`、`feature_tags`、`images`、`selected_tags`、`issues_json` 共 8 个。

---

### Phase 2 — Tool 层

**实现内容（纯函数，无外部依赖）：**
- `tool/input/compute_far.py`：容积率指标计算
- `tool/input/validate_brief.py`：简报完整性校验
- `tool/review/layout_lint.py`：布局规则检查（15 条规则）
- `tool/review/repair_plan.py`：自动修复执行器
- `tool/slide/content_fit.py`：内容密度约束检查

全部通过单元测试。

---

### Phase 3 — FastAPI + 项目 CRUD

**实现内容：**
- `api/deps.py`：DB Session 依赖注入
- `api/middleware.py`：全局异常处理，统一 `APIResponse` 格式
- `api/routers/projects.py`：项目创建、查询、简报提交、确认
- `api/routers/sites.py`：场地坐标录入

---

### Phase 4 — LLM 层 + Intake Agent

**实现内容：**
- `config/llm.py`：统一 LLM 调用封装，支持结构化输出（Pydantic 解析）、重试、并发限制（Semaphore）
- `prompts/intake_system.md`：多轮对话简报采集 Prompt
- `tool/input/geocode.py`：高德地图地理编码
- `agent/intake.py`：多轮 Intake Agent，支持追问、合并历史简报

**问题：AsyncAnthropic 在模块导入时就初始化，早于 pydantic-settings 加载 `.env`**

```python
# 错误：模块导入时读取环境变量（.env 尚未加载）
client = AsyncAnthropic()

# 正确：显式传入从 settings 读取的 key
from config.settings import settings
client = AsyncAnthropic(api_key=settings.anthropic_api_key or None)
```

---

### Phase 5 — 案例库 + Reference Agent

**实现内容：**
- `scripts/seed_cases.json`：15 个多类型建筑案例（博物馆、办公、文化等）
- `scripts/seed_cases.py`：初始化脚本，生成 embedding 写入 DB
- `tool/reference/_embedding.py`：多 Provider embedding（mock / openai / voyage / qwen）
- `tool/reference/search.py`：pgvector 余弦相似度检索 + tag 降级检索
- `tool/reference/rerank.py`：LLM 重排序
- `agent/reference.py`：案例推荐 + 偏好摘要 Agent

**问题 1：pgvector `::vector` 语法被 SQLAlchemy 误解析**

SQLAlchemy 会将 `:vec::vector` 中的 `::vector` 解析为具名参数 `:vector`，导致 SQL 语法错误。

```python
# 错误
"embedding <=> :vec::vector"

# 正确
"embedding <=> CAST(:vec AS vector)"
```
此问题在 `scripts/seed_cases.py` 和 `tool/reference/search.py` 中均有出现。

**问题 2：seed_cases.py 事务级联失败**

一个案例出错后，后续所有 DB 操作因 `InFailedSqlTransaction` 全部失败。

```python
# 修复：每个案例的 except 块中加 rollback
except Exception as e:
    errors += 1
    db.rollback()   # ← 新增
    print(f"  [ERROR] ...")
```

**问题 3：seed_cases.json 中文引号破坏 JSON 结构**

部分案例 `summary` 字段中包含 ASCII 双引号（如 `以"收藏器"为核心`），导致 JSON 文件解析失败。用 Python regex 将内嵌引号替换为中文书名号：

```python
re.sub(r'\"([^\"]{1,20})\"', r'「\1」', content)
```

---

### Phase 6 — 资产生成

**实现内容：**
- `tool/site/poi_retrieval.py`：高德 POI 检索（无 key 时返回 mock）
- `tool/site/mobility_analysis.py`：交通可达性分析
- `tool/asset/chart_generation.py`：matplotlib 图表（bar / line / pie / radar）
- `tool/asset/map_annotation.py`：高德静态地图 + 标注
- `tasks/celery_app.py`：Celery 配置，多队列路由
- `tasks/asset_tasks.py`：并发资产生成任务
- `api/routers/assets.py`：资产查询接口

---

### Phase 7 — Outline + Composer + Render

**实现内容：**
- `prompts/outline_system.md`：大纲生成 Prompt（STRONG_MODEL）
- `agent/outline.py`：Outline Agent，生成 18 页结构化大纲
- `agent/composer.py`：Composer Agent，逐页扩展为 SlideSpec（FAST_MODEL，并发）
- `render/design_system/tokens.css`：Design Token 样式变量
- `render/templates/`：5 套核心 HTML 模板（cover-hero / section-title / text-image / data-chart / closing）
- `render/engine.py`：Jinja2 渲染引擎
- `render/exporter.py`：Playwright 截图 + PDF 合并
- `tasks/outline_tasks.py`：大纲生成 + 页面组合 Celery 任务
- `tasks/render_tasks.py`：渲染任务

---

### Phase 8 — 审查 + 串联

**实现内容：**
- `tool/review/semantic_check.py`：语义审查（LLM）
- `agent/critic.py`：三层 Critic（规则 lint → 语义检查 → Vision 视觉审查）
- `agent/graph.py`：LangGraph 5 节点 StateGraph，含修复循环
- `tasks/review_tasks.py`：审查 Celery 任务
- `tasks/export_tasks.py`：PDF 导出 Celery 任务
- `api/routers/render.py`：渲染/修复接口
- `api/routers/exports.py`：导出接口
- `tests/unit/test_critic.py`：21 个单元测试

---

## 四、测试

### 单元测试（117 个）

| 测试文件 | 覆盖内容 |
|---------|---------|
| `test_phase2_tools.py` | compute_far、validate_brief、layout_lint、repair_plan、content_fit |
| `test_phase4_intake.py` | extract_brief、validate_brief、geocode（mock）|
| `test_phase5_reference.py` | embedding（mock/openai）、search、rerank |
| `test_phase6_tools.py` | chart_generation、map_annotation、poi_retrieval |
| `test_phase7_render.py` | render_slide_html、exporter |
| `test_critic.py` | Critic 三层审查（LLM 调用全 mock）|

### 集成测试（14 个）

`tests/integration/test_project_flow.py` — 对真实 PostgreSQL 数据库运行：

- 项目 CRUD 与状态流转
- Intake Agent（mock LLM）
- pgvector embedding 写入与向量检索
- Outline 生成（mock LLM）
- Composer 创建 Slide 行
- Render Engine HTML 输出
- Critic 规则层
- 全流程冒烟测试

**集成测试修复过程中遇到的问题：**

| 问题 | 原因 | 修复 |
|------|------|------|
| `ValidationResult` 不可导入 | 该类不存在于 `validate_brief` | 删除该导入 |
| `case_search` 函数不存在 | 实际函数名为 `search_cases` | 更正导入 |
| `OutlineSlideEntry` 字段名错误 | `layout_template` → `recommended_template` | 更正字段名 |
| Composer mock 类型错误 | 应 mock `_SlideSpecLLM`，非 `SlideSpec` | 使用内部类型 |
| `ExtractBriefOutput.brief` 不存在 | 实际字段名为 `extracted` | 更正字段名 |
| Vision Review patch 路径错误 | `call_llm_multimodal` 为懒导入，需 patch `config.llm` | 更正 patch 路径 |

---

## 五、集成调试与端到端验证

### 5.1 基础设施启动

```bash
# 启动 PostgreSQL + Redis
docker-compose up db redis -d

# 运行数据库迁移
alembic upgrade head

# 导入案例库（mock embedding）
python scripts/seed_cases.py

# 启动 API 服务
uvicorn main:app --port 8001

# 启动 Celery Worker（Windows 需 --pool=solo）
celery -A tasks.celery_app worker --pool=solo -Q default,outline,render,export
```

### 5.2 LLM 配置问题

**问题：Anthropic API 账户余额不足**

`.env.example` 中的 API key（`sk-ant-api03-TxZL8HvR9sKT...`）账户余额已耗尽，返回 HTTP 400 credit 错误。

**解决方案：切换到 OpenRouter**

OpenRouter 支持 Claude 模型，使用 OpenAI-compatible 接口。修改 `config/llm.py` 支持双后端：

```python
# config/llm.py 核心逻辑
_USE_OPENROUTER = bool(settings.openrouter_api_key)

def _model_name(model: str) -> str:
    """OpenRouter 需要 'anthropic/model-name' 前缀"""
    if _USE_OPENROUTER and "/" not in model:
        return f"anthropic/{model}"
    return model

async def _call_once(...) -> str:
    if _USE_OPENROUTER:
        # 使用 openai.AsyncOpenAI + OpenRouter base_url
        ...
    else:
        # 使用 anthropic.AsyncAnthropic 直连
        ...
```

`.env` 中设置 `OPENROUTER_API_KEY` 后自动启用。

### 5.3 Embedding 配置

从 mock 切换到 Qwen（通义千问）真实 embedding：

1. `settings.py` 新增 `qwen_api_key`、`qwen_url` 字段
2. `_embedding.py` 新增 `qwen` provider（复用 `openai.AsyncOpenAI` + dashscope base_url，设置 `dimensions=1536` 匹配 DB schema）
3. `.env` 设置 `EMBEDDING_PROVIDER=qwen`，`EMBEDDING_MODEL=text-embedding-v4`
4. 重新 seed 案例库

### 5.4 安装缺失依赖

端到端测试过程中发现以下包未安装：

```bash
pip install celery redis openai oss2 playwright
python -m playwright install chromium
```

### 5.5 OSS 配置

`.env` 中 `OSS_ENDPOINT` 填写了阿里云地址但 bucket 不存在，导致截图上传失败。将 `OSS_ENDPOINT` 置空后自动切换 mock 模式（保存至 `D:\tmp\ppt_agent_assets\`）。

### 5.6 Windows 兼容性问题

| 问题 | 解决方案 |
|------|---------|
| Celery prefork pool 在 Windows 下任务不执行 | 启动时加 `--pool=solo` |
| `PYTHONIOENCODING` 导致中文 print 报错 | 所有命令加 `PYTHONIOENCODING=utf-8` |
| `/tmp/` 路径映射到 `D:\tmp\` | 通过 `os.path.realpath()` 确认实际路径 |

---

## 六、端到端验证结果

以「苏州博物馆扩建项目」为测试用例，完整走通全链路：

| 步骤 | API / 任务 | 状态 | 说明 |
|------|-----------|------|------|
| 1 | `POST /projects` | ✅ | 创建项目 |
| 2 | `PATCH /projects/{id}/brief` | ✅ | Intake Agent 提取简报，LLM 识别 building_type=museum、city=苏州市、gfa=25000㎡ |
| 3 | `POST /projects/{id}/confirm-brief` | ✅ | 状态 → INTAKE_CONFIRMED |
| 4 | `POST /projects/{id}/references/recommend` | ✅ | pgvector 检索推荐 5 个博物馆案例 |
| 5 | `POST /projects/{id}/references/select` | ✅ | 选择 3 个案例 |
| 6 | `POST /projects/{id}/references/confirm` | ✅ | LLM 生成偏好摘要，dominant_styles=['modern', 'cultural', 'futuristic'] |
| 7 | `POST /projects/{id}/outline/generate` | ✅ | STRONG_MODEL 生成 18 页大纲，主题「现代与传统交融」 |
| 8 | `POST /projects/{id}/outline/confirm` | ✅ | 触发 compose_slides_task |
| 9 | compose_slides_task | ✅ | 并发生成 18 张 SlideSpec（LLM 偶发 JSON 解析失败后自动重试） |
| 10 | render_slides_task | ✅ | Playwright 渲染 18 张 HTML → PNG，18/18 成功 |
| 11 | review_slides_task | ⚠️ | 规则层通过；语义层 LLM JSON 偶发中文引号解析失败，18 张 escalated |
| 12 | export_deck | ✅ | **生成 PDF，大小 1.3 MB** |

**输出文件：** `D:\tmp\ppt_agent_assets\exports\{project_id}\deck.pdf`

---

## 七、遗留问题 & 后续方向

### 已知问题

| 问题 | 严重程度 | 修复方向 |
|------|---------|---------|
| Semantic Review LLM 返回 JSON 中文引号解析失败 | 中 | Prompt 中明确要求字符串内引号必须转义；或使用更宽松的 JSON 解析（先 strip 再修复）|
| Celery prefork 在 Windows 不可用，需 `--pool=solo` | 低（生产用 Linux）| 部署文档中注明，生产环境无此问题 |
| `RecommendRequest` body 中需重复传 `project_id` | 低 | 从 body schema 中移除 `project_id`，改从路径参数读取 |
| Compose 阶段 18 页并发 LLM 调用，少数页面偶发解析失败后 fallback | 低 | 增加 fallback 内容质量，或在重试时降低并发度 |

### 后续方向

1. **前端界面** — 目前纯 API，可接入 React 前端实现可视化流程操作
2. **真实 OSS 配置** — 补全阿里云 OSS access_key/secret_key，替换 mock 存储
3. **更多模板** — 目前 5 套核心模板，可扩展至 10+ 套满足不同风格需求
4. **Prompt 优化** — 大纲和 Composer 的 Prompt 可针对不同建筑类型做专项调优
5. **案例库扩充** — 目前 15 个案例，扩充至 100+ 提升推荐质量
6. **生产部署** — 补全 docker-compose 生产配置，配置 Nginx 反向代理

---

## 八、关键配置参考

### `.env` 关键字段

```bash
# LLM（二选一）
ANTHROPIC_API_KEY=sk-ant-...          # Anthropic 直连
OPENROUTER_API_KEY=sk-or-v1-...       # OpenRouter（优先级更高）
LLM_STRONG_MODEL=claude-opus-4-6      # 用于大纲生成
LLM_FAST_MODEL=claude-sonnet-4-6      # 用于其他步骤

# Embedding
EMBEDDING_PROVIDER=qwen               # mock / openai / voyage / qwen
QWEN_API_KEY=sk-...
EMBEDDING_MODEL=text-embedding-v4
VECTOR_DIM=1536

# OSS（留空走本地 mock）
OSS_ENDPOINT=                         # 空 = mock，保存至 D:\tmp\
```

### 启动命令（开发环境）

```bash
# 1. 基础设施
docker-compose up db redis -d

# 2. 数据库迁移 + 案例库
alembic upgrade head
python scripts/seed_cases.py

# 3. API 服务
uvicorn main:app --host 0.0.0.0 --port 8001

# 4. Celery Worker（Windows）
celery -A tasks.celery_app worker --pool=solo \
  -Q default,outline,render,export --loglevel=info
```

### 测试命令

```bash
# 单元测试（117 个，无需数据库）
pytest tests/unit/ -q

# 集成测试（14 个，需运行 PostgreSQL）
pytest tests/integration/ -q

# 全部测试
pytest tests/ -q  # 131 个，全部通过
```
