# PPT Agent — 建筑方案 AI 汇报生成系统

> 屏幕分享版 · 建议讲解节奏 8–10 分钟

---

## 一句话介绍

**面向建筑师的 AI 汇报材料生成系统** —— 把零散的建筑策划素材（图纸、效果图、调研文字、参考案例），通过一条**可追踪、可重试、可审查**的多 Agent 流水线，自动组织成一份风格一致、有叙事逻辑的方案汇报 PDF。

---

## 1. 业务背景

**用户场景**：建筑师在方案投标 / 中期汇报阶段，需要把几十上百份零散素材（图纸、效果图、CAD 节选、文字说明、参考案例）整理成一份 30-60 页、风格统一、有叙事逻辑的汇报 PPT。

**核心痛点**：
- 素材种类繁多、命名混乱，难以"按页"组织
- 写文案、做版式、配图三件事互相耦合，反复返工
- 让 LLM 直出 PPT 不可控：要么编造数据，要么版式崩坏，错了无法局部修复

**设计哲学**：**Workflow First, Agent Second**
> 系统首先是一个"**有明确状态、中间结果可存档、失败可重试、每页内容可追溯到原始素材**"的工作流；LLM 只在确定性节点之间做"内容加工"，不让它接管控制流。

---

## 2. 系统全景

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ 前端 SPA     │───▶│  FastAPI     │───▶│ PostgreSQL   │
│ (流程驱动)   │    │  Routers     │    │              │
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

**关键架构决策**：
- 编排不是单一 Orchestrator Agent，而是**FastAPI 路由后台线程 + Celery 任务**显式串联
- 状态机直接落在数据库 `Project.status` 字段，断点续跑靠"读库 → 从对应阶段重入"
- LLM 调用统一走 OpenRouter，自建轻量封装实现 schema 校验 / 重试 / 并发限流

---

## 3. 核心流程：素材包流水线

```
本地素材目录
    │
    ▼  ① ingest（确定性扫描 + 分类 + 去重）
MaterialPackage
  ├── MaterialItem    (原始文件单元)
  ├── Asset           (派生资产：图表、地图、案例卡)
  └── ProjectBrief    (从素材中抽取的项目元信息)
    │
    ▼  ② BriefDoc Agent (LLM)
BriefDoc (叙事主线 / 章节框架)
    │
    ▼  ③ Outline Agent (Claude Opus 强模型)
OutlineSpec (8-12 页规划：每页目的、所需素材类型)
    │
    ▼  ④ MaterialBinding (确定性匹配，无 LLM)
SlideMaterialBinding (每页绑定的素材项 + 派生资产 + 证据)
    │
    ▼  ⑤ VisualTheme Agent
项目级字体 / 配色 / 装饰规则
    │
    ▼  ⑥ Composer Agent (Claude Haiku 快模型 + asyncio 并发)
LayoutSpec × N (每页结构化布局描述)
    │
    ▼  ⑦ Jinja2 + Playwright
HTML → PNG 截图
    │
    ▼  ⑧ Critic Agent (3 层审查 + 自动修复 ≤3 次)
    │
    ▼  ⑨ Export
PDF
```

### 各阶段说明

| 阶段 | 名称 | 是否 LLM | 做什么 / 产物 |
|---|---|---|---|
| ① | **Ingest** | ❌ | 确定性扫描本地素材目录，按文件类型自动分类（图片/图表/文档/文本），去重并生成 `MaterialItem`；同时从素材中抽取项目元信息（建筑类型、面积、地点等）生成 `ProjectBrief`，并派生图表、地图、案例卡等 `Asset` |
| ② | **BriefDoc Agent** | ✅ | 汇总素材包中的文本摘录、素材摘要和 ProjectBrief，由 LLM 提炼叙事主线 —— 包含章节框架、定位语和叙事弧线。产物 `BriefDoc` 为后续 Outline 提供"讲什么故事"的语义锚点 |
| ③ | **Outline Agent** | ✅ 强模型 | 以 ProjectBrief + BriefDoc + PPT 蓝图为输入，由 Claude Opus 生成 8-12 页的 `OutlineSpec`。每页定义页面目的、所需素材类型、关键信息点。这是**全局叙事结构的唯一决策点**，因此使用强模型 |
| ④ | **MaterialBinding** | ❌ | 纯 Python 确定性匹配。按 Outline 中每页声明的素材类型 + tag，从 MaterialPackage 检索匹配的 MaterialItem 和 Asset，产出 `SlideMaterialBinding`（含绑定素材、证据摘要、覆盖率和缺失项） |
| ⑤ | **VisualTheme Agent** | ✅ | 基于 ProjectBrief 和参考案例偏好，生成项目级视觉主题 —— 字体组合、主色/辅色配色、间距规则和装饰元素。`VisualTheme` 作为全局样式约束传递给 Composer 和渲染层 |
| ⑥ | **Composer Agent** | ✅ 快模型 | 逐页将 OutlineSlideEntry + Binding + Theme 转为结构化 `LayoutSpec`。使用 Haiku + `asyncio.gather` 8 路并发，控制文字密度、图文关系和版式骨架。`LayoutSpec` 是**页面级核心协议**，定义区块类型、内容、位置 |
| ⑦ | **Render Engine** | ❌ | Jinja2 模板将 LayoutSpec 渲染为自包含 HTML（Design Token CSS 内联），解析 `asset:{id}` 引用为实际路径。Playwright Headless Chromium 截图生成 PNG。9 套模板覆盖封面、概览、章节、地图、案例对比、图表等版式 |
| ⑧ | **Critic Agent** | 部分 | 三层审查（L1 纯规则 / L2 语义 LLM / L3 视觉 LLM），详见下文。不通过时触发 Composer 局部重生成 → 重渲染 → 重审查，最多循环 3 次 |
| ⑨ | **Export** | ❌ | 将全部 PNG 截图按页序合成 PDF 文件 |

