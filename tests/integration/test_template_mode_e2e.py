"""End-to-end test for template-mode (PR-2 / ADR-006).

Walks the full path for one slide:
- Build a fake SlidePlan
- Construct a SlideData payload (skipping the LLM)
- Build the spec_json that compose_all_slides would persist
- Invoke render_slide_template
- Assert the HTML is well-formed and pulls in plan-derived chrome values

This avoids LLM, DB, and Playwright — those layers are exercised in their
own tests. The point here is to prove compose-mode contract ↔ render-mode
contract are aligned.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from agent.composer import _ComposerTemplateOutput, _default_theme
from render.engine import render_slide_template
from schema.slide_data import ComponentType, EndingData
from schema.slide_plan import SlidePlan, SlidePlanEntry, SlidePlanSection


def _build_plan(project_id, total_pages: int = 8) -> SlidePlan:
    return SlidePlan(
        project_id=project_id,
        project_title="Sample Project",
        total_pages=total_pages,
        sections=[
            SlidePlanSection(no=1, title="封面", en="COVER", page_start=1, page_end=1, accent_color="#2b3b63"),
            SlidePlanSection(no=2, title="正文", en="BODY", page_start=2, page_end=total_pages - 1, accent_color="#49603f"),
            SlidePlanSection(no=3, title="结尾", en="CLOSING", page_start=total_pages, page_end=total_pages, accent_color="#7a4a33"),
        ],
        slides=[
            SlidePlanEntry(slide_no=total_pages, section_no=3, slot_id="closing", component_type=ComponentType.ENDING),
        ],
    )


def test_compose_to_render_pipeline_for_ending():
    """Mimic compose_all_slides' template-mode persistence shape, then render."""
    pid = uuid4()
    plan = _build_plan(pid, total_pages=8)
    theme = _default_theme(pid)

    # 1. SlideData (this is what compose_template_slide returns)
    data = EndingData(
        title="THANK YOU",
        en="GRACIAS",
        tagline="see you in the next chapter",
        signature_parts=["Sample Project", "AGENT", "2026"],
    )

    # 2. Wrap as Composer would
    composed = _ComposerTemplateOutput(
        slide_no=8,
        component_type=ComponentType.ENDING.value,
        data=data.model_dump(mode="json"),
        asset_refs=[],
        content_summary="ending",
    )

    # 3. spec_json, exactly as compose_all_slides would persist
    spec_json = {
        "mode": "template",
        "component_type": composed.component_type,
        "data": composed.data,
        "asset_refs": composed.asset_refs,
        "content_summary": composed.content_summary,
        "slide_no": composed.slide_no,
        "section": "结尾",
        "title": "THANK YOU",
        "is_cover": False,
        "is_chapter_divider": False,
    }

    # 4. Render
    html = render_slide_template(spec_json=spec_json, theme=theme, plan=plan, assets={})

    assert "THANK YOU" in html
    assert "/ 08" in html, "chrome should reflect total_pages from SlidePlan"
    assert 'data-section="03"' in html
    assert ":root" in html, "theme CSS variables must be injected"
    assert ".slide" in html
    # accent rule for section 3 must be emitted
    assert '.slide[data-section="03"]::before { background: #7a4a33; }' in html
def test_render_falls_back_when_plan_missing():
    """Without a SlidePlan, render still works using spec_json embedded fields."""
    pid = uuid4()
    theme = _default_theme(pid)
    data = EndingData(title="END", en="EN", tagline="bye", signature_parts=["A"])
    spec_json = {
        "mode": "template",
        "component_type": "ending",
        "data": data.model_dump(mode="json"),
        "slide_no": 1,
        "title": "END",
        "section": "End",
        "is_cover": False,
        "is_chapter_divider": False,
        "total_pages": 1,
        "project_title": "Solo",
    }
    html = render_slide_template(spec_json=spec_json, theme=theme, plan=None, assets={})
    assert "END" in html
    assert "/ 01" in html


def test_render_raises_on_missing_component_type():
    pid = uuid4()
    theme = _default_theme(pid)
    bad_spec = {"mode": "template", "data": {}}
    with pytest.raises(ValueError, match="missing component_type"):
        render_slide_template(spec_json=bad_spec, theme=theme, plan=None)
