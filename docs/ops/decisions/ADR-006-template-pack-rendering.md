---
name: ADR-006 — Template Pack 渲染管线
description: 引入 Jinja2 模板作为 Composer 第三模式；VisualTheme 单一真源；分级长度约束；chart 上游物化
status: Accepted
date: 2026-05-01
owner: superxiaoyin
---

# ADR-006：Template Pack 渲染管线

## Context

[agent/composer.py](../../../agent/composer.py) 当前是双模式：v3 直出 `body_html`（默认）与 v2 输出 `LayoutSpec` JSON。两种模式都把"内容文案 + 视觉版式"耦合在一次 LLM 调用里，导致：

1. **重复设计成本**：每页都让 LLM 现编版式，类似页（4 个 transition、9 个 concept_scheme、3 个 case_card）每次都重新发明轮子。
2. **视觉一致性弱**：哪怕 VisualTheme 锁住了 token，body_html 里的具体排版还是漂移。
3. **难以模板化的页眉页脚 / 页码 / 章节标签**：每页都靠 LLM 重画，token 浪费。
4. **关键信息页没空间被精雕**：所有 token 预算都被分散到 40 页，关键页（封面、概念方案、章节过渡）反而做不深。

外部项目 [d:\projects\liuzong\PPT-maker\templates\minimalist_architecture\](../../../../liuzong/PPT-maker/templates/minimalist_architecture/) 提供了一套成熟的、token 驱动的 11 组件 Jinja2 模板（cover / toc / transition / policy_list / chart / table / image_grid / content_bullets / case_card / concept_scheme / ending），覆盖 manus.md 40 页中约 90% 的可模板化页型。其 `theme.json` 与本项目 [schema/visual_theme.py:VisualTheme](../../../schema/visual_theme.py#L70-L89) 重合度高但不完全对齐。

需要回答 5 个相互关联的设计决策：

1. 是否引入 Jinja2 模板？
2. 模板与 v3 的关系：替换还是并存？
3. 主题：双源还是单源？
4. LLM 与"整体视觉风格"的关系：自由生成 / pack 选择 / 混合？
5. chart 组件接口与项目素材形态不匹配，谁让步？

## Options Considered

### 1. 是否引入 Jinja2 模板

| 方案 | 评估 |
|------|-----|
| A：完全不用模板，继续 v3 直出 | ❌ 重复设计、视觉漂移、关键页做不深 |
| **B：引入 11 组件 Jinja2 模板**（选） | ✅ 成熟代码，0 设计成本；token 节约可投入关键页；视觉一致性强 |
| C：自研模板系统（不用 Jinja2） | ❌ Python 生态 Jinja2 是默认选择，自研无收益 |

### 2. 模板与 v3 的关系

| 方案 | 评估 |
|------|-----|
| A：模板替换 v3，全量迁移 | ❌ 风险高，回退困难；少数关键创意页（封面变体、综合分析页）受限 |
| **B：模板作为 Composer 第三模式（template / html_free / layout_spec），按蓝图 PageSlot.template_component 字段分发**（选） | ✅ 非破坏迁移；逐页验证；template 失败可优雅回退 html_free |
| C：模板作为渲染层独立组件（不进 Composer） | ❌ 违背项目"Composer 是唯一内容生成入口"的现有架构 |

### 3. 主题：双源还是单源

| 方案 | 评估 |
|------|-----|
| A：保留模板自带的 `theme.json`，与 VisualTheme 并行 | ❌ 双源同步成本；LLM 生成的 VisualTheme 用不上；运维混乱 |
| **B：删除模板的 `theme.json`，VisualTheme 是唯一真源；模板的 CSS 变量批量改名对齐 [render/engine.py:generate_theme_css](../../../render/engine.py#L92) 已有的 `--color-*` 命名**（选） | ✅ 单源；LLM 生成的颜色直接生效；运维简单 |
| C：保留双源，VisualTheme 转 theme.json 再喂模板 | ❌ 中间 adapter 层无价值，徒增复杂度 |

### 4. LLM 与整体视觉风格

| 方案 | 评估 |
|------|-----|
| A：LLM 完全自由生成 palette + 字体 + 装饰 | 现状（[agent/visual_theme.py](../../../agent/visual_theme.py)），偶有视觉不协调，但已经在跑 |
| B：手工 N 个 pack，LLM 只选 pack 不调 token | ❌ 失去"主题与项目内容匹配"的灵活性 |
| **C：手工 N 个 pack 圈定调性，LLM 在 pack 范围内填 token + 选章节口音色**（最终目标，本期先做基础） | ✅ 既保创造力又保不翻车；本期先把 pack 字段和 section_colors 加进 schema，第 2/3 个 pack 留下一轮 |
| D：完全锁死手工 theme | ❌ 需求明确说"整体视觉风格由 LLM 决定是必须的" |

### 5. chart 组件接口

模板 [chart.html.j2:41](../../../../liuzong/PPT-maker/templates/minimalist_architecture/components/chart.html.j2#L41) 只接受图片路径；项目里 chart 数据形态分两种：(a) 已是预渲染图（`economy.*.chart.{N}`），(b) 是 structured_data（`site.poi.table`）。

| 方案 | 评估 |
|------|-----|
| A：扩展模板，让 chart 组件也能消费 structured_data 内联 SVG/Canvas | ❌ 模板逻辑膨胀；前端图表库引入复杂依赖 |
| **B：上游加 `chart_materialize` 步骤，把 structured_data → matplotlib → PNG → Asset → 回填 chart_path；模板不动**（选） | ✅ 复用已有 [tool/asset/chart_generation.py](../../../tool/asset/chart_generation.py)；模板纯净；chart_path 与已有预渲染图统一 |
| C：所有 chart 数据上游强制预渲染（删除 (a) 路径） | ❌ 违背"仅利用当前项目已有的素材"原则 |

## Decision

1. **引入 Jinja2 模板**（Q1: B）。
2. **作为 Composer 第三模式 `template`**，与 `html_free` (v3) / `layout_spec` (v2) 并存（Q2: B）。优先级由 [config/ppt_blueprint.py](../../../config/ppt_blueprint.py) 中每个 `PageSlot.template_component` 字段决定；template 模式失败回退 html_free。
3. **VisualTheme 单一真源**（Q3: B）。删除模板自带 `theme.json`；模板 CSS 变量改名对齐 `--color-*` / `--font-*` / `--space-*` 等 generate_theme_css 已有命名。VisualTheme 新增 `section_colors / template_pack` 字段。
4. **本期落基础设施**（Q4: C 的第一阶段）：
   - VisualTheme 加 `template_pack: Literal[...]` 字段，本期固定单值 `"minimalist_architecture"`
   - VisualTheme 加 `section_colors: list[str]` 字段，由 LLM 根据 BriefDoc 章节调性生成
   - "LLM 选 pack" 机制 + 第 2/3 个 pack 列入未来改进，单独 ADR
5. **chart 上游物化**（Q5: B）：新建 `agent/chart_materialize.py`，在 Composer 产出 SlideData 之后、入库 Slide 之前调用；color_scheme 由 VisualTheme 派生。

### 配套规则

- **template 模式永远不让 LLM 产 HTML/CSS**，只产符合 `SlideData` schema 的结构化 JSON（11 个子模型）。
- **长度约束**：每个 SlideData 子模型用 Pydantic `max_length / max_items` 强约束。校验失败 → LLM 重试一次（带超长字段长度反馈）→ 仍失败 → 调 `truncate_to_schema` 截断兜底。上限值集中放 `config/slide_data_limits.py`。
- **40 不写死**：`total_pages / page_ranges / 章节数 / section_colors` 全部由 `agent/slide_plan.py` 装配产生并以 context 注入模板。

## Consequences

### 好处

- **视觉一致性**：所有可模板化页型走相同结构，token 不再被浪费在重复版式上。
- **关键页有空间被精雕**：v3 (html_free) 留给真正需要创造力的页（封面变体、综合分析页）。
- **新组件低成本**：增加一种页型 = 加一个 .j2 + 一个 SlideData 子模型，不改 Composer。
- **回退路径明确**：template 失败 → html_free → 占位灰底，三级降级，永不阻塞 PDF。
- **concept_render 立即受益**：第 29-37 页 9 张图直接对接 concept_scheme 模板，零数据装配代码。

### 代价

- **Composer 复杂度上升**：三模式分发 + 长度校验 + 重试 + 兜底，新增约 200 行逻辑。
- **模板维护**：模板改造（删 theme.json + 改名 + 解硬编码）一次性工作，但后续模板改动需要工程参与（设计师不能直接改）。
- **VisualTheme 与模板的色域耦合**：本期单 pack，若 VisualTheme 生成深色 / 高饱和 palette，模板视觉可能显怪（详见 brief 第 8 节风险 2）。短期对策：模板内只支持 light/dark 两套兜底；长期对策：多 pack。
- **测试覆盖增加**：11 组件 × fixture + Composer 三模式分发 + 回退路径，CI 时间 +30%。

### 前提 / 未来评估点

- **第 2、3 个 template_pack 与 "LLM 选 pack" 机制**：本期 schema 字段已留好，下一轮 brief（约 3-4 周后）落地。彼时再决定 `template_pack` 是 `Literal[...]` 还是 dynamic enum。
- **chart_materialize 性能与字体兼容**：开发机和容器中文字体表现可能不同，启动时探测；若 PNG 生成成为瓶颈，考虑改用 echarts-server / playwright 截图 SVG。
- **VisualTheme seed 一致性**：同项目重生成时 section_colors 应稳定，需在 LLM 调用时引入 `seed=hash(project_id)`，列入 PR-5 验收。
- **template 模式 fallback 率监控**：`composer_template_fallback_total / composer_template_total` 阈值 10%，超过则视为 prompt / schema 设计问题。

### 修改文件

见 [briefs/2026-05-01-template-pack-rendering.md](../briefs/2026-05-01-template-pack-rendering.md) 第 6.2 节文件改动清单（28 个文件）。

---

## 关联

- **Brief**：[briefs/2026-05-01-template-pack-rendering.md](../briefs/2026-05-01-template-pack-rendering.md)
- **依赖**：[ADR-005](ADR-005-concept-render-via-outline.md)（concept_render 已就绪，是本 ADR 的零阻力切入点）
- **被依赖**：未来 ADR-007（多 pack + LLM 选 pack）、ADR-008（template-mode 局部重写）
- **Supersedes**：无
