---
tags: [infra, background-worker, celery, asyncio]
source: api/routers/outlines.py, api/routers/exports.py, tasks/review_tasks.py
---

# 后台工作线程

> 长时任务通过后台线程或 Celery 异步执行，避免阻塞 HTTP 请求。

---

## `_outline_worker()` — Brief + 大纲生成

```python
# api/routers/outlines.py line 33
async def _outline_worker(project_id: UUID, db: Session):
    await generate_brief_doc(project_id, db)
    await generate_outline(project_id, db)
```

**触发：** `POST .../material-packages/{id}/regenerate`
**类型：** asyncio 后台任务（`asyncio.create_task`）
**耗时：** 约 30-90 秒（两次 LLM 调用）

---

## `_compose_render_worker()` — 编排 + 渲染主流水线

```python
# api/routers/outlines.py line 46
async def _compose_render_worker(
    project_id: UUID,
    outline_id: UUID,
    db: Session,
):
    # 1. 素材绑定（无LLM）
    bindings = bind_outline_slides(project_id, outline_id, db)

    # 2. 视觉主题（LLM，如不存在）
    if not get_latest_theme(project_id, db):
        await generate_visual_theme(VisualThemeInput(...), db)

    # 3. 幻灯片编排（LLM × N 页并发）
    slides = await compose_all_slides(project_id, outline_id, db)

    # 4. HTML 渲染 + Playwright 截图
    await render_and_screenshot(project_id, slides, db)

    # 5. 更新项目状态
    project.status = ProjectStatus.REVIEWING
    db.commit()
```

**触发：** `POST .../outline/confirm`
**类型：** asyncio 后台任务
**耗时：** 约 2-10 分钟（依页数和 LLM 速度）

---

## `_export_worker()` — PDF 导出

```python
# api/routers/exports.py line 23
async def _export_worker(project_id: UUID, db: Session):
    output_path = Path(f"tmp/e2e_output/export/{project_id}.pdf")
    await compile_pdf(project_id, output_path, db)
    project.status = ProjectStatus.EXPORTED
    db.commit()
```

**触发：** `POST .../export`
**类型：** asyncio 后台任务
**耗时：** 约 30-120 秒

---

## `review_slides` — 审查 Celery 任务

```python
# tasks/review_tasks.py
@celery_app.task
def review_slides(project_id: str):
    # 规则审查 → 修复循环
    ...
```

**触发：** `POST .../review`
**类型：** Celery 异步任务（需 Redis broker）
**配置：** `docker-compose.yml` 中的 Redis + Celery worker

---

## 任务状态查询

所有后台任务通过 `Project.status` 反映当前阶段，前端轮询：

```javascript
// frontend/app.js
setInterval(async () => {
    const status = await fetch(`/projects/${id}`).then(r => r.json());
    updateUI(status.status);
}, 2000);
```

## 相关

- [[tasks-infra/APIRoutes]]
- [[enums/ProjectStatus]]
- [[stages/03-大纲生成]]
- [[stages/05-幻灯片编排]]
- [[stages/09-PDF导出]]
