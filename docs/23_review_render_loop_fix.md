# 23. Review-Render 回环修复

> 日期: 2026-04-06
> 状态: 实施中

## 背景

项目存在两套编排路径：

1. **graph.py（LangGraph）** — 设计阶段产物，有完整的 review→render 条件回环，但从未被主流程调用
2. **outlines.py + Celery** — 实际运行路径，缺少 review→render 回环

导致以下问题：
- 规则层修了 spec 但不重新 render，用户看到的截图/PDF 是旧的
- 语义层 repair_actions（如 S007 替换甲方名称）被收集但未执行
- `/repair` 接口只是重跑 review，语义与行为不符
- graph.py 与实际流程不同步（缺少 material_binding、brief_doc），保留只会误导

## 决策

**补全 Celery 链路，删除 graph.py。**

理由：
- 整条链路已端到端验证通过，切 graph 是高风险重写
- graph.py 的 node 实现与实际 agent 代码已分叉
- 回环逻辑不复杂，Celery 完全能表达
- 消除双路径维护负担

## 改动清单

### 1. review_tasks.py — review 后自动触发 re-render

review 完成后，若有 `REPAIR_NEEDED` 且未达上限的 slide，自动触发 render_slides_task 仅渲染这些 slide。

### 2. render_tasks.py — 支持 review_after 参数

render_slides_task 新增 `review_after` bool 参数，渲染完成后自动链式调用 review_slides。

### 3. api/routers/render.py — `/repair` 改为 render + review

`/repair` 接口查找 `REPAIR_NEEDED` 状态的 slide，触发 render→review 而非仅 review。

### 4. agent/critic.py — 执行语义层 repair_actions

语义层产出的 `repair_actions` 通过 `execute_repair()` 实际应用到 spec 上。

### 5. 删除 agent/graph.py

移除死代码，消除双路径混淆。

### 6. render/exporter.py — 批量并发截图

新增 `screenshot_slides_batch()`：一个浏览器实例开多个 tab，通过 `asyncio.Semaphore(4)` 控制并发。
消除原来每张 slide 启动一个 Chromium 实例的开销。

### 7. tasks/render_tasks.py — 用 batch 替代串行

将 `_render_single_slide` 拆为 `_generate_slide_html`（纯 HTML 生成）+ batch 截图。
渲染流程变为：全部 slide 先生成 HTML → 一次 batch 截图 → 批量写回 DB。

### 8. api/routers/outlines.py — _compose_render_worker 同步改为 batch

`_compose_render_worker` 中的渲染循环同样改为先收集 HTML 再 batch 截图。

## 改动后流程

```
/outline/confirm
  -> _compose_render_worker
    -> binding -> compose -> render(全部) -> review_slides.delay()
      -> review 发现问题?
        -> REPAIR_REQUIRED + count < 3:
            标记 REPAIR_NEEDED, 自动触发 render(仅修过的 slides)
            -> render 完成后自动触发 review
            -> 循环, 最多 3 轮
        -> REPAIR_REQUIRED + count >= 3:
            接受现状, 标记 REVIEW_PASSED
        -> ESCALATE_HUMAN:
            标记 FAILED, 等人工
        -> PASS:
            -> READY_FOR_EXPORT

/repair (手动触发)
  -> 找 REPAIR_NEEDED 的 slides
  -> render -> review (手动踢一轮循环)
```

## 实施顺序

| 顺序 | 文件 | 改动 |
|------|------|------|
| 1 | tasks/review_tasks.py | 加回环触发逻辑 |
| 2 | tasks/render_tasks.py | 支持 slide_nos 过滤 + review_after |
| 3 | api/routers/render.py | 修 /repair 语义 |
| 4 | agent/critic.py | 执行语义层 repairs |
| 5 | agent/graph.py | 删除 |