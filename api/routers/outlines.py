import asyncio
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from agent.brief_doc import generate_brief_doc
from agent.composer import _default_theme, compose_all_slides
from agent.material_binding import bind_outline_slides
from agent.outline import generate_outline
from agent.visual_theme import get_latest_theme
from api.deps import get_db
from api.exceptions import InvalidStatusTransitionError, ProjectNotFoundError
from api.response import APIResponse
from db.models.asset import Asset
from db.models.material_package import MaterialPackage
from db.models.outline import Outline
from db.models.project import Project, ProjectBrief
from db.models.slide import Slide
from render.engine import render_slide_html
from schema.common import ProjectStatus, SlideStatus
from schema.outline import OutlineRead
from schema.visual_theme import LayoutSpec

router = APIRouter()
logger = logging.getLogger(__name__)


def _outline_worker(project_id: str):
    import uuid as _uuid
    from db.session import get_db_context

    try:
        with get_db_context() as db:
            asyncio.run(generate_brief_doc(_uuid.UUID(project_id), db))
            asyncio.run(generate_outline(_uuid.UUID(project_id), db))
        logger.info("_outline_worker done: project=%s", project_id)
    except Exception as exc:
        logger.exception("_outline_worker failed: %s", exc)


def _compose_render_worker(project_id: str):
    import uuid as _uuid
    from db.session import get_db_context

    pid = _uuid.UUID(project_id)
    output_dir = Path("tmp/e2e_output/slides")
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        with get_db_context() as db:
            outline = (
                db.query(Outline)
                .filter(Outline.project_id == pid)
                .order_by(Outline.version.desc())
                .first()
            )
            if not outline:
                raise ValueError(f"No outline found for project {project_id}")

            package = (
                db.query(MaterialPackage)
                .filter(MaterialPackage.project_id == pid)
                .order_by(MaterialPackage.version.desc())
                .first()
            )
            project = db.get(Project, pid)
            if package and project:
                project.status = ProjectStatus.BINDING.value
                project.current_phase = "binding"
                db.flush()
                bind_outline_slides(pid, outline.id, db)

            asyncio.run(compose_all_slides(pid, db))

        with get_db_context() as db:
            slides = (
                db.query(Slide)
                .filter(Slide.project_id == pid)
                .order_by(Slide.slide_no.asc())
                .all()
            )
            assets_dict = {
                str(asset.id): {
                    "image_url": asset.image_url,
                    "data_json": asset.data_json,
                    "config_json": asset.config_json,
                    "source_info": asset.source_info,
                    "logical_key": asset.logical_key,
                    "variant": asset.variant,
                }
                for asset in db.query(Asset).filter(Asset.project_id == pid).all()
            }
            outline = (
                db.query(Outline)
                .filter(Outline.project_id == pid)
                .order_by(Outline.version.desc())
                .first()
            )
            theme = get_latest_theme(pid, db) or _default_theme(pid)
            brief = (
                db.query(ProjectBrief)
                .filter(ProjectBrief.project_id == pid)
                .order_by(ProjectBrief.version.desc())
                .first()
            )
            deck_meta = {
                "deck_title": outline.deck_title if outline else "",
                "client_name": brief.client_name if brief else "",
                "total_slides": len(slides),
            }

            # Generate HTML for all slides
            html_map: dict[int, str] = {}
            for slide in slides:
                try:
                    spec = LayoutSpec.model_validate(slide.spec_json)
                    html = render_slide_html(spec, theme=theme, assets=assets_dict, deck_meta=deck_meta)
                    slide.html_content = html[:65535]
                    html_map[slide.slide_no] = html
                except Exception as exc:
                    logger.error("render HTML error slide=%s err=%s", slide.slide_no, exc)
                    slide.status = SlideStatus.FAILED.value

            # Batch screenshot: one browser, concurrent tabs
            from render.exporter import screenshot_slides_batch
            ordered_nos = sorted(html_map.keys())
            html_list = [html_map[no] for no in ordered_nos]
            png_results = asyncio.run(screenshot_slides_batch(html_list))

            slide_by_no = {s.slide_no: s for s in slides}
            for slide_no, png in zip(ordered_nos, png_results):
                slide = slide_by_no[slide_no]
                pad = str(slide_no).zfill(2)
                (output_dir / f"slide_{pad}.png").write_bytes(png)
                slide.screenshot_url = f"/slides-output/slide_{pad}.png"
                slide.status = SlideStatus.RENDERED.value

            project = db.get(Project, pid)
            if project:
                project.status = ProjectStatus.REVIEWING.value
                project.current_phase = "review"
            db.commit()

        from tasks.review_tasks import review_slides

        review_slides.delay(project_id, layers=["rule", "semantic"])
        logger.info("_compose_render_worker done: project=%s", project_id)
    except Exception as exc:
        logger.exception("_compose_render_worker failed: %s", exc)


@router.post("/{project_id}/outline/generate", response_model=APIResponse[dict], status_code=202)
def generate_outline_route(project_id: UUID, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise ProjectNotFoundError(str(project_id))

    project.status = ProjectStatus.ASSET_GENERATING.value
    project.current_phase = "outline_generation"
    db.commit()

    threading.Thread(target=_outline_worker, args=(str(project_id),), daemon=True).start()
    return APIResponse(data={"message": "outline generation started"})


@router.get("/{project_id}/outline", response_model=APIResponse[OutlineRead])
def get_outline(project_id: UUID, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise ProjectNotFoundError(str(project_id))

    outline = (
        db.query(Outline)
        .filter(Outline.project_id == project_id)
        .order_by(Outline.version.desc())
        .first()
    )
    if not outline:
        return APIResponse(data=None)

    return APIResponse(data=OutlineRead.model_validate(outline))


@router.post("/{project_id}/outline/confirm", response_model=APIResponse[dict])
def confirm_outline(project_id: UUID, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise ProjectNotFoundError(str(project_id))

    outline = (
        db.query(Outline)
        .filter(Outline.project_id == project_id)
        .order_by(Outline.version.desc())
        .first()
    )
    if not outline:
        raise InvalidStatusTransitionError(project.status, "SLIDE_PLANNING")

    outline.status = "confirmed"
    outline.confirmed_at = datetime.now(timezone.utc)
    project.status = ProjectStatus.SLIDE_PLANNING.value
    project.current_phase = "binding"
    db.commit()

    threading.Thread(target=_compose_render_worker, args=(str(project_id),), daemon=True).start()
    return APIResponse(data={"status": ProjectStatus.SLIDE_PLANNING.value})
