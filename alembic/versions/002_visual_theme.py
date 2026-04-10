"""Add visual_themes table and update slides table

Revision ID: 002
Revises: 001
Create Date: 2026-03-21
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 新增 visual_themes 表
    op.create_table(
        "visual_themes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("theme_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_visual_themes_project_id", "visual_themes", ["project_id"])
    op.create_foreign_key(
        "fk_visual_themes_project_id",
        "visual_themes", "projects",
        ["project_id"], ["id"],
        ondelete="CASCADE",
    )

    # slides 表：废弃 layout_template 列（保留为 nullable 以向后兼容，后续版本可 DROP）
    op.alter_column("slides", "layout_template", nullable=True)

    # projects 表：添加 visual_theme_id 外键
    op.add_column("projects", sa.Column("visual_theme_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_projects_visual_theme_id",
        "projects", "visual_themes",
        ["visual_theme_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_projects_visual_theme_id", "projects", type_="foreignkey")
    op.drop_column("projects", "visual_theme_id")
    op.drop_constraint("fk_visual_themes_project_id", "visual_themes", type_="foreignkey")
    op.drop_index("ix_visual_themes_project_id", "visual_themes")
    op.drop_table("visual_themes")
