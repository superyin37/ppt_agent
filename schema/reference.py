from pydantic import Field
from typing import Optional
from uuid import UUID
from .common import BaseSchema, BuildingType


class ReferenceCase(BaseSchema):
    id: UUID
    title: str
    architect: Optional[str] = None
    location: Optional[str] = None
    country: Optional[str] = None
    building_type: BuildingType
    style_tags: list[str] = []
    feature_tags: list[str] = []
    scale_category: Optional[str] = None
    gfa_sqm: Optional[float] = None
    year_completed: Optional[int] = None
    images: list[dict] = []
    summary: Optional[str] = None


class RecommendRequest(BaseSchema):
    project_id: UUID
    top_k: int = Field(default=8, ge=3, le=20)
    style_filter: list[str] = []
    feature_filter: list[str] = []


class RecommendResponse(BaseSchema):
    cases: list[ReferenceCase]
    recommendation_reason: str


class SelectionInput(BaseSchema):
    case_id: UUID
    selected_tags: list[str] = Field(..., min_length=1)
    selection_reason: Optional[str] = None


class SelectionBatchInput(BaseSchema):
    project_id: UUID
    selections: list[SelectionInput] = Field(..., min_length=1, max_length=5)


class PreferenceSummary(BaseSchema):
    dominant_styles: list[str]
    dominant_features: list[str]
    narrative_hint: str
