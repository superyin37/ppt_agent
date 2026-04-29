"""
Review Celery tasks — Phase 8
3-layer Critic review + auto-repair for each slide.
"""
import logging
import uuid
import asyncio

from tasks.celery_app import app
from db.session import get_db_context
from schema.common import ProjectStatus, SlideStatus

logger = logging.getLogger(__name__)

MAX_REPAIR_ATTEMPTS = 3


@app.task(
    bind=True,
    max_retries=2,
    soft_time_limit=300,
    time_limit=360,
    name="tasks.review_tasks.review_slides",
)
def review_slides(
    self,
    project_id: str,
    layers: list[str] | None = None,
    slide_nos: list[int] | None = None,
):
    """
    Run Critic review pipeline on all (or specified) slides.
    Saves Review records, updates slide status, advances project to READY_FOR_EXPORT.
    """
    if layers is None:
        layers = ["rule", "semantic"]

    from db.models.slide import Slide
    from db.models.review import Review
    from db.models.project import Project
    from db.models.project import ProjectBrief
    from db.models.outline import Outline
    from schema.outline import OutlineSlideEntry, OutlineSpec

    try:
        with get_db_context() as db:
            # Load slides
            query = db.query(Slide).filter(Slide.project_id == project_id)
            if slide_nos:
                query = query.filter(Slide.slide_no.in_(slide_nos))
            slides = query.order_by(Slide.slide_no).all()

            if not slides:
                logger.warning(f"review_slides: no slides for project {project_id}")
                return {"reviewed": 0}

            # Load brief
            brief_orm = (
                db.query(ProjectBrief)
                .filter(ProjectBrief.project_id == project_id)
                .filter(ProjectBrief.status == "confirmed")
                .order_by(ProjectBrief.version.desc())
                .first()
            )
            brief_dict = _brief_to_dict(brief_orm) if brief_orm else {}

            # Load outline entries + theme for HTML recompose
            outline = (
                db.query(Outline)
                .filter(Outline.project_id == project_id)
                .order_by(Outline.version.desc())
                .first()
            )
            entry_by_slide_no: dict[int, OutlineSlideEntry] = {}
            if outline:
                outline_spec = OutlineSpec.model_validate(outline.spec_json)
                entry_by_slide_no = {e.slide_no: e for e in outline_spec.slides}

            from agent.visual_theme import get_latest_theme
            from agent.composer import _default_theme
            theme = get_latest_theme(uuid.UUID(project_id), db) or _default_theme(uuid.UUID(project_id))

            passed = 0
            failed = 0
            escalated = 0

            for slide in slides:
                try:
                    slide.status = SlideStatus.REVIEW_PENDING.value
                    db.flush()

                    repaired_spec, report, is_html_mode = asyncio.run(
                        _review_one_slide(slide, brief_dict, layers)
                    )

                    # Save Review record
                    review_orm = Review(
                        project_id=uuid.UUID(project_id),
                        target_type="slide",
                        target_id=slide.id,
                        review_layer=report.review_layer,
                        severity=report.severity.value,
                        final_decision=report.final_decision.value,
                        issues_json=[i.model_dump() for i in report.issues],
                        repair_plan=[r.model_dump() for r in report.repair_plan]
                        if report.repair_plan else None,
                    )
                    db.add(review_orm)

                    from schema.review import ReviewDecision
                    decision = report.final_decision

                    if decision == ReviewDecision.PASS:
                        slide.status = SlideStatus.REVIEW_PASSED.value
                        if not is_html_mode:
                            slide.spec_json = repaired_spec.model_dump(mode="json")
                        passed += 1

                    elif decision == ReviewDecision.REPAIR_REQUIRED:
                        if slide.repair_count < MAX_REPAIR_ATTEMPTS:
                            slide.repair_count += 1
                            slide.status = SlideStatus.REPAIR_NEEDED.value
                            if is_html_mode:
                                # Inline re-compose: update body_html before re-render
                                entry = entry_by_slide_no.get(slide.slide_no or 0)
                                if entry and report.issues:
                                    try:
                                        from agent.composer import recompose_slide_html
                                        new_output = asyncio.run(
                                            recompose_slide_html(
                                                original_html=(slide.spec_json or {}).get("body_html", ""),
                                                issues=[i.model_dump() for i in report.issues],
                                                entry=entry,
                                                theme=theme,
                                                brief_dict=brief_dict,
                                            )
                                        )
                                        slide.spec_json = {
                                            **(slide.spec_json or {}),
                                            "body_html": new_output.body_html,
                                            "asset_refs": new_output.asset_refs,
                                            "content_summary": new_output.content_summary,
                                        }
                                    except Exception as recomp_exc:
                                        logger.warning(
                                            "Recompose failed for slide %s: %s",
                                            slide.slide_no, recomp_exc,
                                        )
                            else:
                                slide.spec_json = repaired_spec.model_dump(mode="json")
                            # not counted as passed — will re-render then re-review
                        else:
                            # Max repairs reached — mark as passed with warnings
                            slide.status = SlideStatus.REVIEW_PASSED.value
                            if not is_html_mode:
                                slide.spec_json = repaired_spec.model_dump(mode="json")
                            logger.warning(
                                f"Slide {slide.slide_no}: max repairs reached, accepting"
                            )
                            passed += 1

                    elif decision == ReviewDecision.ESCALATE_HUMAN:
                        slide.status = SlideStatus.FAILED.value
                        escalated += 1
                        failed += 1

                    db.flush()

                except Exception as e:
                    logger.error(f"review_slides: slide {slide.slide_no} error: {e}")
                    slide.status = SlideStatus.FAILED.value
                    failed += 1
                    escalated += 1  # review 崩溃视为需要人工介入，阻止项目静默通过

            # Collect slides that need re-render after repair
            repair_slide_nos = [
                s.slide_no for s in slides
                if s.status == SlideStatus.REPAIR_NEEDED.value
            ]

            # Advance project status
            project = db.get(Project, uuid.UUID(project_id))
            if project:
                if escalated > 0:
                    project.status = ProjectStatus.REVIEWING.value
                    project.error_message = f"{escalated} slide(s) require human review or failed review"
                elif repair_slide_nos:
                    # Slides were repaired — need re-render then re-review
                    project.status = ProjectStatus.RENDERING.value
                    project.current_phase = "render"
                else:
                    project.status = ProjectStatus.READY_FOR_EXPORT.value
                    project.current_phase = "export"

        # After commit: trigger re-render for repaired slides (outside DB context)
        if escalated == 0 and repair_slide_nos:
            from tasks.render_tasks import render_slides_task
            render_slides_task.apply_async(
                args=[project_id],
                kwargs={"slide_nos": repair_slide_nos, "review_after": True},
                countdown=2,
            )
            logger.info(
                "review_slides: triggered re-render for slides %s", repair_slide_nos
            )

        logger.info(
            f"review_slides done: passed={passed}, failed={failed}, escalated={escalated}"
        )
        return {"passed": passed, "failed": failed, "escalated": escalated}

    except Exception as exc:
        logger.exception(f"review_slides error: {exc}")
        self.retry(exc=exc, countdown=10)


