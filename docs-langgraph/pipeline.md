# PPT 生成链路

本文只回答一个问题：执行下面命令后，PPT-Maker 如何把输入资料变成 40 页 HTML deck？

```bash
python -m ppt_maker run --case 688
```

CLI 入口在 [ppt_maker/__main__.py](../ppt_maker/__main__.py)，实际工作流在 [ppt_maker/graph.py](../ppt_maker/graph.py)。

## 一句话流程

```text
输入文件
  -> 资产索引和结构化解析
  -> 多个内容节点并行生成 SlideSpec
  -> 汇总补齐 40 页
  -> Jinja2 渲染 HTML
  -> 校验输出
```

最终输出目录：

```text
output/case_<id>/
  index.html          # 单文件 HTML 演示文稿
  slide_specs.json    # 40 页结构化中间结果
  assets/
    charts/           # matplotlib 生成图表
    generated/        # RunningHub 图片或 SVG 占位
  checkpoint.sqlite   # LangGraph checkpoint
  logs/run.jsonl      # 节点耗时和错误日志
```

## 阶段 1：构造初始状态

`run` 命令先调用 `_build_state()` 创建 `ProjectState`：

```python
ProjectState(
    project_id=case_id,
    case_dir="data/case_<id>",
    output_dir="output/case_<id>",
    template="minimalist_architecture",
    dry_run=False,
    slide_specs={},
    search_cache={},
    charts={},
    generated_images={},
    errors=[],
    retries={},
)
```

这个状态会在 LangGraph 节点之间流动。每个节点读取其中一部分字段，返回一个“局部更新”。

## 阶段 2：读取输入资料

### `load_assets`

实现：[ppt_maker/nodes/load.py](../ppt_maker/nodes/load.py)

输入：

- `state["case_dir"]`

输出：

- `assets: AssetIndex`
- `user_input: UserInput`
- `site_coords: SiteCoords`
- `project_id`

它会扫描 `data/case_<id>/`，把文件按语义键索引。例如：

| 文件 | 语义键 |
|---|---|
| `设计建议书大纲_688.md` | `设计建议书大纲` |
| `GDP及其增速_688.png` | `GDP及其增速` |
| `场地poi_688.xlsx` | `场地poi` |

### `parse_outline`

实现：[ppt_maker/nodes/outline.py](../ppt_maker/nodes/outline.py)

输入：

- `assets.docs["设计建议书大纲"]`

输出：

- `outline: DesignOutline`

它从 markdown 大纲中抽取政策、产业、上位规划、文化特征、经济概述、区位分析、参考案例、设计策略和 3 个概念方案 seed。

### `poi_parser`

实现：[ppt_maker/nodes/poi.py](../ppt_maker/nodes/poi.py)

输入：

- `assets.xlsx["场地poi"]`

输出：

- `poi_data: POIData`

它读取 Excel 中的 POI sheet，整理成基础设施、外部交通、竞品、枢纽站点、区域开发等列表。

## 阶段 3：并行生成页面

`parse_outline` 完成后，多个内容节点可以并行执行，因为它们负责不同页码，互不依赖。它们统一返回：

```python
{"slide_specs": {page_number: SlideSpec(...)}}
```

`slide_specs` 在 `ProjectState` 中配置了 `merge_dict` reducer，所以多个节点写入不同页码时会被合并。

## 40 页生成来源

