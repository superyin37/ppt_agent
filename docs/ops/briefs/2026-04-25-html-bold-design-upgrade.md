---
date: 2026-04-25
status: In Progress
owner: superxiaoyin
assignee: Codex
---

# Task Brief:HTML 默认化与 Bold Visual Design 升级

## 1. Goal

将 PPT 生成主流程切到 Composer v3 HTML 模式,并通过更大胆的 VisualTheme、Composer v3 prompt、Design Advisor gate,显著提升建筑汇报 PPT 的视觉冲击力和设计完成度。

**完成标志**:`scripts/material_package_e2e.py --real-llm --max-slides 3` 和 API/Celery 主流程都默认产出 `spec_json.html_mode=true` 的 slide,渲染页具有明确视觉焦点、强层级、非模板化构图;低设计评分页面会自动进入 recompose。

## 2. Context

- 当前代码默认 `compose_all_slides(..., mode=ComposerMode.STRUCTURED)`,但文档和 E2E 脚本默认口径是 HTML 模式。
- 用户希望 PPT 视觉“更鲜艳大胆、更有设计感”。
- v2 structured 的 11 种 LayoutPrimitive 稳定但限制设计表达;v3 HTML 可直接生成复杂 HTML/CSS/SVG,更适合本目标。
- 已有基础能力:HTML sanitize、theme CSS 注入、vision review、HTML recompose、Design Advisor 5 维评分。

## 3. Out of Scope

- 不删除 structured 模式。
- 不实现 PPTX 原生导出。
- 不重做前端交互。
- 不更换 LLM provider。
- 不在第一阶段引入大型设计模板库或外部 CSS 框架。
- 不修改概念渲染图像模型链路;概念图作为素材继续供 Composer 使用。

## 4. Constraints

### 架构

- API/Celery 主流程必须显式传 `ComposerMode.HTML`,不要依赖默认参数。
- structured 模式必须继续可运行,用于 fallback/debug。
- HTML 模式 review 仍以 vision/design review 为主,不要把假 `LayoutSpec` 送入 rule lint 导致 phantom issues。
- 所有 LLM 调用继续经 `config/llm.py`。

### 安全与渲染

- HTML 输出必须以 `<div class="slide-root">` 为根容器。
- 禁止外部 URL、script、iframe、事件属性;继续使用 `render/html_sanitizer.py`。
- 图片只能使用 `asset:{id}` 引用,由 render engine 替换。
- 画布固定 1920x1080。
- 颜色、字体、字号、间距优先使用 `var(--color-*)`、`var(--font-*)`、`var(--text-*)`、`var(--safe-margin)`。

### 视觉目标

- 默认视觉强度为 `bold`。
- 默认色彩模式建议为 `mixed`:内容页可浅底,封面/章节/概念方案页允许深色或强色背景。
- `visual_theme_system.md` 不再强制 background 只能是极浅色;深色模式需保证文字反转和对比度。
- 强调色应明显高饱和,用于焦点、KPI、路径、编号、标签。
- 避免普通白底卡片堆叠式商务 PPT。
- 封面、章节页、概念方案页必须有更强视觉冲击。
- 数据页应海报化,优先 KPI 巨字 + 图表 + 注释层级。
- 地图页应满版地图 + 浮层标注 / legend / 路径节点。
- 每页必须有明确视觉焦点、至少 3 层信息层级、可解释的构图意图。
- `body_html` 不是内容容器,而是 1920x1080 的可截图设计稿。

## 5. Acceptance Criteria