async def _review_one_slide(slide, brief_dict: dict, layers: list[str]):
    """Load LayoutSpec from slide ORM and run review_slide pipeline.
    Returns (repaired_spec, report, is_html_mode)."""
    from schema.visual_theme import (
        ContentBlock, LayoutSpec, RegionBinding, SingleColumnLayout,
    )
    from agent.critic import review_slide

    spec_json = slide.spec_json or {}
    is_html_mode = spec_json.get("html_mode", False)

    if is_html_mode:
        spec = LayoutSpec(
            slide_no=slide.slide_no or 0,
            primitive=SingleColumnLayout(
                primitive="single-column", max_width_ratio=0.8,
                v_align="top", has_pull_quote=False,
            ),
            region_bindings=[RegionBinding(region_id="content", blocks=[
                ContentBlock(
                    block_id="title", content_type="heading",
                    content=slide.title or "",
                ),
            ])],
            visual_focus="content",
            section=slide.section or "",
            title=slide.title or "",
        )
    else:
        spec = LayoutSpec.model_validate(spec_json)

    # HTML 模式：跳过 rule/semantic lint（fallback_spec 是假数据），只用 vision
    effective_layers = ["vision"] if is_html_mode else layers
    screenshot_url = slide.screenshot_url if "vision" in effective_layers else None
    page_type = "content"
    if spec_json.get("is_cover") or (slide.slide_no or 0) == 1:
        page_type = "cover"
    elif spec_json.get("is_chapter_divider"):
        page_type = "chapter_divider"
    else:
        page_hint = " ".join([
            str(spec_json.get("page_type") or ""),
            str(spec_json.get("slot_id") or ""),
            slide.title or "",
            slide.section or "",
        ]).lower()
        if "concept" in page_hint or "概念" in page_hint:
            page_type = "concept"

    content_summary = spec_json.get("content_summary") or slide.title or ""

    repaired_spec, report = await review_slide(
        spec=spec,
        brief=brief_dict,
        layers=effective_layers,
        screenshot_url=screenshot_url,
        max_repairs=MAX_REPAIR_ATTEMPTS,
        design_advisor=is_html_mode,
        page_type=page_type,
        content_summary=content_summary,
    )
    return repaired_spec, report, is_html_mode


def _brief_to_dict(brief_orm) -> dict:
    return {
        "building_type": brief_orm.building_type,
        "client_name": brief_orm.client_name,
        "style_preferences": brief_orm.style_preferences or [],
        "gross_floor_area": brief_orm.gross_floor_area,
        "far": brief_orm.far,
        "site_address": brief_orm.site_address,
        "special_requirements": brief_orm.special_requirements,
    }
