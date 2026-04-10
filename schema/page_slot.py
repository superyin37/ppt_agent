"""
Blueprint slot schemas.

This module keeps the existing blueprint authoring style compatible while
exposing a structured requirement model for the new material-package pipeline.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class GenerationMethod(str, Enum):
    LLM_TEXT = "llm_text"
    CHART = "chart"
    NANOBANANA = "nanobanana"
    ASSET_REF = "asset_ref"
    WEB_SEARCH = "web_search"
    COMPOSITE = "composite"


class InputRequirement(BaseModel):
    logical_key_pattern: str
    required: bool = True
    consume_as: str = "auto"
    min_count: int = 1
    max_count: int = 1
    preferred_variant: Optional[str] = None
    fallback_policy: str = "allow-empty"


def _to_requirement(value: str | dict | InputRequirement) -> InputRequirement:
    if isinstance(value, InputRequirement):
        return value
    if isinstance(value, str):
        return InputRequirement(logical_key_pattern=value)
    if isinstance(value, dict):
        return InputRequirement(**value)
    raise TypeError(f"Unsupported input requirement: {type(value)!r}")


class PageSlot(BaseModel):
    slot_id: str
    title: str
    chapter: str
    page_count_min: int = 1
    page_count_max: int = 1
    page_count_hint: str = ""
    content_task: str
    required_inputs: list[InputRequirement] = Field(default_factory=list)
    generation_methods: list[GenerationMethod] = Field(default_factory=lambda: [GenerationMethod.LLM_TEXT])
    layout_hint: str = ""

    is_chapter_divider: bool = False
    is_cover: bool = False

    @field_validator("required_inputs", mode="before")
    @classmethod
    def _normalize_required_inputs(cls, value):
        if value is None:
            return []
        return [_to_requirement(item) for item in value]

    @property
    def required_input_keys(self) -> list[str]:
        return [req.logical_key_pattern for req in self.required_inputs]


class PageSlotGroup(BaseModel):
    group_id: str
    slot_template: PageSlot
    repeat_count_min: int = 1
    repeat_count_max: int = 5
    repeat_hint: str = ""


class SlotAssignment(BaseModel):
    slot_id: str
    slide_no: int
    section: str
    title: str
    content_directive: str
    asset_keys: list[str] = Field(default_factory=list)
    layout_hint: str = ""
    is_cover: bool = False
    is_chapter_divider: bool = False
    estimated_content_density: str = "medium"


class SlotAssignmentList(BaseModel):
    project_id: UUID
    deck_title: str
    total_pages: int
    assignments: list[SlotAssignment]
    visual_theme_id: Optional[UUID] = None


def normalize_slot_id(slot_id: str) -> str:
    """Map grouped slot ids like `reference-case-2` to template slot id."""
    return re.sub(r"-\d+$", "", slot_id)
