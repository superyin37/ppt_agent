# 技术面深挖准备：PPT_Agent

> **使用说明**：每个条目按三层深度组织：
> - **30 秒回答**：高密度、无废话，先给结论再给骨架
> - **2 分钟展开**：给出数据流、关键参数、设计取舍
> - **追问预案**：面试官最可能的 3 个 why，准备好再下一层

---

## 第一章 系统全景与设计决策（整体观）

### 1.1 一分钟项目介绍

**30 秒回答**
PPT_Agent 是一个端到端的建筑方案 PPT 自动生成系统：输入素材包（图片、图表、文档），输出 40-41 页的设计提案 PDF。核心是多 Agent LLM 流水线 + Celery 异步编排。当前代码量约 1.5 万行 Python，12 个单测文件 96+ 用例，单次真机全流程跑过 41 页。

**2 分钟展开**
- **上下游定位**：替代传统"建筑师 + 设计师 + PPT 小工"3 人 3 天的工作量，目标是 30 分钟出稿
- **技术栈**：FastAPI + PostgreSQL + pgvector + Redis + Celery + Playwright + Claude/Gemini/OpenRouter 多模型
- **链路 11 步**：Intake → Reference（案例检索）→ Asset 生成 → BriefDoc → VisualTheme → **Outline → ConceptRender** → MaterialBinding → Composer（v2 结构化 / v3 HTML 双模）→ Render（Playwright 截图）→ Review（三层）→ Export（PDF）
- **交付形态**：模块化单体（ADR-001），不走微服务；Celery 分队列异步（render/export/concept_render/default）

**追问预案**
1. **"为什么不做成 SaaS 多租户？"** → 当前是面向建筑院的内部工具，单次生成成本高（¥5-8/篇 LLM 费），多租户需要先解决配额/计费/资源隔离，ROI 不如先把单次效果打磨好
2. **"40 页是怎么定下来的？"** → 来自真实建筑院中标册的平均页数（32-48），在 `config/ppt_blueprint.py` 硬编码为蓝图；可配置但目前未做数据驱动
3. **"如果让你重构，最想动哪里？"** → Composer v2/v3 双模长期维护成本高，应收敛到 v3 HTML；蓝图应该数据驱动以支持不同类型项目（不止建筑）

---

### 1.2 为什么是模块化单体，而不是微服务（ADR-001）

**30 秒回答**
初创阶段 + 数据库共享 + 跨 Agent 传递的是富上下文（整个 Outline/BriefDoc），微服务的网络序列化和 schema 版本对齐成本高于并发收益。我们用目录隔离（`agent/`、`tool/`、`schema/`、`render/`）保留未来拆分的可能。

**2 分钟展开**
- **单体的好处**：冷启动一次、同进程内共享 DB session、Pydantic 对象零序列化开销、单机断点调试
- **为什么不会"单体腐烂"**：硬性约束是**严格的目录分层** —— `agent/` 只依赖 `schema/` 和 `tool/`，不反向依赖；`tool/` 是纯函数 + 外部 client；`schema/` 是 Pydantic v2，无副作用
- **未来拆分线**：如果某个 Agent 成为瓶颈（如 Composer 需要 GPU 本地模型），直接按 `agent/X.py` 抽成 service，对外暴露 `generate_outline()` 这一层，上游调用方只需换 client

**追问预案**
1. **"单机 Celery 能扛多大并发？"** → Windows 下 `--pool=solo` 是瓶颈，Linux 上 prefork 4-8 进程，每机支持 ~20 个并发项目；再往上先加机器，不拆服务
2. **"数据库会不会是瓶颈？"** → 当前连接池 20，一次项目生成 ~200 次查询，瓶颈在 LLM API 而非 DB
3. **"你怎么判断'腐烂'在发生？"** → 看 import graph，如果 `agent/A` 开始 import `agent/B`（而不是都走 `schema/`），就是要拆分的信号

---

### 1.3 为什么是 Celery 而不是 LangGraph / Dify（ADR-002）

**30 秒回答**
核心业务逻辑里有**条件循环 + 人工介入 + 失败重试**三个特性：Review → Repair → Re-render → Re-review 最多 3 轮，用户在 Outline 确认节点会卡住。LangGraph 的图模型表达条件循环需要大量 state 管理，Celery 的 task chain + retry 更直接。

**2 分钟展开**
- **Celery 提供的**：队列路由（render 重任务单独队列）、`max_retries` + 指数退避、Flower 可视化、分布式锁（Redis）
- **LangGraph 的不适配**：需要把整个流程建模成图，Review 循环要用 conditional_edge，节点状态需要持久化到 checkpointer —— 我们已经有 PostgreSQL 做了状态机（`ProjectStatus` 枚举），重复造轮子
- **Dify 的不适配**：Dify 强于"对话式应用"，我们是"一次性批量生成"，核心是异步任务编排，不是对话
- **我们真正用到的 Celery 能力**：`bind=True` 拿到 self 做重试、`task_routes` 分队列、`acks_late` 防 worker 崩溃丢任务

**追问预案**
1. **"Celery task 之间传 UUID 还是对象？"** → 全部传 UUID（project_id），每个 task 自己开 DB session 查数据；避免 pickle 反序列化和对象陈旧问题
2. **"你有没有考虑过 Temporal？"** → 看过，Temporal 适合长时工作流（天级），我们单个项目 30 分钟内结束，Celery 够用；Temporal 额外的运维成本不划算
3. **"Review 的循环用 Celery 怎么保证不会死循环？"** → `max_repairs=3` 硬上限 + BUG-012 修复后 vision-only（见 1.5）避免幻觉 issue 无限触发

---

### 1.4 Composer v2/v3 双模设计（ADR-003）

**30 秒回答**
v2 是"LLM 输出结构化 LayoutSpec JSON → 我们用模板渲染 HTML"，v3 是"LLM 直出 body_html"。v3 是默认模式，v2 保留作为审计/兜底。双模存在是因为 v2 可控性强（规则可 lint），v3 创造力强（视觉效果好），两者 review 策略不同。

**2 分钟展开**
- **v2 流程**：LLM 返回 `{primitive_type: "SplitHLayout", region_bindings: {...}}` → `render_slide_html()` 套 11 种 Jinja 模板
- **v3 流程**：LLM 直接返回 `body_html` → `html_sanitizer.py` 去脚本/事件 → 注入主题 CSS 变量 → 完成
- **关键参数差异**：v2 max_tokens=1500，v3 max_tokens=4000（HTML 比 JSON 长）
- **审查层不同**：v2 走三层（rule lint + semantic + vision），v3 只走 vision（ADR-004，下一节展开）
- **生产数据**：当前默认 v3，v2 在 `--composer-mode structured` 标志下可触发，用于需要严格排版一致性的场景（如投标合规）

**追问预案**
1. **"维护两套不是负担吗？"** → 是，但 v2 的 `LayoutSpec` schema 是整个系统的"可审计契约"，删掉它意味着失去客户端做定制渲染的能力；短期留着
2. **"LLM 直出 HTML 不会乱写样式吗？"** → 会，所以我们注入了 `--color-primary` 等 CSS 变量约束主题色；LLM 只能写 class + 少量 inline style；`html_sanitizer` 做白名单过滤
3. **"v3 的创造力如何量化？"** → 没有量化，是主观评估 + 视觉 Review 得分（D001-D012 的 5 维打分）；这是一个坦诚的 gap

---

### 1.5 为什么 HTML 模式只做视觉审查（ADR-004 / BUG-012）

**30 秒回答**
HTML 是任意 DOM，规则 lint（R001-R015）定义在 `LayoutSpec` 结构上，对 HTML 无意义；语义层检查 `content_blocks` 字段，HTML 里找不到这个字段。强行跑会产生幻觉 issue（R006 EMPTY_SLIDE、R008 KEY_MESSAGE_MISSING），触发无限修复循环。

**2 分钟展开**
- **BUG-012 的现场**：HTML 模式下 critic 把 body_html 塞回 `LayoutSpec.model_validate()` → 得到空 LayoutSpec → rule lint 报 R006/R008 → repair 生成新的 body_html → 再塞回空 LayoutSpec → 同样的 issue → 死循环
- **修复方案**：在 `agent/critic.py` 里加 `is_html_mode` 分支，HTML 模式下跳过 rule/semantic 层，只跑 vision
- **Vision 层为什么还有效**：多模态 LLM 看的是**渲染后的截图**，不依赖任何结构字段，天然适配任意 DOM
- **代价**：放弃了 v2 模式下的可自动化修复（如 text_overflow 自动裁剪），现在必须让 Composer 重新生成

**追问预案**
1. **"为什么不干脆统一只做 vision？"** → Vision 贵（多模态 + 截图），且 v2 结构化在审计/合规场景有价值；混合策略是权衡
2. **"Vision 误判怎么办？"** → Vision 也有幻觉，所以 `max_repairs=3` 硬上限，超限标记 `ESCALATE_HUMAN` 转人工
3. **"为什么 BUG-012 能活到 4 月才发现？"** → 早期只跑 v2，Composer v3 是 4-05 才上线；v3 + Review 真机全跑是 4-07 才做，4-09 发现

---

### 1.6 Concept Render 嵌入 Outline 的决策（ADR-005，最新）

**30 秒回答**
Outline Agent 本来就要为 3 个方案命名和定位，再多输出 7 个字段（massing_hint、material_hint 等）几乎零增量成本；若独立成一个 Agent，要重复传 BriefDoc + MaterialPackage 上下文，多一次 LLM 调用 + 一次 DB 查询。嵌入 Outline 单一真相源。

**2 分钟展开**
- **数据流**：Outline LLM 输出 `concept_proposals: list[ConceptProposal]`（3 个），每个带 design_idea/massing/materials/mood/keywords
- **ConceptRender Agent 的职责简化**：只负责"给定 3 个 proposal，调 runninghub 生成 9 张图"
- **生成策略**：3 个 proposal 并行（asyncio.gather），每个 proposal 内部 3 个视角串行（鸟瞰 → 外透 → 内透），denoise 从 0.75 递减到 0.50，让后一张用前一张做风格锚点
- **失败兜底**：runninghub 挂了 → 每张图生成灰色 placeholder + 水印，状态标 `fallback`，流水线不阻塞

**追问预案**
1. **"为什么不用 text-to-image？要 init_image 图生图做什么？"** → 我们有 `site.boundary.image`（用地红线）作为真实锚点，图生图保证方案图跟真实地形对齐；纯 text2img 会飞
2. **"串行链不会 3 倍延迟吗？"** → 会，单 proposal 9×20s=180s；但 3 个 proposal 并行总延迟 ~180s；换成全并行会失去视觉一致性，权衡了
3. **"denoise 0.75/0.60/0.50 怎么调出来的？"** → 实验性：0.75 让鸟瞰图有足够自由度接近设计意图；后续视角 denoise 下降以保留前一张的风格；是反复试出来的，没有数学推导

