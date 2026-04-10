from datetime import datetime
from uuid import UUID, uuid4
from pydantic import BaseModel, Field
from enum import Enum


class BaseSchema(BaseModel):
    model_config = {"from_attributes": True}


class ProjectStatus(str, Enum):
    INIT = "INIT"
    INTAKE_IN_PROGRESS = "INTAKE_IN_PROGRESS"
    INTAKE_CONFIRMED = "INTAKE_CONFIRMED"
    REFERENCE_SELECTION = "REFERENCE_SELECTION"
    ASSET_GENERATING = "ASSET_GENERATING"
    MATERIAL_READY = "MATERIAL_READY"
    OUTLINE_READY = "OUTLINE_READY"
    BINDING = "BINDING"
    SLIDE_PLANNING = "SLIDE_PLANNING"
    RENDERING = "RENDERING"
    REVIEWING = "REVIEWING"
    READY_FOR_EXPORT = "READY_FOR_EXPORT"
    EXPORTED = "EXPORTED"
    FAILED = "FAILED"


class SlideStatus(str, Enum):
    PENDING = "pending"
    SPEC_READY = "spec_ready"
    RENDERED = "rendered"
    REVIEW_PENDING = "review_pending"
    REVIEW_PASSED = "review_passed"
    REPAIR_NEEDED = "repair_needed"
    REPAIR_IN_PROGRESS = "repair_in_progress"
    READY = "ready"
    FAILED = "failed"


class AssetType(str, Enum):
    IMAGE = "image"
    CHART = "chart"
    MAP = "map"
    CASE_CARD = "case_card"
    CASE_COMPARISON = "case_comparison"
    TEXT_SUMMARY = "text_summary"
    KPI_TABLE = "kpi_table"
    OUTLINE = "outline"
    DOCUMENT = "document"


class ReviewSeverity(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    PASS = "PASS"


class ReviewDecision(str, Enum):
    PASS = "pass"
    REPAIR_REQUIRED = "repair_required"
    ESCALATE_HUMAN = "escalate_human"


class BuildingType(str, Enum):
    MUSEUM = "museum"
    OFFICE = "office"
    RESIDENTIAL = "residential"
    MIXED = "mixed"
    HOTEL = "hotel"
    COMMERCIAL = "commercial"
    CULTURAL = "cultural"
    EDUCATION = "education"


class LayoutTemplate(str, Enum):
    COVER_HERO = "cover-hero"
    OVERVIEW_KPI = "overview-kpi"
    MAP_LEFT_INSIGHT_RIGHT = "map-left-insight-right"
    TWO_CASE_COMPARE = "two-case-compare"
    GALLERY_QUAD = "gallery-quad"
    STRATEGY_DIAGRAM = "strategy-diagram"
    CHAPTER_DIVIDER = "chapter-divider"
    CHART_MAIN_TEXT_SIDE = "chart-main-text-side"
    MATRIX_SUMMARY = "matrix-summary"