- [x] `tasks/outline_tasks.py` 调用 `compose_all_slides()` 时显式使用 `ComposerMode.HTML`
- [x] `api/routers/outlines.py` 主流程显式使用 `ComposerMode.HTML`,且渲染时兼容 `html_mode`
- [x] `agent/composer.py` 的默认值、注释或配置口径与产品默认一致,structured 保留可选
- [x] `.env.example` 或 settings 增加 `COMPOSER_MODE=html` 类配置(如采用配置方案)
- [x] `prompts/composer_system_v3.md` 增加 bold visual design 规则和页面类型策略
- [x] `prompts/visual_theme_system.md` 强化高饱和、强对比、深色/混合背景、构图风格、装饰母题要求
- [x] `schema/visual_theme.py` 评估新增 `color_mode / contrast_level / accent_saturation / font_mood`
- [x] VisualTheme prompt 加入现代字体候选:霞鹜新晰黑、HarmonyOS Sans SC、MiSans、阿里巴巴普惠体、得意黑等,并保留 fallback 字体
- [x] Composer v3 输出约束覆盖 root 容器、CSS 变量、素材引用、禁止外链/滚动/交互控件
- [x] Composer v3 页面类型策略覆盖 cover/toc/chapter/data/map/concept/case/strategy/text-heavy
- [x] Composer v3 repair prompt 支持根据 D007/D009/D010/D012 做结构性增强,不只做文字微调
- [x] Design Advisor 低分 gate 接入 review/recompose,至少支持 `overall_score < 7.0` 自动返工
- [x] `scripts/material_package_e2e.py --max-slides 3 --real-llm` 默认产出 HTML mode slides
- [x] 至少新增/更新单元测试覆盖 HTML 默认路由或 Composer mode 选择
- [x] 更新文档:STATUS / TODO / GLOSSARY / ROADMAP / ADR README / briefs README

## 6. Suggested Approach

### Phase 1:默认模式与入口统一

| 文件 | 改动 |
|------|------|
| `agent/composer.py` | 统一默认模式或读取配置;保留 structured 可选 |
| `tasks/outline_tasks.py` | `compose_all_slides(..., mode=ComposerMode.HTML)` |
| `api/routers/outlines.py` | compose 与 render 都走 HTML-aware 路径 |
| `config/settings.py` / `.env.example` | 可选新增 `COMPOSER_MODE=html` |
| `scripts/material_package_e2e.py` | 保持 CLI 默认 html,补日志/summary 标记 |

### Phase 2:Prompt 升级

| Prompt | 改动 |
|--------|------|
| `prompts/visual_theme_system.md` | 加入 `bold` 设计方向:深色/混合背景、高对比、撞色、高饱和 accent、杂志/展板风格 |
| `prompts/composer_system_v3.md` | 强化每页视觉焦点、非对称构图、SVG 装饰、页面类型策略 |
| `prompts/composer_repair.md` | repair 时允许增强视觉,不只做最小文字修复 |
| `prompts/vision_design_advisor.md` | 增加 gate 语义,让建议可被 recompose 消费 |

#### VisualTheme Prompt 详细规格

`visual_theme_system.md` 需要先解决三个视觉瓶颈:背景过浅、色彩过保守、字体过稳。

**A. 允许色彩模式**

建议新增 schema 字段:

```python
color_mode: Literal["light", "dark", "mixed"]
contrast_level: Literal["standard", "high", "dramatic"]
accent_saturation: Literal["normal", "high", "neon"]
font_mood: Literal["classic", "modern", "editorial", "experimental"]
```

如果第一阶段暂不扩 schema,则把这些信息写入 `generation_prompt_hint` 并在 Composer v3 prompt 中读取。

**B. 背景色规则**

| color_mode | 规则 |
|------------|------|
| `light` | 背景可为近白、浅灰、浅暖色,但避免纯白 |
| `dark` | 背景可为 `#0D0D0D` 到 `#1E2130` 的深色区间;文字色必须反转为浅色 |
| `mixed` | 默认推荐;内容页浅底,封面/章节/概念方案页可深底、强色底或渐变 |

现有 prompt 中“background 通常为极浅色”应改为“按 color_mode 决定;bold/mixed 模式允许深色或强色背景”。

**C. 高饱和色指引**

可在 prompt 中提供明确候选,避免模型继续输出低饱和蓝灰:

| 用途 | 示例 |
|------|------|
| 强调色 | 珊瑚红 `#E85D40`、品红 `#B6246E`、青绿 `#00C2A8` |
| 主色 | 深祖母绿 `#0B5E4E`、电蓝 `#1A4FFF`、近黑蓝 `#111827` |
| 强背景 | 深炭黑 `#0D0D0D`、墨蓝 `#111827`、深紫黑 `#171326` |

Prompt 要求:

- `accent` 倾向 HSL 饱和度 ≥ 70%
- `accent` 与 `background` 对比度 ≥ 3:1
- `primary / accent / background` 必须能形成明确层级
- 避免整套主题都是低饱和蓝灰、米色或单一色相