---

## 第二章 核心模块深挖

每个模块按 **职责 → 输入输出契约 → 关键算法/Prompt → 失败模式 → 优化历史** 五段式展开。

---

### 2.1 Outline Agent（大纲生成）

**职责**
把 `BriefDoc + PPT_BLUEPRINT（40 slots）+ MaterialPackage manifest` 转成 `Outline(40 个 SlotAssignment + 3 个 ConceptProposal)`。

**输入输出契约**
- 入：ProjectBrief、BriefDoc、Blueprint（slot 列表）、MaterialPackage 摘要
- 出：Pydantic `_OutlineLLMOutput`（deck_title、total_pages、assignments、concept_proposals）
- 约束：每个 slot 的 content_directive ≤120 字，必须具体到项目（禁止复读蓝图描述）
- 模型：`LLM_STRONG_MODEL`（当前 Claude Opus / Gemini 3 Pro），max_tokens=8000

**关键 Prompt 设计**（`prompts/outline_system_v2.md`）
- 模板变量替换：`{building_type}`、`{project_name}`、`{city}`、`{province}`、`{positioning_statement}`、`{narrative_arc}`
- Blueprint 上下文：把 40 个 slot 序列化成 JSON 给 LLM（slot_id、title、chapter、required_inputs、layout_hint）
- ConceptProposal 硬约束：3 个方案的 massing/material/mood **必须差异化**，design_idea ≤20 字，narrative 100-150 字
- PageSlotGroup 展开：重复段（如案例页 3-5 个）在 post-processing 阶段展开，不让 LLM 处理

**失败模式**
- LLM timeout → Celery max_retries=2 + 指数退避
- Pydantic 验证失败（LLM 瞎写字段）→ 重试（`_OutlineLLMOutput` 是严格 schema）
- 3 个 proposal 写重复（massing 都是"方形体量"）→ 当前无自动检测，依赖 prompt 约束；TODO 加相似度检查
- 中文引号导致 JSON parse fail → BUG-007，目前开放

**优化历史**
- v1 → v2（outline_system_v2.md）：加入 ConceptProposal 输出，blueprint 序列化从文本列表改成 JSON 结构（LLM 更稳）
- 引入 `concept_logical_key(index, view)` 作为 ConceptProposal 和 Asset 之间的桥，避免命名漂移

**追问预案**
1. **"如果 LLM 给你 41 个 assignment 不是 40 个怎么办？"** → 当前靠 prompt 约束 + Pydantic 不强制长度；后续 normalize 阶段按 slot_id 去重 + 按 blueprint 补齐，多出的丢弃（有日志）
2. **"为什么 blueprint 是代码不是 YAML？"** → PageSlotGroup 有运行时逻辑（repeat_count_min/max + 条件展开），纯数据表达不了；且编译期类型检查比 YAML 强
3. **"同一个 project 跑两次 outline，结果一致吗？"** → 不一致（LLM temperature > 0），但 concept_proposals 的数量/视角/logical_key 结构化部分是一致的

---

### 2.2 Concept Render Agent（方案图生成，最新模块）

**职责**
从 Outline 拿到 3 个 ConceptProposal → 调 runninghub ComfyUI 工作流 → 生成 9 张图（3 方案 × 3 视角）→ 写入 Asset 表。

**输入输出契约**
- 入：project_id → 查 Outline、BriefDoc、ProjectBrief、MaterialPackage、site_ref Asset
- 出：`ConceptRenderStats(total=9, generated=N, placeholders=9-N)`
- 副作用：写 9 条 Asset（logical_key=`concept.{1..3}.{aerial|ext_perspective|int_perspective}`）+ 本地 PNG 文件

**关键算法：Serial-Parallel 混合**
```
Proposals 并行（asyncio.gather）
  ├─ Proposal 1 串行链
  │    Aerial (denoise=0.75, ref=site.boundary.image)
  │      ↓ 输出作为下一张的 init_image
  │    Ext Perspective (denoise=0.60, ref=aerial_output)
  │      ↓
  │    Int Perspective (denoise=0.50, ref=ext_output)
  ├─ Proposal 2 串行链（同上）
  └─ Proposal 3 串行链（同上）
```

**为什么这样设计**
- 并行 3 个 proposal：互相独立，并行无依赖
- 串行 3 个视角：后续视角用前一张做 init_image，保证材质/光影/风格连续
- denoise 递减：0.75 → 0.60 → 0.50，越到后面越"忠于参考图"，避免 runaway divergence

**关键 Prompt**（`tool/image_gen/concept_prompts.py`）
- 3 个 view 各一份模板（~250 词）
- AERIAL："photorealistic 3D building aerial view, NOT a 2D map"（强调不是地图）
- EXT_PERSPECTIVE："human eye-level, golden hour, 35mm, editorial"
- INT_PERSPECTIVE："natural light, magazine quality"
- 共享 NEGATIVE_PROMPT："cartoon, blurry, watermark, text overlay..."

**失败兜底**
- runninghub API key 缺失 → `client=None`，全部走 placeholder
- 单张图生成失败/超时（180s）→ 该张 placeholder，不影响其他图
- placeholder 是灰色 PNG + 中英文水印（fonts fallback 链：msyh.ttc → NotoSansCJK → PingFang → PIL default）

**优化历史**
- 最早想法：9 张全并行 → 风格漂移严重（方案 1 的鸟瞰是现代风、外透变成新中式）
- 迭代到 serial chain + denoise 递减，视觉一致性显著提升
- TODO 未完成：真机 runninghub 验证还没跑（等 API key），目前 placeholder 测试通过

**追问预案**
1. **"图生图比文生图贵吗？"** → 贵 ~1.5x（多了 upload + 参考图处理），但视觉可用率从 ~30% 提升到 ~70%（内部主观评估），ROI 值
2. **"一个 proposal 18s，如果 runninghub 抽风每张 60s 呢？"** → 串行链 180s 超时会触发 placeholder；整个 task max_retries=1；不阻塞后续 slide 生成
3. **"为什么不用 Stable Diffusion 自部署？"** → 建筑类 prompt 需要特殊 LoRA + ControlNet 调试，我们团队没有 CV 专人；runninghub 有现成工作流，按次计费更可控

---

### 2.3 Material Resolver（素材匹配）

**职责**
蓝图写 `required_inputs=["concept_aerial"]`（友好名），Asset 表里是 `logical_key="concept.1.aerial"`（数据驱动）。Material Resolver 做两者之间的模糊匹配。

**输入输出契约**
- 入：`expand_requirement("concept_aerial")` → 返回 patterns `["concept.*.aerial"]`
- 入：`find_matching_assets(patterns, assets)` → 返回匹配的 Asset 列表
- 核心数据结构：`INPUT_ALIAS_PATTERNS: dict[str, list[str]]`（~40 条映射）

**匹配规则**
- glob 风格：`*` 匹配 `[^.]+`（不跨越 `.`）
- 正则实现：`tool/material_resolver.py:logical_key_matches()`
- 一个友好名可映射多个 pattern：`"concept_image": ["concept.*.aerial", "concept.*.ext_perspective", "concept.*.int_perspective"]`

**为什么这样设计**
- 蓝图不该知道数据源细节（解耦）
- 一个 concept 方案有 3 个视角，LLM 选图时应该能用"任意"视角（通配符）
- 未来新增 view（如 "night_scene"）只改 INPUT_ALIAS_PATTERNS，不改 blueprint

**失败模式**
- 友好名拼错 → `expand_requirement()` 返回空列表 → 该 slot 无素材，coverage_score=0
- 通配符匹配过宽 → 多个 asset 同时命中，MaterialBinding 全塞进 `must_use_item_ids`（当前无去重/排序逻辑，TODO）

**优化历史**
- 最早是硬编码的 logical_key（`slot.required_inputs=["concept.1.aerial"]`）→ 三个方案需要复制三次蓝图 → ADR-005 改为通配符 + Resolver

**追问预案**
1. **"通配符和正则哪个更合适？"** → 通配符够用（只需要 `.` 做层级分隔）；用正则一来性能差，二来复杂度让 LLM 难以理解
2. **"如果一个 pattern 匹配 0 个 asset，下游怎么降级？"** → MaterialBinding 的 `coverage_score < 1.0` 会标记，Composer prompt 里告诉 LLM "你可能缺素材，用文字补"
3. **"为什么不用数据库 LIKE 查询？"** → Asset 表全量就 100-200 条，Python 里遍历比打 DB 还快；且 pattern matching 逻辑内聚在一个文件方便改

---

### 2.4 Composer Agent（HTML 生成，核心）

**职责**
把 `SlideMaterialBinding + VisualTheme + Outline slot` → 生成最终 slide 的 HTML。v3 HTML 模式是默认。

**输入输出契约**
- 入：`Outline.assignment + VisualTheme + SlideMaterialBinding + 上下文 slide 前后内容`
- 出：`Slide.body_html`（sanitized + CSS 注入）
- 模型：`LLM_STRONG_MODEL`，max_tokens=4000

**Prompt 核心设计**（`prompts/composer_system_v3.md`）
- 给定一个 example HTML（展示 grid/flex 基本结构）
- 列出可用 CSS 变量（`--color-primary`、`--font-heading`、`--spacing-m`）
- 列出 asset 引用方式（`<img src="{{asset.image_url}}">`）
- 明确禁止：内联 `<script>`、`onclick=` 事件、外链 CDN

**Sanitizer 白名单**（`render/html_sanitizer.py`）
- 允许：`div, p, h1-h6, img, ul, li, table, svg, a`（href 校验）
- 移除：`<script>`、事件处理（`onclick` 等）、`javascript:` URL
- 实现：`html5lib` parser + 白名单节点过滤

**主题注入**
```css
:root {
    --color-primary: #0066FF;  /* 从 VisualTheme 取 */
    --font-heading: "Inter";
    --spacing-m: 12px;
    /* ... */
}
```
在 body_html 前 prepend `<style>`，所有 slide 共享同一组变量。

**失败模式**
- LLM 返回不合法 HTML → sanitizer 尽力救（过滤非法标签）→ Playwright 渲染时浏览器容错
- LLM 输出超 max_tokens → 返回不完整 HTML → 渲染会报错 → Review vision 层发现 → 重修复
- Repair 后仍失败 3 次 → `ESCALATE_HUMAN`，需人工干预

**优化历史**
- v2 → v3 切换原因：v2 的 LayoutSpec JSON 对 LLM 来说太约束，生成的版式趋同；v3 HTML 放开后视觉创造力显著提升
- Repair 路径：新增 `recompose_slide_html()` + `prompts/composer_repair.md`，给定 issues 列表重写 body_html

