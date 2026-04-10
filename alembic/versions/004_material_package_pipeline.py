"""Add material package pipeline tables and columns

Revision ID: 004
Revises: 003
Create Date: 2026-04-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "material_packages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="ready"),
        sa.Column("source_hash", sa.String(length=128), nullable=True),
        sa.Column("manifest_json", JSONB, nullable=True),
        sa.Column("summary_json", JSONB, nullable=True),
        sa.Column("created_from", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("ix_material_packages_project_id", "material_packages", ["project_id"])
    op.create_index("uq_material_packages_project_version", "material_packages", ["project_id", "version"], unique=True)
    op.execute("CREATE TRIGGER trg_material_packages_updated_at BEFORE UPDATE ON material_packages FOR EACH ROW EXECUTE FUNCTION update_updated_at()")

    op.create_table(
        "material_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("package_id", UUID(as_uuid=True), nullable=False),
        sa.Column("logical_key", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("format", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("source_path", sa.Text(), nullable=True),
        sa.Column("preview_url", sa.String(length=1000), nullable=True),
        sa.Column("content_url", sa.String(length=1000), nullable=True),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("structured_data", JSONB, nullable=True),
        sa.Column("tags", JSONB, nullable=True),
        sa.Column("source_hash", sa.String(length=128), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["package_id"], ["material_packages.id"]),
    )
    op.create_index("ix_material_items_package_id", "material_items", ["package_id"])
    op.create_index("ix_material_items_logical_key", "material_items", ["logical_key"])
    op.execute("CREATE TRIGGER trg_material_items_updated_at BEFORE UPDATE ON material_items FOR EACH ROW EXECUTE FUNCTION update_updated_at()")

    op.create_table(
        "slide_material_bindings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("package_id", UUID(as_uuid=True), nullable=False),
        sa.Column("outline_id", UUID(as_uuid=True), nullable=True),
        sa.Column("slide_id", UUID(as_uuid=True), nullable=True),
        sa.Column("slide_no", sa.Integer(), nullable=False),
        sa.Column("slot_id", sa.String(length=100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="ready"),
        sa.Column("must_use_item_ids", JSONB, nullable=True),
        sa.Column("optional_item_ids", JSONB, nullable=True),
        sa.Column("derived_asset_ids", JSONB, nullable=True),
        sa.Column("evidence_snippets", JSONB, nullable=True),
        sa.Column("coverage_score", sa.Float(), nullable=True),
        sa.Column("missing_requirements", JSONB, nullable=True),
        sa.Column("binding_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["package_id"], ["material_packages.id"]),
        sa.ForeignKeyConstraint(["outline_id"], ["outlines.id"]),
        sa.ForeignKeyConstraint(["slide_id"], ["slides.id"]),
    )
    op.create_index("ix_slide_material_bindings_project_package", "slide_material_bindings", ["project_id", "package_id"])
    op.create_index("ix_slide_material_bindings_slide_no", "slide_material_bindings", ["project_id", "slide_no"])
    op.execute("CREATE TRIGGER trg_slide_material_bindings_updated_at BEFORE UPDATE ON slide_material_bindings FOR EACH ROW EXECUTE FUNCTION update_updated_at()")

    op.add_column("assets", sa.Column("package_id", UUID(as_uuid=True), nullable=True))
    op.add_column("assets", sa.Column("source_item_id", UUID(as_uuid=True), nullable=True))
    op.add_column("assets", sa.Column("logical_key", sa.String(length=255), nullable=True))
    op.add_column("assets", sa.Column("variant", sa.String(length=50), nullable=True))
    op.add_column("assets", sa.Column("render_role", sa.String(length=100), nullable=True))
    op.add_column("assets", sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.create_index("ix_assets_package_id", "assets", ["package_id"])
    op.create_index("ix_assets_source_item_id", "assets", ["source_item_id"])
    op.create_index("ix_assets_logical_key", "assets", ["logical_key"])

    op.add_column("brief_docs", sa.Column("package_id", UUID(as_uuid=True), nullable=True))
    op.add_column("brief_docs", sa.Column("material_summary_json", JSONB, nullable=True))
    op.add_column("brief_docs", sa.Column("evidence_keys_json", JSONB, nullable=True))
    op.create_index("ix_brief_docs_package_id", "brief_docs", ["package_id"])

    op.add_column("outlines", sa.Column("package_id", UUID(as_uuid=True), nullable=True))
    op.add_column("outlines", sa.Column("coverage_json", JSONB, nullable=True))
    op.add_column("outlines", sa.Column("slot_binding_hints_json", JSONB, nullable=True))
    op.create_index("ix_outlines_package_id", "outlines", ["package_id"])

    op.add_column("slides", sa.Column("package_id", UUID(as_uuid=True), nullable=True))
    op.add_column("slides", sa.Column("binding_id", UUID(as_uuid=True), nullable=True))
    op.add_column("slides", sa.Column("source_refs_json", JSONB, nullable=True))
    op.add_column("slides", sa.Column("evidence_refs_json", JSONB, nullable=True))
    op.create_index("ix_slides_package_id", "slides", ["package_id"])
    op.create_index("ix_slides_binding_id", "slides", ["binding_id"])


def downgrade() -> None:
    op.drop_index("ix_slides_binding_id", table_name="slides")
    op.drop_index("ix_slides_package_id", table_name="slides")
    op.drop_column("slides", "evidence_refs_json")
    op.drop_column("slides", "source_refs_json")
    op.drop_column("slides", "binding_id")
    op.drop_column("slides", "package_id")

    op.drop_index("ix_outlines_package_id", table_name="outlines")
    op.drop_column("outlines", "slot_binding_hints_json")
    op.drop_column("outlines", "coverage_json")
    op.drop_column("outlines", "package_id")

    op.drop_index("ix_brief_docs_package_id", table_name="brief_docs")
    op.drop_column("brief_docs", "evidence_keys_json")
    op.drop_column("brief_docs", "material_summary_json")
    op.drop_column("brief_docs", "package_id")

    op.drop_index("ix_assets_logical_key", table_name="assets")
    op.drop_index("ix_assets_source_item_id", table_name="assets")
    op.drop_index("ix_assets_package_id", table_name="assets")
    op.drop_column("assets", "is_primary")
    op.drop_column("assets", "render_role")
    op.drop_column("assets", "variant")
    op.drop_column("assets", "logical_key")
    op.drop_column("assets", "source_item_id")
    op.drop_column("assets", "package_id")

    op.drop_table("slide_material_bindings")
    op.drop_table("material_items")
    op.drop_table("material_packages")