**D. 现代字体候选**

标题字体候选扩展:

| 风格 | 候选 |
|------|------|
| 现代建筑 | 霞鹜新晰黑、HarmonyOS Sans SC、MiSans、阿里巴巴普惠体 |
| 海报/editorial | 得意黑、思源黑体 Heavy、方正兰亭黑 |
| 文化类 | 霞鹜文楷、方正标雅宋、思源宋体 |

CSS 输出仍必须带 fallback:

```css
font-family: "霞鹜新晰黑", "思源黑体", "Microsoft YaHei", sans-serif;
```

#### Composer v3 Prompt 详细规格

`composer_system_v3.md` 需要补成“设计规范 + 输出约束 + 页面类型策略”三段,避免只告诉模型“生成漂亮 HTML”。

**A. 输出结构约束**

```html
<div class="slide-root">
  <style>
    .slide-root { ... }           /* 只写本页局部样式 */
    .slide-title { ... }
    .visual-anchor { ... }
  </style>
  ...
</div>
```

要求:

- 根节点必须是 `.slide-root`,不能输出完整 `<html>`、`<head>`、`<body>`。
- `.slide-root` 内可放 `<style>`、`div/section/header/footer/aside`、`svg`、`img`、`table`。
- 所有核心内容必须在 1920x1080 内完成,禁止依赖滚动。
- 禁止 `<script>`、外部 URL、表单、按钮、iframe。
- `<img src>` 只能是 `asset:{id}`。
- 颜色/字体/字号/间距优先使用:
  - `var(--color-primary)`
  - `var(--color-secondary)`
  - `var(--color-accent)`
  - `var(--color-bg)`
  - `var(--color-surface)`
  - `var(--color-text-primary)`
  - `var(--font-heading)`
  - `var(--font-body)`
  - `var(--text-display)`
  - `var(--text-h1)`
  - `var(--text-body)`
  - `var(--safe-margin)`
  - `var(--section-gap)`
  - `var(--element-gap)`

**B. 每页必须声明的设计意图**

在 HTML 里不需要显示设计说明,但 prompt 要要求模型内部完成这 4 个决策:

| 决策 | 要求 |
|------|------|
| visual_anchor | 本页第一视觉焦点是什么:大标题/图片/KPI/地图节点/方案图 |
| hierarchy | 主信息、支撑信息、细节信息分别是什么 |
| composition | 使用哪种构图:poster/editorial/asymmetric/full-bleed/diagrammatic |
| asset_role | 每个 asset 是背景、主视觉、图表、注释还是证据 |

**C. 安全设计构件白名单**

鼓励使用:

- CSS Grid:跨栏标题、主视觉区、边栏、底部信息条
- Flexbox:KPI 排列、局部对齐
- SVG:路径、节点、建筑线稿、几何装饰、淡色纹理
- absolute overlay:地图标注、图片说明、legend、方案标签
- CSS `clip-path`:用于图片遮罩和几何切面,但不要遮挡文字
- 半透明面板:`background: color-mix(...)` 或 `rgba(...)`,保证文字对比度

避免使用:

- 纯白背景 + 普通标题 + bullet 列表
- 大量同质卡片
- 无信息目的的渐变和装饰
- 复杂动画、hover、交互控件
- 过多绝对定位导致内容重叠

#### 页面类型策略

| 页面类型 | 视觉目标 | 推荐 HTML/CSS 策略 | 失败表现 |
|----------|----------|--------------------|----------|
| cover | 第一眼有冲击力 | full-bleed 图/渐变,巨大标题,几何 SVG 背景,项目关键词标签 | 标题居中但无视觉主角 |
| toc | 像展览导览而不是普通目录 | 大号章节编号,纵向索引,分栏 editorial layout | 普通 1-6 列表 |
| chapter_divider | 极简但强烈 | 整页主色,大号章节号,中英双语标题,少量线条 | 小标题居中 |
| data/kpi | 信息海报 | KPI 巨字,图表主视觉,结论条,注释气泡 | 原始表格塞满 |
| map/site | 空间分析图 | 地图满版,半透明浮层,路径/节点 SVG,legend | 小地图 + 大段文字 |
| concept | 建筑方案展示 | 概念图 60%+ 画面,方案名,关键词,卖点注释 | 图片太小或文字喧宾夺主 |
| case | 案例研究杂志页 | 图片拼贴,关键词标签,对比条,启发总结 | 一张图 + 一段说明 |
| strategy/process | 逻辑图解 | 节点、箭头、时间线、矩阵、泳道 | 只有 bullet |
| text-heavy | 编辑式跨页感 | 大标题、拉引、边栏、编号系统、强留白 | 密集正文段落 |

