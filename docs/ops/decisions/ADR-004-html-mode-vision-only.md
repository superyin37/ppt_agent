---
name: ADR-004 — HTML 模式审查只用 vision 层
description: Composer v3 HTML 模式跳过 rule lint 和 semantic check,仅保留 vision review
status: Accepted
date: 2026-04-07
owner: superxiaoyin
---

# ADR-004:HTML 模式审查只用 vision 层

## Context

Composer v3 HTML 模式的 spec_json 结构为 `{"html_mode": true, "body_html": "...", ...}`,没有 `primitive` 和 `region_bindings` 字段。

为了让 rule lint 和 semantic check 仍能跑,曾构造了 **fallback_spec** 作为假 LayoutSpec 送审。实际测试中发现严重问题(见 [postmortems/2026-04-07-review-loop-v2.md](../postmortems/2026-04-07-review-loop-v2.md) Bug 5):

- fallback_spec 只有 1 个 title block,如果标题 <5 字符就触发 **R006 EMPTY_SLIDE (P0)** → ESCALATE_HUMAN
- fallback_spec 没填 key_message → 每轮都触发 **R008 KEY_MESSAGE_MISSING (P2)** → 持续 REPAIR_REQUIRED
- 这两个 issue 来自 fallback_spec 的结构性缺陷,`recompose_slide_html()` 无论怎么改 HTML 都无法消除
- **结果**:回环永远无法收敛,3 slide 全部走满 2 轮仍 ESCALATE_HUMAN,但实际 HTML 内容完好(4680~5783 字符)

## Options Considered

| 方案 | 评估 |
|------|-----|
| **A:HTML 模式跳过 rule lint,只用 vision review**(选) | 简洁,符合"rule lint 是为 LayoutSpec 设计的"本质 |
| B:让 fallback_spec 更完整(从 HTML 反向提取内容填入 blocks) | 本质是"伪造数据骗过检查",且下一个新 rule 可能又需要更多假数据,治标不治本 |

## Decision

**选 A**:HTML 模式的审查层只保留 vision,移除 rule 和 semantic。

```python
# E2E 脚本
layers = ["vision"]  # 原: ["rule", "vision"]

# Celery task
effective_layers = ["vision"] if is_html_mode else layers
```

## Consequences

### 好处
- 回环可以正常收敛
- 审查语义清晰:rule lint 对应 LayoutSpec 结构化模式,vision review 对应 HTML 自由模式
- 不需要维护 fallback_spec 的"假数据"

### 代价
- HTML 模式完全依赖 vision review 的质量
- 如果 vision LLM 不可用,slide 只能走 SKIPPED(但已有过滤机制保证不误判 PASS)

### 前提条件
- vision review 模型必须稳定可用(当前 `google/gemini-3.1-pro-preview`)
- 如果未来 vision 调用失败率上升,需要重新评估是否需要 rule lint 作为兜底

### 修改文件
- `scripts/material_package_e2e.py`
- `tasks/review_tasks.py`

### 来源
- [postmortems/2026-04-07-review-loop-v2.md](../postmortems/2026-04-07-review-loop-v2.md) Bug 5
