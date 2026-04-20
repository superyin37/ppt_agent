---
name: 项目术语表
description: 项目黑话 / 缩写 / 关键概念定义 —— Agent 遇到陌生词汇先查这里
last_updated: 2026-04-20
owner: superxiaoyin
---

# 术语表

> **目的**:让陌生人(或无上下文的 Agent)看代码时能对号入座。不含通用技术词汇。

---

## 核心业务概念

| 术语 | 定义 | 文件 |
|------|------|------|
| **MaterialPackage(素材包)** | 用户上传的原始素材集合,包含图片、图表、文档等。本地路径如 `test_material/project1`。系统的一切都基于它。 | `db/models/material_package.py` |
| **MaterialItem(素材条目)** | 素材包中的单个文件,有 `logical_key`(如 `site.context.photo.1`)和 `kind`(image/chart_bundle/spreadsheet/document) | `db/models/material_item.py` |
| **Asset(资产)** | 从 MaterialItem 派生出的、可被 slide 直接使用的对象(处理后的地图 / 图表 / 文本摘要 / 案例卡) | `db/models/asset.py` |
| **BriefDoc(设计建议书)** | Intake 后的项目元数据 + 叙事策略(positioning_statement / design_principles / narrative_arc) | `db/models/brief_doc.py` |
| **PPT Blueprint(蓝图)** | 40 页结构定义,每页有 section / page_type / required_input_keys | `config/ppt_blueprint.py` |
| **Outline(大纲)** | 基于蓝图 + BriefDoc 生成的每页具体 content_directive(200~300 字指令) | `db/models/outline.py` |
| **SlideMaterialBinding(素材绑定)** | 每页的素材清单:`must_use_item_ids` / `derived_asset_ids` / `evidence_snippets` | `db/models/slide_material_binding.py` |
| **VisualTheme(视觉主题)** | 每项目一套的设计系统:色彩、字体、间距、装饰风格。LLM 生成,不复用预设模板 | `db/models/visual_theme.py` |
| **LayoutSpec(布局规格)** | Composer v2 结构化模式产出,含 `primitive`(布局原语)+ `region_bindings`(区域 → 内容块) | `schema/visual_theme.py` |
| **ContentBlock(内容块)** | LayoutSpec 的最小内容单元,有 13 种 `content_type`(heading / body-text / chart / kpi-card 等) | `schema/visual_theme.py` |
| **body_html** | Composer v3 HTML 模式的产出,LLM 直接输出的 `<body>` 内部内容,由引擎注入 theme CSS | `agent/composer.py` |

---

## Agent 与管线

| 术语 | 定义 |
|------|------|
| **Intake Agent** | 自然语言 → `ProjectBriefData` 的多轮对话 Agent |
| **Reference Agent** | pgvector 向量检索 + 案例重排序 + 偏好摘要生成 |
| **Brief Doc Agent** | 读素材包 → 生成 BriefDoc(设计建议书大纲) |
| **Outline Agent** | 读 BriefDoc + 蓝图 → 生成每页 content_directive |
| **Material Binding** | 逐页将 required_input_keys 匹配到 MaterialItem / Asset |
| **Composer Agent** | 读 SlideMaterialBinding + VisualTheme → 生成 LayoutSpec(v2)或 body_html(v3) |
| **Critic Agent** | 3 层审查:rule lint / semantic check / vision review + 设计顾问评分 |
| **recompose** | Composer v3 的回环修复入口,根据 issues 修 body_html | 
| **Design Advisor** | Vision Review Mode B:5 维度评分 + D001~D012 改善建议 |

---

## 布局原语(11 种 Layout Primitives)

| 原语 | 用途 |
|------|------|
| `full-bleed` | 封面、章节页、大图展示 |
| `split-h` | 左图右文、左案例右分析 |
| `split-v` | 上下分区 |
| `single-column` | 正文、策略文字 |
| `grid` | KPI 卡片、多图等分 |
| `hero-strip` | 大主视觉 + 下方内容条 |
| `sidebar` | 主内容 + 侧边注释 |
| `triptych` | 三等分并排 |
| `overlay-mosaic` | 地图/大图 + 浮层分析标注 |
| `timeline` | 时间轴、流程图 |
| `asymmetric` | 非均等分割(强调一侧) |