#### 素材驱动策略

Composer v3 不应只“插入素材”,而要根据素材类型改变版式:

| Asset 类型 | 推荐处理 |
|------------|----------|
| `image` | hero/full-bleed/collage,局部遮罩,图上标签 |
| `map` | 满版背景 + overlay,突出路径/节点/范围 |
| `chart` | 作为主视觉;旁边只放 1-2 条结论 |
| `kpi_table` | 抽取关键数字做 KPI poster,避免整表 |
| `case_card` | 做三联或杂志式案例卡,突出“可借鉴点” |
| `concept.*` | full-bleed 或大 hero,文字作为注释层 |

#### Recompose 详细规则

`composer_repair.md` 要区分“缺陷修复”和“设计升级”:

| 触发 | recompose 行为 |
|------|----------------|
| `V004 TEXT_ON_BUSY_BG` | 给文字加遮罩/暗层/迁移到安静区域 |
| `V007 BLANK_AREA_WASTE` | 扩大主视觉或增加结构性装饰,不是简单拉伸文字 |
| `D007 缺少焦点` | 重新建立 visual anchor,放大主标题/主图/KPI |
| `D009 装饰缺失` | 增加少量 SVG 线条、编号、色块或边栏 |
| `D010 图文比例失调` | 重排主视觉和文字比例 |
| `D012 重点页冲击力不足` | cover/chapter/concept 允许整体重构 |

修复时必须保留:

- 原始事实、数字、结论
- 已绑定素材引用
- `.slide-root` 根结构
- VisualTheme CSS variables

### Phase 3:Design Advisor Gate

建议阈值:

| 条件 | 动作 |
|------|------|
| `overall_score < 7.0` | recompose HTML |
| `focal_point < 6.5` | 要求建立更强视觉焦点 |
| `polish < 6.5` | 要求增加装饰层次和完成度 |
| `D009` | 要求增强视觉语言 |
| `D012` 且 cover/chapter/concept | 必须重做重点页冲击力 |

### Phase 4:Schema 扩展(可第二轮)

如第一阶段 prompt 不够稳定,再扩 `VisualTheme`:

```python
color_mode: Literal["light", "dark", "mixed"]
contrast_level: Literal["standard", "high", "dramatic"]
accent_saturation: Literal["normal", "high", "neon"]
font_mood: Literal["classic", "modern", "editorial", "experimental"]
visual_intensity: Literal["standard", "bold", "experimental"]
color_strategy: Literal["muted", "high-contrast", "complementary", "gradient", "poster"]
composition_style: Literal["editorial", "poster", "swiss", "cinematic", "exhibition"]
decorative_motif: Literal["grid-lines", "architectural-lines", "oversized-type", "geometric-blocks"]
```

## 7. Relevant Files

### 主要改动

- [agent/composer.py](../../../agent/composer.py)
- [tasks/outline_tasks.py](../../../tasks/outline_tasks.py)
- [api/routers/outlines.py](../../../api/routers/outlines.py)
- [render/engine.py](../../../render/engine.py)
- [tasks/review_tasks.py](../../../tasks/review_tasks.py)
- [agent/critic.py](../../../agent/critic.py)
- [prompts/composer_system_v3.md](../../../prompts/composer_system_v3.md)
- [prompts/visual_theme_system.md](../../../prompts/visual_theme_system.md)
- [prompts/vision_design_advisor.md](../../../prompts/vision_design_advisor.md)

### 参考实现

- [docs/ops/decisions/ADR-003-composer-dual-mode.md](../decisions/ADR-003-composer-dual-mode.md)
- [docs/ops/decisions/ADR-004-html-mode-vision-only.md](../decisions/ADR-004-html-mode-vision-only.md)
- [scripts/material_package_e2e.py](../../../scripts/material_package_e2e.py)

