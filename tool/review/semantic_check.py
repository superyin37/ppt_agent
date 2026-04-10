"""
Semantic consistency checks for slide content.

This module supports both the legacy SlideSpec review flow and the new
LayoutSpec-based material-package flow.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from pydantic import BaseModel

from config.llm import CRITIC_MODEL, FAST_MODEL, call_llm_with_limit
from schema.common import ReviewSeverity
from schema.review import RepairAction, ReviewIssue
from schema.slide import SlideSpec
from schema.visual_theme import LayoutSpec

logger = logging.getLogger(__name__)

SEMANTIC_SYSTEM_PROMPT = """You review semantic consistency for presentation slides.

Check only these categories:
- S001 METRIC_INCONSISTENCY
- S004 UNSUPPORTED_CLAIM
- S005 STYLE_TERM_WRONG
- S006 MISSING_KEY_MESSAGE_SUPPORT
- S007 CLIENT_NAME_WRONG

Return only concrete issues that can be justified from the slide summary and
project brief. If there are no issues, return an empty list.
"""


class _SemanticIssue(BaseModel):
    rule_code: str
    severity: str
    message: str
    location: Optional[str] = None
    auto_fixable: bool = False
    suggested_fix: str = ""


class _SemanticOutput(BaseModel):
    issues: list[_SemanticIssue] = []
    overall_ok: bool = True


class SemanticCheckInput(BaseModel):
    spec: LayoutSpec | SlideSpec
    brief: dict


class SemanticCheckOutput(BaseModel):
    issues: list[ReviewIssue] = []
    repair_actions: list[RepairAction] = []


def _is_invalid_model_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "not a valid model id" in message or "invalid model" in message


def _spec_summary(spec: LayoutSpec | SlideSpec) -> dict:
    blocks_preview: list[str] = []
    primitive_type = ""

    if isinstance(spec, LayoutSpec):
        for region in spec.region_bindings:
            for block in region.blocks:
                content_preview = str(block.content)[:200] if block.content else ""
                blocks_preview.append(f"[{block.block_id}/{block.content_type}]: {content_preview}")
        primitive_type = spec.primitive.primitive
    else:
        for block in spec.blocks:
            content_preview = str(block.content)[:200] if block.content else ""
            blocks_preview.append(f"[{block.block_id}/{block.block_type}]: {content_preview}")
        primitive_type = spec.layout_template.value

    return {
        "slide_no": spec.slide_no,
        "title": spec.title,
        "section": spec.section,
        "primitive_type": primitive_type,
        "key_message": getattr(spec, "key_message", ""),
        "blocks_preview": blocks_preview,
    }


async def semantic_check(input: SemanticCheckInput) -> SemanticCheckOutput:
    spec = input.spec
    slide_summary = _spec_summary(spec)
    brief_summary = {
        "building_type": input.brief.get("building_type"),
        "client_name": input.brief.get("client_name"),
        "style_preferences": input.brief.get("style_preferences", []),
        "gross_floor_area": input.brief.get("gross_floor_area"),
        "far": input.brief.get("far"),
    }

    user_msg = (
        f"<slide>\n{json.dumps(slide_summary, ensure_ascii=False, indent=2)}\n</slide>\n\n"
        f"<project_brief>\n{json.dumps(brief_summary, ensure_ascii=False, indent=2)}\n</project_brief>\n\n"
        "Return semantic issues in the requested schema."
    )

    async def _call_semantic_model(model: str) -> _SemanticOutput:
        return await call_llm_with_limit(
            system_prompt=SEMANTIC_SYSTEM_PROMPT,
            user_message=user_msg,
            output_schema=_SemanticOutput,
            model=model,
            temperature=0.1,
            max_tokens=512,
        )

    try:
        result = await _call_semantic_model(CRITIC_MODEL)
    except Exception as exc:
        if CRITIC_MODEL != FAST_MODEL and _is_invalid_model_error(exc):
            logger.warning(
                "semantic_check invalid critic model '%s' for slide %s, retrying with fast model '%s'",
                CRITIC_MODEL,
                spec.slide_no,
                FAST_MODEL,
            )
            try:
                result = await _call_semantic_model(FAST_MODEL)
            except Exception as fallback_exc:
                logger.warning("semantic_check fallback LLM failed for slide %s: %s", spec.slide_no, fallback_exc)
                return SemanticCheckOutput(issues=[
                    ReviewIssue(
                        issue_id=f"SEMANTIC_SKIPPED_{spec.slide_no}",
                        rule_code="SEMANTIC_SKIPPED",
                        layer="semantic",
                        severity=ReviewSeverity.P2,
                        message=f"Semantic check skipped due to LLM error: {fallback_exc}",
                        suggested_fix="",
                        auto_fixable=False,
                    )
                ])
        else:
            logger.warning("semantic_check LLM failed for slide %s: %s", spec.slide_no, exc)
            return SemanticCheckOutput(issues=[
                ReviewIssue(
                    issue_id=f"SEMANTIC_SKIPPED_{spec.slide_no}",
                    rule_code="SEMANTIC_SKIPPED",
                    layer="semantic",
                    severity=ReviewSeverity.P2,
                    message=f"Semantic check skipped due to LLM error: {exc}",
                    suggested_fix="",
                    auto_fixable=False,
                )
            ])

    issues: list[ReviewIssue] = []
    repair_actions: list[RepairAction] = []
    for index, raw in enumerate(result.issues):
        try:
            severity = ReviewSeverity(raw.severity)
        except ValueError:
            severity = ReviewSeverity.P2

        issues.append(
            ReviewIssue(
                issue_id=f"{raw.rule_code}_{spec.slide_no}_{index}",
                rule_code=raw.rule_code,
                layer="semantic",
                severity=severity,
                message=raw.message,
                location=raw.location,
                suggested_fix=raw.suggested_fix,
                auto_fixable=raw.auto_fixable,
            )
        )

        if raw.rule_code == "S007" and raw.auto_fixable:
            repair_actions.append(
                RepairAction(
                    action_type="replace_client_name",
                    target_block_id=raw.location,
                    params={"correct_name": input.brief.get("client_name", "")},
                )
            )

    return SemanticCheckOutput(issues=issues, repair_actions=repair_actions)
