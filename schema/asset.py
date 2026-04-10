from pydantic import Field
from typing import Optional
from uuid import UUID
from datetime import datetime
from .common import BaseSchema, AssetType


class AssetRead(BaseSchema):
    id: UUID
    project_id: UUID
    version: int
    status: str
    asset_type: AssetType
    subtype: Optional[str] = None
    title: Optional[str] = None
    data_json: Optional[dict] = None
    config_json: Optional[dict] = None
    image_url: Optional[str] = None
    summary: Optional[str] = None
    package_id: Optional[UUID] = None
    source_item_id: Optional[UUID] = None
    logical_key: Optional[str] = None
    variant: Optional[str] = None
    render_role: Optional[str] = None
    created_at: datetime


class ChartConfig(BaseSchema):
    chart_type: str              # bar / line / pie / radar / scatter
    title: str
    x_label: Optional[str] = None
    y_label: Optional[str] = None
    data: list[dict]
    color_scheme: str = "primary"
    width_px: int = 800
    height_px: int = 500


class MapAnnotationConfig(BaseSchema):
    center_lng: float
    center_lat: float
    zoom: int = 14
    annotations: list[dict]
    radius_meters: Optional[int] = None
