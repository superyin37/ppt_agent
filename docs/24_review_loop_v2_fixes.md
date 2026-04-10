# 24. Review-Render 回环 v2 修复

> 日期: 2026-04-07
> 前置: docs/23_review_render_loop_fix.md
> 状态: 待实施

## 背景

docs/23 完成了 Celery 链路的 review->render 回环接线，但遗留了三类问题：

1. HTML 模式（v3）在 Celery review 链路中会崩溃
2. LLM 调用失败时审查静默通过
3. HTML 模式下回环能跑通但空转（body_html 没变，渲染结果每轮完全一样）

## 问题详解

### Bug 1+2: HTML 模式 review 崩溃 + spec 被覆盖

位置: tasks/review_tasks.py `_review_one_slide` + review 结果写回

**崩溃原因:**
```python
# review_tasks.py:176
spec = LayoutSpec.model_validate(slide.spec_json)
```
HTML 模式的 spec_json 结构:
```json
{"html_mode": true, "body_html": "<div>...</div>", "slide_no": 1, ...}
```
没有 `primitive` 和 `region_bindings` 字段，LayoutSpec.model_validate() 直接抛异常。
slide 被标 FAILED + escalated，项目卡死在 REVIEWING 状态。

**覆盖原因:**
```python
# review_tasks.py:98, 105
slide.spec_json = repaired_spec.model_dump(mode="json")
```
即使构造了 fallback_spec 过 review，写回时会把原始 body_html 替换为 LayoutSpec JSON，丢失 HTML 内容。

**修复方案:**

`_review_one_slide` 检测 html_mode，构造 fallback_spec 送审:
```python
async def _review_one_slide(slide, brief_dict, layers):
    spec_json = slide.spec_json or {}
    is_html_mode = spec_json.get("html_mode", False)

    if is_html_mode:
        # HTML 模式: 构造 fallback spec 做 rule/semantic check
        from schema.visual_theme import SingleColumnLayout, ContentBlock, RegionBinding
        spec = LayoutSpec(
            slide_no=slide.slide_no or 0,
            primitive=SingleColumnLayout(...),
            region_bindings=[RegionBinding(region_id="content", blocks=[
                ContentBlock(block_id="title", content_type="heading",
                             content=spec_json.get("title", slide.title or "")),
            ])],
            ...
        )
    else:
        spec = LayoutSpec.model_validate(spec_json)

    screenshot_url = slide.screenshot_url if "vision" in layers else None
    repaired_spec, report = await review_slide(...)
    return repaired_spec, report, is_html_mode
```

Review 结果写回时区分模式:
```python
if is_html_mode:
    # 不覆盖 spec_json，保留原始 body_html
    pass
else:
    slide.spec_json = repaired_spec.model_dump(mode="json")
```

### Bug 3: LLM 失败 = 审查静默通过

位置: tool/review/semantic_check.py, agent/critic.py

**问题:**
```python
# semantic_check.py:131-133
except Exception as fallback_exc:
    return SemanticCheckOutput()  # 空 issues

# critic.py:131-132
except Exception as exc:
    logger.warning(...)  # vision 也返回空 []
```
空 issues -> `_evaluate([])` -> `(PASS, PASS)` -> slide 被标为审查通过。

"审查未执行"不等于"审查通过"。

**修复方案:**

semantic_check 失败时返回一条 warning issue:
```python
except Exception as exc:
    logger.warning(...)
    return SemanticCheckOutput(issues=[
        ReviewIssue(
            issue_id=f"SEMANTIC_SKIPPED_{spec.slide_no}",
            rule_code="SEMANTIC_SKIPPED",
            layer="semantic",
            severity=ReviewSeverity.P2,
            message=f"Semantic check skipped: {exc}",
            auto_fixable=False,
        )
    ])
```

vision review 同理:
```python
except Exception as exc:
    logger.warning(...)
    return [ReviewIssue(
        issue_id=f"VISION_SKIPPED_{slide_no}",
        rule_code="VISION_SKIPPED",
        layer="vision",
        severity=ReviewSeverity.P2,
        message=f"Vision review skipped: {exc}",
        auto_fixable=False,
    )]
```

P2 severity 确保:
- 不会触发 ESCALATE_HUMAN（那是 P0 non-fixable）
- 会触发 REPAIR_REQUIRED（当前 _evaluate 对任何 issue 都返回 REPAIR_REQUIRED）
- 但因为 auto_fixable=False，不会生成无意义的 repair action

