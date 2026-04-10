from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional
import logging

from api.deps import get_db
from api.response import APIResponse
from api.exceptions import ProjectNotFoundError, CaseNotFoundError
from schema.reference import (
    RecommendRequest, RecommendResponse,
    SelectionBatchInput, PreferenceSummary,
)
from schema.common import ProjectStatus
from schema.visual_theme import VisualThemeInput, VisualThemeRead
from db.models.project import Project, ProjectBrief
from db.models.reference import ReferenceCase as ReferenceCaseORM, ProjectReferenceSelection
from agent.reference import recommend_cases, summarise_selection_preferences
from agent.visual_theme import generate_visual_theme, get_latest_theme

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/{project_id}/references/recommend", response_model=APIResponse[RecommendResponse])
async def recommend_references(
    project_id: UUID,
    body: RecommendRequest,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project:
        raise ProjectNotFoundError(str(project_id))

    result = await recommend_cases(
        project_id=project_id,
        db=db,
        top_k=body.top_k,
        style_filter=body.style_filter or None,
    )
    return APIResponse(data=result)


@router.post("/{project_id}/references/select", response_model=APIResponse[dict])
def select_references(
    project_id: UUID,
    body: SelectionBatchInput,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project:
        raise ProjectNotFoundError(str(project_id))

    # Clear previous selections
    db.query(ProjectReferenceSelection).filter(
        ProjectReferenceSelection.project_id == project_id
    ).delete()

    for rank, sel in enumerate(body.selections, start=1):
        case = db.get(ReferenceCaseORM, sel.case_id)
        if not case:
            raise CaseNotFoundError(str(sel.case_id))
        selection = ProjectReferenceSelection(
            project_id=project_id,
            case_id=sel.case_id,
            selected_tags=sel.selected_tags,
            selection_reason=sel.selection_reason,
            rank=rank,
        )
        db.add(selection)

    # Advance to REFERENCE_SELECTION status if still in INTAKE_CONFIRMED
    if project.status == ProjectStatus.INTAKE_CONFIRMED.value:
        project.status = ProjectStatus.REFERENCE_SELECTION.value

    db.commit()
    return APIResponse(data={"selected": [str(s.case_id) for s in body.selections], "count": len(body.selections)})


class ConfirmReferencesResponse(PreferenceSummary):
    visual_theme_id: Optional[UUID] = None
    visual_theme_keywords: list[str] = []
    visual_theme_primary: str = ""


@router.post("/{project_id}/references/confirm", response_model=APIResponse[ConfirmReferencesResponse])
async def confirm_references(
    project_id: UUID,
    db: Session = Depends(get_db),
):
    """
    User confirms case selections.
    1. Summarises aesthetic preferences from selected cases.
    2. Triggers Visual Theme Agent → generates VisualTheme for the project.
    3. Advances project to ASSET_GENERATING.
    """
    project = db.get(Project, project_id)
    if not project:
        raise ProjectNotFoundError(str(project_id))

    # Step 1: 偏好摘要
    summary = await summarise_selection_preferences(project_id=project_id, db=db)

    # Step 2: 读取项目 brief
    brief = (
        db.query(ProjectBrief)
        .filter(ProjectBrief.project_id == project_id)
        .order_by(ProjectBrief.version.desc())
        .first()
    )

    theme_id = None
    theme_keywords: list[str] = []
    theme_primary = ""

    try:
        inp = VisualThemeInput(
            project_id=project_id,
            building_type=brief.building_type if brief else (project.building_type or "unknown"),
            style_preferences=(brief.style_preferences if brief else []) or [],
            dominant_styles=summary.dominant_styles,
            dominant_features=summary.dominant_features,
            narrative_hint=summary.narrative_hint,
            project_name=project.name,
            client_name=brief.client_name if brief else None,
        )
        theme_orm = await generate_visual_theme(inp=inp, db=db)
        theme_id = theme_orm.id
        theme_data = theme_orm.theme_json
        theme_keywords = theme_data.get("style_keywords", [])
        theme_primary = theme_data.get("colors", {}).get("primary", "")
        logger.info(f"VisualTheme generated for project {project_id}: keywords={theme_keywords}")
    except Exception as e:
        logger.error(f"VisualTheme generation failed for project {project_id}: {e}")
        # 不阻断主流程，继续返回偏好摘要

    return APIResponse(data=ConfirmReferencesResponse(
        dominant_styles=summary.dominant_styles,
        dominant_features=summary.dominant_features,
        narrative_hint=summary.narrative_hint,
        visual_theme_id=theme_id,
        visual_theme_keywords=theme_keywords,
        visual_theme_primary=theme_primary,
    ))


@router.post("/{project_id}/references/refresh", response_model=APIResponse[RecommendResponse])
async def refresh_references(
    project_id: UUID,
    body: RecommendRequest,
    db: Session = Depends(get_db),
):
    """Re-run recommendation, excluding already-selected cases."""
    project = db.get(Project, project_id)
    if not project:
        raise ProjectNotFoundError(str(project_id))

    # Get already-selected case IDs to exclude
    existing_selections = (
        db.query(ProjectReferenceSelection)
        .filter(ProjectReferenceSelection.project_id == project_id)
        .all()
    )
    exclude_ids = [str(s.case_id) for s in existing_selections]

    result = await recommend_cases(
        project_id=project_id,
        db=db,
        top_k=body.top_k,
        style_filter=body.style_filter or None,
        exclude_ids=exclude_ids,
    )
    return APIResponse(data=result)
