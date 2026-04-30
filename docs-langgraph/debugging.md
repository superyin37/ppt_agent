---
title: 调试与排查
audience: 维护者 / 第一次调试项目的开发者
read_time: 10 分钟
prerequisites: pipeline.md, templates.md
last_verified_against: f083adb
---

# 调试与排查

> **读完这篇，你应该能回答：**
> - 出问题时先看哪三个文件？
> - `[missing page N]`、图片不显示、模板字段为空分别怎么查？
> - checkpoint 什么时候会让你误以为代码没生效？
> - 哪些问题是降级后的预期行为？

> **关联文档：**
> - 上一篇：[templates.md](templates.md)
> - 下一篇：[extension-guide.md](extension-guide.md)
> - 降级矩阵：[configuration.md](configuration.md)

## 第一级：先看这三处

90% 的问题先看：

| 位置 | 看什么 |
|---|---|
| `python -m ppt_maker inspect --case 688 --page <N>` | 单页 `SlideSpec` 是否正确 |
| `output/case_688/logs/run.jsonl` | 对应节点是否成功、耗时多少、错误是什么 |
| `output/case_688/slide_specs.json` | 全量页面是否齐、路径是否旧、字段是否存在 |

低成本复现优先用：

```bash
python -m ppt_maker run --case 688 --dry-run --force
```

只改模板时用：

```bash
python -m ppt_maker render-only --case 688
```

## 第二级：按症状索引

### 缺页 `[missing page N]`

