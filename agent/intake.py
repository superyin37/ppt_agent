"""
Intake Agent — Phase 4

职责：
1. 接收用户自然语言输入（支持多轮）
2. 调用 extract_project_brief_tool 抽取结构化字段
3. 调用 geocode_address_tool 解析地址坐标
4. 调用 validate_project_brief_tool 本地校验
5. 持久化结果到数据库
6. 返回追问或确认摘要
"""

import json
import logging
from uuid import UUID

from sqlalchemy.orm import Session

from schema.project import ProjectBriefData, IntakeFollowUp, ProjectBriefInput
from schema.common import ProjectStatus
from db.models.project import Project, ProjectBrief
from tool.input.extract_brief import extract_project_brief, ExtractBriefInput, ExtractBriefOutput
from tool.input.validate_brief import validate_project_brief, ValidateBriefInput
from tool.input.geocode import geocode_address, GeocodeInput

logger = logging.getLogger(__name__)


class IntakeResult:
    def __init__(
        self,
        brief: ProjectBriefData,
        follow_up: str | None,
        confirmation_summary: str | None,
        is_complete: bool,
        missing_fields: list[str],
        validation_errors: list[str],
        validation_warnings: list[str],
    ):
        self.brief = brief
        self.follow_up = follow_up
        self.confirmation_summary = confirmation_summary
        self.is_complete = is_complete
        self.missing_fields = missing_fields
        self.validation_errors = validation_errors
        self.validation_warnings = validation_warnings


async def run_intake(
    project_id: UUID,
    raw_text: str,
    db: Session,
) -> IntakeResult:
    """
    Main entry point for Intake Agent.
    Handles multi-turn: loads existing brief from DB, merges new input.
    """
    # Load existing brief for this project
    existing_brief_orm = (
        db.query(ProjectBrief)
        .filter(ProjectBrief.project_id == project_id)
        .order_by(ProjectBrief.version.desc())
        .first()
    )

    existing_dict: dict | None = None
    if existing_brief_orm:
        existing_dict = _orm_to_dict(existing_brief_orm)

    # Step 1: LLM extraction
    logger.info(f"Intake: extracting brief for project {project_id}")
    extract_output: ExtractBriefOutput = await extract_project_brief(
        ExtractBriefInput(raw_text=raw_text, existing_brief=existing_dict)
    )

    brief = extract_output.extracted

    # Step 2: Geocode address if newly available and not yet geocoded
    if brief.site_address and not (existing_dict or {}).get("longitude"):
        try:
            geo = await geocode_address(GeocodeInput(
                address=brief.site_address,
                city=brief.city,
            ))
            # Enrich brief with geocoded data
            brief = brief.model_copy(update={
                "province": geo.province or brief.province,
                "city": geo.city or brief.city,
                "district": geo.district or brief.district,
            })
            logger.info(f"Intake: geocoded address → {geo.formatted_address} ({geo.confidence:.2f})")
        except Exception as e:
            logger.warning(f"Intake: geocode failed (non-blocking): {e}")

    # Step 3: Local validation
    validation = validate_project_brief(ValidateBriefInput(brief=brief))

    # Step 4: Persist to DB
    _upsert_brief(db, project_id, brief, raw_text, existing_brief_orm)

    # Step 5: Update project status
    project = db.get(Project, project_id)
    if project and project.status == ProjectStatus.INIT.value:
        project.status = ProjectStatus.INTAKE_IN_PROGRESS.value
        project.current_phase = "intake"

    db.commit()

    return IntakeResult(
        brief=brief,
        follow_up=extract_output.follow_up,
        confirmation_summary=extract_output.confirmation_summary,
        is_complete=extract_output.is_complete,
        missing_fields=extract_output.missing_fields,
        validation_errors=validation.errors,
        validation_warnings=validation.warnings,
    )


def _orm_to_dict(orm: ProjectBrief) -> dict:
    return {
        "building_type": orm.building_type,
        "client_name": orm.client_name,
        "style_preferences": orm.style_preferences or [],
        "special_requirements": orm.special_requirements,
        "gross_floor_area": float(orm.gross_floor_area) if orm.gross_floor_area else None,
        "site_area": float(orm.site_area) if orm.site_area else None,
        "far": float(orm.far) if orm.far else None,
        "site_address": orm.site_address,
        "province": orm.province,
        "city": orm.city,
        "district": orm.district,
    }


def _upsert_brief(
    db: Session,
    project_id: UUID,
    brief: ProjectBriefData,
    raw_text: str,
    existing_orm: ProjectBrief | None,
) -> ProjectBrief:
    """Create or update the project brief record."""
    if existing_orm:
        # Update in place (keep version)
        _apply_brief_to_orm(existing_orm, brief, raw_text)
        return existing_orm
    else:
        new_brief = ProjectBrief(project_id=project_id, version=1)
        _apply_brief_to_orm(new_brief, brief, raw_text)
        db.add(new_brief)
        return new_brief


def _apply_brief_to_orm(orm: ProjectBrief, brief: ProjectBriefData, raw_text: str) -> None:
    orm.building_type = brief.building_type.value if brief.building_type else None
    orm.client_name = brief.client_name
    orm.style_preferences = brief.style_preferences
    orm.special_requirements = brief.special_requirements
    orm.gross_floor_area = brief.gross_floor_area
    orm.site_area = brief.site_area
    orm.far = brief.far
    orm.site_address = brief.site_address
    orm.province = brief.province
    orm.city = brief.city
    orm.district = brief.district
    orm.raw_input = raw_text
    orm.missing_fields = brief.missing_fields
