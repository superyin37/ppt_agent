"""Unit tests for agent.slide_plan.build_slide_plan (ADR-006)."""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from agent.slide_plan import build_slide_plan
from schema.outline import OutlineSlideEntry, OutlineSpec
from schema.slide_data import ComponentType


def _make_outline(entries: list[OutlineSlideEntry]) -> MagicMock:
    spec = OutlineSpec(
        project_id=uuid4(),
        deck_title="Test Deck",
        theme="modern",
        total_pages=len(entries),
        sections=list(dict.fromkeys(e.section for e in entries)),
        slides=entries,
    )
    outline = MagicMock()
    outline.spec_json = spec.model_dump(mode="json")
    return outline


def _brief() -> MagicMock:
    b = MagicMock()
    b.project_name = "TestProj"
    b.client_name = None
    return b


def _entry(slot_id: str, slide_no: int, section: str, **kw) -> OutlineSlideEntry:
    return OutlineSlideEntry(
        slot_id=slot_id,
        slide_no=slide_no,
        section=section,
        title=f"slide-{slide_no}",
        purpose="",
        key_message="",
        **kw,
    )


def test_minimal_three_page_plan():
    entries = [
        _entry("cover", 1, "Cover", is_cover=True),
        _entry("toc", 2, "Toc"),
        _entry("closing", 3, "End", is_chapter_divider=True),
    ]
    plan = build_slide_plan(_make_outline(entries), _brief())
    assert plan.total_pages == 3
    assert len(plan.sections) == 3
    assert plan.sections[0].page_start == 1 and plan.sections[0].page_end == 1
    assert plan.entry_for(1).component_type is ComponentType.COVER
    assert plan.entry_for(3).component_type is ComponentType.ENDING


def test_section_aggregation_and_page_ranges():
    entries = [
        _entry("cover", 1, "Cover", is_cover=True),
        _entry("toc", 2, "Toc"),
        _entry("chapter-1-divider", 3, "Background", is_chapter_divider=True),
        _entry("policy", 4, "Background"),
        _entry("policy", 5, "Background"),
        _entry("chapter-2-divider", 6, "Site", is_chapter_divider=True),
        _entry("poi-analysis", 7, "Site"),
        _entry("closing", 8, "End"),
    ]
    plan = build_slide_plan(_make_outline(entries), _brief())
    bg = next(s for s in plan.sections if s.title == "Background")
    site = next(s for s in plan.sections if s.title == "Site")
    assert bg.page_start == 3 and bg.page_end == 5
    assert site.page_start == 6 and site.page_end == 7
    assert plan.section_for(4).title == "Background"
    assert plan.entry_for(7).section_no == site.no


def test_section_colors_applied_positionally():
    entries = [
        _entry("cover", 1, "A"),
        _entry("toc", 2, "B"),
        _entry("closing", 3, "C"),
    ]
    plan = build_slide_plan(
        _make_outline(entries),
        _brief(),
        section_colors=["#111", "#222"],
    )
    assert plan.sections[0].accent_color == "#111"
    assert plan.sections[1].accent_color == "#222"
    assert plan.sections[2].accent_color is None  # ran out of colors


def test_unknown_slot_falls_back_to_none_component():
    entries = [_entry("nonexistent-slot-id", 1, "X")]
    plan = build_slide_plan(_make_outline(entries), _brief())
    assert plan.entry_for(1).component_type is None


def test_total_pages_matches_slide_count_not_outline_field():
    entries = [_entry("cover", 1, "Cover"), _entry("closing", 2, "End")]
    outline = _make_outline(entries)
    # Tamper with the spec to claim a different total_pages
    outline.spec_json["total_pages"] = 99
    plan = build_slide_plan(outline, _brief())
    assert plan.total_pages == 2  # derived from slides, not from the (lying) field