---

## 4. 设计亮点

### 4.1 素材包：消灭幻觉的根本办法

**问题**：早期版本让 LLM 直接从自由对话生成 PPT —— 数据靠编、引用无法追溯、改一页要重生成全套。

**方案**：把"用户的所有素材"先固化成 `MaterialPackage`，作为整个流水线的**唯一事实源**。后续所有 Agent 只能消费 MaterialPackage 里有的内容，不能自己想象。

**取舍**：
| 牺牲 | 换来 |
|---|---|
| 用户灵活度（必须先准备素材包） | 每页内容可追溯到具体素材文件 |
| 不能直接对话生成 | 修改单页不影响其他页 |
| | 失败可从任意阶段重入 |

### 4.2 素材绑定：确定性匹配 vs LLM 决策

**问题**：让 LLM 决定"第 5 页用哪几张图、配哪段文字"会产生幻觉 —— 引用不存在的图、把案例 A 的图配到案例 B 的文字旁。

**方案**：`MaterialBinding` 是纯 Python 确定性逻辑，按 `Outline` 中声明的"所需素材类型 + tag"去 MaterialPackage 检索匹配。LLM 不参与这一步。

**收益**：少了一些"创意搭配"的空间，但**消除了图文错位的整类故障**。

### 4.3 强弱模型混用

| 阶段 | 模型 | 理由 |
|---|---|---|
| Outline 生成 | Claude Opus 4.6（强） | 全局叙事结构只生成 1 次，质量优先 |
| Composer 单页合成 | Claude Haiku 4.5（快） | 每页一次，N 页并发，延迟与成本敏感 |
| Critic 语义审查 | Claude Haiku 4.5（快） | 轻量校验，时效优先 |

**收益**：单页合成靠 `asyncio.gather` 8 路并发，端到端延迟可控；Critic 语义层兜底快模型可能丢失的细节。

---

## 5. 审查闭环（Critic）

LLM 输出的不可控性靠**三层审查 + 局部修复**收敛。

| 层 | 实现 | LLM | 代表规则 |
|---|---|---|---|
| **L1 规则审查** | `tool/review/layout_lint.py` | ❌ 纯 Python | 文字溢出 / 缺必需块 / 模板未知 / 内容密度超标 |
| **L2 语义审查** | `tool/review/semantic_check.py` | ✅ 快模型 | 数值与 brief 不一致 / 无支撑断言 / 风格词矛盾 / 甲方名称错误 |
| **L3 视觉审查** | Composer 多模态 LLM | ✅ 快模型 | 视觉杂乱 / 留白浪费 / 图片模糊 |

### 决策树

```
P0 不可修       ──▶  ESCALATE_HUMAN  （标记失败，等人工介入）
P0/P1 可自动修  ──▶  REPAIR_REQUIRED （自动修复，最多重试 3 次）
仅 P2          ──▶  REPAIR_REQUIRED （修复但不阻断导出）
无问题          ──▶  PASS
```

**为什么这么分层**：把"能用规则判的"和"必须看语义的"分开，**节省 LLM 调用 70%+** —— 大部分版式问题（文字溢出、缺标题）根本不需要 LLM。

---

## 6. 参考案例作为素材输入

当前链路不单独做向量检索。参考案例默认以图片、文字说明、案例卡等形式随 `MaterialPackage` 一起进入系统，并在 Outline / VisualTheme / MaterialBinding 阶段直接使用。

### 数据流

```
MaterialPackage
    ├── MaterialItem（案例图片 / 文字说明 / 来源信息）
    ├── Asset（案例卡 / 对比图 / 引用摘要）
    └── ProjectBrief
            │
            ▼  Outline / VisualTheme / MaterialBinding 直接消费
```

### 当前做法

