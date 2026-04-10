from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field

from .common import BaseSchema


class LocalMaterialPackageIngestRequest(BaseSchema):
    local_path: str = Field(..., description="Local directory path for a material package")


class MaterialPackageRead(BaseSchema):
    id: UUID
    project_id: UUID
    version: int
    status: str
    source_hash: Optional[str] = None
    manifest_json: Optional[dict] = None
    summary_json: Optional[dict] = None
    created_from: Optional[dict] = None
    created_at: datetime
    updated_at: datetime


class MaterialItemRead(BaseSchema):
    id: UUID
    package_id: UUID
    logical_key: str
    kind: str
    format: str
    title: Optional[str] = None
    source_path: Optional[str] = None
    preview_url: Optional[str] = None
    content_url: Optional[str] = None
    text_content: Optional[str] = None
    structured_data: Optional[dict] = None
    metadata_json: Optional[dict] = None
    created_at: datetime


class SlideMaterialBindingRead(BaseSchema):
    id: UUID
    project_id: UUID
    package_id: UUID
    outline_id: Optional[UUID] = None
    slide_id: Optional[UUID] = None
    slide_no: int
    slot_id: str
    version: int
    status: str
    must_use_item_ids: Optional[list] = None
    optional_item_ids: Optional[list] = None
    derived_asset_ids: Optional[list] = None
    evidence_snippets: Optional[list] = None
    coverage_score: Optional[float] = None
    missing_requirements: Optional[list] = None
    binding_reason: Optional[str] = None
    created_at: datetime
