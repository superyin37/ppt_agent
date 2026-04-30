---
title: 扩展指南
audience: 维护者 / 准备改功能的开发者
read_time: 12 分钟
prerequisites: pipeline.md, langgraph.md, templates.md
last_verified_against: f083adb
---

# 扩展指南

> **读完这篇，你应该能回答：**
> - 改文案、视觉、数据逻辑、节点和架构分别从哪里动？
> - 把启发式逻辑换成豆包 LLM 时如何保留兜底？
> - 加内容审查节点时应该接在哪条边上？
> - 改完后最低限度要跑哪些自检？

> **关联文档：**
> - 主链路：[pipeline.md](pipeline.md)
> - 架构：[architecture.md](architecture.md)
> - 排查：[debugging.md](debugging.md)

## Level 1：改文案 / 视觉

| 任务 | 入口 |
|---|---|
| 改第 19/26/39 页综合文案 | [summary.py](../ppt_maker/nodes/summary.py) |
| 改目录和章节转场文案 | [cover.py](../ppt_maker/nodes/cover.py) |
| 改颜色、字体、章节色 | [theme.json](../templates/minimalist_architecture/theme.json) |
| 改全局尺寸、排版 | [viewport-base.css](../templates/minimalist_architecture/viewport-base.css) |
| 改单个组件视觉 | [components/](../templates/minimalist_architecture/components) |

只改模板或 CSS 时，用：

```bash
python -m ppt_maker render-only --case 688
```

## Level 2：改数据 / 逻辑

### 加新输入文件类型

例如新增：

```text
data/case_688/市场调研_688.md
```

语义键会是 `市场调研`。节点读取：

```python
assets = state.get("assets")
path = assets.docs.get("市场调研") if assets else None
```

如果多个节点都要用这份解析结果，建议在 [state.py](../ppt_maker/state.py) 加 schema 和 `ProjectState` 字段；如果只有一个节点用，留在节点内部解析即可。

### 把启发式打分换成豆包 LLM

当前 `policy._impact_score()` 是关键词启发式。低风险改法是保留原函数作为兜底：

```python
def _heuristic_score(impact: str) -> int:
    pos = sum(1 for w in ["提升", "降低", "优化"] if w in impact)
    return max(2, min(5, 2 + pos))
```

再接入豆包：

```python
from pydantic import BaseModel
from ..clients.doubao import DoubaoClient


class ImpactScore(BaseModel):
    score: int
    reason: str


def _impact_score(impact: str) -> int:
    client = DoubaoClient()
    if not client.available:
        return _heuristic_score(impact)
    try:
        result = client.structured(
            ImpactScore,
            system="你是一个建筑政策评估专家。只输出 JSON。",
            user=f"评估以下政策对项目的影响，给 1-5 分：{impact}",
        )
        return max(1, min(5, result.score))
    except Exception:
        return _heuristic_score(impact)
```

关键点：

| 要求 | 原因 |
|---|---|
| 缺 key 直接兜底 | 本地和 CI 不应强依赖 LLM |
| 超时/异常兜底 | 外部服务不应阻断 deck |
| 输出用 Pydantic 校验 | 避免自由文本污染节点逻辑 |
| 只在节点层调用 LLM | 模板层保持纯渲染 |

## Level 3：加新结构

### 新增内容节点

1. 新建 `ppt_maker/nodes/risk.py`。
2. 实现：

   ```python
   from ..state import ProjectState, SlideSpec

   def run(state: ProjectState) -> dict:
       spec = SlideSpec(
           page=6,
           component="content_bullets",
           title="风险评估",
           data={"bullets": [{"title": "政策风险", "body": "..."}]},
       )
       return {"slide_specs": {6: spec}}
   ```

3. 在 [nodes/__init__.py](../ppt_maker/nodes/__init__.py) 注册。
4. 在 [graph.py](../ppt_maker/graph.py) 连边。依赖 `parse_outline` 的静态节点通常加入 `CONTENT_NODES`。
5. 更新 [pipeline.md](pipeline.md) 的 40 页表。

