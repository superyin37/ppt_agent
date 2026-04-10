from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from uuid import UUID

from api.deps import get_db
from api.response import APIResponse
from api.exceptions import (
    ProjectNotFoundError,
    BriefIncompleteError,
    InvalidStatusTransitionError,
)
from schema.project import ProjectCreate, ProjectRead, ProjectBriefInput
from schema.common import ProjectStatus
from db.models.project import Project, ProjectBrief
from agent.intake import run_intake

router = APIRouter()


@router.get("", response_model=APIResponse[list[ProjectRead]])
def list_projects(db: Session = Depends(get_db)):
    """列出所有项目，按创建时间倒序。"""
    projects_list = db.query(Project).order_by(Project.created_at.desc()).all()
    return APIResponse(data=[ProjectRead.model_validate(p) for p in projects_list])


@router.post("", response_model=APIResponse[ProjectRead], status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(name=body.name, status=ProjectStatus.INIT.value)
    db.add(project)
    db.commit()
    db.refresh(project)
    return APIResponse(data=ProjectRead.model_validate(project))


@router.get("/{project_id}", response_model=APIResponse[ProjectRead])
def get_project(project_id: UUID, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise ProjectNotFoundError(str(project_id))
    return APIResponse(data=ProjectRead.model_validate(project))


@router.patch("/{project_id}/brief", response_model=APIResponse[dict])
async def update_brief(project_id: UUID, body: ProjectBriefInput, db: Session = Depends(get_db)):
    """
    Multi-turn project brief intake.
    Each call merges new input with existing partial brief via Intake Agent.
    """
    project = db.get(Project, project_id)
    if not project:
        raise ProjectNotFoundError(str(project_id))

    result = await run_intake(
        project_id=project_id,
        raw_text=body.raw_text,
        db=db,
    )

    response_data: dict = {
        "brief": {
            "building_type": result.brief.building_type.value if result.brief.building_type else None,
            "client_name": result.brief.client_name,
            "style_preferences": result.brief.style_preferences,
            "gross_floor_area": result.brief.gross_floor_area,
            "site_area": result.brief.site_area,
            "far": result.brief.far,
            "site_address": result.brief.site_address,
            "province": result.brief.province,
            "city": result.brief.city,
            "district": result.brief.district,
            "missing_fields": result.missing_fields,
            "is_complete": result.is_complete,
        },
    }

    if result.is_complete:
        response_data["confirmation_summary"] = result.confirmation_summary
        response_data["validation_warnings"] = result.validation_warnings
    else:
        response_data["follow_up"] = {
            "question": result.follow_up,
            "missing_fields": result.missing_fields,
            "is_final_confirmation": False,
        }

    if result.validation_errors:
        response_data["validation_errors"] = result.validation_errors

    return APIResponse(data=response_data)


@router.post("/{project_id}/confirm-brief", response_model=APIResponse[dict])
def confirm_brief(project_id: UUID, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise ProjectNotFoundError(str(project_id))

    allowed = {ProjectStatus.INTAKE_IN_PROGRESS.value, ProjectStatus.INIT.value}
    if project.status not in allowed:
        raise InvalidStatusTransitionError(project.status, ProjectStatus.INTAKE_CONFIRMED.value)

    brief = (
        db.query(ProjectBrief)
        .filter(ProjectBrief.project_id == project_id)
        .order_by(ProjectBrief.version.desc())
        .first()
    )
    if not brief:
        raise BriefIncompleteError(["brief not started"])

    # Check completeness before confirming
    missing = brief.missing_fields or []
    if missing:
        raise BriefIncompleteError(missing)

    brief.status = "confirmed"
    project.status = ProjectStatus.INTAKE_CONFIRMED.value
    project.current_phase = "reference_selection"
    db.commit()

    return APIResponse(data={"status": ProjectStatus.INTAKE_CONFIRMED.value})
