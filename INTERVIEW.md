# PPT Agent — 项目说明（面试用）

> 屏幕分享版 · 建议讲解节奏 8–10 分钟，剩余时间留给追问
> 我的职责：**PPT 生成流程设计 + 对话 RAG 流程设计与效果改进**
> 系统作者：外包团队搭建主体框架，我负责其中两条业务线的设计与迭代

---

## 0. 一句话介绍

这是一款**面向建筑师的 AI 全能助手**，PPT Agent 是其中负责"把建筑策划材料自动生成方案汇报 PDF"的子系统 —— 它把设计师手里散落的素材（场地照、效果图、CAD 节选、文字说明）组织成一条**可追踪、可重试、可审查**的生成流水线，最终稳定输出 PDF 汇报材料。

---

## 1. 业务背景与痛点

**用户场景**：建筑师在方案投标 / 中期汇报阶段，需要把几十上百份零散素材（图纸、参考案例、调研文字、规范条文）整理成一份 30-60 页、风格一致、有叙事逻辑的汇报 PPT。这件事在事务所里通常占用一名实习生整整 1-2 周。

**核心痛点**：
- 素材种类多、命名乱，难以"按页"组织
- 写文案、做版式、配图三件事互相耦合，反复返工
- LLM 直出 PPT 不可控：要么编造数据，要么版式崩坏，错了无法局部修

**我们的设计哲学**：**Workflow First, Agent Second**。系统首先是一个"**有明确状态、中间结果可存档、失败可重试、每页内容可追溯到原始素材**"的工作流；LLM 只在每个确定性节点之间做"内容加工"，不让它接管控制流。

---

## 2. 系统全景（先建立大图）

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ 前端轻量 SPA │───▶│  FastAPI     │───▶│ PostgreSQL   │
│ (流程驱动)   │    │  Routers     │    │ + pgvector   │
└──────────────┘    └──────┬───────┘    └──────────────┘
                           │
                  ┌────────┼────────┐
                  ▼        ▼        ▼
              ┌───────┐ ┌──────┐ ┌────────┐
              │ Agent │ │Celery│ │ Render │
              │  层   │ │Tasks │ │Engine  │
              └───┬───┘ └──┬───┘ └───┬────┘
                  │        │         │
                  └────────┼─────────┘
                           ▼
                    ┌──────────────┐
                    │ HTML→PNG→PDF │
                    └──────────────┘
```

**关键事实**：
- 编排不是单一 Orchestrator Agent，而是**FastAPI 路由的后台线程 + Celery 任务**显式串联
- 状态机直接落在数据库 `Project.status` 字段，断点续跑靠"读库 → 从对应阶段重入"
- LLM 调用统一走 OpenRouter，自建 100 行封装实现 schema 校验 / 重试 / 并发限流（**没有用 LangChain / LangGraph**）

---

## 3. 核心流程（亮点 1：素材包流水线）

### 3.1 端到端数据链

```
本地素材目录
    │
    ▼  ① ingest（确定性扫描 + 分类 + 去重）
MaterialPackage
  ├── MaterialItem    (原始文件单元)
  ├── Asset           (派生资产：图表、地图、案例卡)
  └── ProjectBrief    (从素材里抽取的项目元信息)
    │
    ▼  ② BriefDoc Agent (LLM)
BriefDoc (叙事主线 / 章节框架)
    │
    ▼  ③ Outline Agent (Claude Opus 强模型)
OutlineSpec (8-12 页规划：每页目的、所需素材类型)
    │
    ▼  ④ MaterialBinding (确定性匹配，无 LLM)
SlideMaterialBinding (每页绑定的素材项 + 派生资产 + 证据片段)
    │
    ▼  ⑤ VisualTheme Agent
项目级字体/配色/装饰规则
    │
    ▼  ⑥ Composer Agent (Claude Haiku 快模型 + asyncio.gather 并发)
LayoutSpec × N (每页结构化布局描述)
    │
    ▼  ⑦ Jinja2 + Playwright
HTML → PNG 截图
    │
    ▼  ⑧ Critic Agent (3 层审查 + 自动修复循环 ≤3 次)
    │
    ▼  ⑨ Export
