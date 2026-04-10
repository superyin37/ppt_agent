"""Add brief_docs table

Revision ID: 003
Revises: 002
Create Date: 2026-03-21
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "brief_docs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("outline_json", JSONB, nullable=False),
        sa.Column("slot_assignments_json", JSONB, nullable=True),
        sa.Column("narrative_summary", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_brief_docs_project_id", "brief_docs", ["project_id"])
    op.create_foreign_key(
        "fk_brief_docs_project_id",
        "brief_docs", "projects",
        ["project_id"], ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_brief_docs_project_id", "brief_docs", type_="foreignkey")
    op.drop_index("ix_brief_docs_project_id", "brief_docs")
    op.drop_table("brief_docs")
