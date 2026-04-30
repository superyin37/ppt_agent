---
title: 术语表
audience: 第一次读项目的开发者 / 维护者
read_time: 5 分钟
prerequisites: 无
last_verified_against: f083adb
---

# 术语表

> **读完这篇你应该能回答：**
> - 文档里反复出现的 LangGraph 术语是什么意思？
> - 项目内部的 `SlideSpec`、语义键、降级、barrier 指什么？
> - 外部服务 RunningHub、Tavily、豆包分别在当前项目里承担什么角色？
> - 遇到术语时应该继续读哪篇文档？

> **关联文档：**
> - 下一篇：[README.md](README.md)
> - 深度延伸：[langgraph.md](langgraph.md)
> - 外部服务：[llm-and-external-services.md](llm-and-external-services.md)

## LangGraph 术语

| 术语 | 解释 | 主要出现 |
|---|---|---|
| `StateGraph` | LangGraph 的有状态工作流图。节点读取共享 state，并返回局部更新。 | [langgraph.md](langgraph.md) |
| `ProjectState` | 本项目传给 LangGraph 的共享状态字典，字段定义在 [state.py:176](../ppt_maker/state.py#L176)。 | [data.md](data.md), [langgraph.md](langgraph.md) |
| 节点 | 一个接收 `state` 并返回 `dict` 更新的函数，例如 `parse_outline`、`render_html`。 | [pipeline.md](pipeline.md) |
| 边 | 节点之间的固定依赖关系。前置节点完成后，下游节点才有机会执行。 | [langgraph.md](langgraph.md) |
| 条件边 | 运行时根据 state 动态决定后续节点，常用于 fan-out。 | [langgraph.md](langgraph.md) |
| `Send` | LangGraph 的动态 fan-out 机制。本项目用它派发多个案例页 worker 和概念图 worker。 | [langgraph.md](langgraph.md), [pipeline.md](pipeline.md) |
| fan-out | 一个节点拆出多个并发 worker 的模式，例如 3 个案例页、9 张概念图。 | [pipeline.md](pipeline.md) |
| fan-in | 多个并发节点写回 state 后重新汇合。 | [langgraph.md](langgraph.md) |
| reducer | 多个并发节点写同一个 state key 时的合并规则。`slide_specs` 用浅合并，`errors` 用列表拼接。 | [data.md](data.md), [langgraph.md](langgraph.md) |
| superstep | 一批在同一阶段可并发执行的节点。下一批会等上一批全部完成。 | [langgraph.md](langgraph.md) |
| checkpoint | LangGraph 在 superstep 边界保存的状态快照。本项目用 sqlite checkpoint 支持恢复和复用。 | [configuration.md](configuration.md), [langgraph.md](langgraph.md) |
| `thread_id` | checkpoint 的逻辑运行标识。通常和 case 绑定，同一个 case 可复用之前的图状态。 | [langgraph.md](langgraph.md) |

## 项目术语

| 术语 | 解释 | 主要出现 |
|---|---|---|
| case | 一个输入项目目录，例如 `data/case_688/`。 | [README.md](README.md), [pipeline.md](pipeline.md) |
| 语义键 | 输入文件去掉 `_688` 这类尾缀后的业务名，例如 `设计建议书大纲`。节点通过语义键取文件，不硬猜路径。 | [data.md](data.md) |
| `AssetIndex` | case 目录扫描后的索引，分为 `images`、`docs`、`xlsx` 三个桶。 | [data.md](data.md) |
| `SlideSpec` | 内容节点输出给模板层的页面规格，包含 `page`、`component`、`title`、`data`。定义在 [state.py:157](../ppt_maker/state.py#L157)。 | [data.md](data.md), [templates.md](templates.md) |
| `ComponentKind` | `SlideSpec.component` 的枚举，决定使用哪个 Jinja2 组件模板。定义在 [state.py:149](../ppt_maker/state.py#L149)。 | [templates.md](templates.md) |
| `spec.data` | 传给具体组件的松耦合数据字典。Pydantic 只校验它是 dict，不校验内部字段。 | [templates.md](templates.md), [data.md](data.md) |
| 降级 | 外部服务、图片或输入缺失时不让流程崩溃，而是返回空表、SVG 占位图或缺页占位。 | [configuration.md](configuration.md), [debugging.md](debugging.md) |
| barrier | 为等待并发分支全部完成而设置的汇合节点。本项目有静态内容汇合和 Send worker 汇合两层。 | [langgraph.md](langgraph.md), [pipeline.md](pipeline.md) |
| render-only | 只读取已落盘的 `slide_specs.json` 重渲染 HTML，不重跑内容节点或外部服务。 | [configuration.md](configuration.md), [templates.md](templates.md) |
| dry-run | 跳过外部图像 API，直接走 SVG 占位图，适合本地调试模板和流程。 | [configuration.md](configuration.md) |

## 外部服务

| 术语 | 当前角色 | 主要出现 |
|---|---|---|
| RunningHub | 图像生成服务。当前用于文化图、logo/目录插图和 9 张概念方案图；失败时写 SVG 占位图。 | [llm-and-external-services.md](llm-and-external-services.md) |
| Tavily | 联网检索服务。当前用于第 22 页同类产品检索；未配置时返回空结果并继续生成 deck。 | [llm-and-external-services.md](llm-and-external-services.md) |
| 豆包 | Volcengine Ark 上的 LLM 文本能力。当前客户端已实现，但没有节点调用。 | [llm-and-external-services.md](llm-and-external-services.md) |
| `DoubaoClient` | 豆包客户端封装，提供 `chat()` 和 `structured()`。定义在 [doubao.py:18](../ppt_maker/clients/doubao.py#L18)，当前是扩展预留。 | [extension-guide.md](extension-guide.md) |
| Volcengine Ark | 豆包 OpenAI-compatible API 的承载平台。当前只体现在配置和客户端代码里。 | [configuration.md](configuration.md) |

## 内容来源分类

| 来源类别 | 含义 | 当前节点 | 是否走 LLM |
|---|---|---|---|
| Python 字面量 | 硬编码字符串、列表或字典 | `summary_node`, `cover_transition`, `ending` | 否 |
| 规则抽取 | 正则、markdown 表格、Excel sheet/列名映射 | `outline`, `poi_parser`, `policy`, `location`, `economy`, `poi_analysis`, `metrics` | 否 |
| 启发式打分 | 关键词命中数转成数值 | `policy._impact_score` | 否 |
| 外部 LLM 文本 | 调豆包做摘要、抽取或评审 | 当前无 | `DoubaoClient` 已就绪但未被调用 |
| 外部图像 | text-to-image 或 SVG fallback | `culture`, `concept worker`, `cover_transition` | 是，图像模型 |
| 外部检索 | 联网搜索结果进入表格 | `competitor_search` | 否 |
