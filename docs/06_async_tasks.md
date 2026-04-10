# 06. 异步任务队列设计

## 6.1 任务队列规划

使用 Celery + Redis，划分为 3 条队列，按优先级和资源消耗隔离：

| 队列名 | 用途 | Worker 数 | 超时限制 |
|-------|------|----------|---------|
| `default` | 资产生成、大纲生成、SlideSpec 生成 | 4 | 300s |
| `render` | HTML 渲染、Playwright 截图 | 2 | 120s/页 |
| `export` | PDF 组装、PPTX 编译 | 1 | 600s |

---

## 6.2 Celery 配置

```python
# tasks/celery_app.py
from celery import Celery
from config.settings import settings

app = Celery(
    "ppt_agent",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",

    # 队列路由
    task_routes={
        "tasks.asset_tasks.*":  {"queue": "default"},
        "tasks.render_tasks.*": {"queue": "render"},
        "tasks.export_tasks.*": {"queue": "export"},
    },

    # 重试策略
    task_acks_late=True,                    # 任务完成后才 ACK
    task_reject_on_worker_lost=True,        # Worker 崩溃时重新入队
    worker_prefetch_multiplier=1,           # 每次只取 1 个任务（渲染任务重）

    # 超时
    task_soft_time_limit=280,               # soft limit，触发 SoftTimeLimitExceeded
    task_time_limit=300,                    # hard limit，强制 kill

    # 结果保留
    result_expires=86400,                   # 1 天
)
```

---

## 6.3 资产生成任务

```python
# tasks/asset_tasks.py
from celery import shared_task, group, chord
from db.session import get_db_context
from tool.site import poi_retrieval, regional_stats, site_summary
from tool.asset import chart_generation, map_annotation, case_comparison, text_summary
from schema.common import AssetType
import uuid


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    name="tasks.asset_tasks.generate_all_assets"
)
def generate_all_assets(self, project_id: str):
    """
    协调全量资产生成。
    使用 Celery chord：并发生成各类资产，全部完成后更新项目状态。
    """
    try:
        subtasks = group([
            generate_site_assets.s(project_id),
            generate_chart_assets.s(project_id),
            generate_case_assets.s(project_id),
            generate_summary_assets.s(project_id),
        ])
        callback = on_all_assets_complete.s(project_id)
        chord(subtasks)(callback)
    except Exception as exc:
        self.retry(exc=exc, countdown=2 ** self.request.retries)


@shared_task(
    bind=True,
    max_retries=2,
    name="tasks.asset_tasks.generate_site_assets"
)
def generate_site_assets(self, project_id: str) -> dict:
    """生成场地相关资产：区位图、POI图、交通分析图"""
    results = []
    try:
        with get_db_context() as db:
            site = get_site_info(db, project_id)

            # 1. POI 检索
            pois = poi_retrieval.run(site.longitude, site.latitude, radius=1000)

            # 2. 地图标注
            poi_map_url = map_annotation.run(
                center_lng=site.longitude,
                center_lat=site.latitude,
                annotations=pois,
                map_type="poi"
            )
            save_asset(db, project_id, AssetType.MAP, "poi_map", poi_map_url, pois)
            results.append("poi_map")

            # 3. 交通分析
            traffic_data = regional_stats.run_traffic(site.longitude, site.latitude)
            traffic_map_url = map_annotation.run(
                center_lng=site.longitude,
                center_lat=site.latitude,
                annotations=traffic_data["routes"],
                map_type="traffic"
            )
            save_asset(db, project_id, AssetType.MAP, "traffic_map", traffic_map_url, traffic_data)
            results.append("traffic_map")

    except Exception as exc:
        self.retry(exc=exc)
    return {"generated": results}


@shared_task(
    bind=True,
    max_retries=2,
    name="tasks.asset_tasks.generate_chart_assets"
)
def generate_chart_assets(self, project_id: str) -> dict:
    """生成统计图表：区域经济、人口趋势等"""
    results = []
    try:
        with get_db_context() as db:
            brief = get_brief(db, project_id)
            stats = regional_stats.run_economic(brief.city)

            chart_url = chart_generation.run(
                chart_type="line",
                title="区域经济与人口趋势",
                data=stats["data"],
                color_scheme="primary"
            )
            save_asset(db, project_id, AssetType.CHART, "regional_stats", chart_url, stats)
            results.append("regional_stats_chart")
    except Exception as exc:
        self.retry(exc=exc)
    return {"generated": results}


@shared_task(name="tasks.asset_tasks.on_all_assets_complete")
def on_all_assets_complete(results: list, project_id: str):
    """所有资产生成完毕后的回调：更新项目状态"""
    with get_db_context() as db:
        all_success = all(r is not None for r in results)
        if all_success:
            update_project_status(db, project_id, "OUTLINE_READY")
            # 触发大纲生成
            generate_outline.delay(project_id)
        else:
            update_project_status(db, project_id, "FAILED",
                                  error="部分关键资产生成失败")
```

