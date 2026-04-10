# 05. Agent 状态流转设计

> 最后更新：2026-04-10
>
> 项目当前存在两条并行路径：素材包驱动（主路径）和旧路径（案例推荐 + 数据采集）。
> 两条路径在 OUTLINE_READY 之后合流。

---

## 5.1 项目级状态机

```
                        ┌─────────────────────────────────────────┐
                        │           项目状态机                     │
                        └─────────────────────────────────────────┘

 ═══ 路径 A：素材包驱动（主路径）═══        ═══ 路径 B：案例推荐 + 数据采集 ═══

    [素材包本地目录]                           [用户创建项目]
          │                                        │
          ▼                                        ▼
    ┌───────────┐                           ┌───────────┐
    │   INIT    │                           │   INIT    │
    └─────┬─────┘                           └─────┬─────┘
          │ POST /material-packages                │
          │   /ingest-local                        ▼
          ▼                              ┌──────────────────────┐
  ┌─────────────────┐                    │  INTAKE_IN_PROGRESS  │ ◄── 多轮对话
  │ MATERIAL_READY  │                    └──────────┬───────────┘
  └────────┬────────┘                               │ 字段确认
           │ POST /.../regenerate                   ▼
           │ (BriefDoc + Outline)        ┌──────────────────────┐
           ▼                             │  INTAKE_CONFIRMED    │
  ┌─────────────────┐                    └──────────┬───────────┘
  │ OUTLINE_READY   │                               │ 自动推进
  └────────┬────────┘                               ▼
           │                             ┌──────────────────────┐
           │◄────────────────────────────│ REFERENCE_SELECTION  │ ◄── 用户选案例
           │                             └──────────┬───────────┘
           │                                        │ confirm → VisualTheme
           │                                        ▼
           │                             ┌──────────────────────┐
           │                             │  ASSET_GENERATING    │
           │                             └──────────┬───────────┘
           │                                        │ 资产就绪 + BriefDoc + Outline
           │◄───────────────────────────────────────┘
           │
 ═══ 合流点：大纲确认 ═══════════════════════════════════════════

           │ POST /outline/confirm
           ▼
  ┌─────────────────┐
  │    BINDING      │  素材绑定（SlideMaterialBinding）
  └────────┬────────┘
           │ 绑定完成
           ▼
  ┌─────────────────┐
  │ SLIDE_PLANNING  │  Composer 并发生成 Slide（LayoutSpec / HTML）
  └────────┬────────┘
           │ 所有 Slide 生成完成
           ▼
  ┌─────────────────┐
  │   RENDERING     │  HTML → Playwright 截图 → PNG
  └────────┬────────┘
           │ 所有页面渲染完成
           ▼
  ┌─────────────────┐
  │   REVIEWING     │  规则审查 + 语义审查 + 视觉审查（可选）
  └────────┬────────┘
           │
    ┌──────┴──────┐
    │ 无 P0/P1   │ 有 P0/P1
    ▼             ▼
┌───────────────┐  修复 → RENDERING（局部重渲染）
│READY_FOR_EXPORT│
└───────┬───────┘
        │ POST /export
        ▼
  ┌─────────────┐
  │  EXPORTED   │
  └─────────────┘

  ── 任何阶段发生不可恢复错误 ──► FAILED
```

---

## 5.2 页面级状态机

```
    ┌─────────┐
    │ pending │  Slide 尚未生成
    └────┬────┘
         │ Composer 生成 LayoutSpec / HTML
         ▼
    ┌────────────┐
    │ spec_ready │
    └─────┬──────┘
          │ 渲染任务启动（HTML → Playwright → PNG）
          ▼
    ┌──────────┐
    │ rendered │
    └────┬─────┘
         │ 进入审查队列
         ▼
    ┌────────────────┐
    │ review_pending │
    └───────┬────────┘
            │
     ┌──────┴──────┐
     │             │
     ▼             ▼
┌──────────┐  ┌──────────────┐
│ review   │  │ repair_needed│
│ _passed  │  └──────┬───────┘
└────┬─────┘         │ 开始修复（repair_count < 3）
     │                ▼
     │         ┌──────────────────┐
     │         │ repair_in_progress│
     │         └──────┬───────────┘
     │                │ 修复完成，重新渲染
     │                ▼
     │         ┌──────────────┐
     │         │   rendered   │（回到审查）
     │         └──────────────┘
     │
     ▼
  ┌───────┐
  │ ready │
  └───────┘

  ── repair_count >= 3 ──► review_passed（带 P2 警告，不阻断导出）
                        或 failed（P0 问题无法修复）
```

---

## 5.3 Agent 调度架构

> **注意**：早期设计中的 LangGraph StateGraph（`agent/graph.py`、`agent/orchestrator.py`、
> `agent/asset.py`）已不再是当前实现方式。实际的 Agent 调度由 API 路由层和后台线程
> 显式编排，不通过 LangGraph 图引擎。

### 当前实际调度方式

```
API 路由层（显式编排）
│
├── POST /material-packages/ingest-local
│     → ingest_local_material_package()        [tool/material_pipeline.py]
│     → _extract_project_brief()
│     → _derive_assets()
│
├── POST /material-packages/{id}/regenerate
│     → _outline_worker() 后台线程            [api/routers/outlines.py]
│       ├── generate_brief_doc()                [agent/brief_doc.py]
│       └── generate_outline()                  [agent/outline.py]
│
├── POST /outline/confirm
│     → _compose_render_worker() 后台线程     [api/routers/outlines.py]
│       ├── bind_materials()                    [agent/material_binding.py]
│       ├── compose_all_slides()                [agent/composer.py]
│       ├── render_slide_html() × N             [render/engine.py]
│       └── screenshot_slides_batch()           [render/exporter.py]
│
├── POST /review
│     → Celery review_slides                   [tasks/review_tasks.py]
│
└── POST /export
      → _export_worker() 后台线程              [api/routers/exports.py]
        └── compile_pdf()                       [render/exporter.py]
```

