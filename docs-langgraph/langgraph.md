# LangGraph 构造说明

本文解释 [ppt_maker/graph.py](../ppt_maker/graph.py) 如何把各个节点组装成可恢复、可并发的工作流。

## 最小心智模型

PPT-Maker 用 LangGraph 做三件事：

1. 让节点按依赖顺序执行。
2. 让互不依赖的内容节点并行执行。
3. 用 checkpoint 记录执行进度，失败后可以恢复。

简化拓扑：

```text
START
  -> load_assets
       -> parse_outline -> 多个内容节点 -> content_join -> barrier
       -> poi_parser    -> poi_analysis  -> content_join -> barrier

barrier
  -> summary_node
  -> aggregate_specs
  -> render_html
  -> validate
  -> END
```

另有两组动态 fan-out：

```text
parse_outline -> case_study_dispatch -> case_study_worker x 3 -> barrier
parse_outline -> concept_dispatch    -> runninghub_worker x 9 -> barrier
```

## `StateGraph(ProjectState)`

构图从这里开始：

```python
g = StateGraph(ProjectState)
```

`ProjectState` 定义在 [ppt_maker/state.py](../ppt_maker/state.py)。LangGraph 会根据里面的 reducer 知道并发写入怎么合并。

最关键的 reducer：

```python
slide_specs: Annotated[dict[int, SlideSpec], merge_dict]
charts: Annotated[dict[str, str], merge_dict]
generated_images: Annotated[dict[str, str], merge_dict]
search_cache: Annotated[dict[str, Any], merge_dict]
errors: Annotated[list[NodeError], add]
```

这允许多个节点同时返回：

```python
{"slide_specs": {18: spec}}
{"slide_specs": {21: spec}}
```

最终合并成同一个 `state["slide_specs"]`。

## 节点注册

节点函数集中注册在 [ppt_maker/nodes/__init__.py](../ppt_maker/nodes/__init__.py)：

```python
NODE_REGISTRY = {
    "load_assets": load.run,
    "parse_outline": outline.run,
    ...
}
```

`build_graph()` 遍历注册表，把每个函数包一层 `_wrap_with_timer()`：

```python
for name, fn in NODE_REGISTRY.items():
    g.add_node(name, _wrap_with_timer(name, fn))
```

包装层负责：

- 记录节点耗时
- 记录产出页数
- 把异常转成 `NodeError`
- 避免单个节点失败中断整条工作流

## 普通边

普通边表示固定依赖关系：

```python
g.add_edge(START, "load_assets")
g.add_edge("load_assets", "parse_outline")
g.add_edge("load_assets", "poi_parser")
```

含义：

- `load_assets` 是入口节点。
- 它完成后，`parse_outline` 和 `poi_parser` 都可以开始。

## 静态并行内容节点

`CONTENT_NODES` 定义了一批内容节点：

```python
CONTENT_NODES = [
    "policy_research",
    "location_analysis",
    "economy_analysis",
    "poi_analysis",
    "cultural_node",
    "competitor_search",
    "cover_transition",
    "metrics",
]
```

大多数节点只依赖 `parse_outline`：

```python
for n in CONTENT_NODES:
    if n == "poi_analysis":
        continue
    g.add_edge("parse_outline", n)
```

`poi_analysis` 特殊一点，它同时需要 `parse_outline` 和 `poi_parser`：

```python
g.add_edge("poi_parser", "poi_analysis")
g.add_edge("parse_outline", "poi_analysis")
```

## 动态 fan-out：`Send`

有些任务不是一个节点生成所有页面，而是拆成多个 worker。

### 参考案例页

```python
g.add_edge("parse_outline", "case_study_dispatch")
g.add_conditional_edges(
    "case_study_dispatch",
    case_study.fanout,
    ["case_study_worker"],
)
```

`case_study.fanout()` 返回多个 `Send`：

```python
Send("case_study_worker", {"case_idx": i, **state})
```

每个 worker 负责一个案例页，通常是第 23-25 页。

### 概念方案页

```python
g.add_edge("parse_outline", "concept_dispatch")
g.add_conditional_edges(
    "concept_dispatch",
    concept.fanout,
    ["runninghub_worker"],
)
```

`concept.fanout()` 通常发出 9 个 worker：

```text
3 个方案 x 3 个视角 = 9 页
```

对应第 29-37 页。

## 为什么需要 `content_join` 和 `barrier`

`content_join` 和 `barrier` 都是 no-op：

```python
def _barrier(state: ProjectState) -> dict:
    return {}
```

它们的作用不是改状态，而是控制汇合点。

### `content_join`

所有静态内容节点都指向它：

```python
for n in CONTENT_NODES:
    g.add_edge(n, "content_join")
```

这保证静态内容节点完成后才进入下一层。

### `barrier`

三类分支都要汇入 `barrier`：

```python
g.add_edge("content_join", "barrier")
g.add_edge("case_study_worker", "barrier")
g.add_edge("runninghub_worker", "barrier")
```

这保证下游的 `summary_node -> aggregate_specs -> render_html` 只在所有内容分支完成后执行。

如果没有这个汇合点，渲染阶段可能在 worker 尚未写入页面时提前开始。

## 串行尾段

所有内容完成后，进入尾段：

```python
g.add_edge("barrier", "summary_node")
g.add_edge("summary_node", "aggregate_specs")
g.add_edge("aggregate_specs", "render_html")
g.add_edge("render_html", "validate")
g.add_edge("validate", END)
```

这里必须串行：

1. `summary_node` 需要读取前面生成的状态。
2. `aggregate_specs` 需要看到所有页面。
3. `render_html` 需要完整 `slide_specs`。
4. `validate` 需要最终 HTML 路径。

## Checkpoint 如何接入

CLI 中：

```python
ckpt_path = Path(state["output_dir"]) / "checkpoint.sqlite"
with get_checkpointer(ckpt_path) as saver:
    app = build_graph(checkpointer=saver)
    app.invoke(state, config={"configurable": {"thread_id": f"case-{case_id}"}})
```

`get_checkpointer()` 返回：

```python
SqliteSaver.from_conn_string(str(sqlite_path))
```

关键点：

- checkpoint 文件在 `output/case_<id>/checkpoint.sqlite`
- `thread_id` 是 `case-<id>`
- 同一 case 多次运行会复用同一线程
- 使用 `--force` 会先删除 checkpoint 文件

## 节点失败时发生什么

节点函数被 `_wrap_with_timer()` 包住：

```python
try:
    out = fn(state)
except Exception as e:
    return {"errors": [NodeError(node=name, message=str(e))]}
```

因此节点失败后：

- graph 不会直接崩溃
- 错误进入 `state["errors"]`
- `logs/run.jsonl` 写入失败记录
- 后续 `aggregate_specs` 会补缺页

这也是为什么最终可能生成成功，但 deck 里有 `[missing page N]`。

## 新增节点时要改哪里

最小步骤：

1. 新建 `ppt_maker/nodes/my_node.py`。
2. 在 `ppt_maker/nodes/__init__.py` 注册。
3. 在 `ppt_maker/graph.py` 连边。
4. 确保节点返回的字段在 `ProjectState` 里有合理 reducer，尤其是并行写字段。

具体示例见 [extension-guide.md](extension-guide.md)。