PDF
```

### 3.2 设计决策（这是面试可深挖的点）

#### 决策一：为什么要"素材包"这一层？

**问题**：早期版本让 LLM 直接从自由对话生成 PPT，结果是 —— 数据靠编、引用无法追溯、改一页要重生成全套。

**方案**：把"用户的所有素材"先固化成 `MaterialPackage`，作为整个流水线的**唯一事实源**。后续所有 Agent 只能消费 MaterialPackage 里有的内容，不能自己想象。

**取舍**：
- 牺牲：用户灵活度（必须先准备素材包，不能直接对话生成）
- 换来：每页内容**可追溯到具体素材文件**、修改单页不影响其他页、失败可从任意阶段重入

#### 决策二：为什么把"素材绑定"做成确定性匹配，不用 LLM？

**问题**：让 LLM 决定"第 5 页用哪几张图、配哪段文字"会出现幻觉（引用不存在的图、把案例 A 的图配到案例 B 的文字旁）。

**方案**：`MaterialBinding` 是纯确定性逻辑 —— 按 `Outline` 中声明的"所需素材类型 + tag"去 MaterialPackage 里检索匹配。LLM 不参与这一步，但产物在业务语义上等价于一个 Agent。

**取舍**：少了一些"创意搭配"的空间，但**消除了图文错位的整类故障**。

#### 决策三：为什么强弱模型混用？

| 阶段 | 模型 | 理由 |
|---|---|---|
| Outline | Claude Opus 4.6（强） | 全局叙事结构只生成 1 次，质量优先 |
| Composer | Claude Haiku 4.5（快） | 每页一次，N 页并发，延迟与成本敏感 |
| Critic 语义审查 | Haiku 4.5 | 轻量校验，时效优先 |

**收益**：单页合成延迟从 ~12s 降到 ~3s（asyncio.gather 并发 8 路），用 Critic 兜住快模型可能丢失的细节。

---

## 4. 亮点 2：审查闭环（Critic）

LLM 输出的不可控性靠**三层审查 + 局部修复**收敛：

| 层 | 实现 | LLM | 代表规则 |
|---|---|---|---|
| L1 规则审查 | `tool/review/layout_lint.py` | ❌ 纯 Python | 文字溢出 / 缺必需块 / 模板未知 / 内容密度超标 |
| L2 语义审查 | `tool/review/semantic_check.py` | ✅ 快模型 | 数值与 brief 不一致 / 无支撑断言 / 风格词矛盾 / 甲方名称错误 |
| L3 视觉审查 | Composer 多模态 LLM | ✅ 快模型 | 视觉杂乱 / 留白浪费 / 图片模糊 |

**决策树**：
```
P0 不可修 → ESCALATE_HUMAN（标记失败，等人工介入）
P0/P1 可修 → REPAIR_REQUIRED（自动修复，最多重试 3 次）
仅 P2     → REPAIR_REQUIRED（修复但不阻断导出）
无问题    → PASS
```

**为什么这么分层**：把"能用规则判的"和"必须看语义的"分开，**节省 LLM 调用 70%+** —— 大部分版式问题（文字溢出、缺标题）根本不需要 LLM。

---

## 5. 亮点 3：参考案例 RAG（对话 + 推荐场景）

**这是我负责"对话 RAG 部分"在 PPT 系统里的一条落地**：从案例库里召回与项目调性相近的参考案例，供 Outline / VisualTheme Agent 借鉴。

### 5.1 数据流

```
ProjectBrief (建筑类型/风格偏好/规模)
    │
    ▼ build_query_text() → 拼接为检索文本
    ▼ get_embedding()    → 1536 维向量
pgvector 余弦距离检索 (IVFFlat 索引)
    │
    ▼ rerank_cases()     → 业务规则重排
    ▼ preference_summary → 偏好摘要 → 喂给 VisualTheme Agent
