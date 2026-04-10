# 07. Prompt 模板设计

最后更新：2026-04-10

> 所有 Prompt 遵循以下约定：
> - System Prompt 定义角色、能力边界、输出格式
> - 用 XML 标签隔离不同输入段
> - 输出必须为合法 JSON（除 manus.md 外），通过 Pydantic 校验

---

## 目录

| 编号 | Prompt 文件 | 使用 Agent | 状态 |
|------|-------------|-----------|------|
| 7.1 | `prompts/intake_system.md` | Intake Agent | 当前 |
| 7.2 | `prompts/brief_doc_system.md` | Brief Doc Agent | 当前 |
| 7.3 | `prompts/visual_theme_system.md` | Visual Theme Agent | 当前 |
| 7.4 | `prompts/outline_system_v2.md` | Outline Agent v2 | 当前（主线） |
| 7.5 | `prompts/outline_system.md` | Outline Agent v1 | 遗留 |
| 7.6 | `prompts/outline.md` | Outline Agent（原始版） | 遗留 |
| 7.7 | `prompts/composer_system_v2.md` | Composer Agent v2 | 当前 |
| 7.8 | `prompts/composer_system_v3.md` | Composer Agent v3 | 当前（主线） |
| 7.9 | `prompts/composer_repair.md` | Composer Repair Agent | 当前 |
| 7.10 | `prompts/vision_design_advisor.md` | Vision Review Agent | 当前 |
| 7.11 | `prompts/manus.md` | 40 页蓝图源 | 参考/蓝图 |

---

## 7.1 Intake Agent — `prompts/intake_system.md`

**使用 Agent**：Intake Agent（项目信息采集）

**角色定位**：建筑项目信息采集助手，从用户自然语言描述中提取结构化项目基本信息。

**核心职责**：
- 从自然语言中提取项目必填字段（建筑类型、甲方名称、风格偏好、地址、面积指标等）
- 识别缺失字段并生成友好追问（一次 1~2 个字段）
- 所有必填字段就绪时生成确认摘要
- 面积指标三选二：`gross_floor_area` / `site_area` / `far`

**模板变量**：

| 变量 | 说明 |
|------|------|
| `{building_type_hint}` | 当前项目建筑类型提示 |
| `{existing_brief_json}` | 上一轮采集结果（已有信息 JSON） |

**输出格式**：严格 JSON

```json
{
  "extracted": {
    "building_type": null,
    "client_name": null,
    "style_preferences": [],
    "site_address": null,
    "province": null, "city": null, "district": null,
    "gross_floor_area": null, "site_area": null, "far": null,
    "special_requirements": null
  },
  "missing_fields": ["..."],
  "is_complete": false,
  "follow_up": "追问文本",
  "confirmation_summary": null
}
```

---

## 7.2 Brief Doc Agent — `prompts/brief_doc_system.md`

**使用 Agent**：Brief Doc Agent（设计建议书大纲生成）

**角色定位**：资深建筑策划顾问，将采集数据整合为设计建议书大纲，作为方案汇报 PPT 的内容骨架。

**核心职责**：
- 遵循 manus.md 40 页结构框架，将项目数据组织为建议书大纲
- 覆盖五大板块：背景研究（约 11 页）、场地分析（约 7 页）、竞品分析（约 3 页）、参考案例（2-5 页）、项目定位与设计策略
- 输出精炼的叙事方向与设计原则，供下游 Outline Agent 消费

**模板变量**：

| 变量 | 说明 |
|------|------|
| `{building_type}` | 建筑类型 |
| `{project_name}` | 项目名称 |
| `{client_name}` | 甲方名称 |
| `{city}` | 城市 |
| `{province}` | 省份 |
| `{style_preferences}` | 设计风格偏好 |

**输出格式**：严格 JSON，含长度约束