注意: 这意味着 LLM 不可用时每个 slide 都会走 repair 循环 3 轮。
需要在 _evaluate 中加一个例外: 如果所有 issues 都是 SKIPPED 类型，返回 PASS 而不是 REPAIR_REQUIRED:
```python
def _evaluate(issues):
    if not issues:
        return ReviewSeverity.PASS, ReviewDecision.PASS

    # 全部是 SKIPPED 类型 -> 视为通过（无法审查不等于有问题）
    real_issues = [i for i in issues if not i.rule_code.endswith("_SKIPPED")]
    if not real_issues:
        return ReviewSeverity.P2, ReviewDecision.PASS

    # ... 原有逻辑
```

这样 report 里会记录"审查被跳过"，但不会触发无意义的 repair 循环。

### 问题 4: HTML 模式回环空转

**根因:**
即使 bug 1+2 修好，HTML 模式的回环路径是:
```
review(fallback_spec) -> 发现问题(REPAIR_REQUIRED)
  -> render(读 spec_json.body_html, 和上轮完全一样)
  -> review(同样的 fallback_spec, 同样的问题)
  -> repair_count++ -> 3 轮后强制 PASS
```
每轮消耗 LLM 调用（semantic + vision），但产出完全相同。

**根因分析:**
v2 结构化模式的回环有效是因为: review 修了 spec 里的文本 -> render 用修后的 spec 生成新 HTML -> 截图变了。
v3 HTML 模式无效是因为: body_html 是 LLM 直接输出的完整 HTML，review 的 rule/semantic 修复只作用于 fallback_spec，不影响 body_html。

**解决方案: 在回环中插入 re-compose 步骤**

HTML 模式需要的链路:
```
review -> 发现问题 -> re-compose(issues 作为反馈) -> render -> review
```

具体实现:

#### 4a. composer.py 新增 `recompose_slide_html`

```python
async def recompose_slide_html(
    original_html: str,
    issues: list[dict],
    entry: OutlineSlideEntry,
    theme: VisualTheme,
    brief_dict: dict,
) -> _ComposerHTMLOutput:
    """根据 review feedback 重写 HTML slide。"""
    issues_text = "\n".join(
        f"- [{iss.get('rule_code')}] {iss.get('message')}" for iss in issues
    )
    user_message = (
        f"<original_html>\n{original_html}\n</original_html>\n\n"
        f"<review_issues>\n{issues_text}\n</review_issues>\n\n"
        f"<outline_entry>\n{entry.model_dump_json(indent=2)}\n</outline_entry>\n\n"
        f"请根据审查反馈修改 HTML，修复上述问题。保留整体布局和设计风格，只修正有问题的部分。"
    )
    return await call_llm_with_limit(
        system_prompt=_load_repair_prompt(),  # 专用 repair prompt，不复用 v3
        user_message=user_message,
        output_schema=_ComposerHTMLOutput,
        model=STRONG_MODEL,
        temperature=0.3,
        max_tokens=4000,
    )
```

> **⚠️ 注意: 不复用 v3 composer prompt**
>
> v3 prompt (`composer_system_v3.md`) 是"从零设计"场景，会鼓励 LLM 自由发挥。
> re-compose 需要一个**专用的 repair prompt** (`prompts/composer_repair.md`)，核心要求：
> - 保留原始设计的布局结构、配色方案、装饰元素
> - 只修改 review 指出的具体问题
> - 不要重新设计整页
> - 修改前后的 HTML 结构差异应尽量小
>
> 如果复用 v3 prompt，LLM 大概率会完全重写整页 HTML，引入新问题，导致回环不收敛。

#### 4b. review_tasks.py 回环中对 HTML 模式触发 re-compose

当 slide 是 HTML 模式且 decision=REPAIR_REQUIRED 时:
1. 调用 recompose_slide_html，传入当前 body_html + issues
2. 更新 spec_json 中的 body_html
3. 然后走正常的 render -> review 回环