**追问预案**
1. **"LLM 生成的 HTML 会不会有 XSS？"** → Sanitizer 做白名单过滤；且 PPT 生成是内部管线，最终输出是 PNG 截图（不是浏览器里展示的 HTML），即使有 script 也不会执行；双保险
2. **"Playwright 渲染慢怎么办？"** → 单浏览器 4 tab 并发，40 页 ~60s；瓶颈在浏览器启动（3-5s）而非单页渲染；未来考虑 browser pool
3. **"为什么不用 `<iframe>` 隔离 slide？"** → iframe 跨域存储成本高；直接同 document 渲染 + sanitizer 已足够安全

---

### 2.5 Celery 任务编排

**任务清单**
| Queue | Task | 用途 | max_retries |
|-------|------|------|-------------|
| default | `generate_outline_task` | Outline 生成 | 2 |
| default | `compose_slides_task` | Slide HTML 生成 | 2 |
| default | `review_batch_task` | 三层审查 + 修复 | 2 |
| concept_render | `render_concept_images_task` | runninghub 调用 | **1**（尽力而为） |
| render | `render_slides_task` | Playwright 截图 | 2 |
| export | `export_task` | PDF 组装 | 2 |

**关键配置**
```python
# tasks/celery_app.py
serializer = "json"          # 不用 pickle，避免反序列化漏洞
timezone = "Asia/Shanghai"
prefetch_multiplier = 1       # 公平队列，避免长任务堵
acks_late = True              # worker 崩溃时任务可被别的 worker 重拾
```

**任务链路**
```
generate_outline_task
   ↓（用户确认 outline 后手动触发）
compose_slides_task
   ↓（链式 .delay）
render_slides_task
   ↓（链式 .delay）
review_batch_task
   ↓（如需修复）
recompose_slide → render_slides_task → review_batch_task（最多 3 轮）
   ↓（review 通过）
export_task → deck.pdf
```

**concept_render 特殊性**
- 独立队列，避免 runninghub 调用阻塞主流水线
- max_retries=1（不是 2/3），失败就 placeholder，不纠缠
- 异常完全 swallow（return error dict，不 raise），防止 Celery 死信队列堆积

**失败模式**
- worker 崩溃 → `acks_late` 保证任务不丢，另一个 worker 接手
- DB 连接池耗尽 → task 报错 → 重试；瓶颈在 `get_db_context()` 的 context manager
- Redis broker 挂 → 所有 task 阻塞；目前没有 broker 高可用

**追问预案**
1. **"为什么 render 和 export 单独分队列？"** → render 重 CPU（Playwright 浏览器）、export 重 IO（ReportLab PDF 拼接），分队列可以各自限速 worker 数量
2. **"Celery task 里面套 asyncio.run() 为什么不直接 async def task？"** → Celery 原生不支持 async task；主流做法是 sync task + `asyncio.run()` 包一层（每个 task 一个独立 event loop，不共享）
3. **"大项目压测过吗？"** → 单机 10 个并发项目 30 分钟，未压过；最可能的瓶颈是 LLM API 速率限制（Anthropic Tier 2 是 50 RPM）

---

## 第三章 LLM 工程专项（面试高频区）

### 3.1 Prompt 版本化与回归

**30 秒回答**
所有 system prompt 都放在 `prompts/*.md`，文件名带版本号（如 `outline_system_v2.md`）。版本迭代时**不原地改**，新建 `_v3.md` 文件，通过 config 切换。没有自动化回归测试，主要靠 `scripts/material_package_e2e.py` 手动跑验证。

**2 分钟展开**
- **目录**：`prompts/outline_system_v2.md`、`composer_system_v3.md`、`composer_repair.md`、`vision_design_advisor.md`、...
- **模板变量**：用 `{variable}` 格式，Python 侧 `.format()` 替换
- **版本化策略**：改 prompt 就是改代码，走 git；重要改动（如 v2→v3）写 ADR
- **缺的能力（坦承）**：没有 prompt A/B 测试框架，没有输出质量自动打分，没有 prompt 代码之间的 mapping 工具

**追问预案**
1. **"如果 prompt 改坏了怎么回滚？"** → git revert；但"改坏"的发现滞后（要跑 E2E 才知道），这是目前痛点
2. **"为什么不用 LangSmith / Helicone？"** → 成本 + 数据出境合规考虑，目前在日志里记 prompt/response；想上自研轻量方案
3. **"prompt 和代码应该在同一个 repo 吗？"** → 是，prompt 是代码的一部分（行为由它决定），分开 repo 会导致版本漂移

---

### 3.2 结构化输出 + Schema 兜底

**30 秒回答**
用 Pydantic v2 + `instructor`（或类似 response_model 机制）约束 LLM 输出。LLM 偶尔会输出不合法 JSON（中文引号、trailing comma），我们靠**重试 + prompt 示例**而不是激进的 fallback 逻辑。

**2 分钟展开**
- **关键 schema**：`_OutlineLLMOutput`、`_ComposerLLMOutput`、`_ComposerHTMLOutput`、`ConceptProposal`、`SemanticCheckOutput`
- **验证层**：`call_llm_with_limit(response_model=_OutlineLLMOutput)` → 内部调 Pydantic `model_validate()`
- **失败路径**：验证失败 → 走 Celery retry（默认 2 次）→ 仍失败 → 异常冒泡 → task 失败 → 用户侧看到 status=FAILED
- **Composer 的 fallback**：特例，JSON 解析失败时降级到 `_FALLBACK_PRIMITIVE`（单栏布局），而不是直接失败；因为一张 slide 坏了不应毁掉整个 deck

**追问预案**
1. **"BUG-007 中文引号问题为什么没修？"** → 修复方案有：prompt 里强约束 + `ast.literal_eval` 兜底；工作量 1 天，优先级 P2，被 concept_render 抢了工期
2. **"Pydantic v2 比 v1 性能提升明显吗？"** → 明显，v2 用 Rust 实现验证，比 v1 快 5-50x；但我们的瓶颈不在验证，在 LLM 调用，感知不强
3. **"为什么不用 Anthropic 的 tool_use API 强制结构？"** → 当前用的混合：Claude 走 `response_model`，Gemini/OpenRouter 走 JSON mode；tool_use 对 non-Claude 模型不通用

---

### 3.3 Token / 延迟 / 质量三角权衡

**30 秒回答**
不同 Agent 用不同模型：Outline/Composer 用 `LLM_STRONG_MODEL`（贵 + 强 + 慢），Semantic Review 用 `LLM_CRITIC_MODEL`（快 + 便宜），BriefDoc/VisualTheme 介于两者之间。单次项目成本约 ¥5-8，延迟 25-35 分钟。

**2 分钟展开**
- **模型分层**（`config/settings.py`）：
  - `LLM_STRONG_MODEL`：Claude Opus / Gemini 3 Pro，max_tokens 4000-8000
  - `LLM_FAST_MODEL`：Claude Haiku / Gemini Flash，用于简单分类
  - `LLM_CRITIC_MODEL`：Gemini 3.1 Pro（BUG-002 换过，原来是无效的 gpt-4.5）
- **成本分布**（单次项目）：
  - Outline：1 次调用，~3000 output tokens
  - Composer：40 次调用，每次 ~1500-3000 output tokens → **主要成本**
  - Review：40 次调用 × 3 层（v2）或 1 层（v3） → v3 便宜 3x
- **延迟分布**：
  - Concept render：~3 分钟（runninghub）
  - Compose 40 slide：~8 分钟（40 次 LLM 调用，部分并发）
  - Render + Review + Repair：~10-15 分钟（Playwright + vision LLM）

**追问预案**
1. **"如果预算砍一半怎么优化？"** → 降级 Composer 到 fast 模型 + prompt 精修；视觉 Review 按随机采样（40 页抽 10 页），总成本能降 50%，质量下降 15-20%
2. **"温度参数怎么设？"** → Outline 高温（0.7，要创意），Composer 中温（0.5，平衡），Critic 低温（0.2，要稳定）
3. **"会不会用 prompt cache？"** → Anthropic 的 prompt caching 我们已经启用，system prompt 和 blueprint 被缓存（重复项目节省 60% input tokens）

---

### 3.4 幻觉 & 一致性控制

**30 秒回答**
靠三件事：**schema 硬约束**（Pydantic 验证不符即重试）、**素材锚定**（Material Resolver 匹配后把具体 asset 引用注入 prompt）、**视觉 Review 兜底**（多模态 LLM 看截图发现视觉幻觉）。

**2 分钟展开**
- **schema 约束**：LLM 不能瞎发明字段，`_OutlineLLMOutput` 验证失败就重试
- **素材锚定（关键）**：Composer prompt 里会明确列出"可用 assets: [Asset(logical_key=concept.1.aerial, image_url=...)]"，LLM 只能引用这些；如果 LLM 瞎写 image_url，渲染会 404
- **跨 slide 一致性**：VisualTheme 全局唯一（一个 deck 一套色彩），所有 slide 用同一组 CSS 变量
- **事实一致性**：Semantic Review 的 S001 METRIC_INCONSISTENCY 检查（例如 slide 3 说"人口 500 万"，slide 8 说"人口 800 万"）
- **视觉兜底**：Vision Review 看最终截图，能发现 schema 层看不到的问题（元素重叠、文字溢出视觉上的表现）

**追问预案**
1. **"LLM 如果引用一个不存在的 logical_key 怎么办？"** → Composer 渲染阶段检测不到（LLM 写的是字符串），Playwright 渲染会 `<img src>` 404 → 截图里显示 broken image → Vision Review 检测 V003 IMAGE_BROKEN → 触发 repair
2. **"S001 metric 检查真的有效吗？"** → 部分有效，需要 LLM 理解上下文；对明显矛盾（500万 vs 800万）召回率 ~80%，对微妙差异（500万 vs 510万）召回率 ~30%
3. **"为什么不用 RAG 约束事实？"** → 事实源是 MaterialPackage（用户上传的文档），已经在 prompt 里注入；真正的 RAG（向量召回）我们只用在 Reference Agent（案例库），不用于事实核对

---

## 第四章 工程质量与可观测性

### 4.1 测试策略（金字塔）

**分层**
```
          E2E: 1 × scripts/material_package_e2e.py
         ─────────────────────────────────
       Integration: 6 cases × 2 files
         （test_project_flow.py, test_concept_render.py）
     ─────────────────────────────────────
   Unit: 96+ cases × 12 files
```

**关键模式**
- **Unit 测试 runninghub 客户端**：用 `httpx.MockTransport` 模拟 HTTP 响应，不发真实请求
- **Integration 测试**：真 PostgreSQL（conftest 提供 session fixture）+ 真 LLM 或 mock LLM 可选
- **E2E 一键跑**：
```bash
python scripts/material_package_e2e.py test_material/project1 \
    --real-llm --composer-mode html --max-slides 2
```
- **跳过昂贵步骤的标志**：`--skip-concept-render`、`--max-slides N`（smoke 测试）

