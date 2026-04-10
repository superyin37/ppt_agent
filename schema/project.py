from pydantic import Field, field_validator
from typing import Optional
from uuid import UUID
from datetime import datetime
from .common import BaseSchema, ProjectStatus, BuildingType


class ProjectCreate(BaseSchema):
    name: str = Field(..., min_length=1, max_length=255)


class ProjectRead(BaseSchema):
    id: UUID
    name: str
    status: ProjectStatus
    current_phase: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ProjectBriefInput(BaseSchema):
    raw_text: str = Field(..., description="用户原始输入文本")
    attachments: list[str] = Field(default=[], description="附件 URL 列表")


class ProjectBriefData(BaseSchema):
    building_type: Optional[BuildingType] = None
    client_name: Optional[str] = None
    style_preferences: list[str] = Field(default=[])
    special_requirements: Optional[str] = None

    gross_floor_area: Optional[float] = Field(None, gt=0, description="建筑面积（㎡）")
    site_area: Optional[float] = Field(None, gt=0, description="用地面积（㎡）")
    far: Optional[float] = Field(None, gt=0, description="容积率")

    site_address: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None

    missing_fields: list[str] = Field(default=[], description="当前缺失的必填字段")
    is_complete: bool = False

    @field_validator("far", mode="before")
    @classmethod
    def compute_far_if_missing(cls, v, info):
        if v is None:
            gfa = info.data.get("gross_floor_area")
            site = info.data.get("site_area")
            if gfa and site and site > 0:
                return round(gfa / site, 3)
        return v


class ProjectBriefRead(ProjectBriefData):
    id: UUID
    project_id: UUID
    version: int
    status: str
    created_at: datetime
    updated_at: datetime


class IntakeFollowUp(BaseSchema):
    question: str = Field(..., description="追问文本")
    missing_fields: list[str] = Field(..., description="本次追问针对的缺失字段")
    is_final_confirmation: bool = False
