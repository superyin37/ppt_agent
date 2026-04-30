---
title: 模板系统
audience: 第一次读项目的开发者 / 维护者
read_time: 12 分钟
prerequisites: glossary.md, data.md
last_verified_against: f083adb
---

# 模板系统

> **读完这篇，你应该能回答：**
> - 模板系统的输入、输出、内部步骤是什么？
> - 哪些是硬编码、哪些是规则、哪些是 AI、哪些是外部 API？
> - 它怎么失败？怎么降级？怎么排查？
> - 我想改它的话，从哪一行开始动？

> **关联文档：**
> - 上一篇：[data.md](data.md)
> - 下一篇：[debugging.md](debugging.md)
> - 外部服务：[llm-and-external-services.md](llm-and-external-services.md)

## 一句话定位

模板系统接收已经排好序的 `list[SlideSpec]`，输出单文件 `index.html`。内容节点不直接拼 HTML，只选择组件并填充 `spec.data`；模板层不知道 LangGraph，也不关心某页内容由哪个节点生成。

核心代码：[html_renderer.py:20](../ppt_maker/render/html_renderer.py#L20)

默认模板：[templates/minimalist_architecture/](../templates/minimalist_architecture)

## 1. 总体流程

```mermaid
flowchart LR
  A[sorted list[SlideSpec]] --> B[HtmlRenderer.render]
  B --> C[render_slide per spec]
  C --> D[components/<component>.html.j2]
  D --> E[base.html.j2]
  E --> F[output/case_<id>/index.html]
```

### 输入

输入是 `aggregate_specs` 之后的 `SlideSpec` 列表：

| 字段 | 含义 | 模板是否直接使用 |
|---|---|---|
| `page` | 页码，当前固定 1-40 | 是，用于页码、章节判断和 `data-page` |
| `component` | 组件名，对应 `components/<component>.html.j2` | 是 |
| `title` | 页面中文标题 | 是 |
| `subtitle_en` | 英文副标题，可空 | 是 |
| `data` | 组件自己的数据字典 | 是 |
| `notes` | 备注 | 当前模板基本不展示 |

`aggregate_specs` 负责保证 1-40 页都有 spec；缺页会补 `content_bullets` 占位页。

### 输出

输出是一个单文件 HTML：

| 输出内容 | 说明 |
|---|---|
| HTML5 文档 | 由 `base.html.j2` 包裹所有 slide section |
| 内联 CSS | `viewport-base.css` 和 `theme.json` 被注入页面 |
| 40 个 `<section class="slide">` | 每页一个 section |
| 图片 data URI | `embed_image()` 把本地图片转成 `data:<mime>;base64,...` |

单文件 HTML 的好处是可以双击打开、作为附件发送、脱离输出目录分享。代价是体积会变大：dry-run 通常较小，真实 RunningHub 图像较多时可能达到几十 MB。

### 内部步骤

`HtmlRenderer.__init__()` 做这些事：

1. 定位 `templates/<template_name>/`。
2. 读取 `theme.json`。
3. 读取 `viewport-base.css`。
4. 创建 Jinja2 `Environment`：
   - loader 同时挂模板根目录和 `components/`，所以 `base.html.j2` 和组件都能直接读取。
   - `autoescape=select_autoescape(["html"])`，HTML 模板默认转义。
   - `undefined=ChainableUndefined`，缺字段返回空字符串而不是抛错。
   - `trim_blocks` / `lstrip_blocks` 控制模板空白。
5. 注册 `embed_image(path)` 全局函数。
6. 注册 `safe_number` filter。

代码：[html_renderer.py:20-37](../ppt_maker/render/html_renderer.py#L20-L37)

`render()` 主循环很薄：

```python
slide_html = [self.render_slide(s, project_title=project_title) for s in specs]
base = self.env.get_template("base.html.j2")
return base.render(...)
```

代码：[html_renderer.py:86](../ppt_maker/render/html_renderer.py#L86)

`render_slide()` 为每页选择组件，并注入上下文：

```python
{
    "spec": spec,
    "page": spec.page,
    "title": spec.title,
    "subtitle_en": spec.subtitle_en,
    "data": spec.data,
    "theme": self.theme,
    "section": section_code,
    "section_cn": section_cn,
    "section_en": section_en,
    "project_title": project_title,
}
```

代码：[html_renderer.py:69-84](../ppt_maker/render/html_renderer.py#L69-L84)

## 2. 模板目录结构

```text
templates/minimalist_architecture/
  theme.json
  viewport-base.css
  base.html.j2
  components/
    _chrome.html.j2
    cover.html.j2
    toc.html.j2
    transition.html.j2
    ending.html.j2
    policy_list.html.j2
    chart.html.j2
    table.html.j2
    image_grid.html.j2
    content_bullets.html.j2
    case_card.html.j2
    concept_scheme.html.j2
```

`theme.json` 定义颜色和字体。`base.html.j2` 会把 palette 注入 CSS 变量，组件应优先使用变量，不要在组件里散落硬编码颜色。

`components/_chrome.html.j2` 提供页眉、章节标签和页码。组件通常这样调用：

```jinja
{% from "_chrome.html.j2" import chrome %}
<section class="slide" data-page="{{ page }}" data-section="{{ section }}">
  ...
  {{ chrome(page, section, section_en, project_title) }}
</section>
```

## 3. 数据格式：组件 data 契约

`SlideSpec.data` 是 `dict[str, Any]`，Pydantic 不校验内部字段。下面是当前模板实际读取的字段。

### `cover`

| 字段 | 类型 | 模板里如何使用 | 缺失/为空时 |
|---|---|---|---|
| `slogan` | `str` | 封面主标题下方说明 | 空文本 |
| `en` | `str` | 英文说明 | 空文本 |
| `logo` | `str | None` | `embed_image(data.logo)` 转 data URI | 不显示 logo |
| `meta_lines` | `list[str]` | 任务书信息块 | 信息块为空 |
| `year` | `str | int` | 封面年份 | 默认显示 `2026` |
| `date` | `str` | 页脚日期 | 空文本 |

模板：[cover.html.j2](../templates/minimalist_architecture/components/cover.html.j2)

### `toc`

| 字段 | 类型 | 模板里如何使用 | 缺失/为空时 |
|---|---|---|---|
| `entries` | `list[dict]` | 渲染目录四个章节 | 目录列表为空 |
| `entry.no` | `str` | 章节编号 | 空文本 |
| `entry.label` | `str` | 中文章节名 | 空文本 |
| `entry.en` | `str` | 英文章节名 | 空文本 |
| `entry.sub` | `str` | 英文补充说明 | 不显示补充 |
| `illustration` | `str | None` | `embed_image()` 内联插图 | 不显示插图 |

模板：[toc.html.j2](../templates/minimalist_architecture/components/toc.html.j2)

### `transition`

| 字段 | 类型 | 模板里如何使用 | 缺失/为空时 |
|---|---|---|---|
| `section_no` | `str` | 转场页大号章节编号 | 显示 `00` 或空 |
| `sub` | `str` | 副标题附加说明 | 不显示附加说明 |

模板：[transition.html.j2](../templates/minimalist_architecture/components/transition.html.j2)

### `ending`

| 字段 | 类型 | 模板里如何使用 | 缺失/为空时 |
|---|---|---|---|
| `en` | `str` | 结束页英文说明 | 空文本 |
| `tagline` | `str` | 结束页标语 | 空文本 |

模板：[ending.html.j2](../templates/minimalist_architecture/components/ending.html.j2)

### `policy_list`

| 字段 | 类型 | 模板里如何使用 | 缺失/为空时 |
|---|---|---|---|
| `policies` | `list[Policy-like]` | 循环渲染政策卡片 | 不显示政策项 |
| `p.title` | `str` | 政策标题 | 空文本 |
| `p.publish_year` | `int | None` | 标题右侧年份 | 不显示年份 |
| `p.content` | `str` | 政策内容段落 | 不显示该段 |
| `p.impact` | `str` | 影响说明，前缀箭头 | 不显示该段 |
| `p.source_url` | `str` | 链接 | 不显示链接 |

模板：[policy_list.html.j2](../templates/minimalist_architecture/components/policy_list.html.j2)

### `chart`

| 字段 | 类型 | 模板里如何使用 | 缺失/为空时 |
|---|---|---|---|
| `chart_path` | `str` | `embed_image(data.chart_path)` 内联 PNG/SVG | 不显示图片 |
| `bullets` | `list[str]` | 右侧或下方说明段落 | 不显示说明 |

模板：[chart.html.j2](../templates/minimalist_architecture/components/chart.html.j2)

### `table`

| 字段 | 类型 | 模板里如何使用 | 缺失/为空时 |
|---|---|---|---|
| `headers` | `list[str]` | 表头 | 无表格 |
| `rows` | `list[list[str]]` | 表格行 | 无表格 |
| `note` | `str | None` | 表格注释 | 不显示注释 |

如果 `headers` 超过 6 列，模板会给 section 增加 `wide` class。

模板：[table.html.j2](../templates/minimalist_architecture/components/table.html.j2)

### `image_grid`

| 字段 | 类型 | 模板里如何使用 | 缺失/为空时 |
|---|---|---|---|
| `images` | `list[dict]` | 循环渲染图片网格 | 图片网格为空 |
| `img.path` | `str` | `embed_image()` 内联图片 | `<img src="">` |
| `img.caption` | `str` | 图片说明 | 不显示说明 |
| `caption` | `str` | 整页底部说明 | 不显示说明 |

模板：[image_grid.html.j2](../templates/minimalist_architecture/components/image_grid.html.j2)

### `content_bullets`

| 字段 | 类型 | 模板里如何使用 | 缺失/为空时 |
|---|---|---|---|
| `lede` | `str` | 标题下方导语 | 不显示导语 |
| `bullets` | `list[str | dict]` | 编号要点 | 不显示要点 |
| `b.title` | `str` | 要点标题 | 不显示标题 |
| `b.body` | `str` | 要点正文 | 若没有 `body`，显示整个 `b` |
| `illustration` | `str | None` | 有图时切换为图文布局 | 无图布局 |
| `placeholder` | `bool` | 缺页占位标记 | 当前模板不直接用 |
| `missing` | `bool` | 缺页占位标记 | 当前模板不直接用 |

模板：[content_bullets.html.j2](../templates/minimalist_architecture/components/content_bullets.html.j2)

### `case_card`

| 字段 | 类型 | 模板里如何使用 | 缺失/为空时 |
|---|---|---|---|
| `case_idx` | `int` | 显示 `REFERENCE · 01` 这类编号 | 按 0 处理 |
| `case_name` | `str` | 案例名和图片 alt | 显示 `（待补充）` |
| `scale` | `str` | 规模说明 | 显示 `—` |
| `highlights` | `str` | 设计亮点 | 显示 `—` |
| `inspiration` | `str` | 借鉴点 | 显示 `—` |
| `thumbnail` | `str | None` | `embed_image()` 内联缩略图 | 不显示图 |

模板：[case_card.html.j2](../templates/minimalist_architecture/components/case_card.html.j2)

### `concept_scheme`

| 字段 | 类型 | 模板里如何使用 | 缺失/为空时 |
|---|---|---|---|
| `scheme_idx` | `int` | 显示方案编号 | 按 0 处理 |
| `scheme_name` | `str` | 方案名 | 空文本 |
| `view` | `"aerial" | "exterior" | "interior"` | 缺少 `view_label` 时作为标签 fallback | 空文本 |
| `view_label` | `str` | 图像视角标签 | fallback 到 `view` |
| `image` | `str` | `embed_image(data.image)` 内联图像 | 不显示图像 |
| `idea` | `str` | 设计理念段落 | 不显示该段 |
| `analysis` | `str` | 分析段落 | 不显示该段 |
| `prompt` | `str` | 当前模板不展示，主要用于调试和追踪 | 不影响渲染 |

模板：[concept_scheme.html.j2](../templates/minimalist_architecture/components/concept_scheme.html.j2)

## 4. 实现思路与取舍

### 4.1 为什么先 `SlideSpec` 再 HTML

节点只产出 `SlideSpec`，模板再把它渲染成 HTML。这一层中间格式带来三个好处：

| 好处 | 说明 |
|---|---|
| 解耦内容和视觉 | 节点不用知道 HTML/CSS 结构 |
| 可调试 | `slide_specs.json` 可以落盘，`inspect` 和 `render-only` 都依赖它 |
| 可换皮 | 复制 `templates/` 并改组件即可复用同一批 specs |

代价是每新增一个组件要同步改 3 处：`ComponentKind`、组件模板、数据契约文档。如果节点还要产出新字段，也要同步更新对应节点和排查文档。

### 4.2 哪些是预先规定的

| 固定内容 | 位置 |
|---|---|
| 40 页的章节映射 | [html_renderer.py:54-58](../ppt_maker/render/html_renderer.py#L54-L58) |
| 章节中英文标签 | [html_renderer.py:61-67](../ppt_maker/render/html_renderer.py#L61-L67) |
| 组件枚举 | [state.py:149](../ppt_maker/state.py#L149) |
| 主题色、字体、章节色 | [theme.json](../templates/minimalist_architecture/theme.json) |
| 组件骨架 | [components/](../templates/minimalist_architecture/components) |
| 公共页眉页脚 | [_chrome.html.j2](../templates/minimalist_architecture/components/_chrome.html.j2) |

目录页文案、转场页文案、综合页文案不是模板决定的，而是在内容节点里作为 Python 字面量写入 `SlideSpec.data`。

### 4.3 哪些是动态填入的

| 动态内容 | 来源 |
|---|---|
| `spec.title` / `subtitle_en` / `data` | 内容节点产出的 `SlideSpec` |
| 图表 PNG | matplotlib 在节点里生成，然后模板内联 |
| 统计图、区位图、场地图 | 输入目录里的图片，通过语义键进入 spec |
| 概念方案图 | RunningHub 生成，或 SVG 占位 |
| logo / 目录插图 | RunningHub 或 SVG fallback |
| 同类产品表格 | Tavily 检索结果，或未配置说明 |

### 4.4 LLM 在哪一步起作用

**当前 0 处。** 文字内容全部由 Python 字面量、规则抽取、Excel 映射和启发式打分产出。RunningHub 是图像模型，不是豆包文本生成。

`DoubaoClient` 已实现但未接入任何节点。如要在某个文字位置加 LLM 摘要，应该在节点层调用 LLM 并写入 `spec.data`；模板层不需要知道内容来自 LLM。详见 [llm-and-external-services.md](llm-and-external-services.md)。

### 4.5 有没有审查 / 校对环节

**没有。** 当前不存在这些环节：

| 不存在的环节 | 影响 |
|---|---|
| 内容质量审查 | 不判断摘要是否准确 |
| LLM-as-judge | 不做模型复核 |
| 截图回看 | 不检查视觉重叠或空白页 |
| 拼写/术语检查 | 不统一术语 |
| 渲染后视觉对比 | 不做回归截图比较 |

唯一的检查是 `validate.py` 的完整性检查：页数、页码连续性和 `index.html` 是否存在。它不检查 `spec.data` 是否符合组件契约。

### 4.6 单文件 HTML 的取舍

选择：所有图片通过 [html_renderer.py:40-51](../ppt_maker/render/html_renderer.py#L40-L51) 的 `embed_image()` base64 内联。

| 方案 | 结果 |
|---|---|
| 当前方案：base64 内联 | 一个文件，容易分享；体积大，浏览器解码 data URI 有成本 |
| 放弃方案：同目录 `assets/` 引用 | HTML 小，但移动文件容易丢资源 |
| 放弃方案：上传 CDN | 适合线上服务，但引入运维、权限和失效问题 |

### 4.7 `ChainableUndefined` 的隐患

Jinja2 当前配置了 `ChainableUndefined`。这意味着：

```jinja
{{ data.foo.bar.baz }}
```

任意一段缺失时会渲染为空字符串，而不是抛异常。

| 好处 | 代价 |
|---|---|
| 缺可选字段时页面不崩 | 字段名拼错也不会报错 |
| 节点可以渐进补数据 | 常见问题会表现为“某块内容没显示” |

排查方法见 [debugging.md](debugging.md)。长期更稳的做法是在节点写入 `SlideSpec.data` 前，用 TypedDict 或局部 Pydantic model 校验组件数据。

## 5. 添加新模板

复制默认模板：

```powershell
Copy-Item templates/minimalist_architecture templates/my_style -Recurse
```

然后修改：

1. `theme.json`：颜色、字体、章节色。
2. `viewport-base.css`：全局尺寸、排版、基础控件。
3. `base.html.j2`：HTML 外壳。
4. `components/*.html.j2`：各类页面视觉。

运行：

```bash
python -m ppt_maker run --case 688 --template my_style
```

只改模板时，优先使用：

```bash
python -m ppt_maker render-only --case 688 --template my_style
```

这样不会重跑图像生成或联网检索。

## 6. 添加新组件

例如新增 `comparison_matrix`：

1. 在 [state.py:149](../ppt_maker/state.py#L149) 的 `ComponentKind` 加入 `"comparison_matrix"`。
2. 新建 `templates/<template>/components/comparison_matrix.html.j2`。
3. 某个节点产出 `SlideSpec(component="comparison_matrix", data={...})`。
4. 在本文件写清楚该组件的 `data` 契约。
5. 在 [debugging.md](debugging.md) 加上该组件的典型排查项。

如果不改 `ComponentKind`，Pydantic 会在构造 `SlideSpec` 时报错。
