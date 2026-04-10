# 建筑设计方案 PPT 专用 AI Agent 开发文档

## 1. 项目概述

### 1.1 项目背景

本项目旨在构建一个面向建筑设计方案策划场景的垂直 AI Agent 系统。系统从项目需求输入开始，经过信息采集、场地分析、参考案例检索、图表与分析资产生成、PPT 大纲规划、逐页内容生成、页面渲染、自动审查与修复，最终输出可交付的建筑设计方案汇报材料（PDF / PPTX）。

该系统的核心不是“一次性生成 PPT”，而是将建筑策划汇报流程拆解为多个可编排、可追踪、可修复的中间步骤，并通过 Agent + Tool 的方式完成。

---

### 1.2 项目目标

系统需要支持以下完整业务流程：

1. 收集项目基础信息  
   包括建筑类型、建筑面积、用地面积、容积率、风格、甲方名称、项目地址、经纬度、地块范围等。

2. 进行参考案例推荐与选择  
   基于项目类型、风格、规模等信息推荐参考案例，并支持用户从案例中勾选偏好的设计维度。

3. 生成 PPT 所需中间资产  
   包括周边分析图、统计图表、案例分析卡片、指标表、摘要说明、大纲等。

4. 生成最终 PPT  
   基于大纲、页面规划、设计系统、图表与案例素材，生成统一风格的多页 PPT。

5. 自动审查与修复  
   对内容一致性、图文匹配、版式合理性、风格一致性等进行检查，并对局部问题进行修复。

---

### 1.3 系统定位

本系统定位为：

- 建筑策划场景的垂直 AI Agent
- 多阶段多模态内容生成系统
- 中间资产驱动的工作流系统
- 带自动审查闭环的 PPT 编译系统

---

### 1.4 非目标

当前阶段不追求以下能力：

- 通用于所有行业的开放式 PPT 生成
- 无结构化输入的完全自由对话生成
- 设计师级自由编辑器
- 完全替代人工审稿
- 完全依赖单次 LLM 生成完成全部流程

---

## 2. 设计原则

### 2.1 Workflow First

本系统首先是一个工作流系统，其次才是 Agent 系统。  
必须优先保证：

- 状态明确
- 输入完整
- 中间资产可追踪
- 任务可重试
- 局部结果可修复

---

### 2.2 Asset-Centric

最终 PPT 不是系统唯一核心对象。系统应重点管理以下中间资产：

- 结构化项目信息
- 场地与区位数据
- 参考案例与标签偏好
- 图表与周边分析结果
- PPT 大纲
- SlideSpec（页面规范对象）
- 页面渲染结果
- 审查报告

---

### 2.3 Deterministic Core + Agentic Layer

系统拆分为两层：

#### 确定性层
负责：

- 字段校验
- 容积率/面积公式计算
- 地图与地块处理
- 图表生成
- 模板渲染
- 页面规则检查
- 导出 PDF / PPTX

#### Agent 层
负责：

- 信息抽取与缺失识别
- 对话追问
- 案例推荐重排
- 大纲组织
- 页面内容规划
- 审查解释与修复建议

---

### 2.4 Design System First

风格一致性不能完全交给模型临场发挥。  
系统必须预定义统一设计系统，包括：

- 字体体系
- 色彩 token
- 标题层级
- 网格系统
- 图表样式
- 图片样式
- 页脚与页码规范
- 常用页面模板

---

### 2.5 Review-Repair Loop

生成之后必须进入自动审查阶段，发现问题后优先局部修复，而不是整体重生成。

---

## 3. 总体架构

## 3.1 分层架构

系统建议分为以下 8 层：

### 1）前端交互层
负责：

- 聊天输入
- 表单输入
- 地图选点
- 地块绘制
- 案例选择
- 页面预览
- 结果导出

---

### 2）API / Orchestrator 层
负责：

- 项目创建
- 阶段推进
- Agent / Tool 编排
- 异步任务调度
- 错误重试
- 任务状态查询

---

### 3）会话状态层
负责维护当前项目状态，包括：

- 当前阶段
- 必填字段完成情况
- 项目 brief
- 已选择案例
- 已生成资产
- 当前大纲
- 当前页面版本
- 审查结果

---

### 4）领域模型层
负责统一 Schema 定义，包括：

