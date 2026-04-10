import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, Boolean, Integer, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from db.base import Base


class ReferenceCase(Base):
    __tablename__ = "reference_cases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    architect: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    building_type: Mapped[str] = mapped_column(String(100), nullable=False)
    style_tags: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list)
    feature_tags: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list)
    scale_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    gfa_sqm: Mapped[float | None] = mapped_column(nullable=True)
    year_completed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    images: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # embedding stored as JSON array (pgvector column added via migration)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ProjectReferenceSelection(Base):
    __tablename__ = "project_reference_selections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    selected_tags: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list)
    selection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
