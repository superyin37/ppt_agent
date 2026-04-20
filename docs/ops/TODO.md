---
name: 待办清单
description: P0/P1/P2 分级 TODO,带验收标准 — 覆写式,完成后删除或移入 CHANGELOG
last_updated: 2026-04-20
owner: superxiaoyin
---

# TODO

> **更新规则**:完成后直接删除该条(历史在 `CHANGELOG.md` / git log)。不打勾不划线。
> **P0** = 阻塞核心链路 / **P1** = 严重影响质量 / **P2** = 增强/打磨

---

## P0 — 必须做

- [ ] **[P0-1] 跑一次 41 页 real-LLM 全量验证** — 距上次成功运行(2026-04-05)已 15 天,且 review 回环 v2 修复后仅做过 smoke,需确认全链路仍稳定
  - 验收:`test_output/` 下产出完整 `deck.pdf` + 所有 slide PASS(或记录合理 SKIPPED)

## P1 — 质量关键

- [ ] **[P1-1] 验证 BUG-010(Bug 5 修复后回环收敛)** — HTML 模式 vision-only 审查,3 slide 跑通且 PASS,非 ESCALATE_HUMAN
  - 验收:`review_loop_v2_check` 级别的 smoke 跑完,所有 slide 状态为 PASS 或 REVIEW_PASSED
- [ ] **[P1-2] 接入 Nanobanana 图像生成** — 蓝图中"概念方案"章节 9 页依赖它,当前是占位
  - 验收:`tool/image_gen/nanobanana.py` 可从 prompt 生成图像并存入 `Asset`
- [ ] **[P1-3] 接入联网搜索** — 蓝图"背景研究(11 页)"+ "竞品分析(3 页)"依赖它
  - 验收:`tool/search/web_search.py` 可检索并返回结构化结果供 Composer 消费
- [ ] **[P1-4] 修 BUG-007 中文引号 JSON 解析** — Prompt 强制要求内引号转义,或使用宽松 JSON 修复
  - 验收:semantic review 在含中文引号的 slide 上不再抛 `JSONDecodeError`
- [ ] **[P1-5] 串联 `tasks/outline_tasks.py` 的 brief_doc→outline 两步** — 当前仅 E2E 脚本手动串联,API 路径不完整

## P2 — 打磨/增强

- [ ] **[P2-2] 移除 `RecommendRequest` body 中冗余 `project_id`** — BUG-009
- [ ] **[P2-3] Composer 高并发 fallback 优化** — BUG-008,考虑降级 schema 严格度或提升重试上限
- [ ] **[P2-4] 案例库填充真实数据** — 当前 `scripts/seed_cases.json` 仅占位
- [ ] **[P2-5] OSS 真实接入** — 替换 `D:\tmp\` mock,需 ops 提供 access_key/secret_key
- [ ] **[P2-6] PPTX 导出** — `python-pptx` 已在依赖,未实现;低优先,PDF 是一期验收物
- [ ] **[P2-7] 为静态文档(01-15)顶部加 `last_updated` + `owner` 字段** — 让读者能自判时效性
- [ ] **[P2-8] 更新 [../00_index.md](../00_index.md) 补齐 16-28 号文档条目** — 当前索引只到 15 号,缺 13 份文档

## Ideas / Backlog(不承诺做)

- 前端可视化流程(当前是原生 HTML,可替换 React)
- 更多 HTML 模板(当前 11 种原语)
- Prompt 分建筑类型专项调优
- 案例库扩充至 100+
- 生产 docker-compose + Nginx 反向代理
- 图像真实效果图生成(超出蓝图范畴)

---

## 命名约定

- `[P0-N]` / `[P1-N]` / `[P2-N]` — 方便在 commit / PR 中引用(如 `fix [P1-4] json 解析`)
- 完成后直接删除该条,不做 ~~strikethrough~~,保持列表清爽
