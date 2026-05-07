"""SlidePlan assembler — pure function from Outline + ProjectBrief → SlidePlan.

No LLM calls. Reads Outline.spec_json (OutlineSpec) and PPT_BLUEPRINT to compute:
- total_pages (== number of slide entries)
- sections: chapter aggregation with [page_start, page_end]
- slides: per-slide template_component (from blueprint slot lookup)

Used at render time (template mode) to give every component the global context
it needs — total_pages, page_range, section number — eliminating the
hard-coded "40 / 4 chapters / specific page ranges" assumptions in the
external templates.
"""
from __future__ import annotations

import logging
from typing import Optional

from config.ppt_blueprint import get_slot_by_id
from db.models.outline import Outline
from db.models.project import ProjectBrief
from schema.outline import OutlineSpec, OutlineSlideEntry
from schema.page_slot import normalize_slot_id
from schema.slide_data import ComponentType
from schema.slide_plan import SlidePlan, SlidePlanEntry, SlidePlanSection

logger = logging.getLogger(__name__)


# Chapter EN translation fallback. Visual Theme agent / Outline agent may
# override these via section_en on transition slides; this is the last-resort
# default used when nothing better is available.
_CHAPTER_EN: dict[str, str] = {
    "封面": "Cover",
    "目录": "Contents",
    "背景研究": "Background Research",
    "场地分析": "Site Analysis",
    "竞品分析": "Competitive Analysis",
    "参考案例": "Reference Cases",
    "项目定位": "Project Positioning",
    "设计策略": "Design Strategy",
    "概念方案": "Concept Proposals",
    "深化比选": "Comparison & Refinement",
    "设计任务书": "Design Brief",
    "结尾": "Closing",
}


def build_slide_plan(
    outline: Outline,
    brief: ProjectBrief,
    *,
    section_colors: Optional[list[str]] = None,
) -> SlidePlan:
    """Assemble a SlidePlan from an Outline + ProjectBrief.

    Args:
        outline: ORM model with `spec_json` containing a serialised OutlineSpec.
        brief:   Source of project_title fallback.
        section_colors: Optional list[hex] from VisualTheme.section_colors,
                        applied positionally to sections in order. Extra
                        colors are ignored; missing trailing colors leave
                        SlidePlanSection.accent_color = None.

    Returns:
        Validated SlidePlan; deterministic for the same inputs.
    """
    spec = OutlineSpec.model_validate(outline.spec_json)
    slides = sorted(spec.slides, key=lambda s: s.slide_no)

    sections = _aggregate_sections(slides, section_colors or [])
    plan_entries = [_build_entry(s, sections) for s in slides]

    project_title = (
        spec.deck_title
        or getattr(brief, "project_name", None)
        or getattr(brief, "client_name", None)
        or "PROJECT"
    )

    return SlidePlan(
        project_id=spec.project_id,
        project_title=project_title,
        total_pages=len(slides),
        sections=sections,
        slides=plan_entries,
    )


def _aggregate_sections(
    slides: list[OutlineSlideEntry],
    section_colors: list[str],
) -> list[SlidePlanSection]:
    """Group slides by their `section` field, in encounter order.

    Cover and TOC sections (and any "封面"/"目录"/"结尾" markers) are kept as
    their own sections so chrome page-tagging stays consistent. Section
    numbering is 1-based across all sections; if you want concept_scheme's
    `--section-color-N` to skip cover/toc, exclude them upstream from
    section_colors length.
    """
    if not slides:
        return []

    sections: list[SlidePlanSection] = []
    current_name: Optional[str] = None
    current_start = 0

    for slide in slides:
        name = slide.section or "未分类"
        if name != current_name:
            if current_name is not None:
                sections.append(
                    _make_section(
                        no=len(sections) + 1,
                        name=current_name,
                        start=current_start,
                        end=slide.slide_no - 1,
                        section_colors=section_colors,
                    )
                )
            current_name = name
            current_start = slide.slide_no

    # final section
    sections.append(
        _make_section(
            no=len(sections) + 1,
            name=current_name or "未分类",
            start=current_start,
            end=slides[-1].slide_no,
            section_colors=section_colors,
        )
    )
    return sections


def _make_section(
    *, no: int, name: str, start: int, end: int, section_colors: list[str]
) -> SlidePlanSection:
    accent = section_colors[no - 1] if 0 <= no - 1 < len(section_colors) else None
    return SlidePlanSection(
        no=no,
        title=name,
        en=_CHAPTER_EN.get(name, ""),
        page_start=start,
        page_end=end,
        accent_color=accent,
    )


def _build_entry(
    slide: OutlineSlideEntry,
    sections: list[SlidePlanSection],
) -> SlidePlanEntry:
    section_no = _section_no_for(slide.slide_no, sections)
    return SlidePlanEntry(
        slide_no=slide.slide_no,
        section_no=section_no,
        component_type=_component_for_slot(slide.slot_id),
        slot_id=slide.slot_id,
        is_cover=slide.is_cover,
        is_chapter_divider=slide.is_chapter_divider,
    )


def _section_no_for(slide_no: int, sections: list[SlidePlanSection]) -> int:
    for s in sections:
        if s.page_start <= slide_no <= s.page_end:
            return s.no
    # Should never happen — _aggregate_sections covers all slides.
    logger.warning("slide %s falls outside any section; defaulting to 1", slide_no)
    return 1


def _component_for_slot(slot_id: str) -> Optional[ComponentType]:
    slot = get_slot_by_id(slot_id) or get_slot_by_id(normalize_slot_id(slot_id))
    if slot is None:
        return None
    return slot.template_component
