# 11. 审查规则表

> 最后更新：2026-04-10
>
> 审查由 Critic Agent（`agent/critic.py`）编排，包含三层审查：
> 规则审查（无 LLM）→ 语义审查（文本 LLM）→ 视觉审查（多模态 LLM，可选）+ 设计顾问（可选）。

---

## 11.1 规则审查（第一层，`tool/review/layout_lint.py`）

无 LLM，纯规则检查。支持 `LayoutSpec`（新）和 `SlideSpec`（旧）两种输入。

### 常量阈值

```python
MAX_TEXT_CHARS     = 300    # 正文类 block 最大字符数
MAX_HEADING_CHARS  = 40     # heading block 最大字符数
MAX_TITLE_CHARS    = 25     # 页面标题最大字符数
MAX_BULLET_POINTS  = 5      # bullet-list 最大条目数
MAX_IMAGE_BLOCKS   = 4      # 单页最大视觉 block 数
```

### 规则表

| 规则 ID | 规则码 | 检查逻辑 | 严重级别 | 自动修复 |
|--------|-------|---------|---------|---------|
| R001 | TEXT_OVERFLOW | heading block 字符数 > MAX_HEADING_CHARS | P1 | ✅ truncate_text |
| R001b | TEXT_OVERFLOW | body-text / subheading / quote / caption / label 字符数 ≥ MAX_TEXT_CHARS | P1 | ✅ truncate_text |
| R002 | BULLET_OVERFLOW | bullet-list 条目数 > MAX_BULLET_POINTS | P1 | ✅ truncate_bullets |
| R003 | MISSING_REQUIRED_BLOCK | **旧 SlideSpec**：模板必需 block 缺失（如 cover-hero 无 hero_image） | P0 | ❌ |
| R003 | GRID_UNDERFILLED | **LayoutSpec grid**：实际 block 数 < columns×rows/2 | P2 | ❌ |
| R003 | TIMELINE_UNDERFILLED | **LayoutSpec timeline**：文本 block 数 < node_count | P1 | ❌ |
| R003 | MISSING_REQUIRED_BLOCK | **LayoutSpec full-bleed image**：无 image/chart/map block | P1 | ❌ |
| R005 | IMAGE_COUNT_EXCEEDED | 视觉 block（image/chart/map）> MAX_IMAGE_BLOCKS | P2 | ✅ remove_extra_images |
| R006 | EMPTY_SLIDE | 所有 block 内容为空或 < 5 字 | P0 | ❌ |
| R007 | TITLE_TOO_LONG | 页面标题 > MAX_TITLE_CHARS (25) | P2 | ✅ truncate_title |
| R008 | KEY_MESSAGE_MISSING | key_message 为空 | P2 | ❌ |
| R009 | VISUAL_SOURCE_MISSING | **LayoutSpec** 视觉 block 有内容但无 source_refs | P2 | ❌ |
| R010 | HEADING_MISSING | **LayoutSpec** 无 heading/subheading block | P2 | ❌ |
| R012 | NO_REGION_BINDINGS | spec 无内容区域（region_bindings 或 blocks 为空） | P0 | ❌ |
| R015 | EXCESSIVE_DENSITY | 单页总文本字符数 > MAX_TEXT_CHARS × 3 (900) | P1 | ❌ |

### block 类型映射（旧 → 新）

```python
TEXT_TYPES  = {"body-text", "subheading", "quote", "caption", "label", "text"}
IMAGE_TYPES = {"image", "chart", "map"}

# 旧 block_type → 新 content_type 映射
legacy_map = {"text": "body-text", "bullet": "bullet-list", "kpi": "kpi-value"}
```

---

## 11.2 语义审查（第二层，`tool/review/semantic_check.py`）

使用 LLM（优先 CRITIC_MODEL，回退 FAST_MODEL）检查内容一致性。

### 检查规则

| 规则码 | 检查逻辑 | 严重级别 | 自动修复 |
|-------|---------|---------|---------|
| S001 | METRIC_INCONSISTENCY — 页面数值（面积/容积率）与 ProjectBrief 不符 | P0 | ❌ |
| S004 | UNSUPPORTED_CLAIM — 文字中出现无数据支撑的强断言 | P2 | ❌ |
| S005 | STYLE_TERM_WRONG — 使用了与 style_preferences 相悖的描述词 | P2 | ❌ |
| S006 | MISSING_KEY_MESSAGE_SUPPORT — key_message 在 blocks 中无对应支撑内容 | P1 | ❌ |
| S007 | CLIENT_NAME_WRONG — 甲方名称拼写错误 | P0 | ✅ replace_client_name |

### 实现细节

```python
# 输入构造
slide_summary = {
    "slide_no", "title", "section", "primitive_type",
    "key_message", "blocks_preview"   # 每个 block 内容截取前 200 字
}
brief_summary = {
    "building_type", "client_name", "style_preferences",
    "gross_floor_area", "far"
}

# LLM 调用
result = await call_llm_with_limit(
    system_prompt=SEMANTIC_SYSTEM_PROMPT,
    user_message=user_msg,
    output_schema=_SemanticOutput,
    model=CRITIC_MODEL,           # 失败时回退 FAST_MODEL
    temperature=0.1,
    max_tokens=512,
)
```

