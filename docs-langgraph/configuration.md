---
title: 配置、CLI 与降级
audience: 第一次运行项目的开发者 / 维护者
read_time: 10 分钟
prerequisites: glossary.md, llm-and-external-services.md
last_verified_against: f083adb
---

# 配置、CLI 与降级

> **读完这篇，你应该能回答：**
> - `.env` 里每个变量影响什么？
> - `--dry-run`、`--no-images`、`--force` 分别什么时候用？
> - 外部服务失败时工作流是否中断，deck 是否还能生成？
> - checkpoint 为什么会影响调试结果？

> **关联文档：**
> - 上一篇：[llm-and-external-services.md](llm-and-external-services.md)
> - 下一篇：[debugging.md](debugging.md)
> - CLI 入口：[__main__.py](../ppt_maker/__main__.py)

## `.env`

配置从仓库根目录 `.env` 读取，实现在 [config.py](../ppt_maker/config.py)。所有外部 API key 都是可选的；缺失时项目会尽量降级产出 deck。

| 变量 | 别名 | 默认值 | 用途 |
|---|---|---|---|
| `DOUBAO_API_KEY` | 无 | 空 | 豆包 / 火山方舟 LLM；当前没有节点调用 |
| `DOUBAO_BASE_URL` | `DOUBAO_API_BASE` | `https://ark.cn-beijing.volces.com/api/v3` | 豆包 OpenAI-compatible endpoint |
| `DOUBAO_MODEL` | 无 | `doubao-1-5-pro-32k-250115` | 豆包模型名；当前预留 |
| `RUNNING_HUB_KEY` | `RUNNINGHUB_API_KEY` | 空 | RunningHub 图像生成 |
| `TAVILY_API_KEY` | 无 | 空 | Tavily 联网检索 |
| `LOG_LEVEL` | 无 | `INFO` | 日志级别 |

## 外部 API 调用细节

### RunningHub

| 项 | 当前实现 |
|---|---|
| 用途 | 文化图、logo/目录插图、9 张概念方案图 |
| 端点 | `POST https://www.runninghub.cn/openapi/v2/rhart-image-n-pro/text-to-image` |
| 认证 | `Bearer <RUNNING_HUB_KEY>` |
| 请求体 | `{prompt, aspectRatio, resolution}` |
| prompt 上限 | 20000 字符 |
| aspectRatio | `1:1`, `16:9`, `9:16`, `4:3`, `3:4`, `3:2`, `2:3`, `5:4`, `4:5`, `21:9` |
| resolution | `1k`, `2k`, `4k` |
| 轮询 | `POST /openapi/v2/query`，默认每 3 秒一次，最多 300 秒 |
| 状态 | `SUCCESS` / `FAILED` / 进行中 |
| 重试 | transient 错误重试 3 次，2s/4s 指数退避 |
| 并发 | `threading.Semaphore(5)` 跨线程限制 |
| 失败 | 写 SVG 占位图，hint 标出 `no API key` 或异常类型 |
| 文件保存 | 尊重服务端返回的 `outputType`，例如 jpg 或 png |

