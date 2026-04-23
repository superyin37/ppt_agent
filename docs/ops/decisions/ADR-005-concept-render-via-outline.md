---
name: ADR-005 — 概念方案结构化字段由 Outline Agent 输出
description: ConceptProposal 挂在 Outline 输出,不单独拆 Concept Design Agent;图像生成走 runninghub image-to-image
status: Accepted
date: 2026-04-20
owner: superxiaoyin
---

# ADR-005:概念方案结构化字段由 Outline Agent 输出 + runninghub 作为图像生成服务

## Context

蓝图 [config/ppt_blueprint.py](../../../config/ppt_blueprint.py) 第七章固定 9 页(3 方案 × 3 页:鸟瞰 / 室外人视 / 室内人视)预留了概念方案渲染,`generation_methods=[M.NANOBANANA]` 但**从未有对应的执行器**(enum 被定义却无 dispatcher)。

为打通这 9 页,需要两个决策:
1. **"3 个方案的结构化描述(名称 / 理念 / 材质 / 氛围)由哪个 Agent 输出"** —— 目前仅以自由文本形式存在于 outline 的 `content_directive`,无法可靠喂给生图模型
2. **"调用哪家图像生成服务"** —— 原设想 Nanobanana(DN-001),但未验证

同时,image-to-image 模式要求 ref 图:
- 鸟瞰视图的 ref 用素材包中的 `site.boundary.image`(`场地四至分析_285.png`)
- ext / int 人视图的 ref 用链条上一张图(保证三视图一致性)

## Options Considered

### 结构化字段归属

| 方案 | 评估 |
|------|-----|
| A:挂到 BriefDoc Agent 输出 | ❌ BriefDoc 在 Outline 之前,此时尚未确定三方案分配,时序不对 |
| **B:Outline Agent 顺便输出 `concept_proposals`**(选) | ✅ Outline 本来就要命名 / 区分 3 方案,追加字段改动最小;缺点是 Outline 职责略重 |
| C:新建独立 Concept Design Agent(LLM 调用) | ✅ 职责单一,可深度推演(5 条优势 / 3 个技术亮点),但新增一次 LLM 调用、新增一个模块,本期收益有限 |

### 图像生成服务

| 方案 | 评估 |
|------|-----|
| A:Nanobanana 原生 | 未验证,账户 / API 稳定性不明 |
| **B:runninghub `/rhart-image-n-g31-flash-official/image-to-image`**(选) | ✅ 用户已有账户,异步提交 + 轮询 + 下载的标准模式,工作流模型固化,image-to-image 原生支持 |
| C:SDXL / Flux 自建 / OpenRouter 图像模型 | 增加基础设施或成本,本期无必要 |
| D:占位不做 | 违背蓝图第七章设计意图,九页永远空白 |

### 一致性策略(3 视图 / 单方案)

| 方案 | 评估 |
|------|-----|
| A:串行链式 — aerial → ext(ref=aerial)→ int(ref=ext),denoise 递减(0.75→0.6→0.5) | ✅ 体量 / 材质 / 色调自然连贯,代价是单方案 ~90s 串行 |
| B:并行 + 共享 seed + 共享 style prefix | 更快,但一致性仅靠文字约束,不稳 |

## Decision

- **结构化字段:选 B** — 在 `Outline.spec_json["concept_proposals"]` 存 `list[ConceptProposal]`(字段见 brief)
- **图像服务:选 B** — runninghub,封装在 [tool/image_gen/runninghub.py](../../../tool/image_gen/runninghub.py)(待建)
- **一致性:选 A** — 串行链式,3 方案之间并行
- **失败降级**:Pillow 生成 **纯灰底 + "生成失败" 水印** PNG 作占位,不阻塞主管线
- **新增步骤位置**:`Outline → ★ Concept Render ★ → Material Binding`,Celery 队列 `concept_render`

## Consequences

### 好处
- Outline Agent 无需新增独立 LLM 调用,只扩 prompt 输出 schema(增量小)
- runninghub 工作流模型固化,部署 / API 形态稳定
- 串行链式保证三视图强一致性,符合"同一方案的三张效果图"直觉
- 失败降级确保管线健壮性 —— 单张图失败不会让项目状态机走到 FAILED

### 代价
- Outline Agent 职责略重(既做分页分配,又做方案设计)
- 单方案 3 图串行,总时延 ≈ 90s(3 方案并行后总时延不叠加)
- runninghub 单点依赖 —— 服务不可用时 9 张全部降级占位

### 前提 / 未来评估点
- 若后续要做**更深的设计推演**(每方案 5 条优势 / 3 个技术亮点 / 流线分析),本 ADR 被 **Superseded by** 新 ADR,届时拆出独立 **Concept Design Agent**(方案 C)
- 若 runninghub 稳定性或成本成为问题,可横向替换 `tool/image_gen/` 下的 client 实现,不影响上游
- 若 `site.boundary.image` 过于抽象(示意图)导致鸟瞰图"像地图而非建筑",考虑提供额外风格 ref 或降级 text-to-image

### 修改文件(见 [briefs/2026-04-20-concept-render.md](../briefs/2026-04-20-concept-render.md) 第 6 节)

---

## 关联

- **Brief**:[briefs/2026-04-20-concept-render.md](../briefs/2026-04-20-concept-render.md)
- **关闭 DN**:`DN-001 Nanobanana vs 其他图像生成服务` — 选定 runninghub
- **TODO**:`P1-2` — 由本 ADR 指导实施
- **Supersedes**:无