```

### 5.2 关键实现

**SQL**（[tool/reference/search.py:92](tool/reference/search.py#L92)）：
```sql
SELECT ..., 1 - (embedding <=> CAST(:vec AS vector)) AS similarity
FROM reference_cases
WHERE building_type = :building_type
ORDER BY embedding <=> CAST(:vec AS vector)
LIMIT :top_k
```

**多 provider embedding**（[tool/reference/_embedding.py](tool/reference/_embedding.py)）：通过 `EMBEDDING_PROVIDER` 环境变量切换 `openai` / `voyage` / `qwen` / `mock`。Mock 用 `SHA256 → LCG` 产生确定性伪向量，让本地开发完全脱离外部 API。

**降级机制**：pgvector 不可用时自动回退到 `building_type + style_tags` 标签过滤，功能不中断。

---

## 6. 技术栈（按层）

| 层 | 选型 | 选型理由（一句话） |
|---|---|---|
| Web 框架 | FastAPI + Pydantic v2 | 异步原生、Schema 跨层共用 |
| 数据库 | PostgreSQL 16 + pgvector | 关系数据 + 向量检索同库，避免双写 |
| ORM / 迁移 | SQLAlchemy 2.0 + Alembic | pgvector extension 直接 raw SQL 落地 |
| 任务队列 | Celery 5.4 + Redis 7 | 三队列（default / render / export）隔离 Playwright 重资源 |
| LLM | Claude Opus 4.6 / Haiku 4.5 (经 OpenRouter) | 强弱混用控成本，OpenRouter 统一接入 |
| LLM 封装 | 自建 `config/llm.py`（200 行） | 不引入 LangChain，控制权与依赖体积 |
| 渲染 | Jinja2 + Playwright Headless Chromium | 设计师熟悉 HTML/CSS，截图保真 |
| 图表 | matplotlib | 数据驱动图表（bar/line/pie/radar） |
| 前端 | 原生 SPA（HTML/JS/CSS） | 流程页非编辑器，无需复杂框架 |
| 部署 | docker-compose（api/worker/renderer/flower/db/redis） | 6 容器开箱即用 |

---

## 7. 关键设计取舍（面试官常追问的点，我提前准备好答案）

### Q1：为什么不用 LangChain / LangGraph？

依赖里有但代码零引用 —— 早期 `agent/graph.py`（LangGraph 5 节点 StateGraph）已被移除。原因：

- **业务是确定性流水线，不是 Agent 自主决策**：状态机已经在 DB 里（`ProjectStatus` 枚举），Celery 已经做了重试 / 持久化，再叠 LangGraph Checkpointer 是双写
- **跨进程异步边界**（FastAPI 后台线程 + Celery worker + 渲染 worker）很难塞进单一 StateGraph 运行时
- 自建的 200 行 `config/llm.py` 已经覆盖：schema 校验、JSON 解析重试、Semaphore 并发限流、错误分类，**可控性远高于 LangChain 抽象**

### Q2：为什么是 PDF-first 而不是 PPTX？

- HTML/CSS 是 Web 工程能力的舒适区，**版式精确度 + 字体表现 + 图文混排可控性 ≫ python-pptx**
- 客户最终交付物本来就是 PDF，没有"现场再编辑"的诉求
- python-pptx 已在依赖中，未来若需要可补，但不是当前主线

### Q3：为什么要把审查拆成 L1/L2/L3 三层而不是一次性丢给多模态 LLM？

- **成本**：L1 纯规则零成本能挡掉 70% 问题，避免无意义的 LLM 调用
- **可解释性**：规则审查的报错码（R001 / R002…）可以直接告诉用户"标题超长了"，而不是让 LLM 编一段解释
- **可修复性**：规则层错误能直接由 `repair_plan.py` 自动修，不需要 LLM 参与

### Q4：单 Agent 编排 vs 分布式编排，为什么选后者？

实际编排逻辑分布在：
- `api/routers/material_packages.py` —— 摄入触发
- `api/routers/outlines.py` —— 后台线程串联生成链
- `tasks/*.py` —— Celery 异步重任务

**理由**：每个阶段的资源画像差异极大（Outline 是 LLM bound、Render 是 CPU/IO bound、Export 是 IO bound），用 Celery 队列天然做资源隔离比塞进单 Agent 进程更直接。

---

## 8. 我的具体职责

### 我负责的部分

- **PPT 生成 workflow 设计**
  - 拆分阶段、定义状态机、决定哪些阶段走 LLM / 哪些走确定性逻辑
  - Outline → Binding → Composer 的数据契约（特别是 `LayoutSpec` 的协议设计）
  - Critic 三层审查的规则定义与决策树
- **对话 RAG 流程设计与效果改进**
  - Reference Agent 的 query 构造（`build_query_text` 字段拼接策略）
  - Embedding 多 provider 切换与 mock 实现
  - Rerank 策略迭代（业务规则 + 偏好摘要）

### 不是我做的部分（如实说）

- 整体框架（FastAPI 路由骨架、Celery 部署、DB schema 设计）由外包团队搭建
- 渲染管线（Jinja2 模板 + Playwright）由其他成员实现
- 前端 SPA 由前端同事维护

### 我做的"效果改进"具体例子

- 把 Composer 从"HTML 直出"改为"先生成 LayoutSpec 再渲染"，让审查可以在结构层面进行（不必等截图后再判断）
- 引入"素材绑定"作为独立阶段，从根上消除图文错位幻觉
- Critic 加入 L2 语义审查的 S001（数值一致性），解决了甲方反馈的"AI 编造面积数据"问题

---

## 9. 难点与踩过的坑

1. **LLM 输出格式不稳定** → 自建 `call_llm_structured`：把 Pydantic JSON Schema 拼进 system prompt + 失败重试 + 用错误信息引导模型修正
2. **Playwright 在 Celery worker 里冷启动慢** → 拆出独立 `renderer` 队列，单独维护浏览器实例池
3. **Reference Agent 的 query 文本如何拼**：早期把所有 brief 字段一股脑拼进去，召回反而变差 → 现在只拼"判别性强"的字段（建筑类型、风格、规模），并对空字段做过滤
4. **mock embedding 的设计**：本地开发不想依赖 API，又希望相对相似度有意义 → 用 `SHA256 → LCG → L2 normalize`，相同文本得到相同向量，能跑通端到端测试

---

## 10. 未来演进方向

- **PPTX 导出**：补齐 python-pptx 链路，支持设计师二次编辑
- **视觉审查闭环**：L3 视觉审查目前只标记问题，未自动修复 → 下一步让 Critic 输出修复指令再回到 Composer
- **素材包级 RAG**：当前 RAG 只在参考案例库；未来想把项目自身素材也建索引，支持"按语义找素材"
- **从 Workflow 走向 Agent**：现阶段是确定性流水线；如果后续需要"用户对生成结果不满 → 自主决定改哪几页 → 多轮重生成"，可能引入 LangGraph 做局部 Agent 化

---

## 11. 如果只能记住三件事

1. **Workflow First, Agent Second** —— 不让 LLM 接管控制流，状态明确、可重试、可追溯
2. **素材包是唯一事实源** —— 消灭幻觉的根本办法是让 LLM 没有"想象空间"
3. **强弱模型混用 + 三层审查** —— 用最便宜的方式拿到可接受的质量，贵模型只用在刀刃上
