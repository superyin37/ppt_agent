---
name: ADR-006 — HTML 模式作为主流程并推进 Bold Visual Design
description: 将 Composer v3 HTML 模式设为产品主路径,以更大胆的 VisualTheme、HTML 设计 prompt 和 Design Advisor gate 提升视觉表现
status: Accepted
date: 2026-04-25
owner: superxiaoyin
---

# ADR-006:HTML 模式作为主流程并推进 Bold Visual Design

## Context

当前 Composer 已有两条路径:

- v2 structured:`LLM -> LayoutSpec JSON -> 固定渲染函数 -> HTML`
- v3 html:`LLM -> body_html -> sanitize + theme CSS 注入 -> HTML`

v2 的优势是稳定、可 lint、可结构化修复;问题是视觉表现受 11 种布局原语限制,输出容易回到普通图文排版。v3 的优势是可直接使用 HTML/CSS/SVG 做非对称构图、满版色块、海报式排版和复杂视觉层次,更适合建筑方案汇报中“鲜艳大胆、更有设计感”的目标。

目前文档和 E2E 脚本倾向 HTML 默认,但代码入口仍存在默认 structured 的路径:

- `agent/composer.py` 的 `compose_slide()` / `compose_all_slides()` 默认值为 `ComposerMode.STRUCTURED`
- `tasks/outline_tasks.py` 和 `api/routers/outlines.py` 未显式传入 `ComposerMode.HTML`
- `scripts/material_package_e2e.py` 的 CLI 默认是 `--composer-mode html`

这导致“产品主链路到底默认走哪条”存在事实不一致。

## Options Considered

| 方案 | 评估 |
|------|------|
| A:继续 structured 默认,只增强 VisualTheme | 主题会变大胆,但固定渲染函数仍会压制设计自由度,收益有限 |
| **B:HTML 模式作为产品主流程,structured 保留为 fallback/debug**(选) | 符合视觉升级目标;现有 v3、sanitize、vision review、recompose 已具备基础 |
| C:扩展 LayoutSpec 增加更多装饰字段 | 每种新视觉都要加 schema 和 renderer,迭代成本高,仍追不上设计需求 |
| D:完全删除 structured | 风险过高;structured 仍适合作为稳定回退、测试基准和结构化审查路径 |

## Decision

- **主流程默认使用 Composer v3 HTML 模式**。API/Celery/E2E 应显式传 `ComposerMode.HTML`,避免依赖函数默认值。
- **structured 保留**为 fallback/debug/对照测试模式,不在本阶段删除。
- **VisualTheme 扩展为更强的设计方向输入**。除基础色彩/字体/间距外,引入视觉强度、配色策略、构图风格、装饰母题等字段或 prompt 约束。
- **Composer v3 prompt 强化为“设计生成器”而不是“HTML 排版器”**。要求每页有视觉焦点、明确层级、非模板化构图,并按页面类型制定策略。
- **Design Advisor 从建议升级为 gate**。低分或关键建议码触发 HTML recompose,形成 render -> vision/design review -> recompose -> re-render 回环。
- **默认视觉强度为 `bold`**。保留后续支持 `standard / bold / experimental` 的运行参数。
- **允许深色/混合色彩模式**。不再要求全 deck 极浅背景;封面、章节页、概念方案页可使用深色或强色背景,内容页可按可读性混用浅底。

## Implementation Status

2026-04-25 已完成第一轮落地:

- `COMPOSER_MODE=html` 成为配置默认值,structured 保留为可选模式。
- API/Celery outline 入口显式传入 `ComposerMode.HTML`,render 阶段兼容 `spec_json.html_mode`。
- VisualTheme schema 已扩展 bold visual 字段,并传入 HTML composer / recompose 的 theme context。
- `visual_theme_system.md`、`composer_system_v3.md`、`composer_repair.md` 已加入深色/混合背景、高饱和 accent、页面类型策略、素材驱动策略和结构性 repair 规则。
- HTML review 已启用 Design Advisor gate:`overall_score`、`focal_point`、`polish` 和重点页 `D012` 可转为 recompose issue。

2026-04-25 已执行真实 LLM smoke:

- `scripts/material_package_e2e.py test_material/project1 --real-llm --max-slides 3 --output-dir test_output/html_bold_design_smoke` 成功,输出 `run_20260425T111220Z`;3 页 `html_mode=true`,PDF 导出成功。
- `--design-review` smoke 成功产出 `design_scores.json`,但最新 run 暴露两个后续加固点:slide 01 Design Advisor 多模态 JSON 解析失败导致无评分;slide 03 最终仍有 `V007` P2 repair_required。

剩余:加固 Design Advisor 输出解析/重试与 E2E 对 residual repair_required 的失败判定。

## Composer v3 HTML Improvement Spec

