---
tags: [enum, project-status]
source: schema/common.py
---

# ProjectStatus 枚举

> 项目生命周期状态，存于 `projects.status` 字段。

## 状态定义

```python
class ProjectStatus(str, Enum):
    INIT                = "INIT"
    INTAKE_IN_PROGRESS  = "INTAKE_IN_PROGRESS"
    INTAKE_CONFIRMED    = "INTAKE_CONFIRMED"
    REFERENCE_SELECTION = "REFERENCE_SELECTION"
    ASSET_GENERATING    = "ASSET_GENERATING"
    MATERIAL_READY      = "MATERIAL_READY"
    OUTLINE_READY       = "OUTLINE_READY"
    BINDING             = "BINDING"
    SLIDE_PLANNING      = "SLIDE_PLANNING"
    RENDERING           = "RENDERING"
    REVIEWING           = "REVIEWING"
    READY_FOR_EXPORT    = "READY_FOR_EXPORT"
    EXPORTED            = "EXPORTED"
    FAILED              = "FAILED"
```

## 状态转换流程

```
INIT
  ↓ 用户提交 intake 问卷
INTAKE_IN_PROGRESS
  ↓ 用户确认
INTAKE_CONFIRMED
  ↓ 选择参考案例
REFERENCE_SELECTION
  ↓ 素材包摄入完成  ← 阶段一
MATERIAL_READY
  ↓ Brief Doc + 大纲生成完成  ← 阶段二+三
OUTLINE_READY       （等待用户确认）
  ↓ 用户点击「确认大纲」
BINDING             ← 阶段四（素材绑定中）
  ↓ 素材绑定完成，编排开始
SLIDE_PLANNING      ← 阶段五（幻灯片编排中）
  ↓ 编排完成，渲染中
RENDERING           ← 阶段七
  ↓ 渲染完成
REVIEWING           ← 阶段八（审查中）
  ↓ 审查通过
READY_FOR_EXPORT
  ↓ 用户触发导出
EXPORTED            ← 阶段九（PDF 就绪）
```

任何阶段出现不可恢复错误 → `FAILED`

## 各阶段对应状态

| 流水线阶段 | → 状态 |
|-----------|--------|
| [[stages/01-素材包摄入]] | `MATERIAL_READY` |
| [[stages/03-大纲生成]] | `OUTLINE_READY` |
| [[stages/04-素材绑定]] | `BINDING` |
| [[stages/05-幻灯片编排]] | `SLIDE_PLANNING` |
| [[stages/07-渲染]] | `REVIEWING` |
| [[stages/09-PDF导出]] | `EXPORTED` |
