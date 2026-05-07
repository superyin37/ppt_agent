# 29 — 当前 PPT 生成链路 QA

> 记录时间：2026-05-07  
> 范围：当前仓库代码中的素材包到 PPT/PDF 生成链路，重点参考 `scripts/material_package_e2e.py`、`api/routers/outlines.py`、`agent/composer.py`、`agent/visual_theme.py`、`agent/material_binding.py`、`config/ppt_blueprint.py`。

---

## Q1. 当前 PPT 生成链路能不能根据项目大纲动态决定部分视觉设计，比如主题颜色？

可以，但要区分链路入口。

- `scripts/material_package_e2e.py` 会在 `generate_brief_doc()` 之后调用 `build_theme_input_from_package()` 和 `generate_visual_theme()`，由 LLM 生成 `VisualTheme`，包括 `colors`、`style_keywords`、`section_colors`、`template_pack` 等。
- `build_theme_input_from_package()` 会读取素材包中的 `brief.design_outline`（设计建议书大纲）、`BriefDoc.outline_json.chapters`、`recommended_emphasis`、参考案例风格标签和项目风格偏好。因此它能根据项目大纲/章节叙事动态影响主题颜色和章节口音色。
- 但它不是直接读取最终 `OutlineSpec.slides` 来逐页定色；当前更准确的说法是：基于素材包设计大纲 + BriefDoc 章节结构生成项目级视觉主题。
- HTTP 主流程目前不稳定自动生成 VisualTheme：`api/routers/outlines.py::_outline_worker()` 只生成 BriefDoc 和 Outline；`_compose_render_worker()` 渲染时读取最新主题，找不到就用 `_default_theme()`。所以如果没有通过 e2e 脚本或 reference/theme 流程预先生成主题，HTTP 主流程会回退默认主题。

结论：能力已经有，e2e 素材包脚本已接入；HTTP 主流程仍可能走默认主题。

---

## Q2. 当前 e2e 链路有没有开启视觉审查？

默认没有完整开启。

- `scripts/material_package_e2e.py` 默认是 mock LLM 模式，此时 `_render_and_review(..., skip_review=not args.real_llm)` 会跳过真实 review。
- 加 `--real-llm` 后，e2e 会跑视觉审查：
  - `html` / `template` 模式：只跑 `layers=["vision"]`，因为规则/语义 lint 对 HTML fallback spec 不可靠。
  - `structured` 模式：跑 `layers=["rule", "semantic", "vision"]`。
- 设计评分类的 Design Advisor 不是默认开启，必须额外传 `--design-review`。开启后会输出 `design_scores.json` 和 `design_scores_summary.txt`。

结论：e2e 默认不做真实视觉审查；`--real-llm` 开启 vision review；`--design-review` 才开启额外设计评分 gate。

---

## Q3. 当前 PPT 生成链路中是不是大量使用模板？哪些页面没有使用模板？

默认链路不是大量使用模板。

当前默认 composer mode 是 `html`：

- `config/settings.py` 默认 `composer_mode = "html"`。
- `api/routers/outlines.py::_compose_render_worker()` 显式调用 `compose_all_slides(..., mode=ComposerMode.HTML)`。
- `tasks/outline_tasks.py::compose_slides_task()` 也显式使用 `ComposerMode.HTML`。
- `scripts/material_package_e2e.py` 默认 `--composer-mode html`。

因此默认情况下，页面由 LLM 直接输出 `body_html`，不是 Jinja2 template 渲染。

模板模式已经实现为可选模式：

- 需要显式传 `--composer-mode template`，或代码里调用 `compose_all_slides(..., mode=ComposerMode.TEMPLATE)`。
- `config/ppt_blueprint.py` 中大多数 slot 都配置了 `template_component`，会映射到 11 个 Jinja2 组件之一：`cover`、`toc`、`transition`、`policy_list`、`chart`、`table`、`image_grid`、`content_bullets`、`case_card`、`concept_scheme`、`ending`。
- 目前蓝图里明确没有模板组件的是 `competitor-web`（行业竞品搜索分析），注释说明 WEB_SEARCH 未实装时回退 `html_free`。
- 即使 slot 配了模板，如果 template data 生成失败，也会回退 HTML 模式。

结论：默认链路不大量使用模板；template 模式下几乎全页可模板化，明确未模板化的是 `competitor-web`，失败页也会回退 HTML。

---

## Q4. 当前链路中哪些步骤实际调用了大模型？

实际 LLM 调用点如下：

1. `generate_brief_doc()`  
   用 LLM 从素材包摘要、manifest、文本摘录生成 BriefDoc。

2. `generate_visual_theme()`  
   用 LLM 生成项目级视觉主题，包括颜色、字体、装饰风格、section colors。

3. `generate_outline()`  
   用 LLM 基于 PPT_BLUEPRINT、BriefDoc、素材包 manifest 生成每页 slot assignment，并输出概念方案结构。

4. `compose_all_slides()`  
   默认 `html` 模式下，每页调用 LLM 生成 `body_html`。  
   `structured` 模式下，每页调用 LLM 生成 `LayoutSpec`。  
   `template` 模式下，部分页面可由代码确定性生成 SlideData；不能确定性生成的页面会调用 LLM 生成符合模板 schema 的 JSON，失败后再回退 HTML。

