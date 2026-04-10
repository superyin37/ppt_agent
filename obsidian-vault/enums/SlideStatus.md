---
tags: [enum, slide-status]
source: schema/common.py
---

# SlideStatus 枚举

> 单张幻灯片的生命周期状态，存于 `slides.status` 字段。

## 状态定义

```python
class SlideStatus(str, Enum):
    PENDING              = "pending"
    SPEC_READY           = "spec_ready"
    RENDERED             = "rendered"
    REVIEW_PENDING       = "review_pending"
    REVIEW_PASSED        = "review_passed"
    REPAIR_NEEDED        = "repair_needed"
    REPAIR_IN_PROGRESS   = "repair_in_progress"
    READY                = "ready"
    FAILED               = "failed"
```

## 状态转换图

```
pending
  ↓ ComposerAgent 完成 LayoutSpec
spec_ready
  ↓ render_slide_html + screenshot 完成
rendered
  ↓ 进入审查阶段
review_pending
  ├─ 审查通过（P2/PASS）→ review_passed → ready
  └─ 审查失败（P0/P1）→ repair_needed
                          ↓
                      repair_in_progress
                          ↓ 重新编排 + 渲染
                      rendered
                          ↓ 再次审查
                          ├─ 通过 → review_passed → ready
                          └─ 超过最大迭代 → failed
```

## 对应阶段

| 状态 | 产生阶段 |
|------|---------|
| `spec_ready` | [[stages/05-幻灯片编排]] |
| `rendered` | [[stages/07-渲染]] |
| `review_passed` / `repair_needed` | [[stages/08-审查与修复]] |
| `ready` | 审查通过后 |
| `failed` | 任何不可恢复错误 |
