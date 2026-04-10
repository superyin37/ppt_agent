"""
Critic Agent - Phase 8.

Orchestrates a 3-layer quality review for each slide:
  Layer 1 - rule-based lint (layout_lint, no LLM)
  Layer 2 - semantic consistency check (text LLM)
  Layer 3 - vision review (multimodal LLM, optional)
"""
import logging
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from pathlib import Path

from schema.common import ReviewSeverity
from schema.review import (
    DesignAdvice,
    DesignDimension,
    DesignSuggestion,
    RepairAction,
    ReviewDecision,
    ReviewIssue,
    ReviewReport,
)
from schema.visual_theme import LayoutSpec
from tool.review.layout_lint import layout_lint
from tool.review.repair_plan import build_repair_plan_from_issues, execute_repair
from tool.review.semantic_check import SemanticCheckInput, semantic_check

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _load_design_advisor_prompt() -> str:
    path = _PROMPTS_DIR / "vision_design_advisor.md"
    return path.read_text(encoding="utf-8")


VISION_SYSTEM_PROMPT = """You review rendered presentation slides for visual quality.

Check only concrete visual problems that are visible in the screenshot:
- V001 VISUAL_CLUTTER
- V002 IMAGE_BLURRY
- V004 TEXT_ON_BUSY_BG
- V007 BLANK_AREA_WASTE

Return JSON only:
{"issues": [{"rule_code": "V001", "severity": "P2", "message": "...", "auto_fixable": false}]}
"""


class _VisionOutput(BaseModel):
    issues: list[dict] = []


def _is_invalid_model_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "not a valid model id" in message or "invalid model" in message


async def review_slide(
    spec: LayoutSpec,
    brief: dict,
    layers: list[str] | None = None,
    screenshot_url: Optional[str] = None,
    max_repairs: int = 3,
    design_advisor: bool = False,
    page_type: str = "content",
    content_summary: str = "",
    theme_colors: dict | None = None,
) -> tuple[LayoutSpec, ReviewReport]:
    """
    Full critic pipeline for one slide.
    Returns (potentially-repaired spec, ReviewReport).
    """
    if layers is None:
        layers = ["rule", "semantic"]

    all_issues: list[ReviewIssue] = []
    all_repairs: list[RepairAction] = []
    current_spec = spec
    target_id = getattr(spec, "project_id", None) or UUID(int=0)

    if "rule" in layers:
        lint_result = layout_lint(current_spec)
        all_issues.extend(lint_result.issues)

        auto_repair_plan = build_repair_plan_from_issues(lint_result.issues)
        if auto_repair_plan:
            all_repairs.extend(auto_repair_plan)
            repair_report = ReviewReport(
                target_type="slide",
                target_id=target_id,
                review_layer="rule",
                severity=ReviewSeverity.P1,
                issues=lint_result.issues,
                final_decision=ReviewDecision.REPAIR_REQUIRED,
                repair_plan=auto_repair_plan,
            )
            current_spec, repair_logs = execute_repair(current_spec, repair_report)
            logger.debug("Slide %s rule repairs: %s", spec.slide_no, repair_logs)

    if "semantic" in layers:
        try:
            sem_result = await semantic_check(SemanticCheckInput(spec=current_spec, brief=brief))
            all_issues.extend(sem_result.issues)
            all_repairs.extend(sem_result.repair_actions)
            # Execute auto-fixable semantic repairs (e.g. S007 client name)
            if sem_result.repair_actions:
                sem_report = ReviewReport(
                    target_type="slide",
                    target_id=target_id,
                    review_layer="semantic",
                    severity=ReviewSeverity.P1,
                    issues=sem_result.issues,
                    final_decision=ReviewDecision.REPAIR_REQUIRED,
                    repair_plan=sem_result.repair_actions,
                )
                current_spec, sem_logs = execute_repair(current_spec, sem_report)
                logger.debug("Slide %s semantic repairs: %s", spec.slide_no, sem_logs)
        except Exception as exc:
            logger.warning("Semantic check failed for slide %s: %s", spec.slide_no, exc)

    if "vision" in layers and screenshot_url:
        try:
            vision_issues = await _vision_review(screenshot_url, spec.slide_no)
            all_issues.extend(vision_issues)
        except Exception as exc:
            logger.warning("Vision review failed for slide %s: %s", spec.slide_no, exc)
            all_issues.append(ReviewIssue(
                issue_id=f"VISION_SKIPPED_{spec.slide_no}",
                rule_code="VISION_SKIPPED",
                layer="vision",
                severity=ReviewSeverity.P2,
                message=f"Vision review skipped due to error: {exc}",
                suggested_fix="",
                auto_fixable=False,
            ))

    design_advice = None
    if design_advisor and screenshot_url:
        try:
            design_advice = await _design_review(
                screenshot_url,
                getattr(spec, "slide_no", 0),
                page_type,
                content_summary,
                theme_colors or {},
            )
        except Exception as exc:
            logger.warning("Design review failed for slide %s: %s", spec.slide_no, exc)

    final_severity, final_decision = _evaluate(all_issues)

    report = ReviewReport(
        target_type="slide",
        target_id=target_id,
        review_layer=",".join(layers),
        severity=final_severity,
        issues=all_issues[:5],
        final_decision=final_decision,
        repair_plan=all_repairs,
        design_advice=design_advice,
    )
    return current_spec, report


