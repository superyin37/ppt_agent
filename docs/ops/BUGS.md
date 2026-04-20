---
name: Bug 台账
description: 已知 bug 的集中登记表 — 一行一条 bug,便于快速查找"这个问题修过吗"
last_updated: 2026-04-20
owner: superxiaoyin
---

# Bug 台账

> **格式**:一行一 bug。只在条目状态变化时覆写行;不追加版本历史(历史看 git log)。
> **重大 bug 的详细复盘**见 [postmortems/](postmortems/)。

---

## Open(未修复)

| ID | 发现日 | 严重度 | 现象 | 根因假设 | 关联 | Owner |
|----|-------|-------|------|---------|-----|-------|
| BUG-007 | 2026-04-05 | P2 | Semantic Review LLM 返回 JSON 含中文引号导致解析失败 | Prompt 未强制要求转义内引号 | [../../DEVLOG.md:357](../../DEVLOG.md#L357) | 待分配 |
| BUG-008 | 2026-04-05 | P2 | Composer 18 页并发时少数页面解析失败走 fallback | 并发度高 + schema 严格 | [../../DEVLOG.md:360](../../DEVLOG.md#L360) | 待分配 |
| BUG-009 | 2026-04-05 | P3 | `RecommendRequest` body 中需重复传 `project_id`(路径参数已有) | 路径/body 字段冗余 | [../../DEVLOG.md:359](../../DEVLOG.md#L359) | 待分配 |
| BUG-010 | 2026-04-07 | P2 | Bug 5 修复后的 E2E 收敛验证未执行 | 需手动跑一次 smoke | [postmortems/2026-04-07-review-loop-v2.md](postmortems/2026-04-07-review-loop-v2.md) | 待分配 |

---

## Fixed(已修复)

| ID | 修复日 | 严重度 | 现象 | 修复 commit / 文档 |
|----|-------|-------|------|-------------------|
| BUG-001 | 2026-04-05 | P0 | Outline `total_pages=42` 但实际 slide=41,链路数据错位 | `agent/outline.py` 改为 `total_pages = len(slides)` |
| BUG-002 | 2026-04-05 | P0 | Review 调 `openai/gpt-4.5` 被 OpenRouter 拒,失败后静默 PASS | 改 `LLM_CRITIC_MODEL` + semantic/vision 加无效模型 fallback |
| BUG-003 | 2026-04-05 | P1 | 视觉主题生成被 bypass,所有项目都是默认蓝黄配色 | 新增 `build_theme_input_from_package()`,E2E 脚本在 outline 前调用 |
| BUG-004 | 2026-04-07 | P0 | HTML 模式 review 崩溃(`LayoutSpec.model_validate` 对 html_mode spec 抛异常) | [postmortems/2026-04-07-review-loop-v2.md](postmortems/2026-04-07-review-loop-v2.md) Bug 1 |
| BUG-005 | 2026-04-07 | P0 | Review 写回 repaired_spec 覆盖原始 body_html,render 读不到 HTML | [postmortems/2026-04-07-review-loop-v2.md](postmortems/2026-04-07-review-loop-v2.md) Bug 2 |
| BUG-006 | 2026-04-07 | P1 | LLM 失败时返回空 issues → 被 `_evaluate([])` 误判 PASS | 返回 `SEMANTIC_SKIPPED`/`VISION_SKIPPED` + `_evaluate` SKIPPED 过滤 |
| BUG-011 | 2026-04-07 | P1 | HTML 模式 review 回环空转:body_html 不变,review 3 轮无意义 | 新增 `recompose_slide_html()` + `prompts/composer_repair.md` |
| BUG-012 | 2026-04-07 | P1 | fallback_spec 的 R006/R008 phantom issues 导致回环 100% 不收敛 | HTML 模式只保留 vision 层,跳过 rule/semantic |
| BUG-013 | 2026-04-06 | P1 | 旧链路 `/repair` 仅重跑 review,不触发 render,语义与行为不符 | Celery 链补全 review→render 回环,`/repair` 改为 render+review |
| BUG-014 | 历史 | P1 | Alembic 迁移 `JSONB` 默认值 `"'[]'"` 语法错误 | 改为 `sa.text("'[]'")`,影响 8 个字段 |

---

## Wontfix / Deferred

| ID | 严重度 | 现象 | 原因 |
|----|-------|------|-----|
| BUG-ENV-001 | - | Playwright 在 Codex sandbox 内 `WinError 5` | 环境限制,非代码 bug,开发机正常 |
| BUG-ENV-002 | - | Windows Celery prefork 不可用 | 生产用 Linux,Windows 用 `--pool=solo` 绕过 |

---

## ID 分配约定

- 按发现顺序递增,不回收
- P0 = 阻塞核心链路 / P1 = 功能降级 / P2 = 可绕过 / P3 = 瑕疵
- Fixed 后保留在表中便于反查"这个问题以前修过吗"