含义：负责该页的节点没有产出 `SlideSpec`，`aggregate_specs` 自动补了缺页占位。兜底代码：[aggregate.py:17-25](../ppt_maker/nodes/aggregate.py#L17-L25)

排查：

1. 去 [pipeline.md](pipeline.md) 的 40 页表查这个页码对应节点。
2. 查日志：

   ```powershell
   Get-Content output/case_688/logs/run.jsonl -Tail 50
   ```

3. 查该节点是否 `ok=false`。
4. 查输入文件是否缺语义键。

常见映射：

| 缺页 | 可能节点 | 常见原因 |
|---|---|---|
| 4-7 | `policy_research` | 大纲政策章节解析为空 |
| 18/21 | `poi_analysis` | `场地poi.xlsx` 缺失或 sheet 名不匹配 |
| 23-25 | `case_study_worker` | 参考案例不足或语义键不匹配 |
| 29-37 | `runninghub_worker` | 概念 seed 异常或图像节点异常 |

### 图片不显示

先看 `SlideSpec.data` 中的图片路径：

```bash
python -m ppt_maker inspect --case 688 --page 29
```

| 现象 | 原因 | 修复 |
|---|---|---|
| 路径为空 | 节点没找到输入图或生成图 | 查对应节点和语义键 |
| 路径指向旧机器目录 | `slide_specs.json` 来自旧环境 | `run --force --dry-run` 重新生成 |
| SVG 占位图 | 缺 `RUNNING_HUB_KEY`、dry-run 或 RunningHub 失败 | 看占位图 hint 和 `run.jsonl` |
| 文件存在但 HTML 不显示 | 模板字段名不匹配 | 查组件 data 契约 |

图片内联逻辑在 [html_renderer.py:40-51](../ppt_maker/render/html_renderer.py#L40-L51)。

### 第 22 页空表或未配置说明

第 22 页由 `competitor_search` 生成，依赖 Tavily。未配置 `TAVILY_API_KEY` 时页面显示未配置说明，这是预期降级。Tavily wrapper 失败也会返回空列表，不阻断 deck。

代码：[tavily.py:28](../ppt_maker/clients/tavily.py#L28)

### 概念图全是 SVG 占位

第 29-37 页由 `runninghub_worker` 生成。常见原因：

| 原因 | 怎么确认 |
|---|---|
| 使用了 `--dry-run` 或 `--no-images` | CLI 输出里的 `dry_run=True` |
| 缺 `RUNNING_HUB_KEY` | `.env` 未配置 |
| RunningHub API 超时或失败 | `logs/run.jsonl` 中 `runninghub_worker` 耗时和错误 |
| prompt 为空或解析异常 | inspect 第 29-37 页看 `data.prompt` |

图像生成入口：[concept.py:36](../ppt_maker/nodes/concept.py#L36)

### 模板字段不显示

症状：`inspect` 里看起来有数据，但 HTML 某个字段没有显示。

高概率原因是 Jinja2 的 `ChainableUndefined` 静默吞掉了字段错误。比如模板写了：

```jinja
{{ data.case.title }}
```

但实际字段是：

```python
data.case_name
```

排查：

1. 对照 [templates.md](templates.md) 的组件 data 契约。
2. 临时把模板行改成更显眼的 fallback：

   ```jinja
   {{ data.case_name or "MISSING case_name" }}
   ```

3. `render-only` 重渲。

长期修复：在节点写 `SlideSpec.data` 前用 TypedDict 或局部 Pydantic model 校验。

### 改了代码没生效

优先怀疑 checkpoint。CLI 会使用 `output/case_<id>/checkpoint.sqlite` 和固定 `thread_id = case-<id>`，同 case 重跑可能复用旧状态。

修复：

```bash
python -m ppt_maker run --case 688 --force
```

`--force` 会删除 checkpoint 文件。相关代码：[__main__.py:64-69](../ppt_maker/__main__.py#L64-L69)

### 页面内容被覆盖

如果两个节点写同一个页码，`merge_dict` 会浅合并，后写覆盖前写。症状通常是某页内容来自意外节点。

排查：

1. 对照 [pipeline.md](pipeline.md) 的 40 页表。
2. 搜索节点里的页码字面量：

   ```powershell
   rg -n "page=|SlideSpec\\(" ppt_maker/nodes
   ```

3. 检查同一页是否被多个节点产出。

reducer 定义：[state.py:14](../ppt_maker/state.py#L14)

### 概念图 prompt 不对

三个 prompt 来源于 `outline.concept_schemes[i]`：

| 视角 | 字段 |
|---|---|
| 鸟瞰 | `prompt_aerial` |
| 室外人视 | `prompt_exterior` |
| 室内人视 | `prompt_interior` |

如果大纲没有解析出对应 seed，`concept.py` 会使用默认 prompt 和默认方案名。相关代码：[concept.py:43-50](../ppt_maker/nodes/concept.py#L43-L50)

### `summary_node` 内容不像当前项目

这是预期现状：第 19、26、39 页主要是 Python 字面量，不是 LLM 总结，也不深度读取输入资料。

修复方式：

1. 直接修改 [summary.py](../ppt_maker/nodes/summary.py) 的字面量。
2. 或新增节点，在 `summary_node` 后覆盖对应页。

### 图表中文显示方块

图表由 matplotlib 生成。原因通常是系统缺中文字体。Windows 一般有 `Microsoft YaHei`，Linux/CI 需要安装 Noto CJK 或类似字体。

相关代码：[charts.py](../ppt_maker/render/charts.py)

### 节点超时或图像生成很慢

RunningHub 是最慢的外部依赖。查看耗时：

```powershell
Get-Content output/case_688/logs/run.jsonl | Select-String runninghub_worker
```

本地调试建议：

```bash
python -m ppt_maker run --case 688 --dry-run --force
```

模板稳定后再关掉 `--dry-run` 跑真实图。

## 第三级：极端情况

### graph 直接崩

正常节点异常会被 `_wrap_with_timer()` 捕获，不应该让 graph 崩。graph 直接崩通常是构图错误、checkpoint 损坏、依赖包异常或 reducer 配置错误。

先看：

1. 最近是否新增节点但没进 `NODE_REGISTRY`。
2. 最近是否新增并发写字段但没加 reducer。
3. 删除 `checkpoint.sqlite` 后是否恢复。

### checkpoint sqlite 损坏

直接删除：

```powershell
Remove-Item output/case_688/checkpoint.sqlite
```

或用：

```bash
python -m ppt_maker run --case 688 --force
```

### 内存爆或浏览器打开慢

真实 RunningHub 图片会被 base64 内联进单文件 HTML。图片越多，`index.html` 越大，浏览器解码越慢。短期用 `--dry-run` 调试；长期可考虑把图片改成同目录 assets 引用，但当前项目选择单文件 HTML。