```python
# review_tasks.py 的 REPAIR_REQUIRED 分支
if is_html_mode and slide.repair_count < MAX_REPAIR_ATTEMPTS:
    # Re-compose HTML with review feedback
    try:
        new_html_output = asyncio.run(
            recompose_slide_html(
                original_html=slide.spec_json.get("body_html", ""),
                issues=[i.model_dump() for i in report.issues],
                entry=...,  # 从 outline 加载
                theme=...,
                brief_dict=brief_dict,
            )
        )
        slide.spec_json = {
            **slide.spec_json,
            "body_html": new_html_output.body_html,
            "asset_refs": new_html_output.asset_refs,
            "content_summary": new_html_output.content_summary,
        }
    except Exception as exc:
        logger.warning("Re-compose failed for slide %s: %s", slide.slide_no, exc)
```

#### 4c. render_tasks.py 不需要改

render 已经从 spec_json.body_html 读取 HTML，re-compose 更新了 body_html 后 render 自然会用新内容。

#### 4d. 考虑: re-compose 需要 outline entry 和 theme

review_tasks 当前没有加载这些数据。需要在 review_slides 中额外加载:
- Outline (取 OutlineSlideEntry)
- VisualTheme
- 这增加了 review task 的复杂度和 DB 查询

**决定: 内联在 review_tasks 中，不新建独立 task。**

re-compose 和 review 是紧密耦合的（需要 issues 数据），拆成独立 Celery task 会增加序列化开销和故障点（issues 需要 JSON 序列化后再传参）。Outline/Theme 的额外 DB 查询成本很低（各一条 query），不值得为此引入 task 间协调的复杂度。

链路变为:
```
review_slides:
  for each slide:
    review -> 发现 REPAIR_REQUIRED
    if html_mode: re-compose(内联, 更新 body_html)
    标记 REPAIR_NEEDED
  commit
  触发 render_slides_task(review_after=True)  # render 仍独立 task（需要 Playwright）
```

#### 4e. Design Advisor 在回环中的定位

design_advisor（doc 23 新增）输出的 `suggestions` 是否也应作为 re-compose 的输入？

**策略: 分层使用**
- **回环中的 review（第 1~2 轮）**: 只用 rule + vision 的 issues 做 re-compose。这些是硬伤（崩溃级布局问题、大面积空白等），修复明确、收敛快。
- **最后一轮（repair_count == MAX - 1 或 PASS）**: 才跑 design_advisor，**只输出评分报告，不触发修改**。

原因:
1. design_advisor 的建议是主观性的（"建议加装饰"、"配色可更丰富"），LLM re-compose 可能误解意图
2. 每轮 re-compose 都跑 design_advisor 会导致成本翻倍（每页多一次 multimodal 调用）
3. 设计改善建议更适合作为"人工审阅参考"，而非自动修复输入

## 实施顺序

| 顺序 | 内容 | 文件 | 复杂度 |
|------|------|------|--------|
| 1 | HTML 模式 review 不崩溃 + spec 不被覆盖 | tasks/review_tasks.py | 低 |
| 2 | LLM 失败不静默通过 | tool/review/semantic_check.py, agent/critic.py | 低 |
| 3 | _evaluate 区分 SKIPPED | agent/critic.py | 低 |
| 4 | recompose_slide_html + 专用 repair prompt | agent/composer.py, prompts/composer_repair.md | 中 |
| 5 | **E2E 脚本补回环** | scripts/material_package_e2e.py | 中 |
| 6 | Celery review_tasks 内联 re-compose | tasks/review_tasks.py | 中 |

步骤 1-3 是 bug 修复，可立即实施。
步骤 4 是新能力（HTML re-compose）。
步骤 5 **紧跟步骤 4**——E2E 是唯一能端到端验证 re-compose 效果的地方。Celery 链路需要 broker 运行，本地调试困难。先在 E2E 中验证 re-compose 输出质量、确认回环收敛后，再接 Celery。
步骤 6 最后做，将已验证的逻辑搬入 Celery task。

## 改动后的完整回环

### v2 结构化模式 (不变)
```
review -> 修 spec 文本 -> render(修后的 spec) -> review -> ... (最多 3 轮)
```

### v3 HTML 模式 (新)
```
review(fallback_spec + vision) -> 发现问题
  -> recompose(body_html + issues -> LLM 修改，内联在 review_tasks 中)
  -> render(新 body_html) -> review -> ... (最多 3 轮)
  -> 最后一轮: 跑 design_advisor，输出评分报告（不触发修改）
```

### LLM 不可用时
```
review -> semantic/vision SKIPPED(P2)
  -> _evaluate: 全部 SKIPPED -> PASS (记录但不阻塞)
  -> READY_FOR_EXPORT
```