ADR-006 的核心不是“让 LLM 输出 HTML”本身,而是给 v3 HTML 模式补足一套可执行的设计约束。v3 应从“把内容排进页面”升级为“生成可截图的设计稿”。

### 1. 设计契约

每页 HTML 必须同时满足 5 个设计契约:

| 契约 | 要求 |
|------|------|
| 单一视觉焦点 | 第一眼能看到一个明确主视觉:大标题 / 大图 / KPI 巨字 / 地图节点 / 方案图 |
| 信息层级 | 至少 3 层:主标题或主数字、支撑结论、细节/注释 |
| 构图意图 | 使用非对称、满版、强网格、海报式或展板式布局,避免平均分栏和卡片堆叠 |
| 主题一致 | 所有颜色/字体/间距优先用 VisualTheme CSS variables,硬编码颜色只用于局部透明度或 SVG 辅助 |
| 截图安全 | 1920x1080 内无滚动、无遮挡、无外链、无交互控件、无超出安全区的核心信息 |

### 1.1 VisualTheme Bold Extensions

VisualTheme 需要从“基础设计 token”扩展为“视觉方向控制器”。第一阶段可先写入 prompt 和 `generation_prompt_hint`,第二阶段再扩 schema。

建议新增字段:

```python
color_mode: Literal["light", "dark", "mixed"]
contrast_level: Literal["standard", "high", "dramatic"]
accent_saturation: Literal["normal", "high", "neon"]
font_mood: Literal["classic", "modern", "editorial", "experimental"]
visual_intensity: Literal["standard", "bold", "experimental"]
```

字段语义:

| 字段 | 设计含义 |
|------|----------|
| `color_mode=light` | 内容页浅底为主,适合数据密集和正式汇报 |
| `color_mode=dark` | 深底为主,适合高冲击演示,要求文字色反转 |
| `color_mode=mixed` | 推荐默认:内容页浅底,封面/章节/概念页允许深底或强色底 |
| `contrast_level=dramatic` | 使用强明暗对比、大面积色块和更明确的信息层级 |
| `accent_saturation=high/neon` | accent 必须高饱和,用于焦点、编号、路径、KPI 和关键标签 |
| `font_mood=modern/editorial` | 选择更现代或杂志化的标题字体组合 |

`visual_theme_system.md` 的色彩约束应从“background 通常为极浅色”改为:

- `light` 模式:background 可为近白但避免纯白
- `dark` 模式:background 可为 `#0D0D0D` 到 `#1E2130` 区间的深色,文字色必须反转为高对比浅色
- `mixed` 模式:基础内容页可浅底,封面/章节/概念页可使用深色、强色或渐变背景

Bold 主题推荐高饱和色示例:

| 色彩角色 | 示例 |
|----------|------|
| coral accent | `#E85D40` |
| emerald primary | `#0B5E4E` |
| electric blue | `#1A4FFF` |
| magenta accent | `#B6246E` |
| cyan green accent | `#00C2A8` |

Prompt 应要求 `accent` 的 HSL 饱和度倾向 ≥ 70%。代码阶段可先不强制计算,但 Design Advisor gate 应把“强调色不够有力 / 层级不分”作为低分原因。

字体候选也需要扩展:

| 字体倾向 | 中文标题候选 | 说明 |
|----------|--------------|------|
| modern | 霞鹜新晰黑、HarmonyOS Sans SC、MiSans、阿里巴巴普惠体 | 适合现代建筑、商业综合体、科技感方案 |
| editorial | 思源黑体 Heavy、方正兰亭黑、得意黑 | 适合海报式标题和章节页 |
| cultural | 霞鹜文楷、方正标雅宋、思源宋体 | 适合文化类项目,建议只作标题或点缀 |

渲染时仍必须保留 fallback 字体,避免运行环境未安装导致不可控:

```css
font-family: "霞鹜新晰黑", "思源黑体", "Microsoft YaHei", sans-serif;
```

### 2. 页面类型策略

Composer v3 prompt 应按页面类型选择不同视觉策略:

| 页面类型 | 推荐构图 | 强制设计动作 |
|----------|----------|--------------|
| cover | full-bleed / poster / cinematic | 大标题占画面 20% 以上;使用 `cover_bg`、满版图或几何 SVG 背景;必须有强焦点 |
| toc | editorial index / asymmetric list | 目录不是普通列表;使用章节编号、纵向时间轴、色块索引或大号数字 |
| chapter_divider | bold minimal / poster | 大号章节数字或中英双语标题;整页主色/渐变/强留白;禁止普通居中文字 |
| data / kpi | infographic poster | KPI 巨字、图表主视觉、辅助注释;表格必须降级为摘要或重点指标 |
| map / site | full-bleed map + overlay | 地图/场地图满版;使用浮层标注、legend、路径/节点 SVG;文字不能压在复杂区域 |
| concept | architectural hero | 概念图主导 60% 以上画面;方案名、关键词、设计卖点作为注释层 |
| case | magazine collage | 案例图拼贴、关键词标签、对比条;避免一图一段文字的普通图文页 |
| strategy / process | diagrammatic | 使用流程线、箭头、节点、分层结构;不要只输出 bullet |
| text-heavy | editorial spread | 用大标题、拉引 quote、色块边栏、编号系统降低纯文字感 |