### 容错策略

- LLM 调用失败 → 返回 `SEMANTIC_SKIPPED` P2 issue，不阻断流程
- CRITIC_MODEL 无效（"not a valid model id"）→ 自动重试 FAST_MODEL
- FAST_MODEL 也失败 → 记录跳过

---

## 11.3 视觉审查（第三层，`agent/critic.py._vision_review()`）

使用多模态 LLM（CRITIC_MODEL）对渲染截图进行视觉质量检查。

| 规则码 | 检查描述 | 严重级别 |
|-------|---------|---------|
| V001 | VISUAL_CLUTTER — 页面元素密集，视觉压迫感强 | P2 |
| V002 | IMAGE_BLURRY — 图片模糊或分辨率不足 | P1 |
| V004 | TEXT_ON_BUSY_BG — 文字叠加在复杂背景上，可读性差 | P1 |
| V007 | BLANK_AREA_WASTE — 页面存在大片空白区域 | P2 |

### 截图处理

`_resolve_image_url()` 支持三种输入：
- `data:` 前缀 → base64 直接使用
- `http://` / `https://` → URL 直接使用
- 本地路径 → 读取文件转 base64 data URL（搜索 `tmp/e2e_output/slides/`）

### 容错策略

- LLM 失败 → 返回 `VISION_SKIPPED` P2 issue，不阻断流程
- CRITIC_MODEL 无效 → 自动重试 FAST_MODEL
- 截图文件不存在 → 传递原始 URL（可能导致 LLM 失败）

---

## 11.4 设计顾问（可选，`agent/critic.py._design_review()`）

通过 `design_advisor=True` 启用，使用 `prompts/vision_design_advisor.md` 提示词。

### 评分维度（DesignDimension）

由 LLM 返回每个维度的评分（0-10）和评语。

### 输出结构

```python
DesignAdvice(
    slide_no: int,
    dimensions: list[DesignDimension],    # [{dimension, score, comment}]
    overall_score: float,                  # 各维度平均分
    grade: str,                           # A(≥8) / B(≥6) / C(≥4) / D(<4)
    suggestions: list[DesignSuggestion],  # [{code, category, severity, message, css_hint, target_selector}]
    one_liner: str,                       # 一句话总评
)
```

---

## 11.5 修复执行器（`tool/review/repair_plan.py`）

### 可自动修复的动作

```python
AUTO_ACTIONS = {
    "truncate_text",          # 截断文本至 MAX_TEXT_CHARS
    "truncate_bullets",       # 截断 bullet-list 至 MAX_BULLET_POINTS
    "truncate_title",         # 截断标题至 MAX_HEADING_CHARS + "…"
    "remove_extra_images",    # 移除多余视觉 block
    "fill_footer_defaults",   # 页脚默认值（委托调用方）
    "replace_client_name",    # 替换甲方名称（S007 语义修复）
}
```

### 修复流程

```
layout_lint() 返回 issues
    ↓
build_repair_plan_from_issues(issues) → RepairAction 列表
    ↓
execute_repair(spec, report) → (repaired_spec, logs)
    ↓
每个 auto_fixable 动作逐一应用到 spec（LayoutSpec 或 SlideSpec）
非 auto 动作记录为 "skip (manual)"
```

`execute_repair()` 支持 LayoutSpec 和 SlideSpec 两种格式：
- **LayoutSpec**：遍历 `region_bindings[].blocks[]` 查找目标 block
- **SlideSpec**：遍历 `blocks[]` 查找目标 block

---

## 11.6 Critic Agent 整体编排

```python
# agent/critic.py
async def review_slide(
    spec: LayoutSpec,
    brief: dict,
    layers: list[str] = ["rule", "semantic"],   # 可选 "vision"
    screenshot_url: str = None,
    design_advisor: bool = False,
    page_type: str = "content",
    content_summary: str = "",
    theme_colors: dict = None,
) -> tuple[LayoutSpec, ReviewReport]:
```

**执行顺序**：

1. **Rule 层** → `layout_lint(spec)` → 自动修复可修 issue → 更新 spec
2. **Semantic 层** → `semantic_check(spec, brief)` → 自动修复 S007 → 更新 spec
3. **Vision 层**（需 screenshot_url）→ `_vision_review(url, slide_no)` → 记录 issue
4. **Design Advisor**（需 screenshot_url + design_advisor=True）→ `_design_review(...)` → DesignAdvice

### 最终裁决逻辑（`_evaluate()`）

```
无 issue             → PASS
仅 SKIPPED issue     → P2 + PASS（跳过不等于有问题）
有不可修 P0          → P0 + ESCALATE_HUMAN
有 P0 或 P1          → REPAIR_REQUIRED
仅 P2               → REPAIR_REQUIRED
```

### ReviewReport 输出

```python
ReviewReport(
    target_type="slide",
    target_id=project_id,
    review_layer="rule,semantic,vision",   # 已执行的层
    severity=ReviewSeverity,
    issues=all_issues[:5],                  # 最多保留 5 条
    final_decision=ReviewDecision,          # PASS / REPAIR_REQUIRED / ESCALATE_HUMAN
    repair_plan=all_repairs,
    design_advice=DesignAdvice | None,
)
```