- ProjectBrief
- SiteParcel
- ReferenceCase
- ChartAsset
- OutlineSpec
- SlideSpec
- ReviewReport
- DeckArtifact

---

### 5）Tool / Skill 层
负责封装具体能力，例如：

- 地理编码
- 地块处理
- 案例检索
- 图表生成
- 大纲生成
- 页面规划
- HTML 渲染
- 审查与修复

---

### 6）Agent 层
负责推理与决策，建议拆分为多个专职 Agent。

---

### 7）Render / Compile 层
负责：

- 页面 HTML 渲染
- 页面截图
- PDF 导出
- PPTX 组装

---

### 8）存储与基础设施层
负责：

- PostgreSQL
- Redis
- 对象存储
- 向量检索库
- 搜索引擎
- 异步任务队列

---

## 4. 核心业务流程

## 4.1 主流程

### 阶段 1：项目信息采集

采集内容：

- 建筑类型
- 建筑面积
- 用地面积
- 容积率
- 风格
- 甲方名称
- 地址
- 经纬度
- 地块范围

说明：

- 建筑面积、用地面积、容积率三者至少输入两项
- 第三项可由系统自动计算

---

### 阶段 2：参考案例推荐与选择

根据：

- 建筑类型
- 风格
- 规模
- 地域偏好
- 功能偏好

推荐若干案例，并支持用户选择案例标签。

案例标签包括：

- 造型
- 材质
- 交通组织
- 功能配比
- 绿色可持续性

---

### 阶段 3：中间资产生成

生成用于 PPT 的各类资产，例如：

- 项目基础指标表
- 区位图
- 周边配套图
- 交通可达性图
- 区域统计图
- 案例分析卡片
- 案例对比表
- 文字摘要
- PPT 大纲

---

### 阶段 4：PPT 规划与生成

包括：

- 大纲生成
- SlideSpec 生成
- 页面内容填充
- 页面渲染
- 页面审查
- 局部修复
- 导出最终成果

---

## 5. Agent 设计

## 5.1 Orchestrator Agent

### 职责
负责全局流程控制，不直接生成具体内容。

### 功能
- 读取项目状态
- 决定下一步任务
- 调用其他 Agent 或 Tool
- 处理失败与重试
- 控制阶段流转

---

## 5.2 Intake Agent

### 职责
负责项目信息理解与追问。

### 功能
- 从自然语言提取项目字段
- 判断缺失字段
- 生成追问内容
- 输出结构化 ProjectBrief

---

## 5.3 Reference Agent

### 职责
负责案例推荐与偏好总结。

### 功能
- 案例召回
- 案例重排
- 标签分析
- 用户偏好聚合
- 输出案例摘要

---

## 5.4 Asset Agent

### 职责
负责决定需要生成哪些资产。

### 功能
- 规划图区与分析资产
- 调用图表生成 Tool
- 生成周边分析资产
- 组织案例分析资产

---

## 5.5 Outline Agent

### 职责
负责整套 PPT 的叙事组织。

### 功能
- 确定章节结构
- 确定每页目的
- 组织叙事顺序
- 输出 OutlineSpec

---

## 5.6 Slide Composer Agent

### 职责
负责页面级内容规划。

### 功能
- 把 OutlineSpec 转为 SlideSpec
- 决定页面模板
- 决定文字块、图片块、图表块
- 控制内容密度

---

## 5.7 Critic Agent

### 职责
负责审查与修复建议。

### 功能
- 分析规则审查结果
- 分析多模态审查结果
- 输出修复计划
- 决定是否局部重生成

---

## 6. Tool / Skill 设计

## 6.1 项目输入类 Tool

- `extract_project_brief_tool`
- `validate_project_brief_tool`
- `compute_far_metrics_tool`
- `geocode_address_tool`
- `normalize_site_polygon_tool`

---

## 6.2 场地分析类 Tool

- `site_context_search_tool`
- `poi_retrieval_tool`
- `mobility_analysis_tool`
- `regional_stats_tool`
- `site_summary_tool`

---

## 6.3 案例类 Tool

- `reference_case_search_tool`
- `reference_case_rerank_tool`
- `reference_case_tagging_tool`
- `reference_preference_summary_tool`

---

## 6.4 资产生成类 Tool