---

## 5.4 各 Agent 节点职责与 IO 规范

### Intake Agent（`agent/intake.py`）

```
输入：raw_text（用户输入）、已有 brief（partial）
职责：抽取字段，识别缺失，生成追问
输出：updated brief，follow_up question，intake_complete flag
LLM：FAST_MODEL，结构化输出 ProjectBriefData
Tool：geocode_address_tool，compute_far_metrics_tool
```

### Reference Agent（`agent/reference.py`）

```
输入：confirmed brief，用户案例选择结果
职责：向量检索案例，重排，汇总偏好
输出：推荐案例列表，PreferenceSummary
Tool：reference_case_search，reference_case_rerank，preference_summary
```

### Brief Doc Agent（`agent/brief_doc.py`）

```
输入：ProjectBrief + MaterialPackage + MaterialItem（素材包路径）
      或 ProjectBrief + Asset 列表（旧路径）
职责：生成结构化叙事框架（章节 / 定位 / 设计原则 / 叙事弧线）
输出：BriefDoc（outline_json = _BriefDocLLMOutput）
LLM：STRONG_MODEL
Prompt：prompts/brief_doc_system.md
```

### Visual Theme Agent（`agent/visual_theme.py`）

```
输入：VisualThemeInput（building_type / style_preferences / dominant_styles）
职责：生成项目级视觉主题（配色 / 字体 / 间距 / 装饰 / 封面）
输出：VisualTheme ORM（theme_json）
LLM：STRONG_MODEL
Prompt：prompts/visual_theme_system.md
```

### Outline Agent（`agent/outline.py`）

```
输入：BriefDoc + PPT_BLUEPRINT + MaterialPackage + ProjectBrief
职责：按蓝图生成每页内容指令，执行素材覆盖率分析
输出：Outline ORM（spec_json = OutlineSpec，coverage_json）
LLM：STRONG_MODEL
Prompt：prompts/outline_system_v2.md
Tool：material_resolver.expand_requirement()，find_matching_items()
```

### Material Binding（`agent/material_binding.py`）

```
输入：Outline + MaterialItem + Asset
职责：为每页绑定具体素材与资产，计算覆盖率分数
输出：SlideMaterialBinding × N（每页一条）
无 LLM 调用（纯规则匹配）
```

### Composer Agent（`agent/composer.py`）

```
输入：OutlineSlideEntry + SlideMaterialBinding + VisualTheme + Asset 列表
职责：逐页生成 LayoutSpec（v2 结构化）或 body_html（v3 HTML 直出）
输出：Slide ORM × N（spec_json = LayoutSpec 或 {html_mode, body_html}）
LLM：STRONG_MODEL，按页并发（信号量限流）
Prompt：prompts/composer_system_v2.md 或 composer_system_v3.md
容错：_fallback_layout_spec() 保证不阻塞
```

### Critic Agent（`agent/critic.py`）

```
输入：rendered slides（含截图 URL），review reports
职责：分析审查结果，生成修复计划
输出：updated review_reports，repair actions
审查层：
  - 第一层 rule：layout_lint.py（无 LLM）
  - 第二层 semantic：semantic_check.py（FAST_MODEL）
  - 第三层 vision：vision_design_advisor.md（STRONG_MODEL + 多模态截图）
```

---

## 5.5 状态转移触发条件汇总

| 当前状态 | 转移条件 | 目标状态 | 触发方式 |
|---------|---------|---------|---------|
| INIT | 项目创建成功 | INTAKE_IN_PROGRESS | 自动 |
| INIT | 素材包摄入完成 | MATERIAL_READY | API: ingest-local |
| INTAKE_IN_PROGRESS | 所有必填字段确认 + confirm | INTAKE_CONFIRMED | API |
| INTAKE_CONFIRMED | 自动 | REFERENCE_SELECTION | 自动 |
| REFERENCE_SELECTION | 用户 confirm 案例选择 | ASSET_GENERATING | API: references/confirm |
| ASSET_GENERATING | 资产生成 + BriefDoc + Outline 完成 | OUTLINE_READY | Celery / 后台线程 |
| MATERIAL_READY | BriefDoc + Outline 生成完成 | OUTLINE_READY | API: regenerate → 后台线程 |
| OUTLINE_READY | 用户确认大纲 | BINDING | API: outline/confirm |
| BINDING | 素材绑定完成 | SLIDE_PLANNING | 后台线程 |
| SLIDE_PLANNING | 所有 Slide 生成完成 | RENDERING | 后台线程 |
| RENDERING | 所有页面渲染完成 | REVIEWING | 后台线程 |
| REVIEWING | 无 P0/P1 问题 | READY_FOR_EXPORT | Celery |
| REVIEWING | 有 P0/P1 需修复 | RENDERING（局部） | Celery |
| READY_FOR_EXPORT | 导出成功 | EXPORTED | API: /export |
| 任意 | 不可恢复错误 | FAILED | — |

---

## 5.6 错误处理策略

```
网络/API 超时   →  自动重试 3 次，指数退避（1s / 3s / 9s）
LLM 输出格式错误 →  自动重试 2 次，超限后记录 error，状态置 FAILED
资产生成失败    →  跳过非关键资产，记录警告；关键资产失败则 FAILED
渲染崩溃       →  单页标记 failed，其余继续；P0 页崩溃则项目 FAILED
修复超次数      →  P0 → FAILED；P1/P2 → 带警告导出
Composer 失败   →  使用 _fallback_layout_spec() 兜底，不阻塞后续
```
