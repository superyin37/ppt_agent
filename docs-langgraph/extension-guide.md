# 扩展指南

本文给出常见扩展任务的改法。扩展前建议先读：

- [pipeline.md](pipeline.md)
- [langgraph.md](langgraph.md)
- [data.md](data.md)
- [templates.md](templates.md)

## 新增一个内容节点

目标：新增一个节点，生成第 6 页的“风险评估”页面。

### 1. 新建节点文件

新建：

```text
ppt_maker/nodes/risk.py
```

示例：

```python
from __future__ import annotations

from ..state import ProjectState, SlideSpec


def run(state: ProjectState) -> dict:
    spec = SlideSpec(
        page=6,
        component="content_bullets",
        title="风险评估",
        subtitle_en="RISK ASSESSMENT",
        data={
            "lede": "项目风险主要来自政策、市场、交通组织和实施节奏。",
            "bullets": [
                {"title": "政策风险", "body": "关注上位规划和用地条件约束。"},
                {"title": "市场风险", "body": "关注周边竞品供给和客群错位。"},
            ],
        },
    )
    return {"slide_specs": {6: spec}}
```

注意：如果第 6 页已有节点生成，后写入的结果可能覆盖前者。更稳妥的方式是选择空闲页，或明确调整页码分配。

### 2. 注册节点

修改 [ppt_maker/nodes/__init__.py](../ppt_maker/nodes/__init__.py)：

```python
from . import risk

NODE_REGISTRY = {
    ...
    "risk_assessment": risk.run,
}
```

### 3. 接入 graph

如果节点依赖 `parse_outline`，加入 [ppt_maker/graph.py](../ppt_maker/graph.py) 的 `CONTENT_NODES`：

```python
CONTENT_NODES = [
    ...
    "risk_assessment",
]
```

并确保循环会连边：

```text
parse_outline -> risk_assessment -> content_join
```

### 4. 更新文档

至少更新：

- [pipeline.md](pipeline.md) 的页码表
- 如有新输入，更新 [data.md](data.md)

## 新增一个页面组件

目标：新增 `comparison_matrix` 组件。

### 1. 注册组件类型

修改 [ppt_maker/state.py](../ppt_maker/state.py)：

```python
ComponentKind = Literal[
    ...
    "comparison_matrix",
]
```

### 2. 新建模板组件

新建：

```text
templates/minimalist_architecture/components/comparison_matrix.html.j2
```

组件接收 `data`：

```python
{
    "headers": list[str],
    "rows": list[list[str]],
    "highlights": list[int],
}
```

### 3. 节点产出新组件

```python
SlideSpec(
    page=22,
    component="comparison_matrix",
    title="竞品对比矩阵",
    data={
        "headers": ["项目", "距离", "定位", "启示"],
        "rows": [...],
        "highlights": [0, 2],
    },
)
```

### 4. 更新模板文档

在 [templates.md](templates.md) 的组件数据契约中补充 `comparison_matrix`。

## 新增一个模板风格

复制默认模板：

```bash
Copy-Item templates/minimalist_architecture templates/my_style -Recurse
```

修改：

- `theme.json`：颜色和字体。
- `viewport-base.css`：全局排版、尺寸、导航。
- `base.html.j2`：HTML 外壳。
- `components/*.html.j2`：各组件视觉。

运行：

```bash
python -m ppt_maker run --case 688 --template my_style --dry-run --force
```

只改模板时：

```bash
python -m ppt_maker render-only --case 688 --template my_style
```

## 新增输入文件类型

假设要新增 `市场调研_<id>.md`。

### 1. 文件命名

放入：

```text
data/case_688/市场调研_688.md
```

语义键会是：

```text
市场调研
```

### 2. 节点读取

```python
assets = state.get("assets")
path = assets.docs.get("市场调研") if assets else None
```

### 3. 新增 schema

如果数据会被多个节点共享，建议在 [ppt_maker/state.py](../ppt_maker/state.py) 加 Pydantic schema，并在 `ProjectState` 中加字段。

如果只被单个节点使用，可以在节点内部解析，不必污染全局状态。

### 4. 注意 reducer

如果新字段会被多个并行节点写入，必须加 reducer。否则 LangGraph 并发写同一字段时可能报错或行为不符合预期。

## 修改总页数

当前总页数 40 写在多个地方：

| 位置 | 含义 |
|---|---|
| [ppt_maker/nodes/aggregate.py](../ppt_maker/nodes/aggregate.py) | 补齐 1-40 页 |
| [ppt_maker/nodes/validate.py](../ppt_maker/nodes/validate.py) | 校验 40 页 |
| [ppt_maker/render/html_renderer.py](../ppt_maker/render/html_renderer.py) | 章节页码归属 |
| `templates/*/components/_chrome.html.j2` | 页码显示 `/ 40` |
| [docs/pipeline.md](pipeline.md) | 页码表 |

建议抽成配置前，先小心同步修改这些位置。

## 换图像供应商

当前图像供应商是 [ppt_maker/clients/runninghub.py](../ppt_maker/clients/runninghub.py)。

要替换成新的服务，建议保持类似接口：

```python
class MyImageClient:
    @property
    def available(self) -> bool:
        ...

    async def generate(self, prompt: str, out_path: Path) -> Path:
        ...

    def placeholder_svg(self, path: Path, *, title: str, subtitle: str, palette: tuple[str, str], hint: str = "") -> Path:
        ...
```

需要修改调用处：

- [ppt_maker/nodes/concept.py](../ppt_maker/nodes/concept.py)
- [ppt_maker/nodes/culture.py](../ppt_maker/nodes/culture.py)

原则：失败时返回可用占位图，而不是让整个节点崩溃。

## 修改图拓扑

新增依赖时要想清楚两件事：

1. 该节点依赖哪些状态字段？
2. 它写入的字段是否可能和其他节点并发冲突？

常见接法：

```python
g.add_edge("parse_outline", "my_node")
g.add_edge("my_node", "content_join")
```

如果它还依赖 POI：

```python
g.add_edge("parse_outline", "my_node")
g.add_edge("poi_parser", "my_node")
g.add_edge("my_node", "content_join")
```

如果它需要动态展开多个 worker，参考 `case_study_dispatch` 和 `concept_dispatch` 的 `Send` 模式。

## 扩展前的检查清单

- 新节点是否注册到 `NODE_REGISTRY`？
- graph 是否连边？
- 并发写入字段是否有 reducer？
- `SlideSpec.component` 是否在 `ComponentKind` 中？
- 模板组件文件是否存在？
- `spec.data` 是否满足组件契约？
- 改过图逻辑后是否用了 `--force` 清 checkpoint？
- 只改模板时是否用了 `render-only`？
