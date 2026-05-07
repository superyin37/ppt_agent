"""Composer Agent — template mode (v4) per ADR-006.

Produces a typed `SlideData` payload (one of 11 component models) that the
renderer feeds into a Jinja2 template. Never produces HTML/CSS itself.

On validation failure: retry once with the offending field lengths echoed
back into the prompt; if the retry still fails, run `truncate_to_schema`
as a last resort. If even that produces an invalid payload, raise so the
upstream Composer can fall back to v3 html_free mode.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ValidationError

from config.llm import STRONG_MODEL, call_llm_with_limit
from db.models.slide_material_binding import SlideMaterialBinding
from schema.outline import OutlineSlideEntry
from schema.slide_data import (
    COMPONENT_SCHEMA,
    ComponentType,
    truncate_to_schema,
)
from schema.visual_theme import VisualTheme

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "composer_template_mode.md"


class TemplateModeError(Exception):
    """Raised when template-mode composition cannot produce a valid payload
    even after retry + truncation. Caller should fall back to html_free."""


def _load_system_prompt() -> str:
    return _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def _theme_context(theme: VisualTheme) -> dict:
    return {
        "style_keywords": theme.style_keywords,
        "color_mode": getattr(theme, "color_mode", "mixed"),
        "contrast_level": getattr(theme, "contrast_level", "high"),
        "accent_saturation": getattr(theme, "accent_saturation", "high"),
        "font_mood": getattr(theme, "font_mood", "modern"),
        "visual_intensity": getattr(theme, "visual_intensity", "bold"),
        "color_strategy": getattr(theme, "color_strategy", "high-contrast"),
        "composition_style": getattr(theme, "composition_style", "editorial"),
        "decorative_motif": getattr(theme, "decorative_motif", "architectural-lines"),
        "density": theme.spacing.density,
        "color_fill_usage": theme.decoration.color_fill_usage,
        "generation_hint": theme.generation_prompt_hint,
    }


def _binding_context(binding: Optional[SlideMaterialBinding]) -> dict:
    if binding is None:
        return {"binding_id": "", "derived_asset_ids": [], "evidence_snippets": [], "missing_requirements": []}
    return {
        "binding_id": str(binding.id),
        "derived_asset_ids": list(binding.derived_asset_ids or []),
        "evidence_snippets": list(binding.evidence_snippets or []),
        "missing_requirements": list(binding.missing_requirements or []),
    }


def _build_user_message(
    *,
    entry: OutlineSlideEntry,
    component_type: ComponentType,
    schema_cls: type[BaseModel],
    theme: VisualTheme,
    brief_dict: dict,
    asset_summary: list[dict],
    binding: Optional[SlideMaterialBinding],
    length_violations: Optional[dict[str, int]] = None,
) -> str:
    schema_json = schema_cls.model_json_schema()
    parts = [
        f"<component_type>{component_type.value}</component_type>",
        f"<output_schema>\n{json.dumps(schema_json, ensure_ascii=False)}\n</output_schema>",
        f"<outline_entry>\n{entry.model_dump_json(indent=2)}\n</outline_entry>",
        f"<project_brief>\n{json.dumps(brief_dict, ensure_ascii=False)}\n</project_brief>",
        f"<visual_theme>\n{json.dumps(_theme_context(theme), ensure_ascii=False)}\n</visual_theme>",
        f"<bound_assets>\n{json.dumps(asset_summary[:20], ensure_ascii=False, indent=2)}\n</bound_assets>",
        f"<slide_material_binding>\n{json.dumps(_binding_context(binding), ensure_ascii=False)}\n</slide_material_binding>",
    ]
    if length_violations:
        parts.append(
            f"<length_violations>\n{json.dumps(length_violations, ensure_ascii=False)}\n</length_violations>\n"
            "上一次输出超出了上述字段的长度上限。请专门压缩这些字段，其它字段保持原样。"
        )
    parts.append(f"请为该页面生成符合 schema 的 JSON ({component_type.value}).")
    return "\n\n".join(parts)


def _measure_length_violations(raw_dict: dict, exc: ValidationError) -> dict[str, int]:
    """From a Pydantic ValidationError, extract `{field_path: actual_length}`
    for max_length / max_items violations so we can hand them back to the LLM."""
    violations: dict[str, int] = {}
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"])
        etype = err["type"]
        if etype not in {"string_too_long", "list_too_long", "too_long"}:
            continue
        actual = _walk(raw_dict, err["loc"])
        if actual is None:
            continue
        if isinstance(actual, str):
            violations[loc] = len(actual)
        elif isinstance(actual, list):
            violations[loc] = len(actual)
    return violations


def _walk(d, path):
    cur = d
    for p in path:
        if isinstance(cur, dict):
            cur = cur.get(p)
        elif isinstance(cur, list) and isinstance(p, int) and 0 <= p < len(cur):
            cur = cur[p]
        else:
            return None
        if cur is None:
            return None
    return cur


async def compose_template_slide(
    *,
    entry: OutlineSlideEntry,
    component_type: ComponentType,
    theme: VisualTheme,
    brief_dict: dict,
    asset_summary: list[dict],
    binding: Optional[SlideMaterialBinding] = None,
    model: str = STRONG_MODEL,
) -> BaseModel:
    """Produce a SlideData payload for one slide.

    Returns an instance of the appropriate ComponentData subclass (one of
    the 11 in `schema.slide_data.COMPONENT_SCHEMA`). Raises TemplateModeError
    if no valid payload can be produced; caller should fall back to v3.
    """
    schema_cls = COMPONENT_SCHEMA.get(component_type)
    if schema_cls is None:
        raise TemplateModeError(f"no schema registered for component_type={component_type}")

    sys_prompt = _load_system_prompt()
    user_msg = _build_user_message(
        entry=entry,
        component_type=component_type,
        schema_cls=schema_cls,
        theme=theme,
        brief_dict=brief_dict,
        asset_summary=asset_summary,
        binding=binding,
    )

    # Attempt 1
    try:
        result = await call_llm_with_limit(
            system_prompt=sys_prompt,
            user_message=user_msg,
            output_schema=schema_cls,
            model=model,
            temperature=0.3,
            max_tokens=2000,
        )
        return result
    except ValidationError as ve_first:
        logger.warning(
            "template-mode slide %s validation failed (attempt 1): %s",
            entry.slide_no, ve_first,
        )
        violations = _measure_length_violations(_extract_raw_dict(ve_first), ve_first)
    except Exception as exc:
        logger.warning("template-mode slide %s LLM call failed: %s", entry.slide_no, exc)
        raise TemplateModeError(str(exc)) from exc

    # Attempt 2 — retry with feedback
    retry_msg = _build_user_message(
        entry=entry,
        component_type=component_type,
        schema_cls=schema_cls,
        theme=theme,
        brief_dict=brief_dict,
        asset_summary=asset_summary,
        binding=binding,
        length_violations=violations,
    )
    try:
        result = await call_llm_with_limit(
            system_prompt=sys_prompt,
            user_message=retry_msg,
            output_schema=schema_cls,
            model=model,
            temperature=0.2,
            max_tokens=2000,
        )
        return result
    except ValidationError as ve_second:
        logger.warning(
            "template-mode slide %s validation failed again (attempt 2): %s",
            entry.slide_no, ve_second,
        )
        raw = _extract_raw_dict(ve_second)
    except Exception as exc:
        logger.warning("template-mode slide %s LLM retry failed: %s", entry.slide_no, exc)
        raise TemplateModeError(str(exc)) from exc

    # Attempt 3 — truncate fallback
    try:
        truncated = truncate_to_schema(raw, schema_cls)
        return schema_cls.model_validate(truncated)
    except ValidationError as ve_third:
        logger.error(
            "template-mode slide %s failed even after truncation: %s",
            entry.slide_no, ve_third,
        )
        raise TemplateModeError(f"truncate fallback failed: {ve_third}") from ve_third


def _extract_raw_dict(exc: ValidationError) -> dict:
    """Best-effort extraction of the raw dict the LLM produced from a
    Pydantic ValidationError. In Pydantic v2, `exc.errors()[i].get("input")`
    is the value at each error location, but the top-level input is not
    always preserved. We reconstruct by collecting `input` from the deepest
    error or fall back to an empty dict."""
    for err in exc.errors():
        # Each error has 'input' = the value that failed at err['loc']
        # The top-level input is what we want — find errors at root location.
        if not err.get("loc"):
            inp = err.get("input")
            if isinstance(inp, dict):
                return inp
    # Walk all errors, find the deepest dict-typed input
    candidate = {}
    for err in exc.errors():
        inp = err.get("input")
        if isinstance(inp, dict) and len(inp) > len(candidate):
            candidate = inp
    return candidate
