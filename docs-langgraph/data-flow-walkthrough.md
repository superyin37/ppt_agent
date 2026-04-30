---
title: 一次完整运行的数据流走查
audience: 维护者 / 想跟数据走一遍源码的开发者
read_time: 12 分钟
prerequisites: pipeline.md, data.md
last_verified_against: f083adb
---

# 一次完整运行的数据流走查

> **读完这篇，你应该能回答：**
> - `case_688` 的输入如何一步步变成 `SlideSpec`？
> - 从 markdown 政策段落到第 4 页 `policy_list` 之间发生了什么？
> - `slide_specs.json`、`index.html`、`logs/run.jsonl` 分别适合排查什么？
> - 当前本地样本和当前源码不一致时应该怎样判断？

> **关联文档：**
> - 上一篇：[pipeline.md](pipeline.md)
> - 图集：[diagrams.md](diagrams.md)
> - 排查：[debugging.md](debugging.md)

## 0. 命令

计划中的基准命令是：

```bash
python -m ppt_maker run --case 688 --dry-run --force
```

本次文档改造时，本机系统 Python 是 3.10 且缺少 `rich`，而项目要求 Python >= 3.12，所以没有重新跑出新 dry-run。下面的走查以当前源码为准，并引用已有 `output/case_688` 的数据形态作为样本。该输出里出现旧绝对路径和历史 worker 名时，不作为当前拓扑事实。

## 1. CLI 构造初始 `ProjectState`

