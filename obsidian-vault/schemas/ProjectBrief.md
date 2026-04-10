---
tags: [schema, project, database]
source: db/models/project.py
---

# ProjectBrief

> 项目级元信息，从素材包中的大纲文档自动提取。所有后续 Agent 的基础上下文。

## 数据库字段

```
表名: project_briefs
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | |
| `project_id` | UUID FK | 唯一（一个项目一条） |
| `version` | int | 支持重新摄入时更新 |
| `building_type` | str | 建筑类型（见 BuildingType 枚举） |
| `client_name` | str | 委托方/项目名称 |
| `city` | str | 城市 |
| `province` | str | 省份 |
| `district` | str | 行政区 |
| `site_address` | str | 详细地址 |
| `far` | float | 容积率（Floor Area Ratio） |
| `style_preferences` | JSON array | 风格偏好词，如 `["现代", "极简", "生态"]` |
| `meta_json` | JSON | 其他提取信息 |

## 提取逻辑

```python
# tool/material_pipeline.py → _extract_project_brief()
# 从 brief.outline.text 类型的 MaterialItem 中通过正则提取
```

| 提取字段 | 正则/逻辑 |
|---------|----------|
| `city` | 城市名正则匹配 |
| `province` | 省份名正则匹配 |
| `district` | 行政区关键词 |
| `site_address` | 地址字符串 |
| `building_type` | 关键词匹配（见下表） |
| `style_preferences` | 风格关键词列表 |
| `far` | 数值正则，`容积率\s*[≤≥=]\s*(\d+\.?\d*)` |

## `building_type` 推断规则

| 匹配关键词 | building_type |
|-----------|---------------|
| 办公 / 写字楼 / 商务 | `office` |
| 住宅 / 公寓 / 居住 | `residential` |
| 酒店 / 度假 | `hotel` |
| 商业 / 购物 / 综合体 | `commercial` |
| 博物馆 / 美术馆 / 展览 | `museum` |
| 学校 / 教育 / 大学 | `education` |
| 文化 / 图书馆 / 剧院 | `cultural` |
| 混合 / 综合 | `mixed` |

## `style_preferences` 关键词

从文本中提取的审美/设计风格词：
`现代`, `极简`, `生态`, `科技`, `传统`, `文化`, `奢华`, `简约`, `自然`, `工业感`, `人文`, `创意`...

## 被哪些 Agent 消费

| Agent | 使用字段 |
|-------|---------|
| [[agents/BriefDocAgent]] | 全部字段（注入 System Prompt） |
| [[agents/OutlineAgent]] | `building_type`, `client_name`, `city`, `style_preferences` |
| [[agents/ComposerAgent]] | `building_type`, `client_name`, `city` |
| [[agents/VisualThemeAgent]] | `building_type`, `style_preferences` → `VisualThemeInput` |

## 相关

- [[stages/01-素材包摄入]]
- [[tools/MaterialPipeline]]
- [[enums/ProjectStatus]]
