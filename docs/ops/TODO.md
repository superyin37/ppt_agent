---
name: 待办清单
description: P0/P1/P2 分级 TODO,带验收标准 — 覆写式,完成后删除或移入 CHANGELOG
last_updated: 2026-05-06
owner: superxiaoyin
---

# TODO

> **更新规则**:完成后直接删除该条(历史在 `CHANGELOG.md` / git log)。不打勾不划线。
> **P0** = 阻塞核心链路 / **P1** = 严重影响质量 / **P2** = 增强/打磨

---

## P0 — 必须做

当前无 P0。上一轮 P0（RunningHub 9/9 严格验收、Slide 38 placeholder 修复）已完成并移入 [CHANGELOG.md](CHANGELOG.md)。

## P1 — 质量关键

- [ ] **[P1-1] Template mode 视觉密度二轮优化** — 跨素材包验证确认 `V007` 是系统性问题：project1 `28/41` 页 P2，project2 `29/40` 页 P2 且 `V007=23`，project3 `23/39` 页 P2 且 `V007=18`。
  - 验收:project1/project2/project3 重跑后，`V007` 数量显著下降；政策页、文化页、图表页、场地页不能出现下半屏大面积空白。
  - 实施要点:`policy_list` 增加 2 条政策时的纵向填充策略；`content_bullets` 增加分栏/引用/指标区；`chart` 页增大图表和结论区；`image_grid` 页按图片数量自适应排布。

- [ ] **[P1-2] 概念大图文字可读性修复** — Slide 31/34/37 文案直接叠在复杂 RunningHub 效果图上，review 报 `V004`。
  - 验收:概念页标题、方案名、idea、analysis 在深浅复杂背景上均清晰可读。
  - 实施要点:`concept_scheme` 增加固定信息区、遮罩层或渐变安全区；避免正文直接压在高频图像区域。

- [ ] **[P1-3] 地图/场地图可读性策略** — Slide 15-17 地图标注拥挤，存在 `V001/V004`。
  - 验收:地图页主信息清楚，文字不压图内密集标注；必要时仅展示局部裁切或把说明移到独立面板。
  - 实施要点:对地图资产做版式分型：单大图、双图、图文分区；必要时加入半透明底、裁切和局部放大。

- [ ] **[P1-4] `competitor-web` 接入 web search + TABLE 模板** — 当前 Slide 22 稳定兜底 HTML，原因是联网搜索/TABLE 数据尚未完成。
  - 验收:`tool/search/web_search.py` 返回结构化竞品条目；`competitor-web` 的 `template_component` 可切回 `TABLE`；全量 E2E 只保留明确设计原因或 JSON 失败导致的 HTML 页。

- [ ] **[P1-5] Review 报告自动摘要与回归门槛** — 现在 review 能跑，但需要把问题转化成可执行 gate。
  - 验收:E2E 输出按 rule 聚合的摘要，例如 `V007=21,V004=7`；可配置阈值，如 critical=0、placeholder=0、P2 不超过指定数量。

- [ ] **[P1-6] 修 BUG-007 中文引号 JSON 解析** — Prompt 强制要求内引号转义，或使用宽松 JSON 修复。
  - 验收:semantic review 在含中文引号的 slide 上不再抛 `JSONDecodeError`。

- [ ] **[P1-7] 串联 `tasks/outline_tasks.py` 的 brief_doc→outline 两步** — 当前仅 E2E 脚本手动串联，API 路径不完整。
  - 验收:API/Celery 路径能从素材包到 outline 自动串联，不依赖脚本中的手动 glue code。

- [ ] **[P1-8] Outline 页数一致性 gate** — project3 出现 LLM 声明 40 页、实际 outline 39 页；脚本能继续生成，但产品口径需要更明确。
  - 验收:当目标页数和实际 outline 页数不一致时，系统能自动重试/补页，或显式记录“本项目采用 39 页”并让后续页码、目录、PDF 元信息一致。

## P2 — 打磨/增强

- [ ] **[P2-1] VisualTheme section_colors / template_pack 正式落库** — 当前 render 已兼容字段不存在，但 schema/DB/prompt v2 仍需完成。
  - 验收:相同 `project_id` 多次生成章节色稳定；章节色能跟大纲调性对应；`template_pack` 有默认值 `minimalist_architecture`。

- [ ] **[P2-2] 移除 `RecommendRequest` body 中冗余 `project_id`** — BUG-009。
- [ ] **[P2-3] Composer 高并发 fallback 优化** — BUG-008，考虑降级 schema 严格度或提升重试上限。
- [ ] **[P2-4] 案例库填充真实数据** — 当前 `scripts/seed_cases.json` 仅占位。
- [ ] **[P2-5] OSS 真实接入** — 替换本地 mock，需 ops 提供 access_key/secret_key。
- [ ] **[P2-6] PPTX 导出** — `python-pptx` 已在依赖，未实现；低优先，PDF 是一期验收物。
- [ ] **[P2-7] 为静态文档(01-15)顶部加 `last_updated` + `owner` 字段** — 让读者能自判时效性。
- [ ] **[P2-8] 更新 [../00_index.md](../00_index.md) 补齐 16-28 号文档条目** — 当前索引只到 15 号，缺 13 份文档。

## Ideas / Backlog(不承诺做)

- 第 2、3 个 template pack：`editorial_warm`、`tech_mono`。
- “LLM 选 pack”机制。
- chart_materialize 中文字体兼容探测。
- `competitor-web` 联网搜索接入后，做真实竞品数据缓存与引用来源记录。
- `concept-perspective` 双图布局可继续拆分为每方案 2 页，或保留一页双图但增强视觉密度。
- PPTX 导出与 PDF 视觉一致性校验。

---

## 命名约定

- `[P0-N]` / `[P1-N]` / `[P2-N]` — 方便在 commit / PR 中引用(如 `fix [P1-4] web search table`)
- 完成后直接删除该条，不做 ~~strikethrough~~，保持列表清爽