实现入口：[runninghub.py:105](../ppt_maker/clients/runninghub.py#L105)

### Tavily

| 项 | 当前实现 |
|---|---|
| 用途 | 第 22 页同类产品联网检索 |
| client | lazy import `TavilyClient` |
| 参数 | `search_depth="basic"`，默认 `max_results=5` |
| 未配置 key | 返回空列表 |
| 调用失败 | 捕获异常，返回空列表 |
| deck 是否继续 | 继续生成，第 22 页内容减少或显示未配置说明 |

实现入口：[tavily.py:28](../ppt_maker/clients/tavily.py#L28)

### 豆包 / Volcengine Ark

| 项 | 当前实现 |
|---|---|
| 用途 | LLM 文本能力预留 |
| 当前是否被节点调用 | 否 |
| 已实现方法 | `chat()`、`structured()` |
| 缺 key 影响 | 当前无影响 |
| 推荐接入层 | 节点层，写入 `SlideSpec.data` |

实现入口：[doubao.py:18](../ppt_maker/clients/doubao.py#L18)

## 降级矩阵

| 缺少或失败 | 影响节点 | 工作流是否中断 | deck 是否仍可生成 | 用户是否能感知 | 降级行为 |
|---|---|---|---|---|---|
| `RUNNING_HUB_KEY` | `cultural_node`, `cover_transition`, `runninghub_worker` | 否 | 是 | 是，显示 SVG 占位 | 写本地 SVG |
| RunningHub 调用失败 | 同上 | 否 | 是 | 是，SVG hint 有原因 | 记录 warning，写 SVG |
| `TAVILY_API_KEY` | `competitor_search` | 否 | 是 | 是，第 22 页有说明 | 返回未配置说明 |
| Tavily 调用失败 | `competitor_search` | 否 | 是 | 可能，第 22 页内容少 | 返回空结果 |
| `DOUBAO_API_KEY` | 当前无节点 | 否 | 是 | 否 | 无影响 |
| 输入文件缺失 | 对应节点 | 通常否 | 是 | 是，内容为空或缺页 | 少产出页面，aggregate 补缺 |
| 节点异常 | 对应节点 | 否 | 通常是 | 是，可能缺页 | 记录 `NodeError`，继续 |
| 模板字段缺失 | 对应组件 | 否 | 是 | 是，局部空白 | `ChainableUndefined` 渲染空字符串 |

## CLI 命令

入口：[__main__.py](../ppt_maker/__main__.py)

| 命令 | 场景 |
|---|---|
| `python -m ppt_maker list-cases` | 查看 `data/` 下有哪些 case |
| `python -m ppt_maker run --case 688` | 正常完整运行 |
| `python -m ppt_maker run --case 688 --dry-run` | 本地调试，跳过外部图像 API |
| `python -m ppt_maker run --case 688 --no-images` | 当前等价于 `--dry-run` |
| `python -m ppt_maker run --case 688 --force` | 删除 checkpoint 后从头跑 |
| `python -m ppt_maker render-only --case 688` | 只用已有 `slide_specs.json` 重渲 HTML |
| `python -m ppt_maker inspect --case 688 --page 18` | 查看单页 `SlideSpec` |

`--dry-run` 和 `--no-images` 的合并逻辑在 [__main__.py:63](../ppt_maker/__main__.py#L63)。

## 成本与时长参考

| 模式 | 外部 API | 时间特征 |
|---|---|---|
| `--dry-run` / `--no-images` | 不调用 RunningHub 图像 API | 通常最快，适合模板和数据调试 |
| 正常运行但无 RunningHub key | 不调用 RunningHub，写 SVG | 比真实图像快 |
| 正常运行且有 RunningHub key | RunningHub 约 9 张概念图 + logo/目录图 + 文化图 | 时间主要取决于 RunningHub 任务排队和下载 |
| Tavily | 第 22 页约 1 次搜索 | 通常不是耗时瓶颈 |

当前仓库没有稳定基准数据，不在文档里写固定秒数。需要基准时，按 [debugging.md](debugging.md) 里的 `logs/run.jsonl` 耗时统计跑一次。

## Checkpoint

运行时会创建：

```text
output/case_<id>/checkpoint.sqlite
```

CLI 使用固定 thread：

```python
thread_id = f"case-{case_id}"
config = {"configurable": {"thread_id": thread_id}}
```

代码：[__main__.py:68-69](../ppt_maker/__main__.py#L68-L69)

影响：

| 行为 | 结果 |
|---|---|
| 同 case 重跑 | 可能复用已有 checkpoint |
| 中断后重跑 | 可从 checkpoint 恢复 |
| 调试节点代码 | 可能看到旧结果 |
| 加 `--force` | 删除 checkpoint，从头执行 |

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

PowerShell 查看尾部：

```powershell
Get-Content output/case_688/logs/run.jsonl -Tail 20
```

## 字体与图表

图表由 matplotlib 生成。中文字体优先链在 [charts.py](../ppt_maker/render/charts.py)。如果图表中文显示为方块，通常是运行环境缺中文字体。Windows 一般有 `Microsoft YaHei`，Linux/CI 常需要安装 Noto CJK。
