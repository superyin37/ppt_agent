"""
LLM-based reranking of candidate reference cases.
Takes a list of candidates and project brief, returns prioritised list with reasons.
"""
import json
import logging
from pydantic import BaseModel
from typing import Optional

from config.llm import call_llm_structured, FAST_MODEL
from schema.reference import ReferenceCase

logger = logging.getLogger(__name__)

RERANK_SYSTEM_PROMPT = """你是一位建筑案例推荐专家。
根据项目需求，对候选案例进行重排序，选出最相关的案例，并给出每个案例的推荐理由。

## 排序权重
1. 建筑类型匹配（0.4）：类型相同得满分
2. 风格标签匹配（0.3）：与项目风格偏好的重叠程度
3. 规模相近性（0.2）：建筑面积在同量级（小/中/大）
4. 地域文脉（0.1）：中国项目优先中国案例

## 输出格式（严格 JSON）
{
  "ranked_ids": ["uuid1", "uuid2", ...],
  "recommendation_reason": "整体推荐理由（50字以内）",
  "case_notes": {
    "uuid": "该案例推荐理由（20字以内）"
  }
}"""


class _RerankOutput(BaseModel):
    ranked_ids: list[str]
    recommendation_reason: str
    case_notes: dict[str, str] = {}


class RerankInput(BaseModel):
    cases: list[ReferenceCase]
    brief: dict   # ProjectBriefData as dict
    top_k: int = 8


class RerankOutput(BaseModel):
    cases: list[ReferenceCase]
    recommendation_reason: str
    case_notes: dict[str, str] = {}


async def rerank_cases(input: RerankInput) -> RerankOutput:
    """
    LLM-based reranking. Falls back to original order on failure.
    timeout: 20s
    """
    if len(input.cases) <= input.top_k:
        # Nothing to rerank if fewer than top_k
        return RerankOutput(
            cases=input.cases[:input.top_k],
            recommendation_reason="根据建筑类型和风格直接匹配",
        )

    # Prepare compact case summaries for LLM
    cases_summary = [
        {
            "id": str(c.id),
            "title": c.title,
            "building_type": c.building_type.value,
            "style_tags": c.style_tags,
            "feature_tags": c.feature_tags[:4],
            "scale_category": c.scale_category,
            "gfa_sqm": c.gfa_sqm,
            "country": c.country,
            "summary": (c.summary or "")[:100],
        }
        for c in input.cases
    ]

    brief_summary = {
        "building_type": input.brief.get("building_type"),
        "style_preferences": input.brief.get("style_preferences", []),
        "gross_floor_area": input.brief.get("gross_floor_area"),
        "city": input.brief.get("city"),
        "special_requirements": input.brief.get("special_requirements"),
    }

    user_msg = (
        f"<project_brief>\n{json.dumps(brief_summary, ensure_ascii=False)}\n</project_brief>\n\n"
        f"<candidates>\n{json.dumps(cases_summary, ensure_ascii=False, indent=2)}\n</candidates>\n\n"
        f"请从以上 {len(input.cases)} 个候选案例中，选出最适合该项目的 {input.top_k} 个，按相关度排序。"
    )

    try:
        result = await call_llm_structured(
            system_prompt=RERANK_SYSTEM_PROMPT,
            user_message=user_msg,
            output_schema=_RerankOutput,
            model=FAST_MODEL,
            temperature=0.0,
            max_tokens=1024,
        )

        # Re-order cases to match LLM ranking
        id_to_case = {str(c.id): c for c in input.cases}
        ranked = [id_to_case[rid] for rid in result.ranked_ids if rid in id_to_case]

        # Append any cases LLM missed (shouldn't happen, but defensive)
        seen = set(result.ranked_ids)
        for c in input.cases:
            if str(c.id) not in seen:
                ranked.append(c)

        return RerankOutput(
            cases=ranked[:input.top_k],
            recommendation_reason=result.recommendation_reason,
            case_notes=result.case_notes,
        )

    except Exception as e:
        logger.warning(f"Rerank LLM failed, using original order: {e}")
        return RerankOutput(
            cases=input.cases[:input.top_k],
            recommendation_reason="根据向量相似度排序",
        )
