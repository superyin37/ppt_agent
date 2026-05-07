"""SlidePlan — runtime context for template-mode rendering.

Built once per project from Outline + ProjectBrief by `agent.slide_plan`.
Replaces all hardcoded "40 / 4-章节 / page_ranges" assumptions in templates.

Templates receive `total_pages`, `section_no`, `section_en`, etc., from this
plan via `render.engine.render_via_jinja`'s context dict.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from schema.slide_data import ComponentType


class SlidePlanSection(BaseModel):
    """One chapter of the deck."""

    no: int = Field(ge=1, le=99)            # 1-based section index, 2-digit display
    title: str                              # 中文章节名，如 "背景研究"
    en: str = ""                            # 英文翻译，如 "Background Research"
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    accent_color: Optional[str] = None      # hex, e.g. "#2b3b63"; populated from VisualTheme.section_colors


class SlidePlanEntry(BaseModel):
    """One slide's plan-level metadata.

    Does NOT include the actual SlideData payload — that is generated per-slide
    by Composer in template mode and lives on Slide.spec_json. This entry tells
    the renderer which template to load and how to position the slide.
    """

    slide_no: int = Field(ge=1)
    section_no: int = Field(ge=1, le=99)
    component_type: Optional[ComponentType] = None  # None = legacy html_free / layout_spec
    slot_id: str
    is_cover: bool = False
    is_chapter_divider: bool = False


class SlidePlan(BaseModel):
    project_id: UUID
    project_title: str
    total_pages: int = Field(ge=1)
    sections: list[SlidePlanSection] = Field(default_factory=list)
    slides: list[SlidePlanEntry] = Field(default_factory=list)

    def section_for(self, slide_no: int) -> Optional[SlidePlanSection]:
        for s in self.sections:
            if s.page_start <= slide_no <= s.page_end:
                return s
        return None

    def entry_for(self, slide_no: int) -> Optional[SlidePlanEntry]:
        for e in self.slides:
            if e.slide_no == slide_no:
                return e
        return None