**覆盖盲区**（坦承）
- 没有 prompt 回归测试（改 prompt 看不出质量影响）
- Concept render 真机没验过（等 runninghub API key）
- 没有性能/压力测试

**追问预案**
1. **"96 个 unit test 够不够？"** → 覆盖关键路径，但 LLM 输出质量不在单测范围；E2E 才是"真 test"
2. **"E2E 跑一次多久多少钱？"** → 真 LLM 25-35 分钟 + ¥5-8；所以只在大改动时跑，日常改动跑 mock LLM 版本（3 分钟）
3. **"怎么保证 LLM 行为不回归？"** → 没做好；理想方案是固定 seed + 关键 prompt 快照比对，目前靠人工 review 生成的 PDF

---

### 4.2 可观测性与运维

**当前有的**
- **Celery Flower**：task 状态、队列深度、吞吐量
- **结构化日志**：`logger.info("render_concept_images_task: project=%s total=%d generated=%d", ...)`
- **状态机**：`ProjectStatus` 枚举（INTAKE_CONFIRMED → OUTLINE_READY → COMPOSED → RENDERED → EXPORTED），每步持久化，断点续跑
- **DB 快照**：每步产物（Outline、Slide、Review）都持久化为 JSONB，失败后可查

**缺的**（要敢坦承）
- 没有 Prometheus metrics（LLM 延迟分布、token 消耗、placeholder 率）
- 没有分布式 trace（Celery task 之间无 trace_id 传递）
- 没有告警（task 失败率突增、queue 堆积）

**诊断手法**
```
# 查看项目当前状态
SELECT id, status, updated_at FROM projects WHERE id = '...';

# 查看该项目所有 task 日志
grep project_id=<uuid> /var/log/celery/*.log

# 查看某 slide 的审查记录
SELECT review_json FROM reviews WHERE slide_id = ...;
```

**追问预案**
1. **"如果项目卡在 RENDERING 2 小时，你怎么查？"** →  先看 Flower 有没有 render_slides_task 在跑；再看 DB 里该项目 slide 的 image_url 是否部分更新；再看 Playwright 浏览器进程；最后看 LLM API 是否被限流
2. **"想上 OpenTelemetry，优先级？"** → P1，完成 ADR-005 真机验证后立即上；trace_id 贯穿 Celery 任务是关键
3. **"placeholder 率你能看到吗？"** → 能，DB 里 `Asset.status='fallback'` 可聚合；但没做成 dashboard，每次手工查

---

### 4.3 状态机与幂等

**状态机**（`ProjectStatus` 枚举 → DB `projects.status` 字段）
```
INTAKE_CONFIRMED
    ↓
REFERENCE_SELECTION
    ↓
ASSET_GENERATING
    ↓
BRIEF_DOC_READY
    ↓
VISUAL_THEME_READY
    ↓
OUTLINE_READY  ← 用户需手动确认
    ↓
CONCEPT_RENDER_DONE
    ↓
SLIDE_PLANNING
    ↓
COMPOSED
    ↓
RENDERED
    ↓
REVIEW_PASSED | REPAIR_NEEDED | ESCALATE_HUMAN
    ↓
EXPORTED
```

**幂等性**
- Outline 重跑：会新增一条 Outline 记录，取 `ORDER BY created_at DESC LIMIT 1` 的最新
- Concept Render 重跑：`_clear_existing_concept_assets()` 先清旧再生成，保证 9 张图一致
- Slide render 重跑：按 `slide_no` 覆盖 `image_url_rendered` 字段
- Review 重跑：新增 `Review` 记录，决策基于最新一条

**为什么不做严格 idempotency key？** 上游已经按 project_id 串行（一个项目一次只能一个 task 跑），重入场景少

**追问预案**
1. **"如果两个 worker 同时处理同一个 project 会怎样？"** → 当前没有分布式锁，依赖上游不并发调用；严格场景要加 Redis 锁
2. **"数据库事务边界怎么划？"** → 每个 task 一个事务（`get_db_context()` 提交/回滚）；不跨 task 事务
3. **"用户在 outline 阶段改了 brief 怎么办？"** → 新建 project（copy-on-write），旧 project 保留历史；没有 in-place 编辑能力

---

## 第五章 踩坑与迭代史（体现深度）

### 5.1 BUG-012：HTML 模式审查死循环（最典型）

**现象**
v3 HTML 模式上线后，随机 slide 触发 3 轮修复仍失败；日志显示每轮都报一样的 R006 EMPTY_SLIDE、R008 KEY_MESSAGE_MISSING。

**根因分析**
```python
# 问题路径
body_html = "<div>...</div>"                # LLM 输出正确
spec = LayoutSpec.model_validate(body_html) # ← BUG：当成 LayoutSpec 解析
# spec 变成空的默认 LayoutSpec
layout_lint(spec)                            # 规则层检查空 spec
# 必然报 R006（EMPTY_SLIDE）、R008（KEY_MESSAGE_MISSING）
repair → 新的 body_html → 再验证 LayoutSpec → 同样结果 → 死循环
```

**修复**
- 短期（ADR-004）：HTML 模式跳过 rule/semantic 层，只做 vision
- 长期讨论过：为 HTML 模式设计专用的 DOM-based lint，但成本高，收益低，未做

**教训**
- 新模式上线要**审查所有下游**（这里是 critic 对 LayoutSpec 的强耦合）
- 默认 fallback 值比异常更危险（空 spec 被"成功验证"，没报错）
- 循环结构必须有 max_attempts 硬上限（我们有 max_repairs=3，否则 production 会烧钱）

**追问预案**
1. **"怎么定位到死循环是 layout_lint 的锅？"** → 每轮 issues 完全一样这个信号最关键；再看 repair 前后 spec diff 为空
2. **"3 轮 max 怎么定的？"** → 经验值，多数能 1-2 轮修好；3 轮内修不好的大概率是根本性问题，应该转人工
3. **"为什么用 ESCALATE_HUMAN 而不是直接失败？"** → 用户体验：失败让用户重跑 30 分钟不合理；ESCALATE 让用户看到半成品 + 标记问题 slide，可以手动改

---

### 5.2 BUG-002：Review 调用了不存在的模型

**现象**
所有 slide 的 semantic review 返回 "SEMANTIC_SKIPPED"，review pass 率异常偏高。

**根因**
`LLM_CRITIC_MODEL` 配置成了 `openai/gpt-4.5`（不存在），`call_llm()` 捕获 404 → 返回 SKIPPED 标记，但上层没告警。

**修复**
- 改为 `google/gemini-3.1-pro`
- 加了模型可用性启动检查（config 加载时尝试调用）
- SKIPPED 不再当成 PASS，而是 DEGRADED 状态

**教训**
- 配置错误的 fail-silent 是最危险的（静默失败）
- 启动时 fail-fast 比运行时 fail-silent 强 100 倍
- 关键指标（review skip rate）必须监控

**追问预案**
1. **"为什么会配置成不存在的模型？"** → 当时考虑用 GPT-4.5（还没发布），配置先占位，忘了改；是人的问题也是流程问题
2. **"启动检查会不会太重？"** → 每个模型发一个 1-token 请求，成本 <$0.001，延迟 <1s，完全可接受

---

### 5.3 BUG-008：高并发下 Composer schema fallback

**现象**
同时 Compose 18 个 slide 时，部分 slide 走 `_FALLBACK_PRIMITIVE`（单栏布局兜底），手动复核这些 slide，LLM 输出其实是合法的。

**根因**（未完全定位）
- 高并发下 Anthropic API 返回频率 limit 或超时
- Pydantic 验证线程竞争？（存疑）
- 当前缓解：max_retries 提到 3 次

**状态**
仍是开放问题，需要：
1. 降并发到 10 看是否复现
2. 加详细 trace 确认是 API 问题还是验证问题
3. 若是验证问题，给 Pydantic 加 JSON repair 前置

**追问预案**
1. **"为什么不先定位再修？"** → 优先级：concept_render 上线紧急；BUG-008 的 fallback 虽然质量下降但不阻塞
2. **"fallback 比例多少？"** → 约 5-10%，不致命但有改进空间
3. **"会不会是中文引号的 BUG-007 的同一类问题？"** → 可能，两者都可能是 LLM 输出解析失败；合并调查是 todo

---

### 5.4 迭代史（关键时间点）

| 日期 | 里程碑 | 决策 |
|------|--------|------|
| ~2026-03 | 单模块 Composer v1（结构化） | 初始架构 |
| 2026-04-05 | Composer v3 HTML 模式 + VisualTheme | ADR-003 |
| 2026-04-06 | Design Advisor（5 维打分） | 视觉审查增强 |
| 2026-04-07 | Review Loop v2 修复 | ADR-004（vision-only） |
| 2026-04-21 | Concept Render 接入 | ADR-005 |
| 2026-04-23（今天） | 真机 runninghub 验证待做 | [P0-2] |

---

## 第六章 开放性问题与反问清单

### 6.1 常见系统设计变体题

**Q：如果要支持多人实时协作编辑 outline，怎么改？**
- 状态机要支持 CRDT（Yjs / Automerge），每个用户操作生成 op 合并
- Outline 存储从 JSONB 改成 op log + snapshot
- Celery 触发改为"outline.confirmed 事件"，不再是"用户点按钮"
- 预计工期：2-3 个月，会重构 Outline 存储层

**Q：如果要把生成成本降到 ¥1 以内？**
- Composer 全切 fast 模型 + prompt 精细化 → 降 60%
- 砍掉一半 slide 的 vision review（按重要性采样）→ 降 20%
- prompt caching 最大化 → 降 10%
- 合计 ~¥2-3，¥1 以内需要牺牲质量（比如页数降到 20 页）

**Q：如果生成时间要压到 5 分钟？**
- 瓶颈是 40 次 Composer LLM 调用（串行部分）+ Playwright 渲染
- Composer 改全并行 → 60% 时间砍掉（但 LLM tier rate limit 是新瓶颈）
- Playwright 启动预热 + 浏览器池 → 再砍 20%
- 合计 ~8-10 分钟，5 分钟做不到（受 runninghub 最低延迟限制）

**Q：如果要接入别的图像生成后端（Midjourney / SD）？**
- 只需实现 `ImageGenClient` 接口（upload / create / poll / download）
- ConceptRender Agent 代码改 ~20 行
- Prompt 模板可能要调（不同模型对 negative prompt 的响应不同）

---

### 6.2 面试官可能的抽象追问

**Q："你觉得这个系统最大的技术风险是什么？"**
- 短期：LLM 行为不稳定性（同 prompt 不同输出）没有量化验证手段
- 中期：Playwright 渲染在生产环境的稳定性（浏览器崩溃、字体缺失、内存泄漏）
- 长期：架构上 Composer 是核心瓶颈，40 次串行 LLM 调用决定了总延迟的下限

