from datetime import datetime
from typing import Optional, Any
from uuid import UUID

from .common import BaseSchema, LayoutTemplate, SlideStatus


class BlockContent(BaseSchema):
    block_id: str
    block_type: str
    content: Any
    position: Optional[dict] = None
    style_overrides: dict = {}
    source_refs: list[str] = []
    evidence_refs: list[str] = []


class SlideConstraints(BaseSchema):
    max_text_chars: int = 200
    max_bullet_points: int = 5
    min_image_count: int = 0
    max_image_count: int = 4


class StyleTokens(BaseSchema):
    primary_color: str = "#1a1a2e"
    accent_color: str = "#e94560"
    background_color: str = "#ffffff"
    font_heading: str = "PingFang SC"
    font_body: str = "PingFang SC"
    font_size_heading: str = "36px"
    font_size_body: str = "18px"


class SlideSpec(BaseSchema):
    slide_id: Optional[str] = None
    project_id: UUID
    slide_no: int
    section: str
    title: str
    purpose: str
    key_message: str
    layout_template: LayoutTemplate
    blocks: list[BlockContent] = []
    constraints: SlideConstraints = SlideConstraints()
    style_tokens: StyleTokens = StyleTokens()
    review_status: str = "pending"
    asset_refs: list[str] = []


class SlideRead(BaseSchema):
    id: UUID
    project_id: UUID
    slide_no: int
    section: Optional[str] = None
    title: Optional[str] = None
    layout_template: Optional[str] = None
    status: SlideStatus
    binding_id: Optional[UUID] = None
    screenshot_url: Optional[str] = None
    repair_count: int
    spec_json: dict
    source_refs_json: Optional[list] = None
    evidence_refs_json: Optional[list] = None
    created_at: datetime
    updated_at: datetime
