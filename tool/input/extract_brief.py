import json
import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel

from schema.project import ProjectBriefData, IntakeFollowUp
from schema.common import BuildingType
from config.llm import call_llm_structured, FAST_MODEL
from tool.input.compute_far import compute_far_metrics, ComputeFARInput
from tool._base import ToolError


PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "intake_system.md"


class ExtractBriefInput(BaseModel):
    raw_text: str
    existing_brief: Optional[dict] = None   # already-extracted partial brief


class ExtractBriefOutput(BaseModel):
    extracted: ProjectBriefData
    missing_fields: list[str]
    is_complete: bool
    follow_up: Optional[str] = None
    confirmation_summary: Optional[str] = None


class _LLMBriefOutput(BaseModel):
    """Internal schema for LLM structured output."""
    extracted: dict
    missing_fields: list[str]
    is_complete: bool
    follow_up: Optional[str] = None
    confirmation_summary: Optional[str] = None


def _load_system_prompt(building_type_hint: str, existing_brief_json: str) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    return template.format(
        building_type_hint=building_type_hint or "未知（请从用户输入中识别）",
        existing_brief_json=existing_brief_json,
    )


def _merge_briefs(existing: Optional[dict], new: dict) -> dict:
    """Merge new extracted fields into existing brief, keeping non-null values."""
    if not existing:
        return new
    merged = dict(existing)
    for k, v in new.items():
        if v is not None:
            merged[k] = v
        # Keep existing value if new is None/empty list
        elif k == "style_preferences" and v:
            merged[k] = v
    return merged


def _compute_missing_fields(brief: dict) -> list[str]:
    missing = []
    if not brief.get("building_type"):
        missing.append("building_type")
    if not brief.get("client_name"):
        missing.append("client_name")
    if not brief.get("site_address"):
        missing.append("site_address")
    if not brief.get("style_preferences"):
        missing.append("style_preferences")

    gfa = brief.get("gross_floor_area")
    sa = brief.get("site_area")
    far = brief.get("far")
    metric_count = sum([gfa is not None, sa is not None, far is not None])
    if metric_count < 2:
        missing.append("gross_floor_area_or_site_area_or_far（至少两项）")

    return missing


async def extract_project_brief(input: ExtractBriefInput) -> ExtractBriefOutput:
    """
    LLM-based extraction of ProjectBriefData from natural language.
    Merges with existing partial brief (multi-turn support).
    timeout: 30s
    model: FAST_MODEL
    """
    existing = input.existing_brief or {}
    building_type_hint = existing.get("building_type", "")
    existing_json = json.dumps(existing, ensure_ascii=False, indent=2) if existing else "（无已有信息）"

    system_prompt = _load_system_prompt(building_type_hint, existing_json)

    llm_output = await call_llm_structured(
        system_prompt=system_prompt,
        user_message=input.raw_text,
        output_schema=_LLMBriefOutput,
        model=FAST_MODEL,
        temperature=0.0,
        max_tokens=1024,
    )

    # Merge with existing
    merged = _merge_briefs(existing, llm_output.extracted)

    # Auto-compute FAR if two metrics available
    gfa = merged.get("gross_floor_area")
    sa = merged.get("site_area")
    far = merged.get("far")
    metric_count = sum([gfa is not None, sa is not None, far is not None])
    if metric_count == 2:
        try:
            result = compute_far_metrics(ComputeFARInput(
                gross_floor_area=gfa,
                site_area=sa,
                far=far,
            ))
            merged["gross_floor_area"] = result.gross_floor_area
            merged["site_area"] = result.site_area
            merged["far"] = result.far
        except ToolError:
            pass

    missing_fields = _compute_missing_fields(merged)
    is_complete = len(missing_fields) == 0

    # Build Pydantic model (tolerant of extra/missing fields)
    brief_data = ProjectBriefData(
        building_type=merged.get("building_type"),
        client_name=merged.get("client_name"),
        style_preferences=merged.get("style_preferences") or [],
        special_requirements=merged.get("special_requirements"),
        gross_floor_area=merged.get("gross_floor_area"),
        site_area=merged.get("site_area"),
        far=merged.get("far"),
        site_address=merged.get("site_address"),
        province=merged.get("province"),
        city=merged.get("city"),
        district=merged.get("district"),
        missing_fields=missing_fields,
        is_complete=is_complete,
    )

    return ExtractBriefOutput(
        extracted=brief_data,
        missing_fields=missing_fields,
        is_complete=is_complete,
        follow_up=llm_output.follow_up if not is_complete else None,
        confirmation_summary=llm_output.confirmation_summary if is_complete else None,
    )
