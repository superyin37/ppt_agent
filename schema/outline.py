from datetime import datetime
from typing import Optional
from uuid import UUID

from .common import BaseSchema, LayoutTemplate


class OutlineSlideEntry(BaseSchema):
    slot_id: str = ""
    slide_no: int
    section: str
    title: str
    purpose: str
    key_message: str
    required_assets: list[str] = []
    required_input_keys: list[str] = []
    optional_input_keys: list[str] = []
    coverage_status: str = "unknown"
    recommended_binding_scope: list[str] = []
    recommended_template: Optional[LayoutTemplate] = None
    layout_hint: str = ""
    estimated_content_density: str = "medium"
    is_cover: bool = False
    is_chapter_divider: bool = False


class OutlineSpec(BaseSchema):
    outline_id: Optional[str] = None
    project_id: UUID
    deck_title: str
    theme: str
    total_pages: int
    sections: list[str]
    slides: list[OutlineSlideEntry]


class OutlineRead(BaseSchema):
    id: UUID
    project_id: UUID
    version: int
    status: str
    deck_title: Optional[str] = None
    theme: Optional[str] = None
    total_pages: Optional[int] = None
    spec_json: dict
    coverage_json: Optional[dict] = None
    slot_binding_hints_json: Optional[dict] = None
    confirmed_at: Optional[datetime] = None
    created_at: datetime
