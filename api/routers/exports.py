import logging
import threading
from pathlib import Path
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from api.deps import get_db
from api.response import APIResponse
from api.exceptions import ProjectNotFoundError
from db.models.project import Project
from schema.common import ProjectStatus
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)


class ExportRequest(BaseModel):
    export_type: str = "pdf"    # pdf / pptx


def _export_worker(project_id: str, export_type: str = "pdf"):
    """在独立线程中将已渲染的 PNG 编译为 PDF，保存到本地。"""
    import asyncio
    import uuid as _uuid
    from db.session import get_db_context
    from db.models.slide import Slide
    from schema.common import ProjectStatus
    from render.exporter import compile_pdf

    output_dir = Path("tmp/e2e_output/export")
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = output_dir / f"{project_id}.pdf"

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

            png_bytes_list = []
            for slide in slides:
                pad = str(slide.slide_no).zfill(2)
                local_path = Path("tmp/e2e_output/slides") / f"slide_{pad}.png"
                if local_path.exists():
                    png_bytes_list.append(local_path.read_bytes())
                elif slide.html_content:
                    from render.exporter import screenshot_slide
                    png = asyncio.run(screenshot_slide(slide.html_content))
                    png_bytes_list.append(png)
                else:
                    logger.warning(f"No PNG for slide {slide.slide_no}, skipping")

            if not png_bytes_list:
                raise RuntimeError("No PNG data collected for PDF export")

            pdf_bytes = asyncio.run(compile_pdf(png_bytes_list))
            pdf_path.write_bytes(pdf_bytes)

            project = db.get(Project, _uuid.UUID(project_id))
            if project:
                project.status = ProjectStatus.EXPORTED.value
                project.current_phase = "done"
                project.error_message = f"/export-output/{project_id}.pdf"
            db.commit()

        logger.info(f"_export_worker done: project={project_id}, pdf={pdf_path}")

    except Exception as e:
        logger.exception(f"_export_worker failed: {e}")


@router.post("/{project_id}/export", response_model=APIResponse[dict], status_code=202)
def trigger_export(
    project_id: UUID,
    body: ExportRequest = ExportRequest(),
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project:
        raise ProjectNotFoundError(str(project_id))

    # 推进到非终态，让前端轮询继续
    project.status = ProjectStatus.RENDERING.value
    db.commit()

    threading.Thread(
        target=_export_worker,
        args=(str(project_id), body.export_type),
        daemon=True,
    ).start()
    return APIResponse(data={"message": f"导出中 ({body.export_type})"})
