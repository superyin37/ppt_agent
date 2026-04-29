# 系统架构

本文从模块分层角度解释 PPT-Maker。若只想理解 LangGraph 具体怎么连边，先读 [langgraph.md](langgraph.md)；若只想看一次生成链路，先读 [pipeline.md](pipeline.md)。

## 架构分层

```text
CLI 层
  ppt_maker/__main__.py

编排层
  ppt_maker/graph.py

状态与契约层
  ppt_maker/state.py
  ppt_maker/assets.py

内容节点层
  ppt_maker/nodes/*.py

外部服务层
  ppt_maker/clients/*.py

渲染层
  ppt_maker/render/*.py
  templates/<template_name>/

输出层
  output/case_<id>/
```

## CLI 层

入口：[ppt_maker/__main__.py](../ppt_maker/__main__.py)

职责：

- 解析命令行参数
- 创建初始 `ProjectState`
- 配置 checkpoint
- 调用 `build_graph().invoke(...)`
- 提供 `render-only` 和 `inspect` 这两个调试入口

CLI 不直接生成页面。它只负责启动工作流。

## 编排层

入口：[ppt_maker/graph.py](../ppt_maker/graph.py)

职责：

- 创建 `StateGraph(ProjectState)`
- 注册所有节点
- 定义节点之间的边
- 使用 `Send` 动态 fan-out worker
- 用 barrier 汇合并发分支
- 给每个节点包一层计时、日志和错误隔离

设计重点是：内容节点可以并行写入 `slide_specs`，最终由 reducer 合并。

## 状态与契约层

入口：[ppt_maker/state.py](../ppt_maker/state.py)

这里定义了项目的核心数据契约：

- `AssetIndex`：case 输入文件索引
- `UserInput` / `SiteCoords`：基础输入
- `DesignOutline`：从 markdown 大纲抽取出的结构化信息
- `POIData`：从 Excel 抽取出的 POI 信息
- `SlideSpec`：页面的统一中间表示
- `ProjectState`：LangGraph 流转状态

最关键的是 `SlideSpec`：

```python
class SlideSpec(BaseModel):
    page: int
    component: ComponentKind
    title: str = ""
    subtitle_en: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None
```

所有内容节点最终都应该产出 `SlideSpec`，而不是直接拼 HTML。

## 内容节点层

入口：[ppt_maker/nodes/](../ppt_maker/nodes)

每个节点遵守同一个接口：

```python
def run(state: ProjectState) -> dict:
    return {"slide_specs": {page: spec}}
```

节点可以读取 `assets`、`outline`、`poi_data` 等字段，但只返回自己负责的局部更新。

节点注册表在 [ppt_maker/nodes/__init__.py](../ppt_maker/nodes/__init__.py)：

```python
NODE_REGISTRY = {
    "load_assets": load.run,
    "parse_outline": outline.run,
    ...
}
```

新增节点时，先注册到这里，再在 [ppt_maker/graph.py](../ppt_maker/graph.py) 连边。

## 外部服务层

入口：[ppt_maker/clients/](../ppt_maker/clients)

当前有三类外部能力：

| Client | 用途 | 可选性 |
|---|---|---|
| `DoubaoClient` | LLM 能力预留 | 可选 |
| `TavilyWrapper` | 第 22 页联网检索 | 可选 |
| `RunningHubClient` | logo、文化图、概念方案图 | 可选 |

这些服务都应该能降级。也就是说，缺 key 或调用失败时，工作流仍应产出 deck，只是部分内容变成说明或占位图。

## 渲染层

入口：

- [ppt_maker/render/html_renderer.py](../ppt_maker/render/html_renderer.py)
- [templates/minimalist_architecture/](../templates/minimalist_architecture)

渲染层只关心 `SlideSpec`：

```text
SlideSpec(component="chart")
  -> templates/<template>/components/chart.html.j2
  -> HTML 片段
```

`HtmlRenderer` 会：

1. 读取 `theme.json`
2. 读取 `viewport-base.css`
3. 初始化 Jinja2 environment
4. 为每页选择对应组件模板
5. 把图片以内联 `data:` URI 写入 HTML
6. 最后套进 `base.html.j2`

这个设计让内容生成和视觉表现分离：改视觉模板不需要改节点，改节点通常不需要碰模板。

## 输出层

一次成功运行会写出：

| 文件 | 用途 |
|---|---|
| `index.html` | 最终可打开的 40 页演示文稿 |
| `slide_specs.json` | 结构化页面数据，可手改后 `render-only` |
| `assets/charts/` | 图表 PNG |
| `assets/generated/` | AI 生成图或 SVG 占位 |
| `checkpoint.sqlite` | LangGraph 恢复执行 |
| `logs/run.jsonl` | 每个节点的耗时、产页数量、错误 |

## 关键设计取舍

### 1. 先生成结构化 spec，再渲染 HTML

这样可以：

- 用 `inspect` 查看任意页面数据
- 手动编辑 `slide_specs.json` 后快速重渲
- 让模板系统保持可替换

### 2. 节点失败不阻断整份 deck

建筑方案汇报通常宁愿先得到一份有占位页的 deck，也不希望因为一张图失败导致整条链路中断。因此节点异常被记录到 `errors[]`，最终由 `aggregate_specs` 补缺页。

### 3. 使用 checkpoint 避免重复调用昂贵 API

RunningHub 图像生成成本高、耗时长。checkpoint 让已完成节点结果可以复用。调试节点逻辑时记得使用 `--force`。

### 4. 并行节点通过 reducer 合并结果

`slide_specs`、`charts`、`generated_images` 都是字典型 reducer 字段。不同节点写不同 key，可以天然并行合并。