5. `recompose_slide_html()`  
   HTML 页面审查后需要修复时，会调用 LLM 重新生成页面 HTML。

6. `semantic_check()`  
   语义审查层调用文本 LLM。

7. `_vision_review()`  
   视觉审查层调用多模态 LLM。

8. `_design_review()`  
   Design Advisor 调用多模态 LLM，默认 e2e 不启用，需 `--design-review`。

不调用 LLM 的步骤包括：素材包摄入、logical_key 推断、MaterialItem/Asset 派生、SlideMaterialBinding 绑定、模板渲染、Playwright 截图、PDF 合成、chart_materialize 本地图表物化。

---

## Q5. 当前链路中每个 slide 页面的文字部分具体如何生成？是仅提取素材包中的大纲内容还是经过 LLM 处理？

不是仅提取素材包大纲，默认链路会经过多轮 LLM 处理。

默认 `html` 模式下的文字来源链路是：

1. 素材包摄入阶段把 `设计建议书大纲` 识别为 `brief.design_outline`，并作为事实源之一。
2. `generate_brief_doc()` 用 LLM 把素材包摘要和大纲整理成 BriefDoc：章节、关键发现、叙事方向、推荐强调点。
3. `generate_outline()` 用 LLM 把 BriefDoc + PPT_BLUEPRINT + 素材包 manifest 转成每页 `OutlineSlideEntry`，包括 `title`、`purpose`、`key_message`、`required_input_keys`。
4. `bind_outline_slides()` 用 deterministic matching 给每页绑定素材和 evidence snippets。
5. `compose_all_slides(..., mode=HTML)` 再把 `visual_theme`、`outline_entry`、`project_brief`、`slide_material_binding`、`available_assets` 一起交给 LLM，由 LLM 输出最终页面 `body_html` 和 `content_summary`。

template 模式下更混合：

- 一些页会由代码确定性组装文字，例如封面、目录、章节页、结尾、部分图文网格、案例卡、概念鸟瞰页等。
- 一些页会从 `entry.key_message`、`binding.evidence_snippets`、素材摘要、表格预览中截取和压缩。
- 不能确定性生成的模板页会调用 `compose_template_slide()`，由 LLM 输出受 schema 限制的 SlideData。

结论：当前默认产物的页面文字不是素材包大纲的直接搬运，而是 `素材包事实源 → BriefDoc LLM → Outline LLM → Composer LLM` 的加工结果；template 模式会把部分页面降为代码确定性装配。

---

## Q6. 当前链路中一共用到素材包中的多少图表？每一张图表分别被绑定到哪一页？如何决定绑定关系？

以当前 `test_material/project2` 素材包为例，素材包中会被识别为经济图表的文件共 7 张：

| 图表文件 | logical_key | 有效使用页 |
|---|---|---|
| `GDP及其增速_688.png` | `economy.city.chart.0` | `economic-1`：经济背景分析 1/3 |
| `常驻人口及其增速_688.png` | `economy.city.chart.1` | `economic-1`：经济背景分析 1/3 |
| `城镇化率_688.png` | `economy.city.chart.2` | `economic-1`：经济背景分析 1/3 |
| `产业结构_688.png` | `economy.industry.chart.0` | `economic-2`：经济背景分析 2/3 |
| `第三产业发展情况及其产业增速_688.png` | `economy.industry.chart.1` | `economic-2`：经济背景分析 2/3 |
| `消费品零售总额发展情况_688.png` | `economy.consumption.chart.0` | `economic-3`：经济背景分析 3/3 |
| `城镇居民人均收支情况_688.png` | `economy.consumption.chart.1` | `economic-3`：经济背景分析 3/3 |

绑定关系分两层：

1. `bind_outline_slides()` 的数据库绑定层  
   `economic-pages` 蓝图的 `required_inputs` 包含 7 个经济图表输入。由于 alias 会展开为 `economy.city.chart.*`、`economy.industry.chart.*`、`economy.consumption.chart.*`，所以三张 `economic-*` 页面在 `SlideMaterialBinding.derived_asset_ids` 中可能都会匹配到全部 7 个经济图表。

2. `composer` 的有效选择层  
   `agent/composer.py::_assets_for_entry()` 和 `_select_image_grid_assets()` 对具体 slot 做二次筛选：
   - `economic-1` 偏好 `economy.city`，因此使用 GDP、常驻人口、城镇化率 3 张。
   - `economic-2` 偏好 `economy.industry`，因此使用产业结构、第三产业 2 张。
   - `economic-3` 偏好 `economy.consumption`，因此使用消费品零售、人均收支 2 张。

另外还有两类“图表页”不属于素材包中已有图表：

- `policy-impact`：代码可生成 `chart_spec`，再由 `chart_materialize` 用 matplotlib 物化成 PNG。
- `poi-analysis`：从 `场地poi_688.xlsx` 的表格数据物化成柱状图。

结论：project2 素材包中当前可直接使用的经济图表是 7 张；有效落页为 `economic-1/2/3` 三页，按 `logical_key` 前缀和 slot id 的硬编码偏好决定。数据库绑定层较宽，最终页面使用层较窄。
