"""Concept Render Celery task — ADR-005.

Generates 9 concept images (3 proposals × 3 views) via runninghub.
Runs between outline generation and material binding.
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from tasks.celery_app import app
from db.session import get_db_context

logger = logging.getLogger(__name__)


@app.task(
    bind=True,
    max_retries=1,
    name="tasks.concept_render_tasks.render_concept_images_task",
)
def render_concept_images_task(self, project_id: str):
    """Render concept images for the project; failures degrade to placeholders."""
    try:
        from agent.concept_render import run_concept_render

        with get_db_context() as db:
            stats = asyncio.run(run_concept_render(uuid.UUID(project_id), db))
        logger.info(
            "render_concept_images_task: project=%s total=%d generated=%d placeholders=%d",
            project_id,
            stats.total,
            stats.generated,
            stats.placeholders,
        )
        return {
            "project_id": project_id,
            "total": stats.total,
            "generated": stats.generated,
            "placeholders": stats.placeholders,
        }
    except Exception as exc:
        logger.exception("render_concept_images_task failed: %s", exc)
        # retry once then swallow — we never want to block the main pipeline
        if self.request.retries < self.max_retries:
            self.retry(exc=exc, countdown=30)
        return {"project_id": project_id, "error": repr(exc)}
