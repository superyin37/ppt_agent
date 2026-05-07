---
name: 项目当前状态
description: 当前能跑什么/不能跑什么/本周焦点/阻塞点 — 覆写式,只保留最新真相
last_updated: 2026-05-06
owner: superxiaoyin
---

# 项目当前状态

> **更新规则:覆写,不追加**。历史进度看 [../../DEVLOG.md](../../DEVLOG.md) 和 [handoffs/](handoffs/)。

---

## 今日一句话状态

Template Pack 渲染管线已完成 **project1 / project2 / project3** 三套素材的 real-LLM + RunningHub + template mode 全量验证。2026-05-06 跨素材包验证结论：project2 产出 40 页、project3 产出 39 页，两者均 `concept generated=9/placeholders=0`、`template_quality critical=0`、`deck.pdf` 成功导出；经济图表和场地四至等 project2/project3 命名素材已修正映射并进入 slide。剩余主问题已经从“链路能否跑通”转为 P1 视觉质量：`V007` 空白过多、复杂图上的文字可读性、`competitor-web` HTML 兜底。

验证产物：

```text
D:\projects\PPT_Agent\tmp\template_full_real_verify\run_20260504T094923Z
D:\projects\PPT_Agent\tmp\template_project2_real_verify\run_20260506T085641Z
D:\projects\PPT_Agent\tmp\template_project3_real_verify\run_20260506T091205Z
```

---

## 能跑什么 ✅

| 能力 | 状态 | 验证方式 |
|------|------|---------|
| 素材包本地摄入 | ✅ | `scripts/material_package_e2e.py` step 1-2 |
| BriefDoc 生成 | ✅ | full real E2E 2026-05-04 |
| Outline 生成 | ✅ | project1=41 pages,project2=40 pages,project3=39 pages |
| Material Binding(逐页素材绑定) | ✅ | E2E 中 54 items ingested 后正常绑定 |
| Visual Theme 生成 | ✅ | `generate_visual_theme: ok` |
| Composer Template Mode | ✅ | project2=`template=38,html=2`;project3=`template=37,html=2` |
| Composer HTML 模式(v3) | ✅ | `competitor-web` 与少量 template JSON 失败页可兜底为 HTML,PDF 正常导出 |
| Template Jinja 渲染 | ✅ | `render_and_review: ok (41 rendered)` |
| Template Quality Gate | ✅ | `critical_issue_count=0`,无 prompt marker / generic fallback / 重复 image_grid 关键问题 |
| Playwright 批量截图 | ✅ | full E2E 正常产出截图与 review 报告；sandbox 权限问题不影响正常终端运行 |
| PDF 拼装 | ✅ | `export_pdf: ok (deck.pdf)` |
| Review v2 / Vision Review | ✅ | project2=`PASS=11,P2=29`;project3=`PASS=16,P2=23` |
| Concept Render(概念渲染) | ✅ | project2/project3 均 `generated=9`,`placeholders=0` |
| POI chart 物化 | ✅ | `site.poi.table` 可从 XLSX source fallback 解析并生成 chart PNG |
| project2/project3 素材别名映射 | ✅ | `场地四至`、经济图表 PNG、`参考案例N_详情`、`外部道路交通` 均可推断 logical_key 并派生 Asset |
| 单元/集成回归 | ✅ | `tests/unit/test_material_pipeline.py` 7 passed；targeted suite `47 passed` |

---

## 不能跑什么 ❌