`_build_state()` 入口：[__main__.py:20](../ppt_maker/__main__.py#L20)

典型初始 state：

```python
{
    "project_id": "688",
    "case_dir": "data/case_688",
    "output_dir": "output/case_688",
    "template": "minimalist_architecture",
    "dry_run": True,
    "slide_specs": {},
    "search_cache": {},
    "charts": {},
    "generated_images": {},
    "errors": [],
    "retries": {},
}
```

`--dry-run` 和 `--no-images` 会合并成同一个布尔值：[__main__.py:63](../ppt_maker/__main__.py#L63)

## 2. `load_assets` 之后

输入目录：

```text
data/case_688/
  用户输入_688.md
  场地坐标_688.md
  设计建议书大纲_688.md
  场地poi_688.xlsx
  GDP及其增速_688.png
  参考案例1_详情_688.md
  参考案例1_缩略图_1_688.png
```

语义键示例：

| 文件 | 桶 | 语义键 |
|---|---|---|
| `设计建议书大纲_688.md` | `docs` | `设计建议书大纲` |
| `用户输入_688.md` | `docs` | `用户输入` |
| `场地poi_688.xlsx` | `xlsx` | `场地poi` |
| `GDP及其增速_688.png` | `images` | `GDP及其增速` |
| `参考案例1_缩略图_1_688.png` | `images` | `参考案例1_缩略图` |

节点输出：

```python
{
    "assets": AssetIndex(...),
    "user_input": UserInput(...),
    "site_coords": SiteCoords(...),
    "project_id": "688",
}
```

## 3. `parse_outline` 之后

输入片段来自 `data/case_688/设计建议书大纲_688.md`：

```markdown
### 政策分析
1. **《个人住房公积金贷款管理办法》（2026年实施）**
   - 政策内容：首套住房公积金贷款最高限额提升至120万元，二套提升至100万元...
   - 对项目影响：降低刚需及改善型客群购房门槛，提升项目去化速度。
   - 来源链接：https://www.thepaper.cn/newsDetail_forward_32464748
```

解析步骤：

| 步骤 | 函数 | 结果 |
|---|---|---|
| 拆章节 | `_split_sections()` | 得到 `{"政策分析": "..."}` |
| 抽编号项 | `_numbered_items()` | 得到 `("《个人住房公积金贷款管理办法》...", body)` |
| 抽字段 | `_bold_field()` | 得到 `政策内容`、`对项目影响`、`来源链接` |
| 抽年份 | `re.search(r"(\d{4})年", title)` | 得到 `2026` |

当前实现是纯规则解析，没有 LLM 调用。

对应 `Policy` 对象：

```json
{
  "title": "《个人住房公积金贷款管理办法》（2026年实施）",
  "content": "首套住房公积金贷款最高限额提升至120万元，二套提升至100万元，多子女家庭额度进一步上浮，二手房贷款最长期限延长至30年，有效期至2031年。",
  "impact": "降低刚需及改善型客群购房门槛，提升项目去化速度。",
  "source_url": "https://www.thepaper.cn/newsDetail_forward_32464748",
  "publish_year": 2026
}
```

## 4. `policy_research` 之后

输入：`outline.policies`

第 4 页 `SlideSpec` 的形态：

```json
{
  "page": 4,
  "component": "policy_list",
  "title": "相关政策解读 I · 国家与地方政策",
  "data": {
    "policies": [
      {
        "title": "《个人住房公积金贷款管理办法》（2026年实施）",
        "content": "首套住房公积金贷款最高限额提升至120万元...",
        "impact": "降低刚需及改善型客群购房门槛，提升项目去化速度。",
        "source_url": "https://www.thepaper.cn/newsDetail_forward_32464748",
        "publish_year": 2026
      }
    ]
  }
}
```

第 6 页图表来自 `policy._impact_score()` 和 matplotlib：

```text
outline.policies[*].impact
  -> 关键词启发式打分
  -> charts/policy_impact.png
  -> SlideSpec(page=6, component="chart")
```

## 5. `concept_dispatch` 后的 9 个 worker

当前 fan-out 代码：[concept.py:26-31](../ppt_maker/nodes/concept.py#L26-L31)

逻辑形态：

```python
[
    Send("runninghub_worker", {"scheme_idx": 0, "view": "aerial", **state}),
    Send("runninghub_worker", {"scheme_idx": 0, "view": "exterior", **state}),
    Send("runninghub_worker", {"scheme_idx": 0, "view": "interior", **state}),
    ...
]
```

页码计算：[concept.py:39](../ppt_maker/nodes/concept.py#L39)

```text
page = 29 + scheme_idx * 3 + view_order
```

dry-run 或缺 `RUNNING_HUB_KEY` 时，worker 写 SVG 占位图；真实运行时写 jpg/png。

## 6. `aggregate_specs` 之后

`aggregate_specs` 保证 1-40 页都有 spec：

```python
for page in range(1, 41):
    if page not in specs:
        specs[page] = SlideSpec(
            page=page,
            component="content_bullets",
            title=f"[missing page {page}]",
            data={"placeholder": True, "missing": True},
        )
```

代码：[aggregate.py:17-25](../ppt_maker/nodes/aggregate.py#L17-L25)

落盘文件：

```text
output/case_688/slide_specs.json
```

这个文件适合排查“节点产出了什么”，也适合 `render-only` 重渲。

## 7. `render_html` 之后

`render_html` 调用 `HtmlRenderer`：

```text
SlideSpec
  -> components/<component>.html.j2
  -> base.html.j2
  -> index.html
```

图片处理：

```text
chart_path / image / logo
  -> embed_image(path)
  -> data:image/png;base64,...
```

当前已有样本 `output/case_688/index.html` 约 75 MB，说明它包含大量真实图像的 base64 data URI。dry-run 体积会小很多。

## 8. `logs/run.jsonl`

日志每个节点一行。当前已有样本中可以看到：

```json
{"node": "load_assets", "ok": true, "duration_s": 0.003, "slides_emitted": 0}
{"node": "policy_research", "ok": true, "duration_s": 0.207, "slides_emitted": 4}
{"node": "aggregate_specs", "ok": true, "duration_s": 0.001, "slides_emitted": 40}
{"node": "validate", "ok": true, "duration_s": 0.004, "slides_emitted": 0}
```

注意：已有历史日志里可能出现旧 worker 名，这说明输出目录来自旧版本运行。遇到这种情况，以当前源码和 `last_verified_against` 为准，必要时在可用 Python 3.12 环境里重新 `run --force`。