---

## 6.4 渲染任务

```python
# tasks/render_tasks.py
from celery import shared_task, group
from render.engine import render_slide_html
from render.exporter import screenshot_slide


@shared_task(
    bind=True,
    max_retries=2,
    soft_time_limit=100,
    time_limit=120,
    name="tasks.render_tasks.render_all_slides"
)
def render_all_slides(self, project_id: str, slide_nos: list[int] = None):
    """并发渲染所有页面"""
    with get_db_context() as db:
        slides = get_slides(db, project_id, slide_nos)

    subtasks = group([
        render_single_slide.s(project_id, slide.id, slide.spec_json)
        for slide in slides
    ])
    subtasks.apply_async()


@shared_task(
    bind=True,
    max_retries=2,
    soft_time_limit=90,
    time_limit=110,
    name="tasks.render_tasks.render_single_slide"
)
def render_single_slide(self, project_id: str, slide_id: str, spec_json: dict):
    """渲染单页：HTML → 截图 → 上传 OSS"""
    try:
        # 1. 生成 HTML
        html = render_slide_html(spec_json)

        # 2. Playwright 截图
        screenshot_bytes = screenshot_slide(html)

        # 3. 上传 OSS
        url = upload_to_oss(screenshot_bytes, f"slides/{project_id}/{slide_id}.png")

        # 4. 更新 DB
        with get_db_context() as db:
            update_slide(db, slide_id, screenshot_url=url, status="rendered")

    except SoftTimeLimitExceeded:
        with get_db_context() as db:
            update_slide(db, slide_id, status="failed", error="渲染超时")
    except Exception as exc:
        self.retry(exc=exc, countdown=5)
```

---

## 6.5 导出任务

```python
# tasks/export_tasks.py
from celery import shared_task
from render.exporter import compile_pdf, compile_pptx


@shared_task(
    bind=True,
    max_retries=1,
    soft_time_limit=500,
    time_limit=600,
    name="tasks.export_tasks.export_deck"
)
def export_deck(self, project_id: str, export_type: str, export_id: str):
    """
    export_type: pdf / pptx
    """
    try:
        with get_db_context() as db:
            slides = get_ready_slides(db, project_id)
            screenshot_urls = [s.screenshot_url for s in slides]

        if export_type == "pdf":
            file_bytes = compile_pdf(screenshot_urls)
            filename = f"deck_{project_id}.pdf"
        else:
            file_bytes = compile_pptx(screenshot_urls)
            filename = f"deck_{project_id}.pptx"

        file_url = upload_to_oss(file_bytes, f"exports/{filename}")

        with get_db_context() as db:
            update_export(db, export_id, file_url=file_url, status="success")
            update_project_status(db, project_id, "EXPORTED")

    except Exception as exc:
        with get_db_context() as db:
            update_export(db, export_id, status="failed", error=str(exc))
        self.retry(exc=exc)
```

---

## 6.6 任务优先级与失败策略

| 任务 | 优先级 | 最大重试 | 失败后动作 |
|------|-------|---------|----------|
| generate_all_assets | 5（高） | 3 | 项目置 FAILED |
| generate_site_assets | 5 | 2 | 跳过，记录警告 |
| render_single_slide | 7（普通） | 2 | 页面置 failed |
| export_deck | 9（低） | 1 | 导出记录置 failed |

---

## 6.7 任务进度上报

每个长任务通过 Redis 存储进度，供前端轮询：

```python
@shared_task(bind=True, name="tasks.render_tasks.render_all_slides")
def render_all_slides(self, project_id: str, slide_nos: list = None):
    total = len(slide_nos or get_all_slide_nos(project_id))
    done = 0

    for slide_no in (slide_nos or get_all_slide_nos(project_id)):
        render_single_slide(project_id, slide_no)
        done += 1
        # 更新进度到 Redis
        self.update_state(
            state="PROGRESS",
            meta={"done": done, "total": total, "current_slide": slide_no}
        )
```