| 缺口 | 严重度 | 指向 |
|------|-------|------|
| **视觉密度验收**未达成 | P1 | 28 页 P2，主因 `V007` 大面积留白；政策页、内容页、图表页仍显得稀疏 |
| **复杂图片上的文字可读性**不足 | P1 | Slide 31/34/37 的概念大图文字压背景；地图页也有 `V001/V004` |
| **联网搜索**未接入 | P1 | `competitor-web` 不能切到 TABLE 模板，Slide 22 仍是 HTML 模式 |
| **project3 大纲页数不稳定** | P1 | LLM 声明 40 页，但实际 outline 为 39 页；脚本已按实际页数继续生成，需要后续加页数一致性 gate |
| **PPTX 导出**未实现 | P2 | `python-pptx` 已在依赖中,无代码 |
| **真实 OSS 存储**未配置 | P2 | 开发走本地路径 |
| **案例库**仍是占位 | P2 | `scripts/seed_cases.json` 未填真实案例 |
| `tasks/outline_tasks.py` 未串联 `brief_doc` | P2 | 目前 E2E 脚本手动串联 |

---

## 已知数据口径

| 指标 | 值 | 来源 |
|------|-----|-----|
| 最新全量 E2E | **41 页 real-LLM + RunningHub + template mode** | `tmp\template_full_real_verify\run_20260504T094923Z` |
| 模式分布 | **template=40, html=1** | `slides_spec.json` |
| HTML 页 | **Slide 22 competitor-web** | 联网搜索/TABLE 模板未完成，属预期兜底 |
| 概念图 | **9 runninghub + 0 placeholder** | 2026-05-05 strict retry：`generated=9`,`reused=8` |
| Vision review | **PASS=13, P2=28** | `review_reports.json` |
| 关键质量门禁 | **critical_issues=0** | `template_quality_report.json` |
| 最新 targeted 测试 | **47 passed** | composer/template/render/concept order 相关测试 |
| project2 跨素材包 E2E | **40 页; template=38,html=2; concept=9/9; critical=0; PASS=11,P2=29** | `tmp\template_project2_real_verify\run_20260506T085641Z` |
| project3 跨素材包 E2E | **39 页; template=37,html=2; concept=9/9; critical=0; PASS=16,P2=23** | `tmp\template_project3_real_verify\run_20260506T091205Z` |

---

## 本周焦点

- [ ] **模板视觉密度二轮优化**：优先处理 `policy_list`、`content_bullets`、`chart`、`image_grid` 的空白率，目标是明显降低 `V007` P2 数。
- [ ] **概念页可读性修复**：`concept_scheme` 文字层需要遮罩、固定信息区或背景渐变，避免文字直接压复杂效果图。
- [ ] **地图页可读性策略**：对复杂地图/交通图优先做裁切、暗化、标注遮罩或图文分区。
- [ ] **`competitor-web` 模板化**：接入 web search 结构化结果后切回 `TABLE`，减少唯一 HTML 页。
- [ ] **Outline 页数一致性 gate**：project3 出现 LLM 声明 40 页、实际 39 页；需要在 outline 阶段决定是补页、重试，还是显式接受变长页数。

## 阻塞点(Blockers)

详见 [DECISIONS_NEEDED.md](DECISIONS_NEEDED.md)。

---

## 运行环境关键约束

- **Windows Celery**必须 `--pool=solo`,生产 Linux 无此问题。
- **Host 运行脚本**需 override `DATABASE_URL=...@localhost:5432/...`，因为 `.env` 里写的是 docker 网络的 `@db:5432`。
- **Playwright sandbox 权限问题**只影响受限环境里的截图/视觉审查步骤；正常终端或已授权命令下，生成、截图、review、PDF 导出都可跑。
- **真实 E2E 会调用外部服务**：用户已允许测试项目素材、项目上下文、大纲/页面生成提示发送到 OpenRouter，且允许场地参考图和概念提示发送到 RunningHub。

---

## 历史状态参考

- Template Pack 渲染 brief 见 [briefs/2026-05-01-template-pack-rendering.md](briefs/2026-05-01-template-pack-rendering.md)
- 2026-04-05 的详细交接见 [handoffs/2026-04-05.md](handoffs/2026-04-05.md)
- 完整开发阶段进度见 [../17_development_progress.md](../17_development_progress.md)(⚠️ 该文档停留在 2026-04-10,之后未更新)
