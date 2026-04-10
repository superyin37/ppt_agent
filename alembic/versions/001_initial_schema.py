"""Initial schema with pgvector extension

Revision ID: 001
Revises:
Create Date: 2026-03-20
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # updated_at trigger function
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    # ── projects ──────────────────────────────────────────────
    op.create_table("projects",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="INIT"),
        sa.Column("current_phase", sa.String(50)),
        sa.Column("error_message", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_projects_status", "projects", ["status"])
    op.execute("CREATE TRIGGER trg_projects_updated_at BEFORE UPDATE ON projects FOR EACH ROW EXECUTE FUNCTION update_updated_at()")

    # ── project_briefs ────────────────────────────────────────
    op.create_table("project_briefs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("building_type", sa.String(100)),
        sa.Column("client_name", sa.String(255)),
        sa.Column("style_preferences", JSONB, server_default=sa.text("'[]'")),
        sa.Column("special_requirements", sa.Text),
        sa.Column("gross_floor_area", sa.Numeric(12, 2)),
        sa.Column("site_area", sa.Numeric(12, 2)),
        sa.Column("far", sa.Numeric(6, 3)),
        sa.Column("site_address", sa.Text),
        sa.Column("province", sa.String(100)),
        sa.Column("city", sa.String(100)),
        sa.Column("district", sa.String(100)),
        sa.Column("raw_input", sa.Text),
        sa.Column("missing_fields", JSONB, server_default=sa.text("'[]'")),
        sa.Column("conversation_history", JSONB, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("idx_project_briefs_project_id", "project_briefs", ["project_id"])
    op.create_index("idx_project_briefs_latest", "project_briefs", ["project_id", "version"], unique=True)
    op.execute("CREATE TRIGGER trg_project_briefs_updated_at BEFORE UPDATE ON project_briefs FOR EACH ROW EXECUTE FUNCTION update_updated_at()")

    # ── site_locations ────────────────────────────────────────
    op.create_table("site_locations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("longitude", sa.Numeric(11, 7), nullable=False),
        sa.Column("latitude", sa.Numeric(10, 7), nullable=False),
        sa.Column("poi_name", sa.String(255)),
        sa.Column("address_resolved", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("idx_site_locations_project_id", "site_locations", ["project_id"])

    # ── site_polygons ─────────────────────────────────────────
    op.create_table("site_polygons",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("geojson", JSONB, nullable=False),
        sa.Column("area_calculated", sa.Numeric(12, 2)),
        sa.Column("perimeter", sa.Numeric(10, 2)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("idx_site_polygons_project_id", "site_polygons", ["project_id"])

    # ── reference_cases ───────────────────────────────────────
    op.create_table("reference_cases",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("architect", sa.String(255)),
        sa.Column("location", sa.String(255)),
        sa.Column("country", sa.String(100)),
        sa.Column("building_type", sa.String(100), nullable=False),
        sa.Column("style_tags", JSONB, server_default=sa.text("'[]'")),
        sa.Column("feature_tags", JSONB, server_default=sa.text("'[]'")),
        sa.Column("scale_category", sa.String(50)),
        sa.Column("gfa_sqm", sa.Numeric(12, 2)),
        sa.Column("year_completed", sa.Integer),
        sa.Column("images", JSONB, server_default=sa.text("'[]'")),
        sa.Column("summary", sa.Text),
        sa.Column("detail_url", sa.String(1000)),
        sa.Column("source", sa.String(255)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    # Add vector column using raw SQL (pgvector type not in standard SA)
    op.execute("ALTER TABLE reference_cases ADD COLUMN embedding vector(1536)")
    op.create_index("idx_reference_cases_building_type", "reference_cases", ["building_type"])
    op.execute("CREATE INDEX idx_reference_cases_embedding ON reference_cases USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10)")
    op.execute("CREATE TRIGGER trg_reference_cases_updated_at BEFORE UPDATE ON reference_cases FOR EACH ROW EXECUTE FUNCTION update_updated_at()")

    # ── project_reference_selections ─────────────────────────
    op.create_table("project_reference_selections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", UUID(as_uuid=True), nullable=False),
        sa.Column("selected_tags", JSONB, server_default=sa.text("'[]'")),
        sa.Column("selection_reason", sa.Text),
        sa.Column("rank", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["case_id"], ["reference_cases.id"]),
        sa.UniqueConstraint("project_id", "case_id"),
    )
    op.create_index("idx_ref_selections_project_id", "project_reference_selections", ["project_id"])

    # ── assets ────────────────────────────────────────────────
    op.create_table("assets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("asset_type", sa.String(100), nullable=False),
        sa.Column("subtype", sa.String(100)),
        sa.Column("title", sa.String(500)),
        sa.Column("data_json", JSONB),
        sa.Column("config_json", JSONB),
        sa.Column("image_url", sa.String(1000)),
        sa.Column("summary", sa.Text),
        sa.Column("source_info", JSONB),
        sa.Column("error_message", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("idx_assets_project_id", "assets", ["project_id"])
    op.create_index("idx_assets_type", "assets", ["project_id", "asset_type"])
    op.execute("CREATE TRIGGER trg_assets_updated_at BEFORE UPDATE ON assets FOR EACH ROW EXECUTE FUNCTION update_updated_at()")

    # ── outlines ──────────────────────────────────────────────
    op.create_table("outlines",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("deck_title", sa.String(500)),
        sa.Column("theme", sa.String(100)),
        sa.Column("total_pages", sa.Integer),
        sa.Column("spec_json", JSONB, nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("idx_outlines_project_id", "outlines", ["project_id"])
    op.execute("CREATE TRIGGER trg_outlines_updated_at BEFORE UPDATE ON outlines FOR EACH ROW EXECUTE FUNCTION update_updated_at()")

    # ── slides ────────────────────────────────────────────────
    op.create_table("slides",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("outline_id", UUID(as_uuid=True)),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("slide_no", sa.Integer, nullable=False),
        sa.Column("section", sa.String(255)),
        sa.Column("title", sa.String(500)),
        sa.Column("purpose", sa.Text),
        sa.Column("key_message", sa.Text),
        sa.Column("layout_template", sa.String(100)),
        sa.Column("spec_json", JSONB, nullable=False),
        sa.Column("html_content", sa.Text),
        sa.Column("screenshot_url", sa.String(1000)),
        sa.Column("repair_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["outline_id"], ["outlines.id"]),
    )
    op.create_index("idx_slides_project_id", "slides", ["project_id"])
    op.create_index("idx_slides_outline_id", "slides", ["outline_id"])
    op.create_index("idx_slides_slide_no", "slides", ["project_id", "slide_no"])
    op.execute("CREATE TRIGGER trg_slides_updated_at BEFORE UPDATE ON slides FOR EACH ROW EXECUTE FUNCTION update_updated_at()")

    # ── reviews ───────────────────────────────────────────────
    op.create_table("reviews",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=False),
        sa.Column("target_id", UUID(as_uuid=True), nullable=False),
        sa.Column("review_layer", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(10)),
        sa.Column("final_decision", sa.String(50)),
        sa.Column("issues_json", JSONB, server_default=sa.text("'[]'")),
        sa.Column("repair_plan", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("idx_reviews_target", "reviews", ["target_type", "target_id"])
    op.create_index("idx_reviews_project_id", "reviews", ["project_id"])

    # ── jobs ──────────────────────────────────────────────────
    op.create_table("jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("job_type", sa.String(100), nullable=False),
        sa.Column("celery_task_id", sa.String(255)),
        sa.Column("status", sa.String(50), nullable=False, server_default="queued"),
        sa.Column("input_json", JSONB),
        sa.Column("output_json", JSONB),
        sa.Column("error_message", sa.Text),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("idx_jobs_project_id", "jobs", ["project_id"])
    op.create_index("idx_jobs_celery_task_id", "jobs", ["celery_task_id"])

    # ── exports ───────────────────────────────────────────────
    op.create_table("exports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("export_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("file_url", sa.String(1000)),
        sa.Column("file_size_bytes", sa.BigInteger),
        sa.Column("page_count", sa.Integer),
        sa.Column("error_message", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("idx_exports_project_id", "exports", ["project_id"])


def downgrade() -> None:
    for table in [
        "exports", "jobs", "reviews", "slides", "outlines", "assets",
        "project_reference_selections", "reference_cases",
        "site_polygons", "site_locations", "project_briefs", "projects",
    ]:
        op.drop_table(table)
    op.execute("DROP FUNCTION IF EXISTS update_updated_at() CASCADE")
    op.execute("DROP EXTENSION IF EXISTS vector")