| 页码 | 内容 | 生成节点 |
|---|---|---|
| 1 | 封面 | `cover_transition` |
| 2 | 目录 | `cover_transition` |
| 3 | 章节过渡：项目背景 | `cover_transition` |
| 4-5 | 政策解读 | `policy_research` |
| 6 | 政策影响图表 | `policy_research` |
| 7 | 上位规划条件 | `policy_research` |
| 8 | 区位优势概览 | `location_analysis` |
| 9 | 文化特征 | `cultural_node` |
| 10-12 | 城市经济、产业、消费 | `economy_analysis` |
| 13 | 章节过渡：场地分析 | `cover_transition` |
| 14-17 | 场地四至 | `location_analysis` |
| 18 | 周边业态与 POI | `poi_analysis` |
| 19 | 场地综合分析 | `summary_node` |
| 20 | 章节过渡：项目定位 | `cover_transition` |
| 21 | 附近同类型产品 | `poi_analysis` |
| 22 | 同类产品检索 | `competitor_search` |
| 23-25 | 参考案例 1-3 | `case_study_worker` |
| 26 | 项目定位总结 | `summary_node` |
| 27 | 章节过渡：设计方案 | `cover_transition` |
| 28 | 设计策略 | `cover_transition` |
| 29-37 | 3 个概念方案，每个 3 个视角 | `runninghub_worker` |
| 38 | 方案指标矩阵 | `metrics` |
| 39 | 设计任务书 | `summary_node` |
| 40 | 结束页 | `cover_transition` |

## 特殊并发：Send worker

有两类页面数量由数据决定，使用 LangGraph `Send` 动态展开：

| dispatcher | worker | 数量 | 页码 |
|---|---|---:|---|
| `case_study_dispatch` | `case_study_worker` | 3 | 23-25 |
| `concept_dispatch` | `runninghub_worker` | 9 | 29-37 |

普通内容节点是静态注册的；`Send` worker 是运行时 fan-out 的。具体图构造见 [langgraph.md](langgraph.md)。

## 阶段 4：等待并发完成

并行节点不能直接进入渲染，否则可能出现部分页面还没写入 `slide_specs`。因此图里有两个 no-op barrier：

| 节点 | 作用 |
|---|---|
| `content_join` | 等静态内容节点汇合 |
| `barrier` | 等 `content_join`、`case_study_worker`、`runninghub_worker` 全部汇合 |

这两个节点本身不改状态，只利用 LangGraph superstep 的执行语义保证下游只走一次。

## 阶段 5：汇总、渲染、校验

### `summary_node`

实现：[ppt_maker/nodes/summary.py](../ppt_maker/nodes/summary.py)

生成跨节点综合页：

- 第 19 页：场地综合分析
- 第 26 页：项目定位总结
- 第 39 页：设计任务书

### `aggregate_specs`

实现：[ppt_maker/nodes/aggregate.py](../ppt_maker/nodes/aggregate.py)

作用：

- 确保 1-40 页都有 `SlideSpec`
- 缺失页用 `[missing page N]` 占位
- 写出 `output/case_<id>/slide_specs.json`

### `render_html`

实现：[ppt_maker/nodes/render.py](../ppt_maker/nodes/render.py)

作用：

- 读取排序后的 `slide_specs`
- 调用 `HtmlRenderer`
- 写出 `output/case_<id>/index.html`

### `validate`

实现：[ppt_maker/nodes/validate.py](../ppt_maker/nodes/validate.py)

检查：

- `slide_specs` 是否正好 40 页
- 页码是否完整
- `index.html` 是否存在

## 错误与降级

节点外层统一由 `_wrap_with_timer()` 包装。节点抛异常时：

1. 错误写入 `logs/run.jsonl`
2. `errors[]` 追加 `NodeError`
3. 工作流继续往下走
4. `aggregate_specs` 为缺页生成占位页

外部 API 缺失时通常不抛异常，而是降级：

| 缺失项 | 影响 | 降级结果 |
|---|---|---|
| `RUNNING_HUB_KEY` | 文化图、logo、概念图 | 生成 SVG 占位 |
| `TAVILY_API_KEY` | 第 22 页竞品检索 | 表格显示未配置说明 |
| 输入图片缺失 | 对应图片页 | 少图或空占位 |
| 输入大纲缺失 | 多数内容页 | 后续节点少产出，最终缺页占位 |

排查方法见 [debugging.md](debugging.md)。
