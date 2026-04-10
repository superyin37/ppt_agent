# Session Handoff - 2026-04-05

## 1. Purpose

This document is a handoff for the current material-package driven PPT pipeline work.
It is intended to let a new chat/session quickly understand:

- what has already been implemented
- what was verified end-to-end
- which problems were found and fixed
- what still needs to be done next

This handoff is focused on the new `MaterialPackage -> BriefDoc -> Outline -> Binding -> Compose -> Render -> Review` pipeline.

## 2. Current Status

The new material-package mainline is now implemented and runnable.

Current state:

- local material package ingest is implemented
- material normalization and derived asset generation are implemented
- `BriefDoc -> Outline -> Binding -> Compose -> Render -> Review` is wired up
- the e2e validation script can now output:
  - per-slide HTML
  - per-slide PNG screenshots
  - a full-deck PDF
- real-browser screenshot generation has been validated
- real-LLM generation has been validated

Important boundary:

- upstream "mobile input -> auto-produce material package" is still out of scope
- first-phase validation target is a local package such as `test_material/project1`
- `.pptx` is still not the required output for phase 1; PDF is the full-deck review artifact

## 3. Major Implementation Completed

### 3.1 Material Package Data Layer

Added core data models:

- `db/models/material_package.py`
- `db/models/material_item.py`
- `db/models/slide_material_binding.py`

Extended existing models to carry package/binding/source information:

- `db/models/asset.py`
- `db/models/brief_doc.py`
- `db/models/outline.py`
- `db/models/slide.py`

Migration added:

- `alembic/versions/004_material_package_pipeline.py`

### 3.2 Schema and Blueprint Changes

Added/updated schema support for the new pipeline:

- `schema/material_package.py`
- `schema/page_slot.py`
- `schema/asset.py`
- `schema/outline.py`
- `schema/slide.py`
- `schema/visual_theme.py`

`PPT_BLUEPRINT` now works with structured input requirements rather than only loose strings.

### 3.3 Material Package Processing

Added material-package processing helpers:

- `tool/material_pipeline.py`
- `tool/material_resolver.py`

These are responsible for:

- ingesting a local directory such as `test_material/project1`
- normalizing files into `MaterialItem`
- building `manifest_json` / `summary_json`
- generating derived `Asset` records

### 3.4 New Binding Layer

Added:

- `agent/material_binding.py`

This resolves each outline slide into concrete package-backed material bindings before compose.

### 3.5 Agent Updates

Updated:

- `agent/brief_doc.py`
- `agent/outline.py`
- `agent/composer.py`
- `agent/critic.py`

Key outcomes:

- `BriefDoc` consumes material package context
- `Outline` consumes package + blueprint and writes coverage/binding hints
- `Composer` consumes page-level binding, not shallow project-wide asset summaries
- `Critic` supports the newer layout flow and now has safer model fallback behavior

### 3.6 Render / Review Updates

Updated:

- `render/engine.py`
- `render/exporter.py`
- `tool/review/layout_lint.py`
- `tool/review/semantic_check.py`
- `tool/review/repair_plan.py`

Key outcomes:

- chart/table asset handling is improved
- review supports both legacy and new slide/layout structures
- e2e script now exports a full PDF using `render.exporter.compile_pdf()`

### 3.7 API Updates

Updated / added:

- `api/routers/material_packages.py`
- `api/routers/outlines.py`
- `api/routers/slides.py`
- `api/routers/assets.py`
- `main.py`

The new routes support material-package aware operations and new pipeline entry points.

### 3.8 E2E Script

Added:

- `scripts/material_package_e2e.py`

This script is now the main validation entry for local material package testing.

It performs:

1. create project
2. ingest local material package
3. generate `BriefDoc`
4. generate `Outline`
5. confirm outline
6. create slide bindings
7. compose slides
8. render screenshots
9. review slides
10. export full PDF

## 4. Issues Found and Fixed During This Session

### 4.1 Playwright / Browser Screenshot Issue

Observed symptom:

- `WinError 5` when running browser-based screenshot generation inside the Codex sandbox

Root cause:

- environment/sandbox restrictions around browser subprocess IPC / temp access

