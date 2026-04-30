---
title: PPT-Maker 项目理解手册
audience: 第一次读项目的开发者 / 维护者
read_time: 6 分钟
prerequisites: 无
last_verified_against: f083adb
---

# PPT-Maker 项目理解手册

这组文档面向想读懂、调试或扩展 PPT-Maker 的开发者。项目的核心目标是：

> 读取 `data/case_<id>/` 下的建筑设计资料，经过 LangGraph 工作流生成 40 页结构化 `SlideSpec`，再用 Jinja2 模板渲染成单文件 HTML 演示文稿。

## 输入 → 输出全景

一次完整运行不是“直接生成 HTML”，而是分成两层：内容层读取输入资料并产出 40 页 `SlideSpec`，表现层根据 `SlideSpec.component` 找到 Jinja2 组件并渲染 HTML。

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

## LLM 现状一句话

当前 pipeline **不调用任何 LLM 做文本生成**。文字内容来自 Python 字面量、正则/表格解析、Excel 映射、启发式打分和 Tavily 检索结果；豆包 `DoubaoClient` 已实现但未被任何节点调用。外部 AI 当前只用于 RunningHub 图像生成。

详见 [llm-and-external-services.md](llm-and-external-services.md)。

## 项目里没有什么

| 不存在的能力 | 说明 |
|---|---|
| 内容质量审查 | 不检查生成文字是否准确 |
| LLM-as-judge | 没有模型复核节点 |
| 截图回看 | 渲染后不做视觉截图检查 |
| RAG / vector search | 没有向量库或语义检索 |
| 跨节点业务缓存 | 除 LangGraph checkpoint 外，没有独立缓存层 |
| 模板字段契约校验 | `SlideSpec.data` 内部字段不由 Pydantic 校验 |

## 推荐阅读顺序

| 顺序 | 文档 | 读完应当理解 |
|---|---|---|
| 1 | [glossary.md](glossary.md) | LangGraph、项目术语和外部服务名词 |
| 2 | [pipeline.md](pipeline.md) | 一次运行中，输入如何一步步变成 40 页 deck |
| 3 | [llm-and-external-services.md](llm-and-external-services.md) | 当前哪些地方真的调用 AI 或外部 API，哪些没有 |
| 4 | [langgraph.md](langgraph.md) | `build_graph()` 如何构造节点、边、并发 fan-out 和 barrier |
| 5 | [data.md](data.md) | 输入文件、`ProjectState`、reducer、`SlideSpec` 的数据契约 |
| 6 | [templates.md](templates.md) | `SlideSpec` 如何映射到 Jinja2 组件并渲染成 HTML |
| 7 | [configuration.md](configuration.md) | CLI、`.env`、外部 API、checkpoint 和降级行为 |
| 8 | [debugging.md](debugging.md) | 页面缺失、图片没生成、checkpoint 复用等常见排查路径 |
| 9 | [data-flow-walkthrough.md](data-flow-walkthrough.md) | 用 case_688 跟一遍真实数据形态 |
| 10 | [diagrams.md](diagrams.md) | 架构、拓扑、时序、渲染和 checkpoint 图 |
| 11 | [extension-guide.md](extension-guide.md) | 新增节点、页面组件、模板、图像供应商的改法 |
| 12 | [architecture.md](architecture.md) | 从模块分层角度看整体架构和关键设计取舍 |

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