def _resolve_image_url(screenshot_url: str) -> str:
    """Convert local file paths to base64 data URLs so LLM APIs can read them."""
    import base64
    from pathlib import Path

    if screenshot_url.startswith("data:"):
        return screenshot_url
    if screenshot_url.startswith(("http://", "https://")):
        return screenshot_url

    # Local path — try to read and encode as base64
    # Handle both absolute paths and relative paths like "/slides-output/slide_01.png"
    path = Path(screenshot_url)
    if not path.is_absolute():
        # Try common local output directories
        for candidate in [
            Path("tmp/e2e_output/slides") / path.name,
            Path(screenshot_url.lstrip("/")),
        ]:
            if candidate.exists():
                path = candidate
                break

    if path.exists():
        png_bytes = path.read_bytes()
        b64 = base64.b64encode(png_bytes).decode()
        return f"data:image/png;base64,{b64}"

    logger.warning("screenshot not found at %s, passing URL as-is", screenshot_url)
    return screenshot_url


async def _vision_review(screenshot_url: str, slide_no: int) -> list[ReviewIssue]:
    """Multimodal LLM vision review of rendered screenshot."""
    from config.llm import CRITIC_MODEL, FAST_MODEL, call_llm_multimodal

    resolved_url = _resolve_image_url(screenshot_url)

    async def _call_vision_model(model: str) -> _VisionOutput:
        return await call_llm_multimodal(
            system_prompt=VISION_SYSTEM_PROMPT,
            text_message=f"Review slide {slide_no} screenshot for visual quality issues.",
            image_url=resolved_url,
            output_schema=_VisionOutput,
            model=model,
        )

    try:
        result = await _call_vision_model(CRITIC_MODEL)
    except Exception as exc:
        if CRITIC_MODEL != FAST_MODEL and _is_invalid_model_error(exc):
            logger.warning(
                "Vision review invalid critic model '%s' for slide %s, retrying with fast model '%s'",
                CRITIC_MODEL,
                slide_no,
                FAST_MODEL,
            )
            try:
                result = await _call_vision_model(FAST_MODEL)
            except Exception as fallback_exc:
                logger.warning("Vision review fallback LLM error (slide %s): %s", slide_no, fallback_exc)
                return []
        else:
            logger.warning("Vision review LLM error (slide %s): %s", slide_no, exc)
            return []

    issues: list[ReviewIssue] = []
    for i, raw in enumerate(result.issues):
        try:
            sev = ReviewSeverity(raw.get("severity", "P2"))
        except ValueError:
            sev = ReviewSeverity.P2
        issues.append(
            ReviewIssue(
                issue_id=f"{raw.get('rule_code', 'V000')}_{slide_no}_{i}",
                rule_code=raw.get("rule_code", "V000"),
                layer="vision",
                severity=sev,
                message=raw.get("message", ""),
                suggested_fix="",
                auto_fixable=bool(raw.get("auto_fixable", False)),
            )
        )
    return issues


