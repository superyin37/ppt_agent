---
tags: [schema, brief-doc, database]
source: db/models/brief_doc.py
---

# BriefDoc Schema

> 设计建议书大纲，LLM 生成的叙事框架，是 [[agents/OutlineAgent]] 的核心上下文。

## 数据库字段

```
表名: brief_docs
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | |
| `project_id` | UUID FK | |
| `version` | int | 支持重新生成 |
| `status` | str | `"draft"` / `"confirmed"` |
| `outline_json` | JSON | 章节结构 + positioning + design_principles |
| `narrative_arc_json` | JSON | 叙事弧线 + 执行摘要 |

## `outline_json` 结构

```json
{
  "brief_title": "苏州博物馆改造策划建议书",
  "positioning_statement": "传承姑苏文脉，融合当代美学的博物馆改造典范",
  "design_principles": [
    "文脉延续：尊重 IMP 设计基因",
    "功能升级：提升观展体验",
    "生态融合：以水为核，引自然入室"
  ],
  "recommended_emphasis": {
    "policy_focus": "文化遗产保护与活化利用政策导向",
    "site_advantage": "苏州园林毗邻，UNESCO 文化遗产辐射效应",
    "competitive_edge": "差异化展陈体验，文旅融合新模式",
    "case_inspiration": "贝聿铭设计语言的当代演绎"
  },
  "chapters": [
    {
      "chapter_id": "ch01",
      "title": "背景研究",
      "key_findings": ["政策支持文化建筑改造", "周边文化资源丰富"],
      "narrative_direction": "从宏观政策到微观场地，建立项目社会价值"
    }
  ]
}
```

## `narrative_arc_json` 结构

```json
{
  "brief_title": "苏州博物馆改造策划建议书",
  "executive_summary": "本项目以苏州博物馆新馆为核心，打造集文化展示、教育研究、休闲体验于一体的当代博物馆综合体...",
  "narrative_arc": "从「场地的文化底蕴」出发，经由「使用者需求发现」，到达「设计策略的创新提案」，最终呈现一个既尊重历史又面向未来的博物馆愿景。"
}
```

## 被哪些 Agent 消费

| Agent | 使用方式 |
|-------|---------|
| [[agents/OutlineAgent]] | `outline_json["positioning_statement"]` → System Prompt<br>`outline_json["narrative_arc"]` → System Prompt<br>完整 `<brief_doc>` → User Message |

## 相关

- [[stages/02-BriefDoc生成]]
- [[agents/BriefDocAgent]]
- [[agents/OutlineAgent]]
- [[schemas/ProjectBrief]]
