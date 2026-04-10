from pydantic import Field, model_validator
from typing import Optional
from uuid import UUID
from .common import BaseSchema


class SitePointInput(BaseSchema):
    longitude: float = Field(..., ge=-180, le=180)
    latitude: float = Field(..., ge=-90, le=90)


class SitePolygonInput(BaseSchema):
    geojson: dict = Field(..., description="GeoJSON Polygon 对象")

    @model_validator(mode="after")
    def validate_geojson_type(self):
        if self.geojson.get("type") != "Polygon":
            raise ValueError("geojson 必须为 Polygon 类型")
        return self


class SiteRead(BaseSchema):
    project_id: UUID
    longitude: Optional[float] = None
    latitude: Optional[float] = None
    address_resolved: Optional[str] = None
    geojson: Optional[dict] = None
    area_calculated: Optional[float] = None