### 3. HTML/CSS 设计构件

v3 prompt 应鼓励使用以下“安全设计构件”,这些构件不需要新增渲染器代码:

- CSS Grid:主内容区、边栏、跨栏标题、海报式分区
- Flexbox:局部对齐、KPI 横排、图文比例控制
- SVG:建筑线稿、网格线、路径、节点、几何遮罩、半透明装饰
- absolute overlay:地图/图片上的注释面板、标签、legend
- CSS variables:所有主题色、字体、字号、间距
- inline `<style>`:仅作用于 `.slide-root` 内部,避免污染全局

禁止把视觉表现退化为:

- 大量同质卡片网格
- 白底 + 标题 + bullet 的默认文档页
- 只靠渐变背景但没有内容层级
- 过度装饰导致文字不可读
- 把原始长表格完整塞进页面

### 4. 素材使用规则

v3 HTML 必须根据素材类型决定版式:

| Asset 类型 | 使用方式 |
|------------|----------|
| image / concept render | 优先 full-bleed、hero、collage、masked image;不要缩成小插图 |
| map | 优先满版或大面积背景,叠加注释层和 legend |
| chart | 优先作为主视觉;周围用 KPI、结论和注释解释 |
| kpi_table / spreadsheet | 抽取 3-5 个关键数值,做 KPI poster;不要直接展示大表 |
| case_card | 做杂志式案例卡或三联对比,突出设计启发 |

### 5. Repair / Recompose 规则

HTML recompose 不应只做“最小修复”。当触发 Design Advisor gate 时,repair prompt 应允许结构性增强:

- `D007` 缺焦点:放大主标题/主图/KPI,重建阅读路径
- `D009` 装饰缺失:增加少量 SVG 线条、编号、色块或边栏
- `D010` 图文比例失调:重新分配图片与文字占比
- `D012` 重点页冲击力不足:封面/章节/概念页可整体重构
- `overall_score < 7.0`:允许重排布局,但必须保留原始事实和素材引用

## Consequences

### 好处

- 输出更容易形成建筑展板、杂志专题、竞赛汇报式视觉,而不是普通商务 PPT。
- v3 能直接表达 SVG 装饰、几何遮罩、满版图、强色块、KPI 海报化等设计动作。
- Design Advisor gate 可以持续压制“平庸但合法”的页面,把视觉质量变成可自动迭代的目标。
- structured 不删除,保留稳定回退和可测试性。

### 代价

- HTML 模式结构化校验弱,rule/semantic lint 无法完整覆盖页面结构。
- 视觉自由度提高后,更依赖 Playwright 截图和多模态 review 的可靠性。
- LLM 生成 HTML 的 token 消耗更高,返工回环会增加时延和成本。
- Prompt 约束需要更细,否则可能出现装饰过度、文字遮挡、布局溢出等问题。

### 风险控制

- HTML sanitize 继续保留:禁止 script、外部 URL、事件属性、危险标签。
- 所有颜色/字体/字号优先使用 theme CSS variables。
- 图片仅允许使用 `asset:{id}` 引用,由 render engine 替换。
- 画布固定 1920x1080,截图后必须进入 vision/design review。
- structured 模式保留为 fallback,当 HTML 生成失败或连续返工失败时可降级。

## Implementation Notes

第一阶段先不强制扩 schema,优先改主流程和 prompt:

1. API/Celery 显式使用 `ComposerMode.HTML`
2. 更新 `prompts/composer_system_v3.md`,强化 bold visual design 规则
3. 更新 `prompts/visual_theme_system.md`,提高色彩饱和度、构图和装饰策略要求
4. 将 Design Advisor 分数接入 review 回环,低分触发 `recompose_slide_html()`

第二阶段再扩 `VisualTheme` schema:

- `color_mode`
- `contrast_level`
- `accent_saturation`
- `font_mood`
- `visual_intensity`
- `color_strategy`
- `composition_style`
- `decorative_motif`
- `image_treatment`

## Links

- **Brief**:[briefs/2026-04-25-html-bold-design-upgrade.md](../briefs/2026-04-25-html-bold-design-upgrade.md)
- **Related ADR**:[ADR-003 Composer 双模式](ADR-003-composer-dual-mode.md)
- **Related ADR**:[ADR-004 HTML 模式 vision-only 审查](ADR-004-html-mode-vision-only.md)