### 不要动

- `agent/concept_render.py` — 本任务不改变概念图生成链路
- `tool/image_gen/runninghub.py` — 本任务不改变 runninghub client

## 8. Questions / Risks

- **成本 / 时延**:Design Advisor gate 会增加 recompose 轮次,建议先限制最多 1-2 轮。
- **过度设计**:bold 不等于花哨,需要 prompt 明确“强层级、强焦点、少而准的装饰”。
- **API 路径兼容**:`api/routers/outlines.py` 目前部分渲染逻辑直接 `LayoutSpec.model_validate()`,需要补 HTML mode 分支。
- **测试稳定性**:真实 LLM 输出视觉质量波动大,自动化测试应验证模式和结构,视觉质量用 smoke/report 评估。

## 9. Updates

- 2026-04-25:创建 brief 和 ADR-006,准备进入实现阶段。
- 2026-04-25:已实施代码主路径切换与 bold prompt/schema 扩展。
  - `config/settings.py` / `.env.example`:新增 `COMPOSER_MODE=html` 与 Design Advisor gate 阈值配置。
  - `schema/visual_theme.py`:新增 `color_mode`、`contrast_level`、`accent_saturation`、`font_mood`、`visual_intensity`、`color_strategy`、`composition_style`、`decorative_motif`、`image_treatment`。
  - `agent/composer.py`:默认读取 `COMPOSER_MODE`,并把新增 VisualTheme 字段传入 HTML composer / recompose。
  - `tasks/outline_tasks.py` / `api/routers/outlines.py`:主流程显式使用 `ComposerMode.HTML`,render 兼容 `spec_json.html_mode`。
  - `prompts/visual_theme_system.md` / `prompts/composer_system_v3.md` / `prompts/composer_repair.md`:补齐深色/混合背景、高饱和 accent、页面类型策略、结构性 repair 规则。
  - `agent/critic.py` / `tasks/review_tasks.py`:HTML 模式启用 Design Advisor,并将 `overall_score < 7.0`、`focal_point < 6.5`、`polish < 6.5`、重点页 `D012` 转换为可返工 issue。
  - `tests/unit/test_critic.py`:新增 Design Advisor gate 单元测试。
  - `tests/unit/test_composer_mode.py`:新增 Composer mode 配置解析单元测试。

- 2026-04-25:启动本地 DB/Redis 并执行 real-LLM smoke。
  - 已执行 `docker compose up db redis -d`,容器启动成功。
  - 基础命令 `scripts/material_package_e2e.py test_material/project1 --real-llm --max-slides 3 --output-dir test_output/html_bold_design_smoke` 执行成功,输出目录:`test_output/html_bold_design_smoke/run_20260425T111220Z`。
  - 基础 run 产出 `deck.pdf`、`slides_spec.json`、`review_reports.json`;3 页 `spec_json.html_mode=true`;slide 01 和 slide 03 触发过 HTML recompose 后完成导出。
  - 带 `--design-review` 的 run 执行成功,输出目录:`test_output/html_bold_design_smoke/run_20260425T141051Z`;产出 `design_scores.json`,slide 02 overall_score=8.1(A),slide 03 overall_score=8.7(A)。
  - 发现 E2E 脚本只给首轮通过页面补跑 Design Advisor,返工后通过的页面可能漏评分;已修改 `scripts/material_package_e2e.py`,启用 `--design-review` 时最终截图如无 `design_advice` 会补跑评分。
  - 修正后再次执行 `--design-review`,输出目录:`test_output/html_bold_design_smoke/run_20260425T141944Z`;3 页均为 `html_mode=true`,产出 `design_scores.json`,slide 02 overall_score=8.8(A),slide 03 overall_score=8.4(A)。
  - 最新 run 暴露后续问题:slide 01 Design Advisor 多模态输出解析失败导致无评分;slide 03 最终报告仍有 `V007 BLANK_AREA_WASTE` P2,`final_decision=repair_required`,但脚本仍整体标记 validation succeeded。

剩余验证:

- 继续加固 Design Advisor smoke:最新 `--design-review` run 已产出 `design_scores.json`,但 slide 01 的 Design Advisor 多模态 JSON 解析失败;slide 03 最终仍有 `V007` P2 repair_required。
