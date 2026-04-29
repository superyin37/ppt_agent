# PPT-Maker 项目理解手册

这组文档面向想读懂、调试或扩展 PPT-Maker 的开发者。项目的核心目标是：

> 读取 `data/case_<id>/` 下的建筑设计资料，经过 LangGraph 工作流生成 40 页结构化 `SlideSpec`，再用 Jinja2 模板渲染成单文件 HTML 演示文稿。

## 先建立一个心智模型

一次完整运行不是“直接生成 HTML”，而是分成两层：

1. 内容层：多个节点读取输入资料，分别产出自己负责页码的 `SlideSpec`。
2. 表现层：`HtmlRenderer` 根据 `SlideSpec.component` 找到对应 Jinja2 组件，渲染出最终 HTML。

主链路可以简化为：

```text
data/case_<id>/
  -> load_assets
  -> parse_outline + poi_parser
  -> 并行内容节点
  -> summary_node
  -> aggregate_specs
  -> render_html
  -> validate
  -> output/case_<id>/index.html
```

## 推荐阅读顺序

| 顺序 | 文档 | 读完应当理解 |
|---|---|---|
| 1 | [pipeline.md](pipeline.md) | 一次运行中，输入如何一步步变成 40 页 deck |
| 2 | [langgraph.md](langgraph.md) | `build_graph()` 如何构造节点、边、并发 fan-out 和 barrier |
| 3 | [data.md](data.md) | 输入文件、`ProjectState`、reducer、`SlideSpec` 的数据契约 |
| 4 | [templates.md](templates.md) | `SlideSpec` 如何映射到 Jinja2 组件并渲染成 HTML |
| 5 | [configuration.md](configuration.md) | CLI、`.env`、外部 API、checkpoint 和降级行为 |
| 6 | [debugging.md](debugging.md) | 页面缺失、图片没生成、checkpoint 复用等常见排查路径 |
| 7 | [extension-guide.md](extension-guide.md) | 新增节点、页面组件、模板、图像供应商的改法 |
| 8 | [architecture.md](architecture.md) | 从模块分层角度看整体架构和关键设计取舍 |

## 关键代码入口

| 模块 | 作用 |
|---|---|
| [ppt_maker/__main__.py](../ppt_maker/__main__.py) | CLI 入口，创建初始 `ProjectState`，启动 graph |
| [ppt_maker/graph.py](../ppt_maker/graph.py) | LangGraph 拓扑、节点包装、checkpoint |
| [ppt_maker/state.py](../ppt_maker/state.py) | Pydantic schema、`ProjectState`、`SlideSpec` |
| [ppt_maker/assets.py](../ppt_maker/assets.py) | 扫描 case 目录，按语义键索引输入文件 |
| [ppt_maker/nodes/](../ppt_maker/nodes) | 各个内容生成节点 |
| [ppt_maker/render/html_renderer.py](../ppt_maker/render/html_renderer.py) | Jinja2 HTML 渲染器 |
| [templates/minimalist_architecture/](../templates/minimalist_architecture) | 默认视觉模板和组件 |

## 最常用命令

```bash
python -m ppt_maker list-cases
python -m ppt_maker run --case 688 --dry-run
python -m ppt_maker run --case 688 --force
python -m ppt_maker render-only --case 688
python -m ppt_maker inspect --case 688 --page 18
```

面向安装、快速运行和用户视角的说明见仓库根目录 [README.md](../README.md)。本目录重点解释内部实现。
