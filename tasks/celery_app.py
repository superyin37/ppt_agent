from celery import Celery
from config.settings import settings

app = Celery(
    "ppt_agent",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "tasks.asset_tasks",
        "tasks.outline_tasks",
        "tasks.render_tasks",
        "tasks.review_tasks",
        "tasks.export_tasks",
    ],
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_routes={
        "tasks.render_tasks.*": {"queue": "render"},
        "tasks.export_tasks.*": {"queue": "export"},
        "tasks.asset_tasks.*": {"queue": "default"},
        "tasks.outline_tasks.*": {"queue": "default"},
        "tasks.review_tasks.*": {"queue": "default"},
    },
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)
