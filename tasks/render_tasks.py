"""
Render Celery tasks — Phase 7
HTML rendering via Jinja2 + Playwright screenshot + OSS upload.
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
    soft_time_limit=100,
    time_limit=120,
    name="tasks.render_tasks.render_slides_task",
)
def render_slides_task(
    self,
    project_id: str,
    slide_ids: list[str] | None = None,
    slide_nos: list[int] | None = None,
    review_after: bool = False,
):
    """
    Render all (or specified) slides: SlideSpec → HTML → screenshot → OSS.
    Updates each Slide row with screenshot_url and status.
    Advances project to REVIEWING when all slides are done.

    Args:
        slide_nos: Filter by slide number (used by review-repair loop).
        review_after: If True, trigger review_slides after render completes.
    """
    from db.models.slide import Slide
    from db.models.outline import Outline
    from db.models.asset import Asset
    from db.models.project import Project

    try:
        with get_db_context() as db:
            query = db.query(Slide).filter(Slide.project_id == project_id)
            if slide_ids:
                query = query.filter(Slide.id.in_([uuid.UUID(sid) for sid in slide_ids]))
            if slide_nos:
                query = query.filter(Slide.slide_no.in_(slide_nos))
            slides = query.order_by(Slide.slide_no).all()

            if not slides:
                logger.warning(f"render_slides_task: no slides found for project {project_id}")
                return {"rendered": 0}

            # Load assets for this project
            assets_orm = db.query(Asset).filter(Asset.project_id == project_id).all()
            assets_dict = {
                str(a.id): {
                    "image_url": a.image_url,
                    "data_json": a.data_json,
                    "config_json": a.config_json,
                    "source_info": a.source_info,
                    "logical_key": a.logical_key,
                    "variant": a.variant,
                }
                for a in assets_orm
            }

            # Load outline for deck meta
            outline = (
                db.query(Outline)
                .filter(Outline.project_id == project_id)
                .order_by(Outline.version.desc())
                .first()
            )

            # Load VisualTheme
            from agent.visual_theme import get_latest_theme
            from agent.composer import _default_theme
            theme = get_latest_theme(uuid.UUID(project_id), db) or _default_theme(uuid.UUID(project_id))

            # Load brief for client name
            from db.models.project import ProjectBrief
            brief = (
                db.query(ProjectBrief)
                .filter(ProjectBrief.project_id == project_id)
                .order_by(ProjectBrief.version.desc())
                .first()
            )

            deck_meta = {
                "deck_title": outline.deck_title if outline else "",
                "client_name": brief.client_name if brief else "",
                "total_slides": len(slides),
            }

            # Generate HTML for all slides first
            html_list: list[str | None] = []
            for slide in slides:
                try:
                    html = _generate_slide_html(slide, assets_dict, deck_meta, theme=theme)
                    slide.html_content = html[:65535]
                    html_list.append(html)
                except Exception as e:
                    logger.error(f"Slide {slide.slide_no} HTML generation error: {e}")
                    slide.status = SlideStatus.FAILED.value
                    slide.spec_json = {**slide.spec_json, "_render_error": str(e)}
                    html_list.append(None)

            # Batch screenshot: one browser, concurrent tabs
            valid_indices = [i for i, h in enumerate(html_list) if h is not None]
            valid_htmls = [html_list[i] for i in valid_indices]

            from render.exporter import screenshot_slides_batch
            png_results = asyncio.run(screenshot_slides_batch(valid_htmls))

            from tool._oss_client import upload_bytes
            rendered = 0
            failed = len(slides) - len(valid_indices)
            for idx, png_bytes in zip(valid_indices, png_results):
                slide = slides[idx]
                key = f"slides/{slide.project_id}/{slide.id}.png"
                url = upload_bytes(png_bytes, key)
                slide.screenshot_url = url
                slide.status = SlideStatus.RENDERED.value
                rendered += 1

            # Advance project status when all rendered
            project = db.get(Project, uuid.UUID(project_id))
            if project and failed == 0:
                project.status = ProjectStatus.REVIEWING.value
                project.current_phase = "review"
            elif project and rendered > 0:
                project.status = ProjectStatus.REVIEWING.value
                project.current_phase = "review"

        logger.info(f"render_slides_task: rendered={rendered}, failed={failed}")

        # Chain: trigger review after render if requested
        if review_after and rendered > 0:
            from tasks.review_tasks import review_slides
            review_slides.delay(
                project_id,
                layers=["rule", "semantic"],
                slide_nos=slide_nos,
            )
            logger.info("render_slides_task: chained review for project %s", project_id)

        return {"rendered": rendered, "failed": failed}

    except Exception as exc:
        logger.exception(f"render_slides_task error: {exc}")
        self.retry(exc=exc, countdown=5)


def _generate_slide_html(slide, assets_dict: dict, deck_meta: dict, theme=None) -> str:
    """Generate HTML for one slide from spec_json. No screenshot or DB side effects."""
    from render.engine import render_slide_html, render_slide_html_direct
    from schema.visual_theme import LayoutSpec

    spec_json = slide.spec_json or {}

    # HTML 直出模式（v3）
    if spec_json.get("html_mode"):
        return render_slide_html_direct(
            body_html=spec_json.get("body_html", ""),
            theme=theme,
            assets=assets_dict,
            deck_meta=deck_meta,
            slide_no=slide.slide_no or 0,
            total_slides=deck_meta.get("total_slides", 0),
        )

    # v2 结构化模式
    try:
        spec = LayoutSpec.model_validate(spec_json)
    except Exception as e:
        logger.warning(f"Slide {slide.slide_no} spec_json is not a valid LayoutSpec: {e}")
        from schema.visual_theme import (
            SingleColumnLayout, ContentBlock, RegionBinding,
        )
        spec = LayoutSpec(
            slide_no=slide.slide_no or 0,
            primitive=SingleColumnLayout(
                primitive="single-column", max_width_ratio=0.8, v_align="top", has_pull_quote=False,
            ),
            region_bindings=[RegionBinding(region_id="content", blocks=[
                ContentBlock(block_id="title", content_type="heading",
                             content=spec_json.get("title", slide.title or "")),
                ContentBlock(block_id="body", content_type="body-text",
                             content=spec_json.get("key_message", "")),
            ])],
            visual_focus="content",
            section=slide.section or "",
            title=slide.title or "",
        )
    return render_slide_html(spec, theme=theme, assets=assets_dict, deck_meta=deck_meta)
