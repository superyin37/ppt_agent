"""
Reference Agent — Phase 5

职责：
1. 根据项目 brief 生成查询 embedding
2. pgvector 向量检索候选案例
3. LLM 重排序，选出最相关的 top-k
4. 用户完成选择后，汇总偏好 → preference_summary
5. 将偏好摘要写入 DB，推进状态机
"""
import logging
from uuid import UUID

from sqlalchemy.orm import Session

from schema.reference import ReferenceCase, RecommendResponse, PreferenceSummary
from schema.common import ProjectStatus
from db.models.project import Project, ProjectBrief
from db.models.reference import ReferenceCase as ReferenceCaseORM, ProjectReferenceSelection
from tool.reference._embedding import build_query_text, get_embedding
from tool.reference.search import search_cases, CaseSearchInput
from tool.reference.rerank import rerank_cases, RerankInput
from tool.reference.preference_summary import summarise_preferences, PreferenceSummaryInput

logger = logging.getLogger(__name__)


async def recommend_cases(
    project_id: UUID,
    db: Session,
    top_k: int = 8,
    style_filter: list[str] | None = None,
    exclude_ids: list[str] | None = None,
) -> RecommendResponse:
    """
    Main recommendation flow:
    embedding query → vector search → LLM rerank → return top-k with reason.
    """
    brief = _get_confirmed_brief(project_id, db)
    brief_dict = _brief_to_dict(brief)

    building_type = brief.building_type or "museum"
    query_text = build_query_text(brief_dict)
    query_embedding = await get_embedding(query_text)

    # Vector search (or tag fallback)
    search_result = search_cases(
        CaseSearchInput(
            building_type=building_type,
            style_tags=style_filter or brief_dict.get("style_preferences", []),
            top_k=top_k * 2,   # fetch 2x for reranking
            exclude_ids=exclude_ids or [],
            query_embedding=query_embedding,
        ),
        db=db,
    )

    if not search_result.cases:
        logger.warning(f"No cases found for building_type={building_type}")
        return RecommendResponse(
            cases=[],
            recommendation_reason="案例库中暂无匹配的建筑类型案例，请先导入案例数据。",
        )

    # LLM rerank
    rerank_result = await rerank_cases(RerankInput(
        cases=search_result.cases,
        brief=brief_dict,
        top_k=top_k,
    ))

    return RecommendResponse(
        cases=rerank_result.cases,
        recommendation_reason=rerank_result.recommendation_reason,
    )


async def summarise_selection_preferences(
    project_id: UUID,
    db: Session,
) -> PreferenceSummary:
    """
    After user selects cases, summarise their preferences.
    Advances project to ASSET_GENERATING state.
    """
    brief = _get_confirmed_brief(project_id, db)
    brief_dict = _brief_to_dict(brief)

    # Load selections with case details
    selections_orm = (
        db.query(ProjectReferenceSelection)
        .filter(ProjectReferenceSelection.project_id == project_id)
        .order_by(ProjectReferenceSelection.rank)
        .all()
    )

    if not selections_orm:
        return PreferenceSummary(
            dominant_styles=[],
            dominant_features=[],
            narrative_hint="用户尚未选择参考案例",
        )

    selections_for_llm = []
    for sel in selections_orm:
        case = db.get(ReferenceCaseORM, sel.case_id)
        if case:
            selections_for_llm.append({
                "case_id": str(sel.case_id),
                "case_title": case.title,
                "building_type": case.building_type,
                "selected_tags": sel.selected_tags or [],
                "selection_reason": sel.selection_reason,
            })

    summary_result = await summarise_preferences(PreferenceSummaryInput(
        selections=selections_for_llm,
        brief=brief_dict,
    ))

    # Advance project status
    project = db.get(Project, project_id)
    if project and project.status == ProjectStatus.REFERENCE_SELECTION.value:
        project.status = ProjectStatus.ASSET_GENERATING.value
        project.current_phase = "asset_generation"
        db.commit()

    return PreferenceSummary(
        dominant_styles=summary_result.dominant_styles,
        dominant_features=summary_result.dominant_features,
        narrative_hint=summary_result.narrative_hint,
    )


def _get_confirmed_brief(project_id: UUID, db: Session) -> ProjectBrief:
    """Load the latest brief (confirmed or in-progress)."""
    brief = (
        db.query(ProjectBrief)
        .filter(ProjectBrief.project_id == project_id)
        .order_by(ProjectBrief.version.desc())
        .first()
    )
    if not brief:
        # Return empty brief rather than crashing
        return ProjectBrief(
            project_id=project_id,
            building_type="museum",
            style_preferences=[],
        )
    return brief


def _brief_to_dict(brief: ProjectBrief) -> dict:
    return {
        "building_type": brief.building_type,
        "client_name": brief.client_name,
        "style_preferences": brief.style_preferences or [],
        "special_requirements": brief.special_requirements,
        "gross_floor_area": float(brief.gross_floor_area) if brief.gross_floor_area else None,
        "site_area": float(brief.site_area) if brief.site_area else None,
        "far": float(brief.far) if brief.far else None,
        "site_address": brief.site_address,
        "province": brief.province,
        "city": brief.city,
        "district": brief.district,
    }