```json
{
  "brief_title": "项目全称 设计建议书",
  "executive_summary": "≤100字",
  "chapters": [
    {
      "chapter_id": "background",
      "title": "背景研究",
      "key_findings": ["≤3条, 每条≤30字"],
      "narrative_direction": "≤30字"
    }
  ],
  "positioning_statement": "≤50字",
  "design_principles": ["≤4条, 每条≤30字, 动词开头"],
  "recommended_emphasis": {
    "policy_focus": "≤30字",
    "site_advantage": "≤30字",
    "competitive_edge": "≤30字",
    "case_inspiration": "≤30字"
  },
  "narrative_arc": "≤80字"
}
```

**关键约束**：优先使用 `<available_data>` 中的具体数据；宁可内容简短不可截断 JSON。

---

## 7.3 Visual Theme Agent — `prompts/visual_theme_system.md`

**使用 Agent**：Visual Theme Agent（PPT 视觉主题生成）

**角色定位**：专业建筑展示设计师，为整个 PPT 设计完整、协调、有个性的视觉主题。

**核心职责**：
- 根据建筑类型和审美偏好生成色彩方案（primary/secondary/accent/background/cover_bg）
- 选择中文标题字体、正文字体、英文字体
- 确定字阶参数（base_size 20-28px, scale_ratio 1.2-1.5）
- 确定空间密度（compact / normal / spacious）
- 生成 style_keywords（3-5 个中文关键词）和 generation_prompt_hint

**输入信息**（通过上下文提供，非模板变量）：
- building_type、style_preferences
- dominant_styles / dominant_features（从参考案例提取）
- narrative_hint（叙事基调）
- 项目名称、委托方

**色彩约束**：
- primary 与 background 对比度 >= 4.5:1（WCAG AA）
- accent 与 background 对比度 >= 3:1
- secondary 与 primary 色相差 >= 15 度
- background 避免纯白 `#FFFFFF`
- cover_bg 可为 CSS gradient 字符串

**输出格式**：严格 JSON，符合 VisualTheme Schema（色彩、字体、字阶、间距、style_keywords、generation_prompt_hint）

---

## 7.4 Outline Agent v2（主线）— `prompts/outline_system_v2.md`

**使用 Agent**：Outline Agent v2（蓝图驱动的 SlotAssignment 生成）

**角色定位**：建筑方案汇报 PPT 策划专家，根据 PPT 蓝图和设计建议书大纲为每个槽位生成具体内容指令。

**核心职责**：
- 接收 PPT_BLUEPRINT（PageSlot 列表）和 brief_doc，为每个槽位输出 SlotAssignment
- 为每页撰写项目专属的 content_directive（<=80 字，简洁精准）
- 处理可变槽位组（PageSlotGroup），按 repeat_count 展开并编号（如 `policy-1`, `policy-2`）
- 为三个概念方案命名（简洁有诗意）
- 匹配 available_assets 到各页

**模板变量**：

| 变量 | 说明 |
|------|------|
| `{building_type}` | 建筑类型 |
| `{project_name}` | 项目名称 |
| `{client_name}` | 甲方名称 |
| `{city}` | 城市 |
| `{province}` | 省份 |
| `{positioning_statement}` | 定位主张 |
| `{narrative_arc}` | 叙事脉络 |

**输出格式**：严格 JSON

```json
{
  "deck_title": "完整 PPT 标题",
  "total_pages": 40,
  "assignments": [
    {
      "slot_id": "cover",
      "slide_no": 1,
      "section": "封面",
      "title": "≤15字",
      "content_directive": "≤80字",
      "asset_keys": [],
      "layout_hint": "...",
      "is_cover": true,
      "is_chapter_divider": false,
      "estimated_content_density": "low"
    }
  ]
}
```

---

## 7.5 Outline Agent v1（遗留）— `prompts/outline_system.md`

**使用 Agent**：Outline Agent v1（遗留版本）

**角色定位**：建筑方案汇报 PPT 策划专家（简化版）。

**核心职责**：
- 根据项目信息、场地分析、参考案例偏好生成 PPT 大纲（OutlineSpec）
- 遵循九章节叙事结构（封面 - 项目概述 - 场地分析 - 参考案例 - 设计策略 - 功能布局 - 立面造型 - 技术亮点 - 总结）
- 总页数 12-20 页
- 从固定模板列表中选择 recommended_template