**Q："如果让你从零再做一次，哪里会不一样？"**
- Composer 直接 v3 HTML，不搞双模（减少维护）
- 从第一天加 trace_id 和 Prometheus（观测性是 infra，不是功能）
- Outline 数据驱动蓝图（YAML/JSON 而不是 Python dict）
- Review 的 3 层架构过度设计了，生产中只用 vision 层

**Q："你在这个项目里最 proud 的一个决策是什么？"**
- ADR-005：Concept Render 嵌入 Outline 而不是独立 Agent。看似小的选择，但省了一次 LLM 调用 + 上下文重复传输，更关键的是保持了"方案定义"的单一真相源，下游不会出现 outline 说 3 个方案、concept render 只生成 2 个的情况。

---

### 6.3 你可以反问的高信号问题

1. **"团队目前在 LLM 应用层面临的最大技术挑战是什么？"**（看对方是否真的在做 LLM 应用）
2. **"你们怎么量化 LLM 输出质量？"**（看团队成熟度）
3. **"生产环境的 LLM API 配额管理怎么做？"**（看规模）
4. **"prompt 的迭代流程是什么？code review 吗？"**（看工程化程度）
5. **"模型升级（如 Opus 4.6 → 4.7）的回归测试怎么做？"**（看对 model regression 的认知）
6. **"你们踩过的最严重的一次 LLM 相关事故是什么？"**（看踩坑深度 + 团队坦诚度）
7. **"我如果入职，第一个月最有挑战的事情是什么？"**（看是否有清晰的 onboarding）

---

## 第七章 搭建过程中的典型问题与改善

> 第五章讲的是 BUG 级复盘，本章讲的是**工程基建级**的坑：环境、依赖、集成、流程。这部分在面试里比算法题更能体现"是否真的交付过东西"。

---

### 7.1 Playwright 在 Windows 开发机的生态坑

**问题现象**
- 本地开发（Windows）：Celery worker 启动 Playwright 随机崩，错误是 `asyncio.ProactorEventLoop` 不兼容 `prefork`
- CI（Linux Docker）：没问题
- 效果：个人开发迭代慢，"我本地跑通了但 CI 挂"反过来

**定位过程**
1. 第一天以为是 Chromium 版本问题，升级了一轮没用
2. 第二天发现只在 Windows 复现，Linux 正常 → 问题在 OS 级别
3. 查到 Celery 在 Windows 下默认用 `solo` pool（单进程），但代码里显式写了 `prefork`

**解决方案**
```bash
# 启动脚本区分平台
if [[ "$OS" == "Windows_NT" ]]; then
    celery -A tasks.celery_app worker --pool=solo
else
    celery -A tasks.celery_app worker --pool=prefork --concurrency=4
fi
```
- 短期：Windows 本地只跑 solo，接受单进程限制（反正是开发机）
- 长期：生产强制 Linux（Docker），不考虑 Windows 生产

**改善**
- 在 `docs/ops/CLAUDE.md` 里加了"平台差异"章节，新人 onboarding 不再踩
- `docker-compose.yml` 里 Celery worker 用 Linux 镜像，本地也能 `docker-compose up` 起 Linux 环境

**教训**
- 跨平台开发时，**CI 必须模拟生产 OS**（我们早期 CI 是 GitHub Actions Ubuntu，恰好匹配，但 Windows 本地跑通就提交是危险的）
- Celery 在 Windows 不是 first-class support，能避则避

---

### 7.2 LLM 速率限制的"雪崩"

**问题现象**
单项目跑 40 slide，Composer 阶段约一半 slide 同时发 Claude 请求（asyncio.gather），触发 Anthropic Tier 2 的 50 RPM 限制 → 429 错误 → Celery retry → 雪上加霜

**诊断**
- Flower 看到 compose_slides_task 大面积重试
- Anthropic response header 里有 `retry-after: 60s`
- 我们代码里的 max_retries=2 + 指数退避（30s, 60s）叠加，等于等 3 分钟

**改善（分三步走）**
1. **限流器上场**（短期止血）：`tool/llm_client.py` 加 `asyncio.Semaphore(10)`，Composer 调用并发上限 10
2. **批次切分**（中期）：40 slide 分成 4 批（每批 10 个），批间 `await asyncio.sleep(5)`，平摊 RPM
3. **账号升级**（长期）：申请 Anthropic Tier 3（800 RPM），+ OpenRouter fallback

**教训**
- LLM API 的速率限制不是"按秒"而是"滑动窗口"，局部并发很容易触发
- `asyncio.gather()` 不是银弹，对外部受限资源要主动限流
- 重试策略要**看对方的 retry-after**，不能盲目指数退避

**追问预案**
- **"你们有没有实现 token bucket？"** → 没到那一步，semaphore 够用；真正的 token bucket 适合更高 QPS 场景
- **"OpenRouter 降级有没有风险？"** → 有，不同模型输出风格不一样，降级后的 slide 需要标记，review 阶段单独看

---

### 7.3 素材包命名规范：从"用户随便传"到 logical_key 体系

**问题现象**
最早让建筑师"把素材丢到一个文件夹"，结果：
- 同一种东西不同命名：`红线.png`、`用地红线.jpg`、`boundary.png`、`site-boundary-final-v2.png`
- Agent 完全不知道哪个文件对应蓝图里的 `map_site_boundary`
- 结果：人工绑定素材的工作量，比写 PPT 还大

**演进过程**

**v1（失败）：让 LLM 猜**
给 LLM 看文件名列表，让它匹配蓝图 input。准确率 ~60%，错得离谱（把 "elevation_east.png" 识别成平面图）。

**v2（失败）：约定文件夹结构**
强制建筑师按"site/"、"policy/"、"reference/"分文件夹。实际使用：没人遵守，或者只对一半。

**v3（成功）：logical_key + manifest.yaml**
```yaml
# manifest.yaml 放在素材包根目录
items:
  - file: 红线.png
    logical_key: site.boundary.image
    title: 地块边界
  - file: economy_gdp.xlsx
    logical_key: economy.city.chart.gdp
    title: 城市 GDP 数据
```
- **人工写 manifest**：建筑师负责，5-10 分钟/项目
- **工具辅助**：提供 Web 界面上传 → 拖拽分类 → 自动生成 manifest
- **弱约束**：没有 manifest 时，退化到 v1 的 LLM 猜测（带 warning）

**改善数据**
- 素材绑定准确率：60% → 95%
- 建筑师反馈：接受（5 分钟成本换 95% 命中），但希望后续做"智能初猜 + 人工确认"

**教训**
- **不要指望输入端"自然干净"**，要么加工具强制规范，要么在 pipeline 内接受脏数据
- 规范要配合工具落地（只写文档没用）
- **错误成本的位置决定设计**：前置 5 分钟 vs 后置半天 review，显然前置值

---

### 7.4 Celery acks_late 的双刃剑

**问题现象**
开了 `acks_late=True`（worker 崩溃任务可重拾），但导致**同一个 task 被跑两次**的情况：
- worker A 跑 compose_slides_task，临近结束前进程被 OS kill（OOM）
- worker B 拿到任务重跑 → 但 A 已经写了一半 slide 到 DB
- B 看到 DB 里有 slide 记录，以为成功了，直接结束
- 用户拿到的 deck 是混合产物（A 写一半 + B 写一半），视觉风格断裂

**定位**
- 用户反馈某次生成"前 20 页是现代风，后 20 页变成新中式"
- 查 Celery 日志发现同一 task_id 出现在两个 worker
- OOM kill 的原因：Playwright 浏览器吃内存，Composer 阶段同时开 browser + LLM stream，峰值内存 2.5GB，Docker 限制是 2GB

**改善**
1. **幂等化**：compose_slides_task 开始前 `DELETE FROM slides WHERE project_id=...`，保证从空状态开始
2. **内存限制**：Docker memory limit 调到 4GB；Composer 阶段不开 browser（browser 只在 render task 里用）
3. **启动校验**：task 开始时检查 project.status，已经 COMPOSED 的直接跳过
4. **关闭 acks_late？**不，它还是必要的（worker crash 防止任务丢失）；关键是业务层幂等

**教训**
- `acks_late` 是"分布式系统必修课"，但必须配合**业务幂等**
- 内存问题在开发机上看不到（16GB），生产容器上暴露
- 两个进程同时写同一数据集不是小概率事件，要按正常场景设计

---

### 7.5 Pydantic v1 → v2 迁移

**问题现象**
2026-03 中后期升级 Pydantic v1 → v2（因为 instructor 新版本依赖 v2），发现：
- 所有 schema 里的 `@validator` 要改成 `@field_validator`
- `Config` 内部类要改成 `model_config = ConfigDict(...)`
- `dict()` 方法废弃，改 `model_dump()`
- `parse_obj()` 改 `model_validate()`
- 约 80 处改动

**踩的真坑**
- **JSON 序列化差异**：v1 的 `Model.dict()` 默认包含所有字段（None 也包含），v2 的 `model_dump()` 默认也是；但 `model_dump(mode="json")` 会把 datetime 转 ISO 字符串，v1 不会。**我们的 `Slide.spec_json` JSONB 字段受此影响，数据库里旧数据是 `2026-04-05T12:00:00`，新代码写入变成 `datetime.datetime(2026, 4, 5, 12, 0)`**，读的时候反序列化失败
- 修复：所有写 JSONB 字段前显式 `model_dump(mode="json")`

**改善**
- 迁移前：跑一次全量 E2E 固化"迁移前"基线
- 迁移后：跑同一 E2E，diff 生成的 PDF（视觉 + 文本）
- 发现不一致点逐个修
- 总耗时：3 天

**教训**
- 依赖大版本升级不是"pip install --upgrade"那么简单
- JSONB 字段是"无 schema"的，最容易藏兼容性问题
- **测试金字塔的 E2E 层价值**：单测都过了，问题出在集成层

---

### 7.6 模型升级的静默回归（Claude Opus 4.6 → 4.7）

**问题现象**
Anthropic 发布 Opus 4.7，我们默认升级。之后一周发现：
- Outline 生成的 `concept_proposals` 偶尔只有 2 个（应该恒定 3 个）
- 不报错，Pydantic 验证通过（字段都合法，只是 list 长度不对）
- 用户侧：PPT 只有 2 个方案，少 6 页

**定位**
- 回看 prompt：`"请提供 3 个设计方案"`，4.6 乖乖给 3 个，4.7 偶尔给 2 个 + 自己加"第三方案待后续开发"
- Prompt 没严格约束数量

**修复**
```python
# schema/concept_proposal.py 加 validator
@field_validator("concept_proposals")
@classmethod
def validate_length(cls, v):
    if len(v) != 3:
        raise ValueError(f"Expected 3 proposals, got {len(v)}")
    return v
```
- Pydantic 拒绝不合法输出 → 触发 Celery retry
- 同时改 prompt：`"必须 exactly 3 个方案，不多不少"`

