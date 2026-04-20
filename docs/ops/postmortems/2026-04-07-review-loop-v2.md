---
name: Review-Render 回环 v2 —— 5 个 bug 联动修复
date: 2026-04-07
severity: P0
status: Resolved
owner: superxiaoyin
---

# Review-Render 回环 v2 —— 5 个 bug 联动修复

## Impact

- HTML 模式 slide 在 Celery review 链路中直接崩溃,slide 标 FAILED + escalated,项目卡死在 REVIEWING 状态
- 即使绕过崩溃,原始 body_html 会被 LayoutSpec JSON 覆盖,render 读不到 HTML
- LLM 调用失败时,审查被静默判为 PASS(本应是"未执行")
- HTML 模式回环 3 轮空转,body_html 完全没变,每轮都烧 LLM token
- 回环 100% 不收敛,所有 slide 走满 2 轮仍 ESCALATE_HUMAN

**链路影响**:整条 `MaterialPackage → PDF` 管线在 HTML 模式(默认模式)下不可用。

## Timeline

- **2026-04-06** — docs/23 完成 Celery 链 review→render 回环初接线,结构化模式(v2)跑通
- **2026-04-07 上午** — 代码审查发现 HTML 模式崩溃(Bug 1, 2, 3, 4)
- **2026-04-07 下午** — 修复前 4 个 bug,写 docs/24 实施计划
- **2026-04-07 傍晚** — E2E smoke(`review_loop_v2_check`)发现 Bug 5 "phantom issues"
- **2026-04-07 夜** — 决策改为 vision-only(ADR-004),全部修复完成
- **验证状态** — recompose → re-render → re-review 链路通了,但完整回环收敛验证(BUG-010)仍待执行

## Root Cause

### 表层
5 个 bug 看起来各不相干:
1. `LayoutSpec.model_validate(spec_json)` 对 html_mode spec 抛异常
2. `slide.spec_json = repaired_spec.model_dump()` 覆盖丢失 body_html
3. 异常处理返回空 issues → `_evaluate([])` 误判 PASS
4. HTML 回环 body_html 不变 → 空转
5. fallback_spec 的 R006/R008 phantom issues 让回环不收敛

### 深层根因:架构不一致

**Composer v3 引入 HTML 模式时(ADR-003),没有端到端审视 review 链路。** v2 结构化模式的回环假设:

1. spec_json 是 LayoutSpec
2. review 能通过修 spec 影响下一轮 render
3. rule lint 检查的是"真实结构"

HTML 模式全部打破:

1. spec_json 是 `{"html_mode": true, "body_html": ...}`
2. review 修 fallback_spec 不影响 body_html
3. rule lint 检查的是 fallback_spec 这个"假数据"

### 为什么测试没拦住

- 单元测试覆盖 review/critic 各自的行为,但**没覆盖 Composer → Review 的跨模块集成**
- E2E 脚本默认跑结构化模式,HTML 模式跑过但没跑完整回环
- Celery 任务路径 `tasks/review_tasks.py` 的测试覆盖薄弱

## Fix

### 修改文件(6 个)

| 文件 | 改动 | 对应 Bug |
|------|-----|---------|
| `tasks/review_tasks.py` | html_mode 检测、spec 写回守卫、内联 recompose、vision-only layers | Bug 1, 2, 4, 5 |
| `tool/review/semantic_check.py` | LLM 失败返回 `SEMANTIC_SKIPPED` issue(P2) | Bug 3 |
| `agent/critic.py` | `VISION_SKIPPED` issue + `_evaluate()` SKIPPED 过滤 | Bug 3 |
| `agent/composer.py` | 新增 `recompose_slide_html()` + `_load_repair_prompt()` | Bug 4 |
| `prompts/composer_repair.md` | 新建:修复专用 prompt,不复用 v3 composer prompt | Bug 4 |
| `scripts/material_package_e2e.py` | review→recompose→re-render 循环 + vision-only layers | Bug 4, 5 |

### 关键修复细节

**Bug 3(SKIPPED 过滤)**:
```python
real_issues = [i for i in issues if not i.rule_code.endswith("_SKIPPED")]
if not real_issues:
    return ReviewSeverity.P2, ReviewDecision.PASS
```
"审查未执行" ≠ "审查通过",但也不该阻塞流程,记录即可。

**Bug 5(ADR-004 vision-only)**:
```python
effective_layers = ["vision"] if is_html_mode else layers
```
见 [../decisions/ADR-004-html-mode-vision-only.md](../decisions/ADR-004-html-mode-vision-only.md)。

## Lessons Learned

### 立即执行
- ✅ 为每个"新模式 / 新路径"加集成测试,覆盖跨模块链路(不只单元测试)
- ✅ LLM 异常处理不能返回"空成功",要明确 SKIPPED 语义
- 🔲 P1-1 任务:跑完整 HTML 模式回环收敛验证(BUG-010)

### 流程改进
- 引入新模式时,**同步审视下游所有消费者**(review / render / export 都要过一遍)
- Review 链路的 fallback 机制要经过"最坏情况"思考,否则 phantom issues 会让回环永远不收敛
- Celery 任务路径必须有 smoke test 覆盖

### 架构原则
- **fallback 数据不要用于生成决策信号** —— 它可以让代码不崩,但不能让检查规则基于它做判断
- **规则层的设计要与数据层绑定**,跨数据模型复用规则会出问题
- 引入新模式时,**优先删除旧约束而非让新数据适配旧约束**(旧路就是老套路,勉强塞进去只会出事)

## Related

- **Bugs**: BUG-004, BUG-005, BUG-006, BUG-011, BUG-012(见 [../BUGS.md](../BUGS.md))
- **ADR**: [ADR-003(Composer 双模式)](../decisions/ADR-003-composer-dual-mode.md)、[ADR-004(HTML vision-only)](../decisions/ADR-004-html-mode-vision-only.md)
- **原始文档**:
  - [../../23_review_render_loop_fix.md](../../23_review_render_loop_fix.md)(初步回环接线)
  - [../../24_review_loop_v2_fixes.md](../../24_review_loop_v2_fixes.md)(实施计划)
  - [../../25_bugfix_log_review_loop_v2.md](../../25_bugfix_log_review_loop_v2.md)(bug 逐条记录)
