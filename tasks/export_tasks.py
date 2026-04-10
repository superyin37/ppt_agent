"""
Export Celery tasks — Phase 8
Compile rendered slides into PDF (or PPTX placeholder) and upload to OSS.
"""
import logging
import uuid
import asyncio

from tasks.celery_app import app
from db.session import get_db_context
from schema.common import ProjectStatus, SlideStatus

logger = logging.getLogger(__name__)


@app.task(
    bind=True,
    max_retries=2,
    soft_time_limit=180,
    time_limit=240,
    name="tasks.export_tasks.export_deck",
)
def export_deck(self, project_id: str, export_type: str = "pdf"):
    """
    Compile all rendered slides into a PDF and upload to OSS.
    Updates project status to EXPORTED.
    export_type: "pdf" (default) | "pptx" (future)
    """
    from db.models.slide import Slide
    from db.models.project import Project

    try:
        with get_db_context() as db:
            slides = (
                db.query(Slide)
                .filter(Slide.project_id == project_id)
                .order_by(Slide.slide_no)
                .all()
            )

            if not slides:
                raise RuntimeError(f"No slides found for project {project_id}")

            if export_type == "pdf":
                export_url = asyncio.run(_compile_pdf_export(slides, project_id))
            else:
                logger.warning(f"export_type={export_type} not supported, defaulting to pdf")
                export_url = asyncio.run(_compile_pdf_export(slides, project_id))

            # Update project
            project = db.get(Project, uuid.UUID(project_id))
            if project:
                project.status = ProjectStatus.EXPORTED.value
                project.current_phase = "done"

        logger.info(f"export_deck done: project={project_id}, url={export_url}")
        return {"export_url": export_url, "export_type": export_type}

    except Exception as exc:
        logger.exception(f"export_deck error: {exc}")
        self.retry(exc=exc, countdown=15)


async def _compile_pdf_export(slides, project_id: str) -> str:
    """Collect PNG bytes from OSS (or re-render), compile PDF, upload."""
    import httpx
    from render.exporter import compile_pdf
    from tool._oss_client import upload_bytes

    png_bytes_list = []
    for slide in slides:
        if slide.screenshot_url and not slide.screenshot_url.startswith("/tmp/"):
            # Fetch from OSS URL
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(slide.screenshot_url)
                    resp.raise_for_status()
                    png_bytes_list.append(resp.content)
                    continue
            except Exception as e:
                logger.warning(f"Slide {slide.slide_no}: failed to fetch screenshot: {e}")

        # Fallback: re-render from html_content or re-use placeholder
        if slide.html_content:
            from render.exporter import screenshot_slide
            png = await screenshot_slide(slide.html_content)
        elif slide.screenshot_url and slide.screenshot_url.startswith("/tmp/"):
            # Local mock file from dev environment
            try:
                with open(slide.screenshot_url, "rb") as f:
                    png = f.read()
            except Exception:
                png = _blank_slide_png()
        else:
            png = _blank_slide_png()
        png_bytes_list.append(png)

    if not png_bytes_list:
        raise RuntimeError("No PNG data collected for PDF export")

    pdf_bytes = await compile_pdf(png_bytes_list)

    # Upload PDF to OSS
    key = f"exports/{project_id}/deck.pdf"
    url = upload_bytes(pdf_bytes, key, content_type="application/pdf")
    return url


def _blank_slide_png() -> bytes:
    """Minimal 1×1 white PNG as last-resort fallback."""
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