- `chart_generation_tool`
- `map_annotation_tool`
- `case_comparison_asset_tool`
- `text_summary_asset_tool`

---

## 6.5 大纲与页面类 Tool

- `outline_generation_tool`
- `slide_spec_generation_tool`
- `slide_content_fit_tool`
- `deck_style_resolution_tool`

---

## 6.6 渲染类 Tool

- `html_slide_render_tool`
- `slide_screenshot_tool`
- `deck_pdf_export_tool`
- `deck_pptx_compile_tool`

---

## 6.7 审查类 Tool

- `layout_lint_tool`
- `semantic_consistency_check_tool`
- `vision_review_tool`
- `deck_consistency_review_tool`
- `repair_plan_tool`

---

## 7. 核心数据模型

## 7.1 ProjectBrief

```json
{
  "project_id": "proj_xxx",
  "building_type": "museum",
  "client_name": "xxx文化集团",
  "style_preferences": ["modern", "minimal"],
  "site_address": "天津市主城区...",
  "longitude": 117.19,
  "latitude": 39.13,
  "parcel_geojson": {},
  "gross_floor_area": 12000,
  "site_area": 10000,
  "far": 1.2,
  "status": "confirmed"
}
```

---

## 7.2 ReferenceCase

```json
{
  "case_id": "case_xxx",
  "title": "某文化建筑案例",
  "architect": "XXX Design",
  "location": "中国",
  "building_type": "museum",
  "style_tags": ["modern", "cultural"],
  "feature_tags": ["造型", "材质", "交通组织"],
  "images": [],
  "summary": "..."
}
```

---

## 7.3 SelectedReference

```json
{
  "project_id": "proj_xxx",
  "case_id": "case_xxx",
  "selected_tags": ["造型", "材质"],
  "selection_reason": "偏好轻盈立面与文化建筑气质"
}
```

---

## 7.4 ChartAsset

```json
{
  "asset_id": "asset_chart_001",
  "project_id": "proj_xxx",
  "asset_type": "chart",
  "subtype": "regional_stats",
  "title": "区域经济与人口趋势",
  "data_json": {},
  "image_url": "...",
  "summary": "..."
}
```

---

## 7.5 OutlineSpec

```json
{
  "outline_id": "outline_v1",
  "project_id": "proj_xxx",
  "deck_title": "xxx项目概念方案汇报",
  "theme": "modern-cultural-minimal",
  "slides": []
}
```

---

## 7.6 SlideSpec

```json
{
  "slide_id": "slide_04_v2",
  "project_id": "proj_xxx",
  "slide_no": 4,
  "section": "场地分析",
  "title": "周边文化与公共服务资源",
  "purpose": "论证区位潜力",
  "key_message": "项目周边已形成文化配套与公共服务节点集聚",
  "layout_template": "map-left-insight-right",
  "blocks": [],
  "style_tokens": {},
  "review_status": "pending"
}
```

---

## 7.7 ReviewReport

```json
{
  "review_id": "review_slide_04_v1",
  "target_type": "slide",
  "target_id": "slide_04_v2",
  "severity": "P1",
  "issues": [
    {
      "code": "TEXT_OVERFLOW",
      "message": "右侧文本区域溢出",
      "suggested_fix": "将 bullet 数量压缩为 3 条"
    }
  ],
  "final_decision": "repair_required"
}
```

---

## 8. 状态机设计

## 8.1 项目级状态

- `INIT`
- `INTAKE_IN_PROGRESS`
- `INTAKE_CONFIRMED`
- `REFERENCE_SELECTION`
- `ASSET_GENERATING`
- `OUTLINE_READY`
- `SLIDE_PLANNING`
- `RENDERING`
- `REVIEWING`
- `READY_FOR_EXPORT`
- `EXPORTED`
- `FAILED`

---

## 8.2 状态转移规则

### INIT -> INTAKE_IN_PROGRESS
项目创建成功

### INTAKE_IN_PROGRESS -> INTAKE_CONFIRMED
满足以下最小条件：

- building_type 已确认
- 地址或地图点位已确认
- 地块范围已确认
- 指标三项中至少两项已确认
- 风格已确认
- client_name 已确认

### INTAKE_CONFIRMED -> REFERENCE_SELECTION
项目信息确认完成

### REFERENCE_SELECTION -> ASSET_GENERATING
案例选择完成