**模板变量**：

| 变量 | 说明 |
|------|------|
| `{building_type}` | 建筑类型 |
| `{project_name}` | 项目名称 |
| `{client_name}` | 甲方名称 |
| `{style_preferences}` | 设计风格偏好 |

**输出格式**：OutlineSpec JSON（含 slides 数组，每页包含 purpose、key_message、recommended_template）

**与 v2 的区别**：v1 自行规划页面结构，v2 基于 PPT_BLUEPRINT 蓝图填充内容指令；v1 页数 12-20，v2 约 40 页。

---

## 7.6 Outline 原始版（遗留）— `prompts/outline.md`

**使用 Agent**：Outline Agent（最早期版本）

**角色定位**：国家一级注册建筑师，擅长可行性研究、场地条件分析、任务书编制。

**核心职责**：
- 从对话历史中提取项目需求，生成完整的建筑方案大纲
- 四大板块约 30+ 个子章节：
  - 项目背景（政策分析、产业政策、上位规划、规划条件、文化特征、经济背景）
  - 场地分析（区位、交通、周边产业、四至分析、设计限制条件）
  - 项目定位（竞品分析、案例参考、定位总结）
  - 设计建议（形态/风格/景观材料参考、设计策略、愿景、方案图、任务书）
- 要求政策引用标注文件名/文号，经济数据标注年份

**模板变量**：无显式模板变量，通过对话历史传入项目需求。

**输出格式**：自由文本（按章节结构输出），非 JSON。

**备注**：这是最详细的大纲 prompt，逐章逐节规定了内容要求（含"读取图片"等指令），后续 brief_doc_system.md 和 outline_system_v2.md 是对此 prompt 的拆分和结构化改造。

---

## 7.7 Composer Agent v2 — `prompts/composer_system_v2.md`

**使用 Agent**：Composer Agent v2（LayoutSpec 版式规划）

**角色定位**：建筑汇报 PPT 版式规划专家，将大纲条目扩展为 LayoutSpec 并结合 VisualTheme 做视觉决策。

**核心职责**：
- 每次处理一页幻灯片，选择合适的布局原语（11 种）
- 定义 11 种布局原语及其参数：full-bleed / split-h / split-v / single-column / grid / hero-strip / sidebar / triptych / overlay-mosaic / timeline / asymmetric
- 为每个区域绑定内容块（ContentBlock），支持 13 种 content_type（heading / subheading / body-text / bullet-list / kpi-value / image / chart / map / table / quote / caption / label / accent-element）
- 根据 content_directive 撰写实质性展示内容（严禁复制 directive 原文）

**模板变量**：无显式模板变量，通过上下文（XML 标签）传入 outline_entry、VisualTheme、available_assets。

**输出格式**：严格 JSON（单页 LayoutSpec）

```json
{
  "slide_no": 1,
  "section": "封面",
  "title": "页面标题",
  "is_cover": false,
  "is_chapter_divider": false,
  "primitive_type": "split-h",
  "primitive_params": { "..." },
  "region_bindings": [
    {
      "region_id": "left",
      "blocks": [
        { "block_id": "title", "content_type": "heading", "content": "...", "emphasis": "normal" }
      ]
    }
  ],
  "visual_focus": "left"
}
```

**关键约束**：每页内容块 <= 8 个；block_id 页内唯一；region_id 必须匹配所选原语的合法区域。

---

## 7.8 Composer Agent v3（主线）— `prompts/composer_system_v3.md`

**使用 Agent**：Composer Agent v3（HTML 直出）

**角色定位**：建筑汇报 PPT 视觉设计大师，将大纲条目直接设计为 1920x1080 HTML 幻灯片。

**核心职责**：
- 每次处理一页，输出完整 HTML 片段（以 `<div class="slide-root">` 为根容器）
- 通过 CSS 变量引用 VisualTheme 的色彩、字体、字阶、间距
- 自由设计布局（CSS Grid / Flexbox），不限于预设模板
- 鼓励使用内联 SVG 装饰（几何图形、渐变、图案纹理、数据可视化）
- 遵守四级信息层次：Action Title -> Visual Anchor -> Supporting Logic -> Data/Detail
- 根据 content_directive 撰写实质性内容（严禁复制 directive）

