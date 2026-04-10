from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional

from api.deps import get_db
from api.response import APIResponse
from api.exceptions import ProjectNotFoundError
from db.models.project import Project
from schema.common import SlideStatus
from pydantic import BaseModel

router = APIRouter()


class RenderRequest(BaseModel):
    slide_nos: list[int] = []


class ReviewRequest(BaseModel):
    layers: list[str] = ["rule", "semantic"]
    slide_nos: list[int] = []


class RepairRequest(BaseModel):
    slide_nos: list[int] = []
    force: bool = False


@router.post("/{project_id}/render", response_model=APIResponse[dict], status_code=202)
def trigger_render(
    project_id: UUID,
    body: RenderRequest = RenderRequest(),
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project:
        raise ProjectNotFoundError(str(project_id))

    from tasks.render_tasks import render_slides_task
    slide_ids = None   # render all slides
    task = render_slides_task.delay(str(project_id), slide_ids)
    return APIResponse(data={
        "job_id": task.id,
        "total_slides": 0,
        "message": "渲染任务已进入队列",
    })


@router.post("/{project_id}/review", response_model=APIResponse[dict], status_code=202)
def trigger_review(
    project_id: UUID,
    body: ReviewRequest = ReviewRequest(),
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project:
        raise ProjectNotFoundError(str(project_id))

    from tasks.review_tasks import review_slides
    task = review_slides.delay(
        str(project_id),
        layers=body.layers or ["rule", "semantic"],
        slide_nos=body.slide_nos or None,
    )
    return APIResponse(data={"job_id": task.id, "message": "审查任务已进入队列"})


@router.post("/{project_id}/repair", response_model=APIResponse[dict], status_code=202)
def trigger_repair(
    project_id: UUID,
    body: RepairRequest = RepairRequest(),
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project:
        raise ProjectNotFoundError(str(project_id))

    # Find slides that need repair
    from db.models.slide import Slide
    repair_slides = (
        db.query(Slide)
        .filter(Slide.project_id == project_id)
        .filter(Slide.status == SlideStatus.REPAIR_NEEDED.value)
        .all()
    )
    slide_nos = [s.slide_no for s in repair_slides] or body.slide_nos or None

    if not slide_nos:
        return APIResponse(data={"message": "无需修复的页面"})

    # Repair = re-render repaired specs, then re-review
    from tasks.render_tasks import render_slides_task
    task = render_slides_task.delay(
        str(project_id),
        slide_nos=slide_nos,
        review_after=True,
    )
    return APIResponse(data={"job_id": task.id, "message": "修复渲染已进入队列"})