What was verified:

- Playwright itself is fine outside the restricted sandbox
- Chrome headless and Playwright both generated real PNGs when allowed to run with broader permissions

Current conclusion:

- no code-level Playwright bug was found
- the issue was environmental, not pipeline logic

### 4.2 E2E Output Was Only Per-Slide PNG

Observed issue:

- earlier e2e output was only page-by-page screenshots

Fix:

- `scripts/material_package_e2e.py` was updated to also export a full `deck.pdf`

Current behavior:

- every run now produces both per-slide review artifacts and a full-deck PDF

### 4.3 Outline Page Count Mismatch

Observed issue:

- in a real run, outline metadata said `total_pages=42`
- actual outline slide list, bindings, compose, and render were all `41`

Root cause:

- `agent/outline.py` trusted the LLM `total_pages` field directly instead of reconciling it with actual generated slide assignments

Fix:

- `agent/outline.py` now sets `total_pages = len(slides)`
- if the LLM count differs from actual generated slides, a warning is logged and actual count wins

### 4.4 Critic Model Invalid

Observed issue:

- review/semantic check used `openai/gpt-4.5`
- OpenRouter returned `not a valid model ID`

Fix:

- critic default model was changed away from the invalid ID
- semantic and vision review now both support invalid-model fallback to the fast model

Files involved:

- `tool/review/semantic_check.py`
- `agent/critic.py`
- `config/settings.py`
- `.env`

### 4.5 Requested Model Changes Applied

Per latest request, the model split is now:

- `BriefDoc`: strong model
- `Outline`: strong model
- `Composer`: strong model
- `Review`: `google/gemini-3.1-pro-preview`

Files changed:

- `agent/composer.py`
- `config/settings.py`
- `.env`

## 5. Validation History

### 5.1 Mock-LLM + Real Screenshot Full Run

Run output:

- `test_output/material_package_e2e/run_20260405T074335Z`

This verified:

- full 41-slide chain
- real screenshots
- material package ingest path

But generation content still used fallback LLM behavior because it was intentionally mock mode.

### 5.2 First Full Real-LLM Run

Run output:

- `test_output/material_package_e2e_real/run_20260405T075719Z`

This verified:

- real `BriefDoc`
- real `Outline`
- real `Composer`
- real screenshots
- full exported PDF

Problems found in that run:

- outline page count mismatch (`42` vs actual `41`)
- review model invalid (`openai/gpt-4.5`)

Artifacts:

- PDF: `test_output/material_package_e2e_real/run_20260405T075719Z/deck.pdf`

### 5.3 Fix Verification Run

Run output:

- `test_output/material_package_fix_check/run_20260405T084533Z`

This was a 2-slide real-LLM verification after:

- page-count fix
- critic fallback fix

Verified:

- `outline_total_pages = 2`
- `outline_slides_len = 2`
- `rendered_slides_len = 2`
- PDF output was produced

### 5.4 Model Switch Verification Run

Run output:

- `test_output/material_package_model_switch_check/run_20260405T092149Z`

This was a 1-slide real-LLM verification after:

- switching `Composer` to `STRONG_MODEL`
- switching `review` to `google/gemini-3.1-pro-preview`

Verified from logs:

- `Composer` used `claude-opus-4-6`
- `review` used `google/gemini-3.1-pro-preview`

## 6. Current Model Configuration

As of the end of this session:

- `LLM_STRONG_MODEL=claude-opus-4-6`
- `LLM_FAST_MODEL=claude-sonnet-4-6`
- `LLM_CRITIC_MODEL=google/gemini-3.1-pro-preview`

Actual stage mapping:

- `BriefDoc` -> `STRONG_MODEL`
- `Outline` -> `STRONG_MODEL`
- `Composer` -> `STRONG_MODEL`
- `semantic review` -> `CRITIC_MODEL`
- `vision review` -> `CRITIC_MODEL`

Important implementation detail:

- model names without `/` are normalized to `anthropic/<name>`
- full provider-qualified names such as `google/gemini-3.1-pro-preview` are passed through unchanged

## 7. Tests Added / Verified

Verified tests:

