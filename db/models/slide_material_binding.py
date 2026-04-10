import uuid
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, func, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB

from db.base import Base


class SlideMaterialBinding(Base):
    __tablename__ = "slide_material_bindings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True)
    package_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("material_packages.id"), nullable=False, index=True)
    outline_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("outlines.id"), nullable=True)
    slide_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("slides.id"), nullable=True)
    slide_no: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    slot_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="ready")
    must_use_item_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    optional_item_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    derived_asset_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    evidence_snippets: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    coverage_score: Mapped[float | None] = mapped_column(nullable=True)
    missing_requirements: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    binding_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
