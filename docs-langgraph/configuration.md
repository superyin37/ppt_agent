# 配置、CLI 与 checkpoint

本文解释运行项目时会用到的环境变量、命令行参数、降级行为和 checkpoint 机制。

## `.env`

配置从仓库根目录 `.env` 读取，实现在 [ppt_maker/config.py](../ppt_maker/config.py)。

仓库提供 `.env.example`。所有外部 API key 都是可选的，缺失时项目会尽量降级产出 deck。

| 变量 | 别名 | 默认值 | 用途 |
|---|---|---|---|
| `DOUBAO_API_KEY` | 无 | 空 | 豆包 / 火山方舟 LLM |
| `DOUBAO_BASE_URL` | `DOUBAO_API_BASE` | `https://ark.cn-beijing.volces.com/api/v3` | 豆包 OpenAI-compatible endpoint |
| `DOUBAO_MODEL` | 无 | `doubao-1-5-pro-32k-250115` | 模型名 |
| `RUNNING_HUB_KEY` | `RUNNINGHUB_API_KEY` | 空 | RunningHub 图像生成 |
| `TAVILY_API_KEY` | 无 | 空 | Tavily 联网检索 |
| `LOG_LEVEL` | 无 | `INFO` | 日志级别 |

## 降级矩阵

| 缺少或失败 | 影响节点 | 降级行为 |
|---|---|---|
| `RUNNING_HUB_KEY` | `cultural_node`、`cover_transition`、`runninghub_worker` | 使用本地 SVG 占位图 |
| RunningHub 调用失败 | 同上 | 记录 hint，仍返回占位图路径 |
| `TAVILY_API_KEY` | `competitor_search` | 第 22 页表格显示未配置说明 |
| Tavily 调用失败 | `competitor_search` | 第 22 页内容减少，但节点完成 |
| `DOUBAO_API_KEY` | 当前多数节点不强依赖 | 跳过 LLM 增强 |
| 输入文件缺失 | 对应节点 | 少产出页面，最终由 `aggregate_specs` 补缺页 |
| 节点异常 | 对应节点 | 记录 `NodeError`，工作流继续 |

`--dry-run` 和 `--no-images` 都会设置 `state["dry_run"] = True`，图像相关节点直接走占位图路径，适合本地调模板。

## CLI 命令

入口：[ppt_maker/__main__.py](../ppt_maker/__main__.py)

### 列出 case

```bash
python -m ppt_maker list-cases
```

列出 `data/` 下所有 `case_*` 目录。

### 完整运行

```bash
python -m ppt_maker run --case 688
```

常用参数：

| 参数 | 含义 |
|---|---|
| `--case <id>` | 必需，对应 `data/case_<id>` |
| `--template <name>` | 模板名，默认 `minimalist_architecture` |
| `--dry-run` | 跳过外部 API，使用占位结果 |
| `--no-images` | 当前等价于 `--dry-run` |
| `--force` | 删除 checkpoint 后从头跑 |

示例：

```bash
python -m ppt_maker run --case 688 --dry-run
python -m ppt_maker run --case 688 --force
python -m ppt_maker run --case 688 --template my_style
```

### 只重渲 HTML

```bash
python -m ppt_maker render-only --case 688
```

读取现有 `output/case_688/slide_specs.json`，重新生成 `index.html`。不会运行 LangGraph，也不会调用外部 API。

适合：

- 改模板 CSS 后看效果
- 手动修改 `slide_specs.json` 后重渲
- 不想重跑 RunningHub 图像生成

### 查看单页 spec

```bash
python -m ppt_maker inspect --case 688 --page 18
```

打印某一页的 `SlideSpec` JSON。调试“页面为什么这样渲染”时先看这里。

## Checkpoint

实现：[ppt_maker/graph.py](../ppt_maker/graph.py)

运行时会创建：

```text
output/case_<id>/checkpoint.sqlite
```

CLI 中的关键代码：

```python
thread_id = f"case-{case_id}"
config = {"configurable": {"thread_id": thread_id}}
```

含义：

- 同一个 case 会复用同一个 LangGraph thread。
- 已成功的 superstep 会保存到 SQLite。
- 中断后再次运行，会从 checkpoint 恢复。
- 昂贵的图像生成节点不会无意义重复执行。

调试代码变更时注意：如果 checkpoint 还在，可能复用旧状态，导致你以为改动没生效。

清理方式：

```bash
python -m ppt_maker run --case 688 --force
```

或手动删除：

```bash
Remove-Item output/case_688/checkpoint.sqlite
```

## 日志

每个节点都会写一行 JSON 到：

```text
output/case_<id>/logs/run.jsonl
```

示例：

```json
{"node": "policy_research", "ok": true, "duration_s": 0.412, "slides_emitted": 4}
{"node": "runninghub_worker", "ok": false, "duration_s": 305.0, "error": "TimeoutError: ..."}
```

常用排查：

```bash
Get-Content output/case_688/logs/run.jsonl -Tail 20
```

或使用 `jq`：

```bash
jq -s 'sort_by(-.duration_s) | .[0:10]' output/case_688/logs/run.jsonl
```

## 字体与图表

图表生成在 [ppt_maker/render/charts.py](../ppt_maker/render/charts.py)。它会尝试使用中文字体优先链，包括：

```text
Microsoft YaHei
PingFang SC
SimHei
Noto CJK
Arial Unicode MS
```

如果图表中文显示为方块，通常是运行环境缺中文字体。Windows 一般有 `Microsoft YaHei`，Linux/CI 常需要安装 Noto CJK。
