---
name: ADR-003 — Composer 双模式共存
description: Composer 引入 HTML 直出模式(v3),与 LayoutSpec 结构化模式(v2)共存
status: Accepted
date: 2026-04-05
owner: superxiaoyin
---

# ADR-003:Composer 双模式共存(v2 结构化 + v3 HTML 直出)

## Context

Composer v2 管线:`LLM → LayoutSpec JSON → render_slide_html() → 固定 HTML 模板`

修复视觉主题后,PPT 输出拿到了项目专属配色,但**布局/装饰依然死板**,根因:

- Composer prompt 限制封面只能用 2 / 11 种原语,LLM 永远选 `full-bleed`
- `render/engine.py` 的 `_render_*()` 输出固定模板
- 装饰元素只有一个 `accent-element`(40×4px bar)
- `CoverStyle` 字段是死代码(渲染器和 composer 都不读)

**根因**:LayoutSpec 中间层约束了 LLM 的创造力。

## Options Considered

| 方案 | 评估 |
|------|-----|
| A:扩充 LayoutSpec 字段,增加装饰自由度 | 永远追不上需求,每个新装饰都要加字段 |
| B:完全抛弃 LayoutSpec,LLM 直出 HTML | 失去结构化审查能力,难回退 |
| **C:双模式共存(选)** | 保留 v2 作为结构化保障;引入 v3 HTML 直出给设计自由度 |

## Decision

**选 C**:

```
v2: Composer LLM → LayoutSpec JSON → render_slide_html() → 固定 HTML 模板
v3: Composer LLM → body_html + metadata → sanitize + wrap with theme CSS → HTML
```

E2E 脚本通过 `--composer-mode html|structured` 切换,默认 `html`。

## Consequences

### 好处
- 设计自由度大幅提升(SVG 装饰、CSS 渐变、几何形状)
- v2 仍可用,作为 fallback 或严格结构化场景
- 风险可控:HTML 安全层 `html_sanitizer.py` 过滤危险元素

### 代价
- 两套 prompt + 两套渲染分支,维护负担 × 2
- HTML 模式下传统 rule lint 失效(见 [ADR-004](ADR-004-html-mode-vision-only.md))
- LLM token 消耗增加(max_tokens 从 1500 → 4000)

### 关键约束
- LLM 只能输出 `<body>` 内部,theme CSS 由引擎注入
- LLM 必须用 `var(--color-primary)` 等 CSS 变量保证主题一致性
- `src="asset:xxx"` 引用由现有 asset resolver 解析

### 新增文件
- `render/html_sanitizer.py`
- `prompts/composer_system_v3.md`
- `prompts/composer_repair.md`(配合 review 回环,见 [postmortems/2026-04-07](../postmortems/2026-04-07-review-loop-v2.md))

### 来源
- [../../22_session_handoff_20260405.md](../../22_session_handoff_20260405.md) Section 14
