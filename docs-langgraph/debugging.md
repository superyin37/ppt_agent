# 调试与排查

本文按常见问题组织。多数问题都可以从三个地方开始查：

```text
output/case_<id>/slide_specs.json
output/case_<id>/logs/run.jsonl
output/case_<id>/checkpoint.sqlite
```

## 先跑一个低成本版本

调模板或数据解析时，先用 dry run：

```bash
python -m ppt_maker run --case 688 --dry-run --force
```

这会跳过外部图像生成，速度更快，也避免重复消耗 API。

## 查看某一页的结构化数据

```bash
python -m ppt_maker inspect --case 688 --page 18
```

如果页面内容不对，先看 `SlideSpec`：

- `component` 是否是预期组件
- `title` 是否正确
- `data` 是否有模板需要的字段
- 图片路径是否存在

如果 `SlideSpec` 正确但 HTML 不对，问题通常在模板。  
如果 `SlideSpec` 本身不对，问题通常在节点或输入解析。

## 只重渲 HTML

```bash
python -m ppt_maker render-only --case 688
```

适用场景：

- 只改了 `templates/`
- 只改了 CSS
- 手动编辑了 `slide_specs.json`
- 不想重跑 LangGraph 和外部 API

## 改了代码但结果没变化

优先怀疑 checkpoint 复用了旧状态。

使用：

```bash
python -m ppt_maker run --case 688 --force
```

`--force` 会删除：

```text
output/case_688/checkpoint.sqlite
```

然后从头执行。

## deck 中出现 `[missing page N]`

原因：负责该页的节点没有产出 `SlideSpec`，或者节点异常了。

排查步骤：

1. 根据 [pipeline.md](pipeline.md) 中的“40 页生成来源”表找到该页对应节点。
2. 查看日志：

   ```bash
   Get-Content output/case_688/logs/run.jsonl -Tail 50
   ```

3. 搜索对应节点是否 `ok=false`。
4. 查看输入文件是否缺少对应语义键。

常见例子：

| 缺页 | 可能节点 | 常见原因 |
|---|---|---|
| 4-7 | `policy_research` | 大纲中政策章节解析失败 |
| 18/21 | `poi_analysis` | `场地poi.xlsx` 缺失或 sheet 名不匹配 |
| 23-25 | `case_study_worker` | 参考案例不足或图片语义键不匹配 |
| 29-37 | `runninghub_worker` | 概念方案 seed 不足或图像节点异常 |

## 图片没有显示

先看 `SlideSpec.data` 中的图片路径：

```bash
python -m ppt_maker inspect --case 688 --page 29
```

再确认路径文件存在。

常见原因：

| 现象 | 原因 |
|---|---|
| 路径为空 | 节点没找到输入图片或生成图 |
| 路径指向旧机器目录 | `slide_specs.json` 是旧环境生成的 |
| SVG 占位图 | 缺 `RUNNING_HUB_KEY`、`--dry-run`、或 RunningHub 调用失败 |
| HTML 里不显示但文件存在 | 模板字段名不匹配 |

如果 `slide_specs.json` 里是旧绝对路径，建议重新运行：

```bash
python -m ppt_maker run --case 688 --force --dry-run
```

## 第 22 页没有联网结果

第 22 页由 `competitor_search` 生成，依赖 `TAVILY_API_KEY`。

检查 `.env`：

```text
TAVILY_API_KEY=...
```

如果未配置，页面会显示未配置说明，这是预期降级行为。

## 图像生成很慢

第 29-37 页由 `runninghub_worker` 生成，通常是全链路最慢的部分。

看耗时：

```bash
Get-Content output/case_688/logs/run.jsonl | Select-String runninghub_worker
```

本地调试建议：

```bash
python -m ppt_maker run --case 688 --dry-run --force
```

模板稳定后再关掉 `--dry-run` 跑真实图。

## 图表中文显示方块

图表由 matplotlib 生成。原因通常是系统缺中文字体。

Windows 通常有 `Microsoft YaHei`。Linux/CI 需要安装 Noto CJK 或类似字体。

相关代码：[ppt_maker/render/charts.py](../ppt_maker/render/charts.py)

## 页面 HTML 样式错乱

先区分是数据问题还是模板问题：

1. `inspect` 看 `SlideSpec` 是否正确。
2. `render-only` 排除节点影响。
3. 检查对应组件：

   ```text
   templates/minimalist_architecture/components/<component>.html.j2
   ```

4. 检查全局 CSS：

   ```text
   templates/minimalist_architecture/viewport-base.css
   ```

如果只改了 CSS，不需要重新 `run`，直接 `render-only`。

## 查看节点耗时

PowerShell 简单看尾部：

```bash
Get-Content output/case_688/logs/run.jsonl -Tail 20
```

如果有 `jq`：

```bash
jq -s 'sort_by(-.duration_s) | .[0:10]' output/case_688/logs/run.jsonl
```

## 最小排查顺序

遇到生成问题时，建议按这个顺序：

1. `python -m ppt_maker inspect --case 688 --page <N>`
2. 查 `logs/run.jsonl` 中对应节点。
3. 查 `data/case_<id>/` 是否有节点需要的输入。
4. 如改过代码，使用 `--force` 清 checkpoint。
5. 如只改模板，使用 `render-only`。
