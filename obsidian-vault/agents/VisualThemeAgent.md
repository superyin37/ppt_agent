---
tags: [agent, llm, visual-theme]
source: agent/visual_theme.py
model: STRONG_MODEL
---

# VisualThemeAgent

> **阶段六**（可选）：根据项目信息和审美偏好，生成项目级 `VisualTheme`，一次生成作用于全部幻灯片。

## 触发时机

```
POST /projects/{project_id}/outline/confirm
→ _compose_render_worker() in api/routers/outlines.py
  → generate_visual_theme()  ← 本 Agent（在 compose 之前）
```

或通过客户端显式请求独立触发。

## 核心函数

```python
# agent/visual_theme.py line 46
async def generate_visual_theme(
    inp: VisualThemeInput,
    db: Session,
) -> VisualThemeORM
```

## 输入 — `VisualThemeInput`

```python
class VisualThemeInput(BaseModel):
    project_id: UUID
    project_name: str
    client_name: Optional[str]
    building_type: str               # 建筑类型
    style_preferences: list[str]     # 用户指定风格词，如 ["现代", "极简"]
    dominant_styles: list[str]       # 从参考案例提取的风格标签
    dominant_features: list[str]     # 从参考案例提取的特征标签
    narrative_hint: Optional[str]    # 如 "学术严谨" / "创意前卫"
```

## System Prompt

文件：`prompts/visual_theme_system.md`（→ [[prompts/VisualThemeSystem]]）

## User Message 格式

```
请为以下建筑项目生成完整的视觉主题：

## 项目信息
- 项目名称：{inp.project_name}
- 委托方：{inp.client_name}
- 建筑类型：{inp.building_type}

## 用户风格偏好
- {style_preference_1}

## 案例审美倾向
主要风格标签：{dominant_styles}
主要特征标签：{dominant_features}

## 叙事基调
{inp.narrative_hint}

请生成完整 VisualTheme JSON。project_id 使用：{inp.project_id}
```

## LLM 配置

```python
function    = call_llm_structured     # 结构化输出
model       = STRONG_MODEL
temperature = 0.7                     # 允许一定创意
max_tokens  = 4096
output_schema = VisualTheme           # Pydantic 模型直接作为输出 schema
```

## 输出 Schema — `VisualTheme`

详见 [[schemas/VisualTheme]]

主要子系统：
- `colors: ColorSystem` — 10 个颜色槽（含 WCAG 对比度约束）
- `typography: TypographySystem` — 字体 + 字号（base_size 20-28，scale_ratio 1.2-1.5）
- `spacing: SpacingSystem` — 间距 + 密度（compact/normal/spacious）
- `decoration: DecorationStyle` — 分割线、圆角、图片处理、背景肌理
- `cover: CoverStyle` — 封面布局情绪

## 字号安全护栏（LLM 后处理）

```python
# agent/visual_theme.py
if t.base_size < 20:  clamped["base_size"] = 20
if t.base_size > 28:  clamped["base_size"] = 28
if t.scale_ratio < 1.2: clamped["scale_ratio"] = 1.25
if t.scale_ratio > 1.5: clamped["scale_ratio"] = 1.5
```
确保 1920×1080 投影环境可读性。

## 版本管理

每次调用递增 `version`，最新带 `status="draft"` 的主题被 `ComposerAgent` 读取。

## 相关

- [[stages/06-视觉主题生成]]
- [[prompts/VisualThemeSystem]]
- [[schemas/VisualTheme]]
- [[agents/ComposerAgent]]