**模板变量**：无显式模板变量，通过上下文传入 outline_entry、project_brief、VisualTheme、available_assets、evidence_snippets。

**输出格式**：严格 JSON

```json
{
  "slide_no": 1,
  "body_html": "<div class=\"slide-root\">...</div>",
  "asset_refs": ["asset:uuid1"],
  "content_summary": "封面：项目名称与效果图"
}
```

**与 v2 的区别**：v2 输出抽象的 LayoutSpec（布局原语 + 内容块），由渲染层解释执行；v3 直接输出 HTML，跳过中间抽象层。

**关键约束**：
- body_html <= 8000 字符
- 禁止 `<script>` / `<iframe>` / `<form>` / 外部 URL
- 图片必须用 `asset:{id}` 引用
- 字号底线：正文 >= 20px，标题 >= 40px，禁止 < 16px
- 颜色必须通过 CSS 变量引用，不硬编码

---

## 7.9 Composer Repair — `prompts/composer_repair.md`

**使用 Agent**：Composer Repair Agent（HTML 修复模式）

**角色定位**：PPT 视觉设计修复专家，基于审查结果修复 HTML 幻灯片的具体问题。

**核心职责**：
- 接收原始 HTML + 审查问题列表，最小化修改修复问题
- 保留原始设计风格、布局结构、配色方案
- 支持的修复类型：V007 空白浪费、V001 视觉杂乱、V004 文字背景冲突、D005 布局偏重、D006 对齐偏移、D007 缺少焦点、D009 装饰缺失、R001 文本溢出

**模板变量**：无显式模板变量，通过上下文传入原始 HTML 和问题列表。

**输出格式**：严格 JSON（与 Composer v3 同结构）

```json
{
  "slide_no": 1,
  "body_html": "<div class=\"slide-root\">...</div>",
  "asset_refs": ["asset:uuid1"],
  "content_summary": "封面：项目名称与效果图（修复了 V007 空白浪费）"
}
```

**关键约束**：
- 禁止从零重写 — 必须基于原始 HTML 修改
- 不改变风格方向，不移除有效内容
- 字号底线与 v3 一致（正文 >= 20px，禁止 < 16px）
- 颜色使用 CSS 变量

---

## 7.10 Vision Design Advisor — `prompts/vision_design_advisor.md`

**使用 Agent**：Vision Review Agent（视觉设计质量评审）

**角色定位**：资深演示文稿视觉设计教授，对幻灯片截图进行多维度设计评分。

**核心职责**：
- 接收 1920x1080 幻灯片截图（图片输入），从五个维度评分（0-10）：
  - **color** — 配色与对比度（WCAG 标准、60:30:10 比例）
  - **typography** — 排版与文字层次（字号差异、行距、文字量）
  - **layout** — 布局与空间平衡（网格构图、留白节奏、安全区）
  - **focal_point** — 视觉焦点（第一眼焦点、信息层级、阅读路径）
  - **polish** — 整体完成度（装饰精致度、间距一致性、专业感）
- 输出具体可操作的改善建议，附建议代号（D001-D012）
- 针对不同页面类型（封面/过渡页/数据页/图片页）有差异化评分基准

**模板变量**：无显式模板变量，图片通过多模态输入提供。

**输出格式**：严格 JSON

```json
{
  "dimensions": [
    {"dimension": "color", "score": 7.5, "comment": "..."},
    {"dimension": "typography", "score": 8.0, "comment": "..."},
    {"dimension": "layout", "score": 6.0, "comment": "..."},
    {"dimension": "focal_point", "score": 7.0, "comment": "..."},
    {"dimension": "polish", "score": 5.5, "comment": "..."}
  ],
  "suggestions": [
    {
      "code": "D005",
      "category": "layout",
      "severity": "recommended",
      "message": "具体问题描述",
      "css_hint": "修复 CSS 提示",
      "target_selector": ".slide-root"
    }
  ],
  "one_liner": "一句话总评"
}
```

