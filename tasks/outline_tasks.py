"""
Outline & Composer Celery tasks — Phase 7

Task graph:
  generate_outline_task → (user confirms) → compose_slides_task → render_slides
"""
import logging
import uuid

from tasks.celery_app import app
from db.session import get_db_context
from schema.common import ProjectStatus

logger = logging.getLogger(__name__)


@app.task(bind=True, max_retries=2, name="tasks.outline_tasks.generate_outline_task")
def generate_outline_task(self, project_id: str):
    """
    Call Outline Agent to generate PPT outline from brief + preferences + assets.
    Saves result to outlines table and advances project to OUTLINE_READY.
    """
    import asyncio
    try:
        from agent.outline import generate_outline
        with get_db_context() as db:
            outline = asyncio.run(generate_outline(uuid.UUID(project_id), db))
        logger.info(f"generate_outline_task: done, outline_id={outline.id}")
        return {"outline_id": str(outline.id), "total_pages": outline.total_pages}
    except Exception as exc:
        logger.exception(f"generate_outline_task failed: {exc}")
        self.retry(exc=exc, countdown=2 ** self.request.retries * 10)


@app.task(bind=True, max_retries=2, name="tasks.outline_tasks.compose_slides_task")
def compose_slides_task(self, project_id: str):
    """
    Call Composer Agent to expand outline into per-slide SlideSpecs.
    Saves all Slide rows to DB and advances project to RENDERING.
    Then dispatches render_slides_task.
    """
    import asyncio
    try:
        from agent.composer import ComposerMode, compose_all_slides
        with get_db_context() as db:
            slides = asyncio.run(compose_all_slides(uuid.UUID(project_id), db, mode=ComposerMode.HTML))
        logger.info(f"compose_slides_task: composed {len(slides)} slides for project {project_id}")

        # Trigger rendering
        from tasks.render_tasks import render_slides_task
        render_slides_task.delay(project_id)
        return {"slides_composed": len(slides)}
    except Exception as exc:
        logger.exception(f"compose_slides_task failed: {exc}")
        self.retry(exc=exc, countdown=2 ** self.request.retries * 10)
