---
name: Agent 冷启动包
description: Coding Agent 进入项目必读的最小上下文:规范、禁区、常用命令、常见陷阱
last_updated: 2026-04-20
owner: superxiaoyin
---

# Agent 冷启动包 — PPT Agent

> 如果你是刚进来的 Coding Agent,读完这一篇就能开始写代码。深入细节再看 [../00_index.md](../00_index.md)。

---

## 1. 项目一句话定位

**建筑方案 PPT 自动生成系统**:输入素材包(图片/图表/设计大纲),经 LangGraph 多 Agent 流水线,输出 40 页建筑汇报 PDF。

主管线:`MaterialPackage → BriefDoc → Outline → Binding → Compose → Render → Review → PDF`

---

## 2. 技术栈与模型

| 层 | 技术 |
|----|------|
| Web | FastAPI 0.111 + Uvicorn |
| 异步 | Celery 5.4 + Redis |
| 编排 | LangGraph 0.1(部分路径已切为 Celery 链) |
| LLM | OpenRouter 代理,统一经 [config/llm.py](../../config/llm.py) |
| 数据库 | PostgreSQL 16 + pgvector |
| 渲染 | Jinja2 / LLM 直出 HTML → Playwright 截图 → PDF |

**当前模型配置**(见 [.env](../../.env)):
- `LLM_STRONG_MODEL=claude-opus-4-6` — BriefDoc / Outline / Composer
- `LLM_FAST_MODEL=claude-sonnet-4-6` — 降级 fallback
- `LLM_CRITIC_MODEL=google/gemini-3.1-pro-preview` — 审查

---

## 3. Composer 双模式(**务必理解**)

| 模式 | 路径 | 何时用 |
|------|------|-------|
| **Structured (v2)** | LLM → LayoutSpec JSON → 固定 HTML 模板 | 需要严格结构一致性 |
| **HTML (v3,默认)** | LLM → body_html → 安全过滤 + theme CSS 注入 | 需要设计自由度,默认模式 |

E2E 脚本通过 `--composer-mode html|structured` 切换。默认 HTML。

**⚠️ HTML 模式下审查层只用 vision**,跳过 rule/semantic(见 [decisions/ADR-004](decisions/ADR-004-html-mode-vision-only.md))。

---

## 4. 禁区(Don't do this)

| ❌ 不要 | 原因 |
|--------|-----|
| 再引入 `agent/graph.py` 死代码 | 已被删除,主流程已切 Celery,见 [decisions/ADR-002](decisions/ADR-002-celery-over-langgraph.md) |
| 对 HTML 模式 slide 调 `LayoutSpec.model_validate(spec_json)` | 结构不兼容,直接抛异常,见 [postmortems/2026-04-07-review-loop-v2.md](postmortems/2026-04-07-review-loop-v2.md) Bug 1 |
| 在 review 写回时无脑覆盖 `slide.spec_json` | HTML 模式下会丢失 body_html,需 `is_html_mode` 守卫 |
| LLM 调用失败时返回空 issues | 会被误判为 PASS,必须返回 `*_SKIPPED` issue |
| 在 docker 外直接跑脚本 | 需先启动 db/redis,且 host override `DATABASE_URL=...@localhost:5432/...` |
| 建筑类型硬编码 | 所有类型走 `building_type` 参数注入,不加 if-else |
| 把 API key / OSS secret 写进文档或提交 | `.env` 已 gitignore,文档中用占位符 |

---

## 5. 常用命令(Windows / PowerShell 主机)

### 启动基础设施
```bash
docker compose up db redis -d
```

### 运行测试
```bash
# 单元测试(无需 DB)
pytest tests/unit/ -q

# 集成测试(需要 DB)
$env:DATABASE_URL='postgresql://user:password@localhost:5432/ppt_agent'
pytest tests/integration/ -q
```

### E2E 验证(最常用)
```bash
$env:DATABASE_URL='postgresql://user:password@localhost:5432/ppt_agent'
$env:REDIS_URL='redis://localhost:6379/0'

# 全量 41 页 real-LLM
python scripts/material_package_e2e.py test_material/project1 --real-llm --output-dir test_output/full

# 快速 smoke(2 slide)
python scripts/material_package_e2e.py test_material/project1 --real-llm --max-slides 2 --output-dir test_output/smoke
```

### Celery Worker(Windows 必须 --pool=solo)
```bash
celery -A tasks.celery_app worker --pool=solo -Q default,outline,render,export --loglevel=info
```

---

## 6. 代码规范要点

- **Pydantic v2**,不是 v1。`.model_dump()` 而非 `.dict()`
- **所有 LLM 调用必须经 [config/llm.py](../../config/llm.py)** 的 `call_llm_structured` / `call_llm_with_limit`,不要直连 SDK
- **DB 会话**用 `db/session.py` 的 `get_db_context()` 上下文管理器
- **API 响应**统一 `APIResponse[T]` 泛型,见 [api/response.py](../../api/response.py)
- **异常**用 [api/exceptions.py](../../api/exceptions.py) 中的业务异常类,不裸 raise

---

## 7. 必读清单(按优先级)

1. [STATUS.md](STATUS.md) — 现在能跑什么、不能跑什么
2. [DECISIONS_NEEDED.md](DECISIONS_NEEDED.md) — 有什么等人拍板
3. [BUGS.md](BUGS.md) — 已知坑
4. [GLOSSARY.md](GLOSSARY.md) — 项目黑话
5. [handoffs/](handoffs/)(最新一份) — 上次开发到哪
6. [decisions/](decisions/) — 架构为什么这么设计

## 8. 遇到问题时

- **架构层疑问** → [../00_index.md](../00_index.md) 查 01-15 号文档
- **类型不确定** → [../03_pydantic_models.md](../03_pydantic_models.md) 或 [../28_schema_guide.md](../28_schema_guide.md)
- **管线流程不清楚** → [../26_pipeline_flow_overview.md](../26_pipeline_flow_overview.md)
- **审查规则** → [../11_review_rules.md](../11_review_rules.md)
- **以上都没有** → 读具体源码 + 问用户