注意页码冲突：`merge_dict` 会让同页后写覆盖前写。

### 新增页面组件

1. 在 [state.py:149](../ppt_maker/state.py#L149) 的 `ComponentKind` 加 `"comparison_matrix"`。
2. 新建 `templates/<template>/components/comparison_matrix.html.j2`。
3. 节点产出：

   ```python
   SlideSpec(page=22, component="comparison_matrix", data={...})
   ```

4. 在 [templates.md](templates.md) 写清 data 契约。

### 新增模板风格

```powershell
Copy-Item templates/minimalist_architecture templates/my_style -Recurse
```

修改 `theme.json`、`viewport-base.css` 和组件模板后：

```bash
python -m ppt_maker render-only --case 688 --template my_style
```

## Level 4：改架构

### 修改总页数

至少检查：

| 位置 | 事项 |
|---|---|
| [aggregate.py:17](../ppt_maker/nodes/aggregate.py#L17) | 补页范围 |
| [validate.py:18-19](../ppt_maker/nodes/validate.py#L18-L19) | 页数校验 |
| [html_renderer.py:54-58](../ppt_maker/render/html_renderer.py#L54-L58) | 章节页码边界 |
| [cover.py:7-16](../ppt_maker/nodes/cover.py#L7-L16) | 目录文案 |
| [cover.py](../ppt_maker/nodes/cover.py) | 转场页页码 |
| [concept.py:28-39](../ppt_maker/nodes/concept.py#L28-L39) | 3x3 概念图页码 |
| [case_study.py:13-19](../ppt_maker/nodes/case_study.py#L13-L19) | 3 个案例页 |
| [summary.py](../ppt_maker/nodes/summary.py) | 19/26/39 三页 |
| [pipeline.md](pipeline.md) | 40 页表 |

### 换图像供应商

保持 RunningHub 当前接口形状最省事：

```python
class MyImageClient:
    @property
    def available(self) -> bool: ...
    async def generate(self, prompt: str, out_path: Path) -> Path: ...
    def placeholder_svg(self, out_path: Path, *, title: str, hint: str = "") -> Path: ...
```

需要改：

| 调用处 | 用途 |
|---|---|
| [concept.py](../ppt_maker/nodes/concept.py) | 29-37 页概念图 |
| [culture.py](../ppt_maker/nodes/culture.py) | 第 9 页文化图 |
| [cover.py](../ppt_maker/nodes/cover.py) / [concept.py](../ppt_maker/nodes/concept.py) | logo 和目录插图 |

原则：失败时返回占位图路径，不让整条 graph 崩。

### 加内容审查节点

当前项目没有审查节点。如果要加，推荐接在渲染之后、校验之前：

```text
aggregate_specs -> render_html -> review -> validate
```

实现方向：

1. 新建 `ppt_maker/nodes/review.py`。
2. 节点读取 `slide_specs` 和 `output_html`。
3. 可选地截图 HTML，再调用 vision LLM 或规则检查。
4. 审查失败时写 `errors` 或 report，不建议阻断 HTML 产出。
5. 在 [graph.py](../ppt_maker/graph.py) 改边。

## 扩展前 self-test

每次扩展后至少跑：

| 检查 | 命令或动作 |
|---|---|
| dry-run 能否跑通 | `python -m ppt_maker run --case 688 --dry-run --force` |
| 单页 spec 是否符合预期 | `python -m ppt_maker inspect --case 688 --page <N>` |
| 只改模板能否复现 | `python -m ppt_maker render-only --case 688` |
| 日志是否有节点成功记录 | 看 `output/case_688/logs/run.jsonl` |
| 新组件字段是否符合契约 | 对照 [templates.md](templates.md) |
| 新页码是否进入 40 页表 | 更新 [pipeline.md](pipeline.md) |
| 改 graph 后是否清 checkpoint | 使用 `--force` |