- **统一入口**：参考案例和其他设计素材走同一条素材包链路，不再单独推荐或检索
- **统一事实源**：页面里使用的案例内容直接来自素材包文件与派生资产，不会出现“检索结果”和“实际引用素材”不一致
- **统一复用**：同一份案例素材既能参与叙事，也能直接生成案例卡、对比图等页面资产

---

## 7. 技术栈

| 层 | 选型 | 选型理由 |
|---|---|---|
| Web 框架 | FastAPI + Pydantic v2 | 异步原生、Schema 跨层共用 |
| 数据库 | PostgreSQL 16 | 保存项目、素材、提纲、页面与审查记录 |
| ORM / 迁移 | SQLAlchemy 2.0 + Alembic | 常规关系模型与迁移管理 |
| 任务队列 | Celery 5.4 + Redis 7 | 三队列（default / render / export）资源隔离 |
| LLM | Claude Opus 4.6 / Haiku 4.5（OpenRouter） | 强弱混用控成本 |
| LLM 封装 | 自建轻量封装 | 不引入 LangChain，控制权与依赖体积 |
| 渲染 | Jinja2 + Playwright Headless Chromium | 设计师熟悉 HTML/CSS、截图保真 |
| 图表 | matplotlib | 数据驱动图表（bar/line/pie/radar） |
| 部署 | docker-compose | 6 容器开箱即用：api / worker / renderer / flower / db / redis |

---

## 8. 关键设计取舍

### Q1：为什么不用 LangChain / LangGraph？

依赖里有但代码零引用 —— 早期 LangGraph StateGraph 已被移除。原因：

- **业务是确定性流水线，不是 Agent 自主决策**：状态机已在 DB 里（`ProjectStatus` 枚举），Celery 已做了重试 / 持久化，再叠 LangGraph Checkpointer 是双写
- **跨进程异步边界**（FastAPI 后台线程 + Celery worker + 渲染 worker）很难塞进单一 StateGraph 运行时
- 自建的轻量封装已覆盖：schema 校验、JSON 解析重试、Semaphore 并发限流、错误分类，**可控性远高于 LangChain 抽象**

### Q2：为什么是 PDF-first 而不是 PPTX？

- HTML/CSS 在版式精确度、字体表现、图文混排上**全面优于 python-pptx**
- 客户最终交付物本来就是 PDF，没有"现场再编辑"的诉求
- python-pptx 已在依赖中，未来若需要可补，但不是当前主线

### Q3：为什么把审查拆成 L1/L2/L3 三层？

- **成本**：L1 纯规则零成本能挡掉 70% 问题，避免无意义的 LLM 调用
- **可解释性**：规则审查的报错码（R001 / R002…）可以直接告诉用户"标题超长了"，而不是让 LLM 编一段解释
- **可修复性**：规则层错误能直接由 `repair_plan.py` 自动修，不需要 LLM 参与

### Q4：单 Agent 编排 vs 分布式编排？

实际编排逻辑分布在：
- `api/routers/material_packages.py` —— 摄入触发
- `api/routers/outlines.py` —— 后台线程串联生成链
- `tasks/*.py` —— Celery 异步重任务

**理由**：每个阶段的资源画像差异极大（Outline 是 LLM bound、Render 是 CPU/IO bound、Export 是 IO bound），用 Celery 队列天然做资源隔离比塞进单 Agent 进程更直接。

---

## 9. 工程难点

| 难点 | 解法 |
|---|---|
| LLM 输出格式不稳定 | 自建 `call_llm_structured`：Pydantic JSON Schema 拼进 system prompt + 失败重试 + 用错误信息引导模型修正 |
| Playwright 在 Celery worker 冷启动慢 | 拆出独立 `renderer` 队列，单独维护浏览器实例 |
| Reference Agent 召回质量 | query 文本只拼"判别性强"的字段（建筑类型、风格、规模），并对空字段做过滤 |
| 参考案例链路与主流程一致性 | 参考案例默认通过 `MaterialPackage` 进入，避免额外检索链路与主链路维护两套事实源 |

---

## 10. 未来演进

- **PPTX 导出**：补齐 python-pptx 链路，支持设计师二次编辑
- **视觉审查闭环**：L3 视觉审查目前只标记问题，未自动修复 → 让 Critic 输出修复指令再回到 Composer
- **素材包利用增强**：未来可在素材包内部补充更细的标签和语义组织，支持更快定位已有素材，但当前主链路不依赖额外检索阶段
- **从 Workflow 走向 Agent**：现阶段是确定性流水线；如果后续需要"用户对结果不满 → 自主决定改哪几页 → 多轮重生成"，可考虑引入 LangGraph 做局部 Agent 化

---

## 11. 如果只能记住三件事

1. **Workflow First, Agent Second** —— 不让 LLM 接管控制流，状态明确、可重试、可追溯
2. **素材包是唯一事实源** —— 消灭幻觉的根本办法是让 LLM 没有"想象空间"
3. **强弱模型混用 + 三层审查** —— 用最便宜的方式拿到可接受的质量，贵模型只用在刀刃上