---

## 审查规则代号

### Rule(规则层,无 LLM)
`R001`=TEXT_OVERFLOW / `R002`=BULLET_OVERFLOW / `R003`=MISSING_REQUIRED_BLOCK / `R005`=IMAGE_COUNT_EXCEEDED / `R006`=EMPTY_SLIDE / `R007`=TITLE_TOO_LONG / `R008`=KEY_MESSAGE_MISSING / `R009`=TEMPLATE_UNKNOWN / `R015`=EXCESSIVE_DENSITY

### Semantic(语义层,快模型)
`S001`=METRIC_INCONSISTENCY / `S004`=UNSUPPORTED_CLAIM / `S005`=STYLE_TERM_WRONG / `S006`=MISSING_KEY_MESSAGE_SUPPORT / `S007`=CLIENT_NAME_WRONG

### Vision(视觉层,多模态)
`V001`=VISUAL_CLUTTER / `V002`=IMAGE_BLURRY / `V004`=TEXT_ON_BUSY_BG / `V007`=BLANK_AREA_WASTE

### Design Advisor(评分建议,非缺陷)
`D001`~`D012` —— 12 种建议代号(对比度不足、配色冲突、字阶混乱等)

### 特殊 issue
- `SEMANTIC_SKIPPED`(P2)— semantic LLM 调用失败时记录,不触发修复
- `VISION_SKIPPED`(P2)— vision LLM 调用失败时记录,不触发修复

---

## 状态机(ProjectStatus)

```
INIT → INTAKE_IN_PROGRESS → INTAKE_CONFIRMED
     → REFERENCE_SELECTION → ASSET_GENERATING → OUTLINE_READY
     → SLIDE_PLANNING → RENDERING → REVIEWING
     → READY_FOR_EXPORT → EXPORTED
     → FAILED(任意节点不可恢复)
```

SlideStatus:`PENDING` / `COMPOSED` / `RENDERED` / `REVIEW_PASSED` / `REPAIR_NEEDED` / `FAILED`

---

## 缩写 / 配置

| 缩写 | 含义 |
|------|------|
| **FAR** | Floor Area Ratio,容积率 |
| **GFA** | Gross Floor Area,总建筑面积 |
| **POI** | Point of Interest,兴趣点(地图) |
| **WCAG AA** | Web Content Accessibility Guidelines,色彩对比度标准 |
| **OSS** | Object Storage Service,对象存储(阿里云 / 本地 mock) |
| **pgvector** | PostgreSQL 向量检索扩展 |
| **LLM_STRONG_MODEL** | 强模型,用于 BriefDoc/Outline/Composer(当前 claude-opus-4-6) |
| **LLM_FAST_MODEL** | 快模型,用于降级 fallback(当前 claude-sonnet-4-6) |
| **LLM_CRITIC_MODEL** | 审查模型,用于 semantic/vision review(当前 google/gemini-3.1-pro-preview) |

---

## 模式 / 版本

| 名称 | 含义 |
|------|------|
| **Composer v2 / Structured mode** | LLM → LayoutSpec JSON → 固定 HTML 模板 |
| **Composer v3 / HTML mode(默认)** | LLM → body_html → 安全过滤 + theme CSS 注入 |
| **Review v2** | 2026-04-07 修复后的 review 回环,含 HTML 模式 recompose |
| **Vision Review Mode A** | 缺陷检测(V001~V007) |
| **Vision Review Mode B / Design Advisor** | 5 维度评分 + 改善建议 |

---

## 不是什么(澄清)

- **"素材包"不是 ZIP 文件** —— 是本地目录 + DB 记录
- **"蓝图"不是模板** —— 是 40 页结构定义,每页内容仍由 LLM 生成
- **"视觉主题"不是预设样式集** —— 每项目由 LLM 独立生成
- **"Review"不仅仅是"通过 / 不通过"** —— 还包含修复指令和评分
- **`agent/graph.py` 不是主流程** —— 已废弃,主流程是 Celery 链
