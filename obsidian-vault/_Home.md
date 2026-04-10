# PPT Agent — 知识库首页

> **PPT Agent** 是一个将本地素材包自动转化为建筑方案汇报 PDF 的 AI 流水线系统。
> 本知识库记录所有流程细节、数据结构、LLM prompt 及实现细节。

---

## 可视化总览（Canvas）

| Canvas | 内容 |
|--------|------|
| [[pipeline-overview]] | **9 阶段流水线全景图**（推荐入口） |
| [[data-flow]] | **数据模型关系图**（数据流向） |
| [[agent-network]] | **Agent 协作网络**（LLM 调用链） |

---

## 快速导航

### 🔄 流水线阶段

| 阶段 | 文件 | 状态变更 |
|------|------|----------|
| ① 素材包摄入 | [[stages/01-素材包摄入]] | → `MATERIAL_READY` |
| ② Brief Doc 生成 | [[stages/02-BriefDoc生成]] | LLM |
| ③ 大纲生成 | [[stages/03-大纲生成]] | LLM → `OUTLINE_READY` |
| ④ 素材绑定 | [[stages/04-素材绑定]] | → `BINDING` |
| ⑤ 幻灯片编排 | [[stages/05-幻灯片编排]] | LLM × N → `SLIDE_PLANNING` |
| ⑥ 视觉主题生成 | [[stages/06-视觉主题生成]] | LLM（可选）|
| ⑦ 渲染 | [[stages/07-渲染]] | Playwright → `REVIEWING` |
| ⑧ 审查与修复 | [[stages/08-审查与修复]] | 可选循环 |
| ⑨ PDF 导出 | [[stages/09-PDF导出]] | → `EXPORTED` |

### 🤖 LLM Agents

- [[agents/BriefDocAgent]] — 叙事框架生成
- [[agents/OutlineAgent]] — 大纲规划
- [[agents/MaterialBindingAgent]] — 素材绑定
- [[agents/ComposerAgent]] — 版式编排（v2/v3）
- [[agents/VisualThemeAgent]] — 视觉主题

### 📐 数据 Schema

- [[schemas/MaterialPackage]] — 素材包 + MaterialItem
- [[schemas/Asset]] — 派生资产
- [[schemas/ProjectBrief]] — 项目元信息
- [[schemas/BriefDocSchema]] — Brief 文档结构
- [[schemas/OutlineSlideEntry]] — 大纲页面条目
- [[schemas/SlideMaterialBinding]] — 素材绑定结果
- [[schemas/Slide]] — 幻灯片模型
- [[schemas/VisualTheme]] — 视觉主题
- [[schemas/LayoutSpec]] — 布局规格
- [[schemas/LayoutPrimitive]] — 11 种布局原语

### 📝 Prompt 模板

- [[prompts/BriefDocSystemPrompt]] — Brief Agent 系统提示词
- [[prompts/OutlineSystemV2]] — Outline Agent 系统提示词
- [[prompts/ComposerSystemV2]] — Composer Agent 系统提示词
- [[prompts/VisualThemeSystem]] — VisualTheme Agent 系统提示词

### 🔢 枚举类型

- [[enums/ProjectStatus]] — 项目状态枚举（13 个状态）
- [[enums/SlideStatus]] — 幻灯片状态枚举
- [[enums/AssetType]] — 资产类型枚举

### 🛠️ 工具与基础设施

- [[tools/MaterialPipeline]] — 素材摄入管道（`tool/material_pipeline.py`）
- [[tools/MaterialResolver]] — logical_key 匹配工具
- [[tasks-infra/APIRoutes]] — API 路由索引
- [[tasks-infra/BackgroundWorkers]] — 后台工作线程

---

## 代码文件索引

```
agent/
  brief_doc.py        → BriefDocAgent
  outline.py          → OutlineAgent
  material_binding.py → MaterialBindingAgent
  composer.py         → ComposerAgent (v2/v3)
  visual_theme.py     → VisualThemeAgent
render/
  engine.py           → LayoutSpec → HTML 渲染引擎
  exporter.py         → Playwright 截图 + PDF
schema/
  visual_theme.py     → VisualTheme / LayoutSpec / LayoutPrimitive
  outline.py          → OutlineSpec / OutlineSlideEntry
  common.py           → 所有枚举类型
  page_slot.py        → PageSlot / PageSlotGroup
config/
  ppt_blueprint.py    → PPT 蓝图模板库（40页结构）
  llm.py              → LLM 客户端（STRONG_MODEL / call_llm_with_limit）
tool/
  material_pipeline.py  → 素材摄入全流程
  material_resolver.py  → logical_key 展开与匹配
```
