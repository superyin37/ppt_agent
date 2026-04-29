# 模板系统

模板系统负责把结构化 `SlideSpec` 渲染为最终 HTML。内容节点不直接拼 HTML，它们只选择组件并填充 `spec.data`。

核心代码：[ppt_maker/render/html_renderer.py](../ppt_maker/render/html_renderer.py)

默认模板：[templates/minimalist_architecture/](../templates/minimalist_architecture)

## 目录结构

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

## 渲染流程

```text
SlideSpec[]
  -> HtmlRenderer.render()
  -> render_slide(spec)
  -> components/<spec.component>.html.j2
  -> base.html.j2
  -> index.html
```

`HtmlRenderer.__init__()` 会：

1. 找到 `templates/<template_name>/`
2. 读取 `theme.json`
3. 读取 `viewport-base.css`
4. 配置 Jinja2 loader
5. 注册 `embed_image(path)`，用于把图片转成 `data:` URI

`render_slide()` 会为每页提供以下上下文：

```python
{
    "spec": SlideSpec,
    "page": int,
    "title": str,
    "subtitle_en": str | None,
    "data": dict,
    "theme": dict,
    "section": "01" | "02" | "03" | "04",
    "section_cn": str,
    "section_en": str,
    "project_title": str,
}
```

章节归属当前写死在 `HtmlRenderer.section_for_page()`：

| 页码 | 章节 |
|---|---|
| 1-12 | `01` 背景 |
| 13-19 | `02` 场地 |
| 20-26 | `03` 定位 |
| 27-40 | `04` 方案 |

## `theme.json`

`theme.json` 定义颜色和字体：

```json
{
  "palette": {
    "bg": "#f4f1ea",
    "surface": "#ffffff",
    "ink": "#15192a",
    "accent": "#2b3b63"
  },
  "fonts": {
    "cn_display": "...",
    "cn_body": "...",
    "en_display": "...",
    "en_mono": "..."
  },
  "section_colors": {
    "01": "#2b3b63",
    "02": "#49603f",
    "03": "#7a4a33",
    "04": "#15192a"
  }
}
```

`base.html.j2` 会把 palette 注入 CSS 变量。组件应尽量使用变量，而不是写死颜色。

## 公共 chrome

`components/_chrome.html.j2` 提供每页公共元素：

- 页眉 running head
- 章节标签
- 页码

组件一般这样使用：

```jinja
{% from "_chrome.html.j2" import chrome %}
<section class="slide" data-page="{{ page }}" data-section="{{ section }}">
  ...
  {{ chrome(page, section=section, section_en=section_en, project_title=project_title) }}
</section>
```

## 组件数据契约

下面是当前组件期望的 `spec.data` 形状。

### `cover`

```python
{
    "slogan": str,
    "en": str,
    "logo": str | None,
    "meta_lines": list[str],
}
```

### `toc`

```python
{
    "entries": [
        {"no": str, "label": str, "en": str, "sub": str}
    ],
    "illustration": str | None,
}
```

### `transition`

```python
{
    "section_no": str,
    "sub": str,
}
```

### `ending`

```python
{
    "en": str,
    "tagline": str,
}
```

### `policy_list`

```python
{
    "policies": [
        {
            "title": str,
            "content": str,
            "impact": str,
            "source_url": str,
            "publish_year": int | None,
        }
    ]
}
```

### `chart`

```python
{
    "chart_path": str,
    "bullets": list[str],
}
```

### `table`

```python
{
    "headers": list[str],
    "rows": list[list[str]],
    "note": str | None,
}
```

### `image_grid`

```python
{
    "images": [
        {"path": str, "caption": str}
    ],
    "caption": str,
}
```

### `content_bullets`

```python
{
    "lede": str,
    "bullets": [
        {"title": str, "body": str}
    ],
    "illustration": str | None,
}
```

缺页占位也使用这个组件，并额外带：

```python
{"placeholder": True, "missing": True}
```

### `case_card`

```python
{
    "case_idx": int,
    "case_name": str,
    "scale": str,
    "highlights": str,
    "inspiration": str,
    "thumbnail": str | None,
}
```

### `concept_scheme`

```python
{
    "scheme_idx": int,
    "scheme_name": str,
    "view": "aerial" | "exterior" | "interior",
    "view_label": str,
    "image": str,
    "idea": str,
    "analysis": str,
    "prompt": str,
}
```

## 添加新模板

复制默认模板：

```bash
Copy-Item templates/minimalist_architecture templates/my_style -Recurse
```

然后修改：

1. `theme.json`：颜色、字体、章节色。
2. `viewport-base.css`：全局尺寸、排版、基础控件。
3. `base.html.j2`：HTML 外壳和导航。
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

## 添加新组件

例如新增 `comparison_matrix`：

1. 在 [ppt_maker/state.py](../ppt_maker/state.py) 的 `ComponentKind` 加入 `"comparison_matrix"`。
2. 新建 `templates/<template>/components/comparison_matrix.html.j2`。
3. 某个节点产出 `SlideSpec(component="comparison_matrix", data={...})`。
4. 在文档中写清楚该组件的 `data` 契约。

如果不改 `ComponentKind`，Pydantic 会在构造 `SlideSpec` 时报错。