- `tests/unit/test_critic.py` -> passed
- `tests/integration/test_project_flow.py` relevant outline tests -> passed when `DATABASE_URL` is overridden to `localhost`

New or updated test coverage includes:

- outline page count uses actual generated slide count
- semantic check retries with fast model when critic model is invalid

## 8. Important Operational Notes

### 8.1 Host vs Container Database Address

`.env` currently uses:

- `DATABASE_URL=postgresql://user:password@db:5432/ppt_agent`
- `REDIS_URL=redis://redis:6379/0`

That works when the app runs inside Docker networking.

When running scripts from the host terminal, override to:

```powershell
$env:DATABASE_URL='postgresql://user:password@localhost:5432/ppt_agent'
$env:REDIS_URL='redis://localhost:6379/0'
```

### 8.2 Docker Requirement

Before local host-side validation, ensure:

```powershell
docker compose up db redis -d
```

### 8.3 Browser Rendering Note

Inside the Codex sandbox, browser screenshot generation needed elevated execution permissions.

For normal local terminal runs on the developer machine, this should not be a pipeline logic blocker, but it was a constraint for this chat environment.

### 8.4 Secrets

Do not copy live keys into docs or commits.

This handoff intentionally avoids reproducing any secret values from `.env`.

## 9. Recommended Next Step

The highest-value next action is:

1. run a full 41-page real validation with the latest model split
2. inspect the resulting full PDF
3. inspect review results and layout fallback behavior

Reason:

- the full real run was already done once, but before the latest requested model switch
- after the latest model change, only a 1-slide real verification has been completed

## 10. Commands for the Next Session

### 10.1 Full Real Validation

```powershell
$env:DATABASE_URL='postgresql://user:password@localhost:5432/ppt_agent'
$env:REDIS_URL='redis://localhost:6379/0'
.\.venv\Scripts\python.exe scripts\material_package_e2e.py test_material/project1 --real-llm --output-dir test_output/material_package_full_latest
```

### 10.2 Quick Smoke Validation

```powershell
$env:DATABASE_URL='postgresql://user:password@localhost:5432/ppt_agent'
$env:REDIS_URL='redis://localhost:6379/0'
.\.venv\Scripts\python.exe scripts\material_package_e2e.py test_material/project1 --real-llm --output-dir test_output/material_package_smoke --max-slides 2
```

