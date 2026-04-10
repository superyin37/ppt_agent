---
tags: [agent, llm, brief-doc]
source: agent/brief_doc.py
model: STRONG_MODEL
---

# BriefDocAgent

> **阶段二**：将素材包元信息整合为「设计建议书大纲」（叙事框架 + 章节结构）。

## 触发时机

```
POST /projects/{project_id}/material-packages/{package_id}/regenerate
→ api/routers/material_packages.py line 80
→ _outline_worker() in api/routers/outlines.py line 33
```

## 核心函数

```python
# agent/brief_doc.py line 46
async def generate_brief_doc(project_id: UUID, db: Session) -> BriefDoc
```

## 输入组装

### System Prompt
文件：`prompts/brief_doc_system.md`（→ [[prompts/BriefDocSystemPrompt]]）

注入变量：
| 变量 | 来源 | 示例 |
|------|------|------|
| `{building_type}` | `ProjectBrief.building_type` | `"museum"` |
| `{project_name}` | `ProjectBrief.client_name` | `"苏州博物馆改造"` |
| `{client_name}` | `ProjectBrief.client_name` | |
| `{city}` | `ProjectBrief.city` | `"苏州"` |
| `{province}` | `ProjectBrief.province` | `"江苏"` |
| `{style_preferences}` | `ProjectBrief.style_preferences` | `"现代、极简"` |

### User Message 构建逻辑

- **有素材包时（推荐路径）**：`_build_material_package_message()` — 注入 manifest + 文本摘录
- **无素材包时（降级路径）**：`_build_legacy_assets_message()` — 注入资产分组数据

#### `_build_material_package_message()` 输出结构

```xml
<material_package>
{
  "package_id": "uuid",
  "version": 1,
  "summary": { ... },        // 计数与摘要
  "manifest": { ... },        // 按条目分组的 logical_keys
  "text_items": [             // 最多 15 条文本摘录（前 240 字符）
    {
      "logical_key": "policy.national.1",
      "title": "政策文件名称",
      "snippet": "..."
    }
  ]
}
</material_package>
```

## LLM 配置

```python
model     = STRONG_MODEL        # config/llm.py
function  = call_llm_with_limit
```

## 输出 Schema — `_BriefDocLLMOutput`

```python
class _BriefDocLLMOutput(BaseModel):
    brief_title: str                         # PPT 演示标题
    executive_summary: str                   # 200字项目概述
    chapters: list[_ChapterEntry]            # 章节列表
    positioning_statement: str               # 差异化价值定位（一句话）
    design_principles: list[str]             # 设计方向，3-5条
    recommended_emphasis: _RecommendedEmphasis
    narrative_arc: str                       # 整体叙事走向

class _ChapterEntry(BaseModel):
    chapter_id: str                          # 如 "ch01"
    title: str                               # 章节标题
    key_findings: list[str]                  # 核心发现列表
    narrative_direction: str                 # 叙事方向

class _RecommendedEmphasis(BaseModel):
    policy_focus: str                        # 政策聚焦点
    site_advantage: str                      # 场地优势
    competitive_edge: str                    # 竞争优势
    case_inspiration: str                    # 案例启发
```

## 产出 — `BriefDoc` ORM

存入 `brief_docs` 表：
- `outline_json`：包含 `chapters`、`positioning_statement`、`design_principles`、`recommended_emphasis`
- `narrative_arc_json`：包含 `narrative_arc`、`executive_summary`

`outline_json` 后续被 [[agents/OutlineAgent]] 读取，注入 `positioning_statement` 和 `narrative_arc` 到大纲生成 prompt。

## 相关

- [[stages/02-BriefDoc生成]]
- [[prompts/BriefDocSystemPrompt]]
- [[schemas/BriefDocSchema]]
- [[schemas/ProjectBrief]]
- [[schemas/MaterialPackage]]