**教训**
- **模型升级必须跑回归**，我们没跑，翻车
- 靠自然语言约束数量是脆弱的，schema 层强制更可靠
- 建立"模型升级 checklist"：每次升级都跑全量 E2E + 抽样人工 review

**后续制度化**
- 在 `config/settings.py` 固定模型版本（不用 "latest"）
- 升级走 PR 流程，PR 模板里必须贴 E2E 结果对比

---

### 7.7 字体渲染的跨平台噩梦

**问题现象**
- 本地 Windows：中文渲染正常（msyh.ttc）
- CI Linux：部分 slide 的中文变成 `□□□`（豆腐块）
- 生产 Docker（也 Linux）：一样变豆腐

**根因**
- Playwright 截图用的是系统字体
- Docker 基础镜像（python:3.11-slim）不装中文字体
- `CSS font-family: "Microsoft YaHei"` 在 Linux 上 fallback 到 sans-serif，但 sans-serif 没中文

**修复**
```dockerfile
# Dockerfile
RUN apt-get update && apt-get install -y \
    fonts-noto-cjk \
    fonts-noto-cjk-extra \
    && rm -rf /var/lib/apt/lists/*
```
- 同时在 VisualTheme 的 CSS 里用多层 fallback：`font-family: "Microsoft YaHei", "Noto Sans CJK SC", "PingFang SC", sans-serif`
- Placeholder 图片的字体也是同样 fallback 链（`tool/image_gen/placeholder.py` 里 4 层候选）

**改善**
- CI 加一个 smoke test：生成一页中文 slide → 截图 → 像素级检查不是豆腐
- 写进 onboarding 文档："部署必须装 CJK 字体包"

**教训**
- 视觉输出系统对字体极端敏感，这种问题**纯代码 review 看不出来**，必须有视觉测试
- Playwright 的字体行为取决于 OS，不是 Chromium 自带
- Docker slim 镜像"省下的几百 MB"常常换来这种问题

---

### 7.8 中文引号导致的 JSON parse 失败（BUG-007，开放中）

**问题现象**
LLM 偶尔输出：
```json
{"title": "“现代简约”风格", "description": "..."}
```
JSON 规范不允许 `"` 之外的引号，但 LLM 混入了中文 `"` → Python `json.loads()` 失败

**为什么 LLM 会这样写**
- Prompt 里给了中文示例文本
- LLM 对"视觉美观"的倾向 —— 中文引号看起来更合适
- 模型越强，越容易"自作聪明"

**缓解（未彻底解决）**
- Prompt 强约束：`"严禁使用 " ' 等中文标点，只用 ASCII 引号"`
- Pre-process：`text.replace(""", '"').replace(""", '"').replace("'", "'").replace("'", "'")` 在 `json.loads` 前做

**为什么不用 `ast.literal_eval`**
- 它接受 Python 语法（dict literals），但 LLM 输出的不一定是 Python 合法的（比如 `true` 不是 `True`）
- 引号替换更通用

**改善**
- 加了 `_safe_json_parse()` 工具函数，pipeline 里所有 LLM JSON 输出走它
- 仍有偶发 case（新类型的标点）会漏掉，是 P2 级长尾问题

**教训**
- LLM 输出 JSON 不是真的 JSON，要容错
- "严格 schema"哲学让你信心过度，底层解析一样要防御

---

### 7.9 Review 循环收敛 —— 为什么是 3 轮

**问题现象**
早期没有 `max_repairs` 上限，依赖"review PASS 才退出"，结果：
- 某些 slide 卡在 R008（KEY_MESSAGE_MISSING），每次修复都被 vision 层挑出新问题
- 一个项目跑了 14 轮 repair，烧掉 $20 LLM 费，还是没 PASS
- BUG-012（第五章详述）雪上加霜

**探索过程**
- **v0**：无上限 → 烧钱无底洞
- **v1**：max=10 → 仍然 80% 跑满 10 轮，成本降了但效果没变
- **v2**：max=5 + 人工升级 → 50% 跑满 5 轮
- **v3**：**max=3 + ESCALATE_HUMAN** → 70% 1-2 轮搞定，剩余 30% 直接升级，成本可控

**数据支撑**
统计了 50 个历史项目的 repair 次数分布：
- 1 轮 PASS：45%
- 2 轮 PASS：22%
- 3 轮 PASS：8%
- 3 轮后仍失败：25%

**结论**：3 轮之后不 PASS 的，继续跑也几乎不 PASS（边际收益趋零）。

**ESCALATE_HUMAN 的用户体验**
- 前端显示"该页需要人工审核"徽章
- 提供"重新生成"按钮（新的 LLM 温度 + seed）
- 或允许用户直接在编辑器里改 HTML

**教训**
- LLM 迭代修复的"收敛性"没有数学保证，必须硬上限
- 决定上限的依据是**边际收益**而不是预算
- 人工升级不是失败，是优秀的兜底策略

---

### 7.10 Concept Render 串行链 denoise 的调参过程

**问题现象**
第一版 concept render：3 个视角全并行生成，denoise=0.7（默认）
- 结果：方案 1 的鸟瞰是现代玻璃盒子，外透变成新中式大屋顶，内透变成工业风 loft
- 用户反馈："这是三个不同建筑吧？"

**调参实验（约 2 周）**

| 迭代 | 策略 | 结果 | 问题 |
|------|------|------|------|
| i1 | 全并行，denoise=0.7 | 风格飞散 | ← baseline |
| i2 | 全并行，denoise=0.4 | 三张图几乎相同 | 失去视角差异 |
| i3 | 串行，denoise=0.5（全部） | 有改善 | 鸟瞰图太"紧"（denoise 低 = 不敢改地形）|
| i4 | 串行，denoise=0.75/0.75/0.75 | 鸟瞰好了，外透内透又飞 | 后续视角没利用前张 |
| i5 | 串行，denoise=0.75/0.5/0.5 | 接近可用 | 内透偶尔还是飞 |
| **i6** | **串行，denoise=0.75/0.60/0.50** | **可用** | **当前生产版本** |

**关键洞察**
- 第一张（鸟瞰）需要高自由度（denoise 高），因为要从"用地红线图"变成"建筑体量图"
- 后续视角需要**递减 denoise**，越往后越"忠于前一张"，锚住风格
- 0.75 → 0.60 → 0.50 是经验曲线，不是数学最优

**验证手段**
- 每次调参，跑 5 个不同项目 × 3 次 → 15 组图 → 建筑师主观评分（1-5 分）
- i6 平均分 4.2，i5 3.6，i4 3.1

**教训**
- 调参没有银弹，靠大量样本 + 领域专家评估
- 这种"品味"问题单靠工程师自测不可靠
- 记录每次实验结果（即便是"失败"的），是后来发现规律的基础

---

## 第八章 团队协作故事

> 技术面试看"能不能干活"，但高级面试看"能不能带项目"。本章展示跨专业和跨团队协作的具体实践，体现**沟通 + 推进 + 落地**的能力。

---

### 8.1 跨专业协作：与建筑师的深度合作

#### 8.1.1 Kick-off 的认知错位

**背景**
项目启动后第一周，我问建筑师小王："你觉得一个好的方案 PPT 应该长什么样？"

**对话实录**（示意）
- 小王："要有设计的'呼吸感'。"
- 我："……具体是什么意思？"
- 小王："就是视觉上有层次、留白到位、不堆砌。"
- 我："我怎么把这个写进 prompt？"
- 小王："……你试试就知道了。"

**问题本质**
- 建筑师的"语言"是视觉 + 经验；工程师的"语言"是参数 + 逻辑
- 两者之间需要**翻译层**，但最初没人做这件事

**破局**
- 改方法：不问"什么是好"，改问"给我看 5 个你觉得最好的和最差的方案 PPT"
- 拿到样本后**逐页标注**："这一页为什么好？用了什么元素？占比？"
- 一周下来积累了 200+ 条具体规则，比如：
  - "鸟瞰图必须占 60% 以上版面，不能被文字压缩"
  - "方案对比页必须三列等宽，不能任意"
  - "设计说明一页不超过 3 段文字，每段 2-3 行"

**沉淀**
- 这批规则变成了：
  1. **Blueprint 的 layout_hint 字段**（每个 slot 写明布局约束）
  2. **Design Advisor 的 D001-D012 评分码**（视觉审查的 rubric）
  3. **Composer prompt 里的"设计原则"段**

**教训**
- 不要问抽象问题，要**以实例为起点反推规则**
- 领域专家的知识是**隐性**的，要做"考古"，不能指望他们主动产出规范
- 工程师的角色是"建规范的人"，不是"找规范的人"

---

#### 8.1.2 建立"建筑术语词典"

**问题**
LLM 生成的内容"建筑味"不够：
- 写"地块周围有很多路" → 建筑师改成"地块呈三路交汇，东侧临 40m 主干道"
- 写"建筑高度不一" → 应该是"形成高低错落的天际线韵律"
- 写"绿地面积大" → 应该用"绿地率 ≥35%，形成庭院 + 广场双层级绿化体系"

**诊断**
LLM 有能力用专业术语，但它不知道**这个场景该用哪个术语**。

**解决：术语词典 + prompt 注入**
建筑师提供了 3 类术语表：
```yaml
# prompts/terminology/architecture_glossary.yaml
scale_terms:  # 尺度
  - "人行尺度（≤6m）"
  - "街道尺度（6-20m）"
  - "城市尺度（>20m）"

massing_terms:  # 体量
  - "连续体量"
  - "散点布局"
  - "围合空间"
  - "轴线展开"

materiality:  # 材质
  - "透光表皮"
  - "石材基座"
  - "玻璃幕墙"
  - "竹木饰面"
# ...共 200+ 术语
```

注入到 Composer 的 system prompt："生成文本时，**优先**使用以下术语表中的表达……"

**效果**
- 建筑师抽样评估：术语使用正确率从 40% 提升到 85%
- 剩余 15% 是新词或 LLM 创造性滥用（如"新中式工业风"这种不存在的概念）

**维护机制**
- 新项目发现新术语 → 建筑师 PR 到 glossary
- 每季度一次 review，淘汰老化词汇

**教训**
- LLM 的"专业性"不是天生的，要喂领域词汇
- 术语表比整段专业 prompt 更有效（精准锚定）
- 这个资产随时间增值，是护城河的一部分

---

#### 8.1.3 Prompt 共创机制

**问题**
早期 prompt 都是我写，建筑师事后吐槽"又不对了"。一周 3-4 次迭代，非常耗人。