### ASSET_GENERATING -> OUTLINE_READY
所有关键资产生成成功

### OUTLINE_READY -> SLIDE_PLANNING
大纲确认完成

### SLIDE_PLANNING -> RENDERING
所有 SlideSpec 已生成

### RENDERING -> REVIEWING
所有页面渲染成功

### REVIEWING -> READY_FOR_EXPORT
无严重问题

### READY_FOR_EXPORT -> EXPORTED
导出成功

---

## 9. 中间资产设计

## 9.1 资产类型

### 基础资产
- 项目摘要卡
- 指标表
- 用地参数表

### 场地资产
- 区位图
- 周边 POI 图
- 交通分析图
- 场地分析摘要

### 案例资产
- 案例卡片
- 案例对比表
- 标签聚合图
- 参考启发摘要

### 设计资产
- 功能分配建议
- 体量策略建议
- 材质建议
- 叙事建议

---

## 9.2 资产存储要求

每个资产必须保存以下内容：

- 原始数据 JSON
- 生成配置 JSON
- 图片或图表文件
- 摘要文本
- 来源信息
- 版本信息

---

## 10. 大纲与页面规划

## 10.1 OutlineSpec

大纲必须同时满足：

- 人可读
- 机可读
- 可追踪到每页目的
- 可关联资产

每页至少应包含：

- 页码
- 所属章节
- 页面目的
- 核心信息
- 所需资产
- 推荐模板

---

## 10.2 SlideSpec

SlideSpec 是页面级核心对象。  
每页渲染前必须先生成 SlideSpec。

字段建议包括：

- slide_no
- section
- title
- purpose
- key_message
- layout_template
- blocks
- constraints
- style_tokens

---

## 10.3 页面模板建议

建议预置模板，而不是自由布局。模板示例：

- `cover-hero`
- `overview-kpi`
- `map-left-insight-right`
- `two-case-compare`
- `gallery-quad`
- `strategy-diagram`
- `chapter-divider`
- `chart-main-text-side`
- `matrix-summary`

---

## 11. 渲染方案

## 11.1 推荐路线

建议优先采用以下渲染链路：

`SlideSpec -> HTML/CSS -> 截图/导出 PDF -> 组装 PPTX`

这样做的原因：

- HTML/CSS 对版式控制更强
- 页面调试与预览更方便
- 便于做截图级多模态审查
- 便于逐页修复

---

## 11.2 渲染子模块

- Template Resolver
- Content Fitter
- Image Placer
- Chart Embedder
- HTML Renderer
- Screenshot Exporter
- Deck Compiler

---

## 12. 审查与修复

## 12.1 审查分层

### 第一层：规则审查
检查：

- 文本溢出
- 元素重叠
- 图片比例异常
- 安全边界越界
- 必要资产缺失
- 页面空白异常
- 字数超限

---

### 第二层：语义审查
检查：

- 指标是否前后一致
- 图表与结论是否匹配
- 案例与描述是否匹配
- 页面论点是否得到支撑

---

### 第三层：多模态审查
检查：

- 页面是否拥挤
- 图片是否模糊
- 裁剪是否异常
- 焦点是否清晰
- 风格是否一致
- 图文对比度是否足够

---

## 12.2 问题分级

- `P0`：页面不可用 / 数据错误 / 严重重叠
- `P1`：重要视觉错误 / 文本溢出 / 图文不符
- `P2`：风格轻微不一致 / 留白不佳 / 文案略长

---

## 12.3 修复策略

修复优先级：

1. 自动修复规则问题
2. 局部重写内容
3. 切换模板
4. 高风险问题转人工确认

限制：

- 每页最大修复次数 `3`
- 超限后进入人工确认状态

---

## 13. 技术栈建议

## 13.1 后端
- FastAPI
- SQLAlchemy / SQLModel
- PostgreSQL
- Redis
- Celery / RQ / Dramatiq

---

## 13.2 前端
- Next.js
- TypeScript
- 地图 SDK（如高德地图）

---

## 13.3 Agent / LLM
- 支持结构化输出的 LLM
- LangGraph 或自定义状态机编排
- Pydantic schema output

---

## 13.4 渲染
- HTML/CSS 模板引擎
- Playwright 截图
- WeasyPrint / Chromium 导出 PDF
- python-pptx 组装 PPTX