def _evaluate(issues: list[ReviewIssue]) -> tuple[ReviewSeverity, ReviewDecision]:
    """Determine overall severity and decision from issue list."""
    if not issues:
        return ReviewSeverity.PASS, ReviewDecision.PASS

    # All issues are SKIPPED -> record but don't block (can't review ≠ has problems)
    real_issues = [i for i in issues if not i.rule_code.endswith("_SKIPPED")]
    if not real_issues:
        return ReviewSeverity.P2, ReviewDecision.PASS

    has_p0 = any(i.severity == ReviewSeverity.P0 for i in real_issues)
    has_p1 = any(i.severity == ReviewSeverity.P1 for i in real_issues)

    p0_non_fixable = [i for i in real_issues if i.severity == ReviewSeverity.P0 and not i.auto_fixable]
    if p0_non_fixable:
        return ReviewSeverity.P0, ReviewDecision.ESCALATE_HUMAN

    if has_p0 or has_p1:
        return (ReviewSeverity.P0 if has_p0 else ReviewSeverity.P1), ReviewDecision.REPAIR_REQUIRED

    return ReviewSeverity.P2, ReviewDecision.REPAIR_REQUIRED


class _DesignAdvisorOutput(BaseModel):
    dimensions: list[dict] = []
    suggestions: list[dict] = []
    one_liner: str = ""


def _score_to_grade(score: float) -> str:
    if score >= 8.0:
        return "A"
    if score >= 6.0:
        return "B"
    if score >= 4.0:
        return "C"
    return "D"


async def _design_review(
    screenshot_url: str,
    slide_no: int,
    page_type: str,
    content_summary: str,
    theme_colors: dict,
) -> DesignAdvice:
    """Multimodal design advisor — scores visual quality and gives improvement suggestions."""
    from config.llm import CRITIC_MODEL, FAST_MODEL, call_llm_multimodal

    resolved_url = _resolve_image_url(screenshot_url)
    system_prompt = _load_design_advisor_prompt()

    color_info = ""
    if theme_colors:
        parts = [f"{k}={v}" for k, v in theme_colors.items() if v]
        color_info = f"\n- Theme colors: {', '.join(parts)}" if parts else ""

    user_msg = (
        f"Review slide {slide_no} ({page_type}) for design quality.\n\n"
        f"Context:\n"
        f"- Page type: {page_type}\n"
        f"- Content summary: {content_summary}"
        f"{color_info}"
    )

    async def _call(model: str) -> _DesignAdvisorOutput:
        return await call_llm_multimodal(
            system_prompt=system_prompt,
            text_message=user_msg,
            image_url=resolved_url,
            output_schema=_DesignAdvisorOutput,
            model=model,
            max_tokens=3000,
            temperature=0.3,
        )

    try:
        result = await _call(CRITIC_MODEL)
    except Exception as exc:
        if CRITIC_MODEL != FAST_MODEL and _is_invalid_model_error(exc):
            logger.warning(
                "Design review invalid critic model '%s' for slide %s, retrying with fast model",
                CRITIC_MODEL, slide_no,
            )
            result = await _call(FAST_MODEL)
        else:
            raise

    # Parse dimensions
    dims: list[DesignDimension] = []
    for raw in result.dimensions:
        dims.append(DesignDimension(
            dimension=raw.get("dimension", "unknown"),
            score=float(raw.get("score", 0)),
            comment=raw.get("comment", ""),
        ))

    overall = sum(d.score for d in dims) / len(dims) if dims else 0.0

    # Parse suggestions
    suggs: list[DesignSuggestion] = []
    for raw in result.suggestions:
        suggs.append(DesignSuggestion(
            code=raw.get("code", "D000"),
            category=raw.get("category", ""),
            severity=raw.get("severity", "recommended"),
            message=raw.get("message", ""),
            css_hint=raw.get("css_hint", ""),
            target_selector=raw.get("target_selector", ""),
        ))

    return DesignAdvice(
        slide_no=slide_no,
        dimensions=dims,
        overall_score=round(overall, 1),
        grade=_score_to_grade(overall),
        suggestions=suggs,
        one_liner=result.one_liner,
    )