**改善：Prompt Pair Programming**
- 周会 2 小时，屏幕共享 + 建筑师在旁边
- 拿一个真实案例，当场跑 LLM → 看输出 → 改 prompt → 再跑
- 建筑师直接口述他希望加什么约束，我现场落到 prompt 里

**产出**
- 每次 session 产 1-2 版新 prompt，直接 git commit
- 建筑师第一次 commit 后有点兴奋："原来这就是写代码啊"
- 逐渐变成建筑师自己能看懂 prompt 的主干，只问变量替换机制

**意外收获**
建筑师提了一个工程师想不到的 prompt 改进："你能不能在 prompt 里告诉 LLM '你是一个**有 10 年经验的主创建筑师**'？" —— 角色扮演注入让输出质感明显提升，这是行业惯例，工程师不熟悉。

**教训**
- Prompt 不只是工程师的活，领域专家深度参与才是正道
- 缩短反馈闭环（2 小时现场 vs 一周异步迭代）效率差 10 倍
- "角色扮演注入"这种 prompt 技巧，靠自己试不出来，靠跨专业灵感碰撞

---

#### 8.1.4 评审标准的建立 —— Design Advisor 的缘起

**问题**
视觉 Review 早期只有"合格/不合格"二元判断，建筑师觉得粗糙：
- 有些 slide 明明可用，但不够"精致"
- 有些 slide 严格说 PASS，但色彩搭配有问题

**讨论过程**
跟 3 位建筑师开了个 2 小时的工作坊，问题是："你看 PPT 时，眼睛依次看什么？"

**提炼出 5 个维度**
1. **色彩（color）**：主色辅色比例、冷暖平衡、饱和度
2. **排版（typography）**：字体一致性、字号层级、行间距
3. **布局（layout）**：留白、对齐、重心
4. **视觉焦点（focal_point）**：是否有明确主角、是否分散
5. **精致度（polish）**：细节（边距、间距、对齐）

每个维度 1-5 分，有 D001-D012 的子项建议码。

**落地**
- `schema/review.py` 里 `DesignAdvice` 结构
- `prompts/vision_design_advisor.md` 单独的 vision prompt
- Review 输出 JSON 里包含分数 + 建议，前端可展示

**效果**
- 建筑师能看懂 Review 结果（不再是"FAIL: R006"这种难理解的）
- 不合格时 prompt 能指向具体维度，repair 效率提升

**教训**
- 评价体系要靠近用户语言，不要工程师自嗨
- 5 维度是权衡（再多就混乱，再少就粗糙），定数字需要实验
- 建立 rubric 是一次性投入，带来长期复利

---

#### 8.1.5 案例库：从混乱到可检索

**背景**
Reference Agent 的初衷：生成 PPT 时能参考"同类项目的过往案例"。但建筑师手头的案例是：
- 散落在微信、企业微信、硬盘、PPT 文件里
- 命名随意："某中心 final.pptx"、"东方项目汇报-v7-最终版（勿动）.pptx"
- 没有元数据（这是哪类建筑？什么年代？谁做的？）

**建设过程（约 2 个月）**

**阶段 1（1 周）：定义 schema**
```python
class ReferenceCase:
    title: str              # "上海市某文化中心"
    city: str
    building_type: str      # "文化建筑" / "商业建筑" / ...
    year: int
    architect_team: str
    key_design_moves: list[str]  # ["退让形成广场", "屋顶绿化"]
    thumbnail_url: str
    slides: list[SlideInfo]
```

**阶段 2（4 周）：案例录入**
- 建筑师手动整理 50 个高质量案例
- 每个案例填 schema + 提取 5-10 张代表性 slide
- 工具：内部管理界面（我写的），建筑师录入 + 审核

**阶段 3（1 周）：embed + 索引**
- pgvector 把 title + key_design_moves 向量化
- 检索：新项目的 positioning_statement → 向量相似度 top-10 → 建筑师确认 → 选 3-5 个入 outline

**阶段 4（持续）：维护**
- 新项目完成后，PM 判断是否入库
- 每月一次 review，淘汰过时案例

**数据**
- 初始 50 → 现在 120 案例
- Reference Agent 推荐采纳率：70%（建筑师接受推荐）
- 单次检索延迟：<200ms

**教训**
- 数据资产的冷启动是最难的，必须咬牙做完 MVP
- 前期 schema 设计重要，改起来是乘法成本
- "数据维护"是运营活，不能丢给工程师长期兼职

---

#### 8.1.6 持续 feedback 的闭环

**问题**
建筑师用完系统生成了 PPT，觉得不好 → 怎么反馈回开发？

**早期**（坏）
- 微信群发截图："第 12 页有问题"
- 我追问："哪里问题？哪个 slide_id？什么 bug？"
- 来回三天才能定位

**改善：内嵌反馈工具**
PPT 渲染完成后，每页可以点"👎"按钮，弹出表单：
```
- 问题类型：排版 / 内容 / 图片 / 其他
- 严重程度：致命 / 明显 / 轻微
- 具体描述：（文本框）
- 建议：（文本框）
```

反馈自动：
- 记录到 DB `feedback_events` 表
- 关联 project_id、slide_no、body_html snapshot
- 每周汇总成看板，Top 3 问题进下周 sprint

**数据**
- 单项目平均 5-8 条反馈
- 60% 可转化为 prompt 改进或 bug fix
- 每季度问题分布变化 → 能看到哪些问题被解决、哪些是长期痛点

**教训**
- 反馈通道必须**结构化 + 内嵌**，让反馈者零成本
- 反馈要能**关联到具体对象**（slide_id 精确到页），否则信息不够
- 反馈数据本身是金矿，定期 review 能看出系统盲区

---

### 8.2 跨团队协作：接入 Node.js 主系统

> 主系统是 Node.js 写的"建筑设计 AI 助手"，功能包括对话、图像生成、PPT 生成等。PPT_Agent 是其中"PPT 生成"模块的后端。

#### 8.2.1 架构决策：独立服务还是内嵌

**背景**
主系统团队（Node.js）的第一反应："你能不能直接写成一个 Node 的 npm 包？我们 import 一下？"

**我的回答**："不行，原因有三：
1. Python 生态：LLM SDK（Anthropic/OpenAI/Gemini）、Playwright、pgvector、ReportLab，Node.js 替代品不成熟
2. Celery 异步编排：Node.js 没有等效的成熟方案（Bull 有但差距大）
3. 团队分工：Python 团队不会改 Node 代码，Node 团队也不会维护 Python 工具链"

**最终决策**：独立 Python 服务（FastAPI），通过 REST/SSE 跟主系统通信。

**讨论的其他方案**（被否）
- **gRPC**：序列化高效但运维复杂，我们流量不大用不上
- **Message Queue（RabbitMQ/Kafka）**：异步好但 Node 侧复杂度高，主系统 PM 不同意
- **共享 PostgreSQL**：Node 端直接读 Python 写的表 → schema 紧耦合，拒绝

**落地**
- Python 服务独立部署（Docker）
- 对外暴露 FastAPI 接口（`/api/v1/ppt/*`）
- Node 主系统通过 HTTP 调用
- 独立数据库（`ppt_agent` schema），不与主系统共库

**教训**
- 技术选型要讲清楚**为什么不能折衷**，否则会被推回去
- 独立服务的边界是"数据库 + 部署 + 代码库"，不能只是"一个 npm 包"
- 跨语言协作宁可网络开销，不要语言翻译

---

#### 8.2.2 API 契约设计 —— 磨了 3 次的痛苦

**v1 契约**（失败）
```
POST /api/v1/ppt/generate
{
  "project_id": "uuid",
  "brief": {...},
  "materials": [...]
}
→ 同步返回完整 PDF（base64）
```
**问题**：30 分钟 HTTP 请求 → Nginx 超时、Node 端不会等、用户体验差

**v2 契约**（部分成功）
```
POST /api/v1/ppt/generate → 立即返回 {task_id}
GET  /api/v1/ppt/status/{task_id} → 返回 {status, progress}
GET  /api/v1/ppt/result/{task_id} → 返回 PDF URL
```
**问题**：Node 端必须 polling，每 5s 一次，40 次 request 才拿到结果，前端 UX 差

**v3 契约**（最终）
```
POST /api/v1/ppt/generate → 返回 {task_id, sse_url}
GET  /api/v1/ppt/events/{task_id} → SSE 流
     event: status_change
     data: {"status": "COMPOSING", "progress": 0.3}
     
     event: slide_rendered
     data: {"slide_no": 5, "image_url": "https://..."}
     
     event: complete
     data: {"pdf_url": "https://..."}
```

**为什么是 SSE 不是 WebSocket**
- SSE 单向（服务器 → 客户端），够用
- Nginx / CDN 原生支持（WebSocket 需要特殊配置）
- 断线自动重连（浏览器内置）
- Node 端 `EventSource` 3 行代码接入

**协议字段设计的痛点**
- 早期 `progress` 是百分比，但各阶段耗时不均（compose 占 40%、review 占 30%），线性进度条有"卡顿感"
- 改成"阶段 + 阶段内进度"：`{"stage": "COMPOSING", "stage_progress": 0.6, "overall_progress": 0.35}`
- 前端可以显示"正在合成第 24/40 页（总进度 35%）"更有信息量

**教训**
- API 契约是**跨团队技术债**的主要来源，设计时多想一步
- HTTP 长请求在真实网络环境下不可靠，异步 + 通知是正道
- SSE 在这种场景胜过 WebSocket，不要默认上 WebSocket

---

#### 8.2.3 认证与多租户

**现状**
主系统已有用户体系（JWT token），PPT_Agent 不应该重建。

**方案**
- 主系统网关校验 JWT → 转发请求到 PPT_Agent 时带上 `X-User-Id` header
- PPT_Agent 不校验 token（信任内网），只读 header
- 所有 DB 写入带 user_id，支持多租户数据隔离

**安全边界**
- PPT_Agent **不暴露公网**，只在 VPC 内
- 主系统 → PPT_Agent 走内网域名
- 公网用户 → 主系统 → PPT_Agent（三跳）

**踩的坑**
- 一次压测时 Nginx 把 `X-User-Id` header 过滤了（默认规则），导致所有请求成了匿名 → DB 里一堆 `user_id=null` 的垃圾数据
- 修复：Nginx 配置显式 allow `X-User-Id`
- 教训：内部 header 的传递不是自动的，要测

**追问预案**
- **"为什么不直接 PPT_Agent 也验 JWT？"** → 主系统要换 JWT 实现（比如加 2FA）时，PPT_Agent 会跟着改；职责不清
- **"X-User-Id 伪造风险？"** → 只在内网可达，公网请求必须经过主系统网关；是设计选择

---

#### 8.2.4 素材包流转：OSS 预签名 URL

**问题**
用户上传素材（~100MB 的图片文档）：
- 走 Node 主系统 → PPT_Agent 太慢（两跳带宽瓶颈）
- 直传 PPT_Agent 又暴露了服务公网地址

