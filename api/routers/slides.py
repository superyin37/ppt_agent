from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_db
from api.exceptions import ProjectNotFoundError
from api.response import APIResponse
from db.models.project import Project
from db.models.slide import Slide
from db.models.slide_material_binding import SlideMaterialBinding
from schema.common import SlideStatus
from schema.material_package import SlideMaterialBindingRead
from schema.slide import SlideRead

router = APIRouter()


@router.post("/{project_id}/slides/plan", response_model=APIResponse[dict], status_code=202)
def plan_slides(project_id: UUID, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise ProjectNotFoundError(str(project_id))
    return APIResponse(data={"job_id": None, "message": "slides are generated after outline confirmation"})


@router.get("/{project_id}/slides", response_model=APIResponse[list[SlideRead]])
def list_slides(project_id: UUID, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise ProjectNotFoundError(str(project_id))

    slides = (
        db.query(Slide)
        .filter(Slide.project_id == project_id)
        .order_by(Slide.slide_no.asc())
        .all()
    )
    return APIResponse(data=[_to_slide_read(slide) for slide in slides])


@router.get("/{project_id}/slides/{slide_no}", response_model=APIResponse[SlideRead])
def get_slide(project_id: UUID, slide_no: int, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise ProjectNotFoundError(str(project_id))

    slide = (
        db.query(Slide)
        .filter(Slide.project_id == project_id, Slide.slide_no == slide_no)
        .first()
    )
    if not slide:
        return APIResponse(data=None)
    return APIResponse(data=_to_slide_read(slide))


@router.get("/{project_id}/slides/{slide_no}/binding", response_model=APIResponse[SlideMaterialBindingRead])
def get_slide_binding(project_id: UUID, slide_no: int, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise ProjectNotFoundError(str(project_id))

    binding = (
        db.query(SlideMaterialBinding)
        .filter(SlideMaterialBinding.project_id == project_id, SlideMaterialBinding.slide_no == slide_no)
        .order_by(SlideMaterialBinding.version.desc())
        .first()
    )
    if not binding:
        return APIResponse(data=None)
    return APIResponse(data=SlideMaterialBindingRead.model_validate(binding))


def _to_slide_read(slide: Slide) -> SlideRead:
    return SlideRead(
        id=slide.id,
        project_id=slide.project_id,
        slide_no=slide.slide_no,
        section=slide.section,
        title=slide.title,
        layout_template=slide.layout_template,
        status=SlideStatus(slide.status),
        binding_id=slide.binding_id,
        screenshot_url=slide.screenshot_url,
        repair_count=slide.repair_count,
        spec_json=slide.spec_json,
        source_refs_json=slide.source_refs_json,
        evidence_refs_json=slide.evidence_refs_json,
        created_at=slide.created_at,
        updated_at=slide.updated_at,
    )