---

## 13.5 检索
- pgvector / Milvus / Qdrant
- Elasticsearch / Meilisearch

---

## 14. 数据库设计建议

## 14.1 核心表

- `projects`
- `project_briefs`
- `site_locations`
- `site_polygons`
- `reference_cases`
- `project_reference_selections`
- `assets`
- `asset_versions`
- `outlines`
- `slides`
- `slide_versions`
- `reviews`
- `review_issues`
- `jobs`
- `exports`

---

## 14.2 通用字段建议

所有核心表建议包含：

- `id`
- `project_id`
- `version`
- `status`
- `created_at`
- `updated_at`

---

## 15. API 设计

## 15.1 项目接口

- `POST /projects`
- `GET /projects/{project_id}`
- `PATCH /projects/{project_id}/brief`
- `POST /projects/{project_id}/confirm-brief`

---

## 15.2 地块接口

- `POST /projects/{project_id}/site/point`
- `POST /projects/{project_id}/site/polygon`
- `GET /projects/{project_id}/site`

---

## 15.3 案例接口

- `POST /projects/{project_id}/references/recommend`
- `POST /projects/{project_id}/references/select`
- `POST /projects/{project_id}/references/refresh`

---

## 15.4 资产接口

- `POST /projects/{project_id}/assets/generate`
- `GET /projects/{project_id}/assets`

---

## 15.5 大纲与页面接口

- `POST /projects/{project_id}/outline/generate`
- `GET /projects/{project_id}/outline`
- `POST /projects/{project_id}/slides/plan`
- `GET /projects/{project_id}/slides`

---

## 15.6 渲染与审查接口

- `POST /projects/{project_id}/render`
- `POST /projects/{project_id}/review`
- `POST /projects/{project_id}/repair`
- `POST /projects/{project_id}/export`

---

## 16. MVP 规划

## 16.1 MVP 范围

建议第一阶段仅支持：

- 2~3 类建筑项目
- 8~10 页固定结构 PPT
- 有限案例库
- 有限页面模板
- PDF 导出优先
- 手动确认少量关键节点

---

## 16.2 MVP 功能列表

- 项目信息采集
- 地图选点 + 地块绘制
- 案例推荐与标签选择
- 周边分析图生成
- 一类统计图生成
- 案例对比卡片生成
- 大纲生成
- SlideSpec 生成
- HTML 渲染
- 规则审查
- PDF 导出

---

## 16.3 V2 规划

- 多模态审查
- 自动局部修复
- 原生 PPTX 导出
- 页面手动微调
- 模板切换
- 联网搜索补充案例与素材

---

## 17. 可观测性与运维

## 17.1 日志

必须记录：

- Tool 调用输入输出摘要
- Agent 决策摘要
- 渲染日志
- 审查日志
- 修复日志

---

## 17.2 指标

建议监控：

- 项目平均完成时间
- 每阶段失败率
- 页面平均修复次数
- 导出成功率
- 审查通过率
- 人工干预率

---

## 17.3 审计

建议保留以下记录：

- 数据来源
- 资产版本
- 页面版本
- 导出版本
- 人工确认记录

---

## 18. 推荐开发顺序

## Phase 1：基础闭环
- Schema 定义
- 项目状态机
- 项目信息采集
- 案例推荐
- 资产生成
- OutlineSpec / SlideSpec
- HTML 渲染
- PDF 导出

---

## Phase 2：质量增强
- 规则审查
- 语义审查
- 局部修复能力

---

## Phase 3：高级能力
- 多模态审查
- 原生 PPTX 导出
- 页面级交互修订
- 联网内容增强

---

## 19. 总结

本系统不是简单的“AI 生成 PPT”，而是一个面向建筑策划场景的多阶段 Agent 工作流系统。  
其核心成功因素不在于单次模型生成能力，而在于：

- 统一的领域模型
- 明确的项目状态机
- 中间资产驱动
- 设计系统约束
- 页面级 SlideSpec 抽象
- 渲染、审查、修复闭环

推荐实现路线为：

**ProjectBrief -> Asset Generation -> OutlineSpec -> SlideSpec -> HTML Render -> Review -> Repair -> Export**

该路线能够在保证可控性的同时，逐步提升视觉质量与自动化水平。