### 10.3 Relevant Tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_critic.py -q
```

```powershell
$env:DATABASE_URL='postgresql://user:password@localhost:5432/ppt_agent'
.\.venv\Scripts\python.exe -m pytest tests\integration\test_project_flow.py -q -k "outline_generation_with_mock_llm or outline_generation_uses_actual_assignment_count"
```

## 11. Key Files to Read First in a New Session

If continuing this work in a new session, read these first:

- `docs/20_material_package_integration.md`
- `docs/21_material_package_implementation_appendix.md`
- `docs/22_session_handoff_20260405.md`
- `scripts/material_package_e2e.py`
- `agent/outline.py`
- `agent/composer.py`
- `tool/review/semantic_check.py`
- `agent/critic.py`

## 12. Suggested Follow-up Work After the Next Full Run

If the next full real run succeeds, the next likely engineering tasks are:

- inspect `Composer` schema mismatch warnings and reduce fallback frequency
- improve `VisualTheme` generation or loading so decks are not always using the default theme
- evaluate whether PDF export should become an API-level first-class artifact
- decide whether phase 2 should start on package diff / incremental regeneration

## 13. Visual Theme & Pipeline Gap Fix (2026-04-05 Session 2)

### 13.1 Problem

新 MaterialPackage 管线绕过了旧管线中 `confirm_references` 触发的 `generate_visual_theme()`，
导致所有项目都用 `_default_theme()` 硬编码蓝黄配色。同时 `ensure_project_brief_from_package()`
产出的 stub brief 缺少 city/province/building_type 等关键字段。

审计还发现 vision 审查层被硬编码排除、`VisualThemeInput` 缺少 `project_id` 字段等问题。

### 13.2 Changes Made

#### P0-1: `tool/material_pipeline.py` — 改进 brief 提取

`ensure_project_brief_from_package()` 新增：
- 从 `brief.design_outline` 类型素材的 text_content 中解析城市、区县、building_type
- 扩展 building_type 关键词检测（公厕→public, 办公→office, 住宅→residential 等）
- 提取 style_preferences 关键词（而非硬编码 `["modern", "minimal"]`）
- 填充 city / province / district / site_address 字段

#### P0-2: `schema/visual_theme.py` — 修复 VisualThemeInput

- 添加 `project_id: UUID` 字段（`_build_user_message()` 引用了 `inp.project_id`）

#### P0-3: `agent/visual_theme.py` — 新增素材包驱动的主题生成入口

- 新增 `build_theme_input_from_package()` 辅助函数
- 从素材包的 case analysis text 提取 `dominant_styles` / `dominant_features`
- 从 brief 提取 building_type / style_preferences / narrative_hint

#### P0-4: `scripts/material_package_e2e.py` — 接入 visual theme 步骤

- 在 outline 之前加入 `generate_visual_theme()` 调用
- 使用 `build_theme_input_from_package()` 构建输入

#### P1: `scripts/material_package_e2e.py` — 启用 vision 审查

- 审查层改为 `["rule", "semantic", "vision"]`
- 传入 `screenshot_url` 参数

### 13.3 Files Changed

- `tool/material_pipeline.py`
- `schema/visual_theme.py`
- `agent/visual_theme.py`
- `scripts/material_package_e2e.py`

## 14. Composer v3 — HTML Direct Output Mode (2026-04-05 Session 2)

### 14.1 Motivation

After fixing visual theme generation, the PPT output now gets project-specific colors,
but the layout/decoration remains rigid because:

- Composer prompt limits covers to 2 of 11 primitives; LLM always picks `full-bleed`
- Render engine `_render_*()` functions output fixed HTML templates
- No decorative elements beyond a single `accent-element` (40×4px bar)
- `CoverStyle` fields are dead code (never read by renderer or composer)

The root cause is the LayoutSpec intermediate layer constraining LLM creative freedom.

### 14.2 Architecture Change

```
Previously: Composer LLM → LayoutSpec JSON → render_slide_html() → Fixed HTML
Now:        Composer LLM → body_html + metadata → sanitize + wrap with theme CSS → HTML
```

Both modes coexist — E2E script accepts `--composer-mode html|structured`.

### 14.3 Implementation

#### Phase 1: `render/html_sanitizer.py` — HTML safety layer
- Strips `<script>`, event handlers (`onclick` etc), `javascript:` URLs, `@import`
- Preserves `<style>`, inline styles, SVG, all visual HTML elements

#### Phase 2: `prompts/composer_system_v3.md` — HTML mode system prompt
- LLM outputs `body_html` using CSS variables from theme
- Encourages SVG decorations, CSS gradients, geometric shapes
- Explicit 1920×1080 canvas constraint
- Lists available CSS variables (color, typography, spacing)

#### Phase 3: `agent/composer.py` — Dual mode compose
- `ComposerMode.STRUCTURED` = existing LayoutSpec pipeline (unchanged)
- `ComposerMode.HTML` = new HTML direct output pipeline
- `compose_slide()` gains `mode` parameter
- New `_ComposerHTMLOutput` schema: `body_html`, `asset_refs`, `content_summary`
- `render_slide_html()` gains HTML passthrough branch

#### Phase 4: `scripts/material_package_e2e.py` — `--composer-mode` flag
- Default: `html`
- `--composer-mode structured` to use legacy pipeline

### 14.4 Key Design Decisions

- LLM outputs only `<body>` content; theme CSS injected by engine
- LLM must use `var(--color-primary)` etc for theme consistency
- `src="asset:xxx"` references resolved by existing asset resolver
- `max_tokens` raised from 1500 to 4000 for HTML output
- `Slide.spec_json` now stores `{"mode": "html", "body_html": ..., ...}`
- Vision review becomes primary quality gate in HTML mode

### 14.5 Files Changed

- `render/html_sanitizer.py` (new)
- `prompts/composer_system_v3.md` (new)
- `agent/composer.py`
- `render/engine.py`
- `scripts/material_package_e2e.py`
