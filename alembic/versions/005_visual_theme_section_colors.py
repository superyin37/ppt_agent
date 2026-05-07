"""Add VisualTheme template metadata columns

Revision ID: 005
Revises: 004
Create Date: 2026-05-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("visual_themes", sa.Column("section_colors_json", sa.Text(), nullable=True))
    op.add_column(
        "visual_themes",
        sa.Column(
            "template_pack",
            sa.String(length=64),
            nullable=False,
            server_default="minimalist_architecture",
        ),
    )


def downgrade() -> None:
    op.drop_column("visual_themes", "template_pack")
    op.drop_column("visual_themes", "section_colors_json")
