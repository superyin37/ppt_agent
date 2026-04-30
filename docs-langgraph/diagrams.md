---
title: 图集
audience: 第一次读项目的开发者 / 维护者 / 架构师
read_time: 8 分钟
prerequisites: glossary.md, pipeline.md
last_verified_against: f083adb
---

# 图集

> **读完这篇，你应该能回答：**
> - 项目的层次、拓扑、并发、渲染和外部服务时序分别长什么样？
> - 哪张图应该被其他文档引用？
> - reducer、checkpoint、RunningHub fallback 的关系怎么解释？

> **关联文档：**
> - 主链路：[pipeline.md](pipeline.md)
> - LangGraph：[langgraph.md](langgraph.md)
> - 模板系统：[templates.md](templates.md)

## 图 1：分层架构

```mermaid
flowchart TB
  CLI[CLI: __main__.py] --> G[Graph: graph.py]
  G --> S[State/contracts: state.py + assets.py]
  G --> N[Nodes: ppt_maker/nodes/*]
  N --> C[Clients: RunningHub / Tavily / Doubao reserved]
  N --> R[Render: HtmlRenderer]
  R --> T[Templates: Jinja2 components]
  R --> O[Output: index.html + slide_specs.json]
  G --> CK[checkpoint.sqlite]
  N --> L[logs/run.jsonl]
```

## 图 2：完整 LangGraph 拓扑

```mermaid
flowchart TD
  START --> load_assets
  load_assets --> parse_outline
  load_assets --> poi_parser
  parse_outline --> policy_research
  parse_outline --> location_analysis
  parse_outline --> economy_analysis
  parse_outline --> cultural_node
  parse_outline --> competitor_search
  parse_outline --> cover_transition
  parse_outline --> metrics
  parse_outline --> poi_analysis
  poi_parser --> poi_analysis
  parse_outline --> case_study_dispatch
  case_study_dispatch -.Send x3.-> case_study_worker
  parse_outline --> concept_dispatch
  concept_dispatch -.Send x9.-> runninghub_worker
  policy_research --> content_join
  location_analysis --> content_join
  economy_analysis --> content_join
  poi_analysis --> content_join
  cultural_node --> content_join
  competitor_search --> content_join
  cover_transition --> content_join
  metrics --> content_join
  content_join --> barrier
  case_study_worker --> barrier
  runninghub_worker --> barrier
  barrier --> summary_node
  summary_node --> aggregate_specs
  aggregate_specs --> render_html
  render_html --> validate
  validate --> END
```

## 图 3：superstep 时序

```mermaid
sequenceDiagram
  participant A as load_assets
  participant O as parse_outline
  participant P as poi_parser
  participant S as static content
  participant D as dispatchers
  participant W as Send workers
  participant B as barrier
  participant R as render tail

  A->>O: next superstep
  A->>P: next superstep
  O->>S: content fan-out
  O->>D: Send dispatch
  P->>S: poi_analysis dependency
  D->>W: dynamic workers
  S->>B: via content_join
  W->>B: worker fan-in
  B->>R: summary -> aggregate -> render -> validate
```

## 图 4：HtmlRenderer 数据流

```mermaid
flowchart LR
  A[SlideSpec] --> B[render_slide]
  B --> C{component}
  C --> D[components/chart.html.j2]
  C --> E[components/table.html.j2]
  C --> F[components/concept_scheme.html.j2]
  D --> G[slide HTML]
  E --> G
  F --> G
  G --> H[base.html.j2]
  H --> I[index.html]
  A --> J[embed_image paths]
  J --> K[data URI]
  K --> G
```

## 图 5：RunningHub 调用时序

```mermaid
sequenceDiagram
  participant N as node
  participant C as RunningHubClient
  participant API as RunningHub API
  participant O as output assets

  N->>C: generate(prompt, out_path)
  alt no key or dry-run handled by node
    C->>O: placeholder_svg
  else API available
    C->>API: submit prompt
    API-->>C: taskId
    loop poll until SUCCESS/FAILED/timeout
      C->>API: query taskId
      API-->>C: status
    end
    C->>API: download image
    C->>O: write jpg/png
  end
  C-->>N: path
```

## 图 6：reducer 合并

```mermaid
flowchart LR
  A[node A returns slide_specs 18] --> M[merge_dict]
  B[node B returns slide_specs 21] --> M
  C[node C returns charts policy_impact] --> MC[merge_dict]
  M --> S[state.slide_specs]
  MC --> CH[state.charts]
```

浅合并规则：不同 key 合并，同 key 后写覆盖前写。

## 图 7：checkpoint 与 thread_id

```mermaid
flowchart LR
  A[run --case 688] --> B[thread_id case-688]
  B --> C[output/case_688/checkpoint.sqlite]
  C --> D[resume or reuse state]
  E[run --case 688 --force] --> F[delete checkpoint.sqlite]
  F --> G[fresh run]
```
