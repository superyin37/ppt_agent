---
date: 2026-04-20
status: Done
completed_on: 2026-04-21
owner: superxiaoyin
assignee: Claude Code (Opus 4.7)
---

# Task Brief:概念方案建筑渲染图生成(Concept Render)

## 1. Goal

在管线中新增一个 `concept_render` 步骤,为 3 个概念方案各生成 **鸟瞰图 / 室外人视图 / 室内人视图** 共 9 张建筑渲染图,作为 `Asset` 记录供 Composer 消费。

**完成标志**:`scripts/material_package_e2e.py` 跑全量 real-LLM 时,第七章 9 页(`concept-aerial-*` / `concept-perspective-*`)能在 PDF 中呈现**真实生成的图**而非占位。

---

## 2. Context

- 蓝图 [config/ppt_blueprint.py:321-382](../../../config/ppt_blueprint.py#L321-L382) 预留了 9 页概念方案槽位,标注 `generation_methods=[M.NANOBANANA]`,但**从未被消费**(`NANOBANANA` enum 被定义但无 dispatcher,见上轮分析)
- TODO `[P1-2] 接入 Nanobanana 图像生成`(现改为 runninghub)是蓝图完整度的最后一块硬缺口,接入后蓝图 41 页均可跑出真实内容
- 使用 runninghub `/rhart-image-n-g31-flash-official/image-to-image` 模型,image-to-image 模式(非 text-to-image)

---

## 3. Out of Scope

- **封面页 / 目录页 / 文化插画页**的 Nanobanana(蓝图中也有标注)— 先只做第七章 9 页,其他页继续走占位或素材
- **text-to-image 模式** — 本期只做 image-to-image
- **其他图像模型接入**(Midjourney / SD 等)— runninghub 一家即可
- **Web 上传到 OSS** — 先落盘 `D:\tmp\assets\{project_id}\`,OSS 是 P2-5
- **图像编辑 / 局部重绘** — 一次生成不满意就打回到 ConceptProposal 调整,不做图像级二次编辑

---

## 4. Constraints

### 架构
- 新步骤放在 **Outline 之后 / Material Binding 之前**,作为独立 Celery task(队列 `concept_render`)
- `ConceptProposal` 结构化字段**由 Outline Agent 输出**(方案 B,选定);方案 C(独立 Concept Design Agent)列入 [decisions/](../decisions/) 的未来改进方向
- **不要动 Composer / Critic** — 本改动对下游透明,下游只看到 `Asset` 多了 9 条

### 技术
- 所有 LLM 调用经 [config/llm.py](../../../config/llm.py)(不影响,本任务不调 LLM)
- runninghub HTTP 调用独立封装在 `tool/image_gen/runninghub.py`,单测可 mock
- 异步 polling:runninghub 任务异步,submit → poll task_id → download image
- 3 张图**串行链式**:鸟瞰图先出,作为 ext_perspective 的 ref;ext_perspective 作为 int_perspective 的 ref
- 3 个方案之间**并行**(Celery `group`)—— 总时延 ≈ 单方案串行时长

### 失败降级
- 任意一张失败 → **纯灰底 PNG + "生成失败" 水印** 作占位,记录 `Asset.meta.generation_failed=True`
- **不阻塞**主管线,整个项目继续 Compose / Review
- 记录新的 rule code `V008=CONCEPT_IMAGE_MISSING`(P2)由 Critic 视觉层识别

### 环境
- `.env` 已有 `RUNNING_HUB_KEY`;新增 `RUNNING_HUB_WORKFLOW_ID`、`RUNNING_HUB_BASE_URL`、`RUNNING_HUB_*_NODE_ID`(全部 `RUNNING_HUB_*` 前缀,保持与既有命名一致)
- 本地跑 E2E 默认**开启** concept_render;通过 `settings.CONCEPT_RENDER_ENABLED=false` 可关闭(smoke test 用)

---

## 5. Acceptance Criteria

- [ ] Outline Agent 输出的 JSON 含 `concept_proposals: [ConceptProposal × 3]`,每个 proposal 字段齐全(name / design_idea / narrative / design_keywords / massing_hint / material_hint / mood_hint)
- [ ] 新表 / spec_json 字段落地,`db/migrations/005_concept_proposals.py`(如选独立字段)
- [ ] `tool/image_gen/runninghub.py` 单测:mock HTTP 下 submit + poll + download 链路通,超时 / 错误返回正确异常
- [ ] `agent/concept_render.py` 端到端:输入 outline + brief_doc + material_package → 输出 9 个 `Asset` 记录(或占位)
- [ ] `scripts/material_package_e2e.py` 插入新步骤,跑 `test_material/project1` 能生成 9 张真实图(或占位,若 API key 未配)
- [ ] PDF 中第七章 9 页图片位置显示生成的图,`logical_key=concept.{N}.{view}` 的 Asset 被 Material Binding 正确匹配
- [ ] 失败路径验证:kill runninghub endpoint 或返回错误,9 张图全部降级为灰底水印,PDF 仍能产出
- [ ] 新增集成测试 `tests/integration/test_concept_render.py`(至少 1 个:跑单方案单图 + mock API)
- [ ] 更新 [GLOSSARY.md](../GLOSSARY.md) 加 `ConceptProposal` / `ConceptRender Agent` 词条
- [ ] 更新 [STATUS.md](../STATUS.md) 从 "不能跑什么" 移除"Nanobanana 未接入",加入 "能跑什么" 列表
- [ ] 更新 [TODO.md](../TODO.md) 删除 P1-2,CHANGELOG.md 追加条目
- [ ] 写一个 [decisions/ADR-005-concept-render-via-outline.md](../decisions/) 记录方案 B 的决策 + 方案 C 作为未来改进

---

## 6. Suggested Approach

### 文件改动清单

| 文件 | 改动类型 |
|------|---------|
| `schema/concept_proposal.py` | 新建 — `ConceptProposal` Pydantic v2 模型 |
| `prompts/outline_system_v2.md` | 扩 — 增加 `concept_proposals` 输出要求 + schema 示例 |
| `agent/outline.py` | 扩 — 解析并持久化 `concept_proposals` 到 `Outline.spec_json["concept_proposals"]` |
| `tool/image_gen/__init__.py` | 新建 |
| `tool/image_gen/runninghub.py` | 新建 — HTTP client,submit / poll / download |
| `tool/image_gen/concept_prompts.py` | 新建 — 3 档 prompt 模板 + 变量填充 |
| `tool/image_gen/placeholder.py` | 新建 — Pillow 生成灰底 + 水印 |
| `agent/concept_render.py` | 新建 — 编排 9 张图生成 + Asset 入库 |
| `tasks/concept_render_tasks.py` | 新建 — Celery `@shared_task` + 并发 group |
| `tasks/celery_app.py` | 扩 — 注册 `concept_render` 队列 |
| `tool/material_resolver.py` | 扩 — 识别 `concept.{N}.{view}` logical_key |
| `config/ppt_blueprint.py` | 扩 — aerial/perspective 页 `required_inputs` 显式加 concept logical keys |
| `scripts/material_package_e2e.py` | 扩 — Outline 后 / Material Binding 前插入 `run_concept_render()` |
| `.env.example` | 扩 — 3 个 runninghub 配置 |
| `tests/unit/test_runninghub.py` | 新建 — mock HTTP 单测 |
| `tests/integration/test_concept_render.py` | 新建 — E2E 单方案 |

### 流水

```
Outline Agent
  ↓ (spec_json.concept_proposals 就位)
★ Concept Render ★
  ├─ 方案 1:aerial(ref=site.boundary) → ext(ref=aerial) → int(ref=ext)
  ├─ 方案 2:aerial → ext → int             (三方案并行)
  └─ 方案 3:aerial → ext → int
  ↓ (9 条 Asset 记录入库)
Material Binding
  ↓ 按 concept.{N}.{view} logical_key 匹配
Composer / Render / Review / Export
```

### `ConceptProposal` schema 建议

```python
class ConceptProposal(BaseModel):
    index: int = Field(ge=1, le=3)
    name: str                      # "云上之城"
    design_idea: str               # ≤20 字核心理念
    narrative: str                 # 100-150 字理念解析
    design_keywords: list[str]     # ≤5 个,中英文皆可,供生图 prompt
    massing_hint: str              # 体量描述,如 "L形退台 + 中庭"
    material_hint: str             # "玻璃 + 素水泥 + 金属格栅"
    mood_hint: str                 # "温润 / 冷峻 / 未来感"
```

### runninghub prompt 模板

```python
AERIAL = (
    "Architectural rendering, aerial bird's-eye view, photorealistic. "
    "{concept_name} — {design_idea}. "
    "Building type: {building_type}. Site context: {site_context}. "
    "Massing: {massing_hint}. Materials: {material_hint}. "
    "Style: {mood_hint}, {style_prefs}, cinematic lighting, ultra-detailed, "
    "architectural visualization, professional rendering, 4K."
)
EXT_PERSP = (
    "Architectural photography, human eye-level exterior view, photorealistic. "
    "{concept_name} — {design_idea}. Facade: {material_hint}. "
    "Mood: {mood_hint}. Composition: golden hour, cinematic depth, 35mm lens, "
    "editorial architectural photography, award-winning."
)
INT_PERSP = (
    "Interior architectural photography, human eye-level, photorealistic. "
    "{concept_name} — {design_idea}. Interior materials: {material_hint}. "
    "Mood: {mood_hint}. Composition: natural light, 24mm lens, "
    "editorial interior photography, magazine quality."
)
NEGATIVE = "cartoon, low quality, blurry, distorted, watermark, text overlay, crowds, people"
```

### runninghub 调用参数推测(需在开发中对齐 API 文档)

```python
{
    "workflow_id": "rhart-image-n-g31-flash-official/image-to-image",
    "prompt": "...",
    "negative_prompt": "...",
    "init_image_url": "<uploaded ref image url or base64>",
    "denoise_strength": 0.65,   # 鸟瞰 0.75 / ext 0.6 / int 0.5 递减,保一致性
    "seed": <project_id 的 hash>,  # 同项目稳定
    "width": 1920, "height": 1080,
}
```

### reference image 选择

| 视图 | ref image | denoise 建议 |
|------|-----------|-------------|
| aerial | 素材包 `site.boundary.image`(`场地四至分析_285.png`) | 0.75(形变大,但保留场地形状) |
| ext_perspective | 上一步生成的 aerial | 0.6 |
| int_perspective | 上一步生成的 ext_perspective | 0.5 |

### Asset logical_key 约定

```
concept.1.aerial
concept.1.ext_perspective
concept.1.int_perspective
concept.2.aerial
...
concept.3.int_perspective
```

---

## 7. Relevant Files

### 主要改动
- 见第 6 节清单

### 参考实现
- [tool/material_pipeline.py](../../../tool/material_pipeline.py) — Asset 入库的现有范式,照抄 `_build_item_payload` + DB insert 逻辑
- [tool/asset/map_annotation.py](../../../tool/asset/map_annotation.py) — 同属"派生资产"类工具,可作为 `agent/concept_render.py` 的结构参考
- [agent/outline.py](../../../agent/outline.py) — `concept_proposals` 持久化入口
- [tasks/render_tasks.py](../../../tasks/render_tasks.py) — Celery group 并发模式参考

### 不要动
- [agent/composer.py](../../../agent/composer.py) — Composer 对本改动透明
- [agent/critic.py](../../../agent/critic.py) — Critic 不主动判断"是否应该有概念图",图不存在时直接按缺素材处理
- [tasks/review_tasks.py](../../../tasks/review_tasks.py) — Review 回环逻辑与本任务无关

---

## 8. Questions / Risks

### 开工前要对齐
- **runninghub API 文档** — 我将凭名字 `/rhart-image-n-g31-flash-official/image-to-image` 做合理假设(submit + poll + download 标准异步模式),实际参数名 / 鉴权方式需开发中读官方文档;若 API 与假设偏差大,需调整 `tool/image_gen/runninghub.py`
- **image-to-image 是否必须 ref 图** — 若可无 ref 退化 text-to-image,需保留此路径用于方案 2/3 的 aerial(此时无上游图)

### 已知风险
- **串行链式时延长** — 单方案 3 张图串行,每张假设 30s,单方案 ≈ 90s,3 方案并行仍 ≈ 90s。用户可接受
- **image-to-image 保留 ref 形状过强** — 若场地四至图是抽象示意图,生成的鸟瞰图可能"像地图而非建筑",需在 prompt 里强调 "3D building, not a map diagram";如仍失败,考虑改成 text-to-image 或提供额外风格 ref
- **runninghub 费用** — 9 次 / 项目,开发期 smoke 要 `CONCEPT_RENDER_ENABLED=false` 避免烧钱
- **E2E 等待时间变长** — 全量 real-LLM 跑会多 90s,预留

### 未来改进(不在本期范围)
- **方案 C:独立 Concept Design Agent** — 把方案结构化字段从 Outline 剥离,让 Outline 只关心页面分配 / 命名,Concept Design Agent 负责生成完整设计描述(体量 / 流线 / 景观等)。当前任务用方案 B(挂 Outline)是为了改动最小,若后续要做更深的设计推演(如每方案 5 条优势 / 3 个技术亮点),再拆出独立 Agent
- **其他章节的 Nanobanana**(封面 / 目录 / 文化页)— 本期不做,`generation_methods=[NANOBANANA]` 的其他槽位继续走占位
- **图像后期编辑 / 微调**

---

## 9. Updates

### 2026-04-21 — 开发完成

**实际落地与 brief 一致的部分**:
- Outline Agent 输出 `concept_proposals`(方案 B)✅
- 串行链式一致性(aerial 0.75 → ext 0.60 → int 0.50)✅
- 鸟瞰参考图用 `site.boundary.image` ✅
- 失败降级纯灰 + "生成失败" 水印 ✅
- 新 Celery 队列 `concept_render` + `concept_render_tasks.py` ✅

**与 brief 假设偏差/补充**:
- runninghub 鉴权是 JSON body `apiKey`(不是 HTTP header),且 workflow 参数通过 `nodeInfoList` 覆盖而非扁平字段。凭 ComfyUI_RH_APICall 源码对齐,实际节点 id(`RUNNING_HUB_*_NODE_ID`)做成可配置,不同 workflow 可换
- image-to-image 若没有 ref 图(项目缺 `site.boundary.image`),不退化成 text-to-image,而是直接落降级占位 — 简化逻辑,保证管线不抖
- 已新增 `CONCEPT_RENDER_ENABLED=false` 开关,smoke / dev 可跳过烧钱

**产出**:见 [CHANGELOG 2026-04-21](../CHANGELOG.md#2026-04-21--concept-render-管线adr-005) 完整清单。决策记录见 [ADR-005](../decisions/ADR-005-concept-render-via-outline.md)。

**遗留**:
- 真机 workflow_id / api_key 尚未申请;本地只验证 placeholder 降级路径 + 单元 mock,真机一次端到端列入 [TODO P0-2](../TODO.md)