**方案：OSS 直传 + 预签名**
```
1. Node 主系统 → OSS 申请 PUT 预签名 URL (5 分钟有效)
2. 主系统把 URL 返回前端
3. 前端直传 OSS
4. 主系统通知 PPT_Agent："素材在 oss://bucket/path/"
5. PPT_Agent 读 OSS (内网端点，免费流量)
```

**为什么 Node 主系统签 URL 而不是 PPT_Agent**
- 职责：素材归属于用户（主系统的实体），PPT_Agent 只是消费者
- 如果 PPT_Agent 签，它需要理解"哪个 user 上传了哪个素材"，耦合度高

**踩的坑**
- 早期 OSS bucket 开了公网读，然后被爬虫扒了一波（幸好都是测试数据）
- 修复：bucket 全私有 + Python 侧读时用 STS 临时凭证
- 教训：**默认关，显式开**，不是反过来

**追问预案**
- **"为什么不用 base64 embed 在请求里？"** → 100MB base64 撑爆 HTTP body，Nginx 限制 + JSON 解析崩
- **"OSS 挂了怎么办？"** → 主系统有重试 + 降级到本地 NAS；PPT_Agent 端读失败就任务失败，不做复杂降级

---

#### 8.2.5 异步进度推送 —— SSE 链路的眼泪

**架构**
```
浏览器 ─── EventSource ───▶ Node 主系统 ─── SSE 代理 ───▶ PPT_Agent
                                  │
                                  └── 鉴权 + 路由
```

**踩坑**
- **Nginx 默认开启 proxy_buffering** → SSE 消息被缓冲，浏览器收不到实时更新
  - 修复：`proxy_buffering off` + `proxy_cache off` + `Content-Type: text/event-stream` 保持
- **Node Express 默认超时 2 分钟** → 长连接被断
  - 修复：`req.setTimeout(0)`
- **多个 Node 实例时用户 reconnect 到另一个实例**，该实例没有对应 SSE 源 → 重连失败
  - 修复：用 sticky session（基于 task_id hash）或换 Redis Pub/Sub 广播
- **浏览器 tab 切后台后 SSE 连接被限流** → 进度卡住
  - 修复：visibilitychange event 重连

**SSE 事件设计**
```
event: status_change    # 阶段切换
event: slide_rendered   # 单页渲染完成（前端可逐页预览）
event: review_issue     # 实时报审查问题
event: error            # 非致命错误
event: complete         # 完成，带 pdf_url
event: heartbeat        # 每 30s 一次，防中间件误判死连接
```

**为什么要 heartbeat**
早期没 heartbeat，CDN 检测到 30s 无数据 → 断开连接 → 用户看到"连接断开" → 重连 → 重复。

**教训**
- SSE 看起来简单，生产环境的"真实网络"里问题很多
- 代理链路中任何一跳的配置都可能成为 bottleneck
- **假设中间件会作恶** —— buffer / cache / timeout 默认都不友好

---

#### 8.2.6 前端进度 UI 的协同

**前端团队的需求**
- 生成过程可视化（不能只转圈）
- 每完成一页能"预览"（用户提前看到效果，体验更好）
- 出错时友好提示（不能就 "ERROR: foo"）

**我的协议交付**
- SSE 事件定义（8.2.5）
- 错误码 + 文案映射表：
```typescript
// 前后端共享
enum PPTErrorCode {
    LLM_TIMEOUT = "llm_timeout",          // 文案："AI 生成超时，正在重试"
    MATERIAL_MISSING = "material_missing", // 文案："部分素材未找到，将使用占位图"
    ESCALATE_HUMAN = "escalate_human",    // 文案："部分页面需要人工调整"
    ...
}
```
- 阶段 i18n 表：`COMPOSING` → "正在生成第 {n}/{total} 页"

**沟通摩擦**
- 前端想要 "`total_pages` 在最开始就知道"，但我们的架构是 Outline 生成后才确定
  - 妥协：Outline 阶段结束触发一个 `outline_ready` 事件，带 `total_pages`
- 前端想要"用户能随时暂停"，但 Celery 任务中断会留脏数据
  - 妥协：只支持"整体取消"（重置 project 状态），不支持"暂停继续"

**教训**
- 前后端协同最大摩擦是**时序假设**，要早对齐
- 妥协不是全输，给前端 80% 的能力 + 明确 20% 的不做原因，比承诺 100% 最后交 60% 好

---

#### 8.2.7 错误语义的对齐

**问题**
Python 抛 `RunningHubTimeout`，到 Node 端变成 `{"error": "RunningHubTimeout..."}`，再到前端是 `系统错误`。用户看了一脸懵。

**解决**
- 定义跨语言的错误码枚举（YAML 单源，Python/TS/中文文案生成）
- 每个错误码附：
  - 严重程度（fatal / degraded / info）
  - 用户可操作建议（重试 / 等待 / 联系客服）
  - 内部 debug 信息（仅后端日志）

```yaml
# errors.yaml
- code: runninghub_timeout
  severity: degraded
  user_message_zh: "方案图生成超时，已使用占位图"
  user_action: "可稍后在编辑器中手动替换图片"
  internal_notes: "runninghub API unresponsive > 180s"
```

**效果**
- 前端无需写错误翻译逻辑，直接展示 user_message
- 客服看到 error_code 能快速定位
- 工程师不同语言（Python/Node）有一致的错误字典

**教训**
- 错误处理不是"throw 了就完事"，要设计成"对用户有意义的反馈"
- 跨语言错误码需要**单源定义**，否则会漂移

---

#### 8.2.8 部署与 CI 打通

**问题**
最早两个团队独立部署：
- Node 发版 → 主系统上新功能 → 调 PPT_Agent 的新 API → PPT_Agent 没部署 → 生产 500
- 反过来也一样

**解决**
- **API 版本化**：`/api/v1/`、`/api/v2/` 并存一段时间
- **兼容期 ≥ 2 周**：v2 发布后，v1 保留 2 周
- **契约测试**：Node 端跑 PPT_Agent 的 mock server（PPT_Agent 团队维护），保证 Node 调用符合契约
- **CI 联动**：PPT_Agent 的 CI 跑完后，触发 Node 主系统的契约测试（GitHub Actions 跨 repo workflow）

**部署时序**
```
规则：改 API 时，先部署提供方（后端），再部署消费方（前端）
例外：如果是 break change，要先发新版本（v2），双跑一段，切完流量后再下老版本
```

**教训**
- 跨团队部署必须有**契约层**，否则就是"谁倒霉谁先上线"
- 版本并存 + 兼容期是老生常谈，但真要落地 CI 是苦活
- 规则要写明文（doc），不能靠"口头约定"

---

#### 8.2.9 摩擦事件及解决

**事件 1：凌晨 2 点的生产事故**
- 现象：用户生成 PPT 无响应
- 定位：Node 主系统升级了 Node 版本（16→20），EventSource 行为变化，SSE 连接立即断开
- 处理：Node 回滚，工作日修复
- 改进：跨团队的 runtime 升级要提前通告，加入联调清单

**事件 2：素材丢失的罗生门**
- 现象：用户说"我上传的图怎么没用到？"
- 查日志：PPT_Agent 收到的素材列表里没那张图
- 查 Node 日志：前端上传成功了
- 查 OSS：文件存在，但 key 对不上（前端 base64 编码 key 特殊字符，Node 转发时解码不一致）
- 处理：统一 key 规范（只用 ASCII + `-_`）
- 改进：跨语言的字符串转义是地雷区，定规范 + 测

**事件 3：联调会的误解**
- Node 团队说："你们 API 响应慢，需要加缓存"
- 我："我们单次 30 分钟是必然的，你缓存个啥"
- 查了半天才发现他们说的是 `/api/v1/ppt/status` 的 polling 响应慢（DB 查询没建索引）
- 改进：沟通时用对方能懂的术语 + 给出具体 API path，不要用抽象词

**教训**
- 跨团队沟通 60% 的问题是**用词对不上**，多确认"你说的 X 是指什么"
- 生产事故后写 postmortem（`docs/ops/postmortems/`），不甩锅，只改进
- 跨团队的运维手册（"发布前 checklist"、"on-call 响应表"）是必要基建

---

### 8.3 总结：协作能力的三件事

**1. 把专业语言翻译成规范**
建筑师说"呼吸感"，工程师要拆解成"图片占比 ≥ 60%、留白 ≥ 30%"。翻译能力是跨专业协作的核心。

**2. 在边界设计契约**
跨团队不是"我们一起写代码"，而是"在合适的地方定清楚接口"。API 契约、错误码、时序假设，都是契约。

**3. 建立反馈闭环**
一次性的协作是项目，持续的协作是系统。反馈工具、定期 review、postmortem 制度，让协作从依赖"个人关系"变成"组织能力"。

---

## 附：速查索引

| 关键决策 | 文档 | 文件引用 |
|---------|------|---------|
| 模块化单体 | ADR-001 | [docs/ops/decisions/](docs/ops/decisions/) |
| Celery over LangGraph | ADR-002 | [docs/ops/decisions/](docs/ops/decisions/) |
| Composer 双模 | ADR-003 | [docs/ops/decisions/](docs/ops/decisions/) |
| Vision-only review | ADR-004 | [docs/ops/decisions/](docs/ops/decisions/) |
| Concept Render | ADR-005 | [docs/ops/decisions/ADR-005-concept-render-via-outline.md](docs/ops/decisions/ADR-005-concept-render-via-outline.md) |

| 核心模块 | 文件 |
|---------|------|
| Outline Agent | [agent/outline.py](agent/outline.py) |
| Concept Render Agent | [agent/concept_render.py](agent/concept_render.py) |
| Composer | [agent/composer.py](agent/composer.py) |
| Critic（审查） | [agent/critic.py](agent/critic.py) |
| Material Resolver | [tool/material_resolver.py](tool/material_resolver.py) |
| RunningHub Client | [tool/image_gen/runninghub.py](tool/image_gen/runninghub.py) |
| Concept Prompts | [tool/image_gen/concept_prompts.py](tool/image_gen/concept_prompts.py) |
| Blueprint | [config/ppt_blueprint.py](config/ppt_blueprint.py) |
| Settings | [config/settings.py](config/settings.py) |
| Celery App | [tasks/celery_app.py](tasks/celery_app.py) |
| Concept Render Task | [tasks/concept_render_tasks.py](tasks/concept_render_tasks.py) |

| 测试入口 | 文件 |
|---------|------|
| E2E 脚本 | [scripts/material_package_e2e.py](scripts/material_package_e2e.py) |
| RunningHub 单测 | [tests/unit/test_runninghub.py](tests/unit/test_runninghub.py) |
| Concept Render 集成测 | [tests/integration/test_concept_render.py](tests/integration/test_concept_render.py) |