---

## 7.11 40 页蓝图源 — `prompts/manus.md`

**使用 Agent**：无直接绑定 Agent — 作为 PPT_BLUEPRINT 的页面结构参考源，被 Brief Doc Agent 和 Outline Agent v2 间接消费。

**角色定位**：资深建筑师，整理输入图文信息并排版为 40 页可编辑 PPT 汇报文件。

**核心职责**：
- 定义 40 页 PPT 的逐页内容蓝图，每页标明所需素材和内容任务
- 页面结构概览：
  - 第 1 页：封面（logo + 标题 + slogan）
  - 第 2 页：目录页（插画 + 目录）
  - 第 3 页：过渡页 — 背景研究
  - 第 4-6 页：政策解读与影响分析
  - 第 7 页：上位规划
  - 第 8 页：交通与基础设施（图片上传）
  - 第 9 页：文化特征与插画
  - 第 10-12 页：经济背景（GDP、人口、产业、消费数据图表）
  - 第 13 页：过渡页 — 场地分析
  - 第 14-17 页：区位与交通分析（图片 + 四至分析）
  - 第 18 页：场地 POI 分析与可视化
  - 第 19 页：场地综合总结
  - 第 20 页：过渡页 — 项目定位
  - 第 21-22 页：竞品分析
  - 第 23-25 页：参考案例（每案例一页，含缩略图）
  - 第 26 页：项目定位总结
  - 第 27 页：过渡页 — 设计策略
  - 第 28 页：设计策略
  - 第 29-37 页：三个概念方案（每方案含理念 + 鸟瞰图 + 室外人视图 + 室内人视图）
  - 第 38 页：材质分析 + 经济技术指标
  - 第 39 页：设计任务书
  - 第 40 页：结尾页

**模板变量**：

| 变量 | 说明 |
|------|------|
| `<用户输入_项目id>` | 用户输入文档引用 |
| `<设计建议书大纲_项目id>` | 设计建议书大纲文档引用 |
| `<枢纽站点_项目id>` 等 | 各类图片/文档资产引用（按页面需要） |

**输出格式**：非结构化 — 逐页指令式描述，供系统解析为 PageSlot 蓝图。

**备注**：这是整个 PPT 生成流程的结构基准文件。outline_system_v2.md 在此蓝图基础上为每个槽位填充具体内容。

---

## Prompt 之间的协作关系

```
intake_system.md          ──> 结构化项目信息
        │
        v
brief_doc_system.md       ──> 设计建议书大纲 (brief_doc)
        │
        ├──> visual_theme_system.md    ──> 视觉主题 (VisualTheme)
        │
        v
manus.md (蓝图结构)
   + brief_doc
        │
        v
outline_system_v2.md      ──> SlotAssignment 列表
        │
        v
composer_system_v3.md     ──> HTML 幻灯片
        │
        v
vision_design_advisor.md  ──> 视觉评审得分 + 问题列表
        │
        v
composer_repair.md        ──> 修复后的 HTML 幻灯片
```

---

## Prompt 版本管理约定

```
prompts/
├── intake_system.md             ← 当前版本
├── brief_doc_system.md          ← 当前版本
├── visual_theme_system.md       ← 当前版本
├── outline_system_v2.md         ← 当前主线版本
├── outline_system.md            ← 遗留 v1（保留备用）
├── outline.md                   ← 遗留原始版（保留备用）
├── composer_system_v2.md        ← LayoutSpec 版（保留备用）
├── composer_system_v3.md        ← 当前主线版本（HTML 直出）
├── composer_repair.md           ← 当前版本
├── vision_design_advisor.md     ← 当前版本
└── manus.md                     ← 40 页蓝图源（参考基准）
```

- Prompt 变更需记录版本号和变更原因
- 生产环境使用版本通过 `config/settings.py` 中 `PROMPT_VERSION` 控制
- A/B 测试时记录不同版本的输出质量指标
