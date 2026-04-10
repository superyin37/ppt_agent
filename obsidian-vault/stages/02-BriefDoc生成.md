---
tags: [stage, llm, brief-doc]
status-after: (中间状态，等待 OutlineAgent)
source: agent/brief_doc.py
---

# 阶段二：Brief Doc 生成

> LLM 调用，将素材包元信息整合为结构化的叙事框架文档（设计建议书大纲）。

## 触发

```
POST /projects/{project_id}/material-packages/{package_id}/regenerate
→ api/routers/material_packages.py (line 80)
→ _outline_worker() in api/routers/outlines.py (line 33)
  ① generate_brief_doc(project_id, db)  ← 本阶段
  ② generate_outline(project_id, db)    ← 下一阶段
```

## 执行流程

```
1. 加载 ProjectBrief（最新版本）
2. _load_system_prompt(brief)  → 注入项目信息到系统提示词
3. 加载 MaterialPackage（最新版本）
4a. 有素材包 → _build_material_package_message(package, items)
4b. 无素材包 → _build_legacy_assets_message(assets)
5. call_llm_with_limit(system, user, _BriefDocLLMOutput)
6. 解析 _BriefDocLLMOutput → 写入 BriefDoc 记录
```

## LLM 调用细节

→ 详见 [[agents/BriefDocAgent]]

- **Model:** `STRONG_MODEL`（`config/llm.py`）
- **System Prompt:** `prompts/brief_doc_system.md`（→ [[prompts/BriefDocSystemPrompt]]）
- **输出 Schema:** `_BriefDocLLMOutput`

## 关键产出字段

`BriefDoc.outline_json` 的关键字段会直接注入到 [[stages/03-大纲生成]] 的 System Prompt：

```python
# agent/outline.py → _load_system_prompt()
"{positioning_statement}" ← brief_doc.outline_json["positioning_statement"]
"{narrative_arc}"         ← brief_doc.outline_json["narrative_arc"]
```

## 产出

- 1 条 `BriefDoc` 记录（→ [[schemas/BriefDocSchema]]）

## 相关

- [[agents/BriefDocAgent]]
- [[prompts/BriefDocSystemPrompt]]
- [[schemas/BriefDocSchema]]
- [[schemas/ProjectBrief]]
- 上一阶段：[[stages/01-素材包摄入]]
- 下一阶段：[[stages/03-大纲生成]]
