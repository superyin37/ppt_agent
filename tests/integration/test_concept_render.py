"""Integration test for the concept render stage (ADR-005).

Covers:
- All 9 assets produced when runninghub succeeds (3 proposals × 3 views).
- All 9 fall back to placeholders when runninghub is unreachable.
- Persisted assets have the expected logical_key pattern `concept.{N}.{view}`.

RunningHubClient is patched at import site so no HTTP traffic occurs.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from agent.concept_render import run_concept_render
from db.models.asset import Asset
from db.models.brief_doc import BriefDoc
from db.models.material_item import MaterialItem
from db.models.material_package import MaterialPackage
from db.models.outline import Outline
from db.models.project import Project, ProjectBrief
from db.session import SessionLocal
from schema.common import ProjectStatus
from tool.image_gen.runninghub import RunningHubError, RunningHubResult


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def project_with_outline(db, tmp_path):
    project = Project(name="Concept Render Test", status=ProjectStatus.INIT.value)
    db.add(project)
    db.flush()

    brief = ProjectBrief(
        project_id=project.id,
        version=1,
        status="confirmed",
        building_type="cultural",
        client_name="Test City",
        style_preferences=["modern", "minimal"],
        city="Suzhou",
        missing_fields=[],
    )
    db.add(brief)

    brief_doc = BriefDoc(
        project_id=project.id,
        version=1,
        outline_json={"positioning_statement": "riverside cultural landmark"},
    )
    db.add(brief_doc)

    package = MaterialPackage(
        project_id=project.id,
        version=1,
        source="local",
        summary_json={},
        manifest_json={},
    )
    db.add(package)
    db.flush()

    ref_img = tmp_path / "site_boundary.png"
    ref_img.write_bytes(b"\x89PNG\r\n\x1a\nfake-site")
    site_item = MaterialItem(
        id=uuid4(),
        package_id=package.id,
        logical_key="site.boundary.image",
        kind="image",
        format="png",
        title="场地四至分析",
        source_path=str(ref_img),
    )
    db.add(site_item)

    concept_proposals = [
        {
            "index": i,
            "name": f"方案{i}",
            "design_idea": f"第{i}个设计理念",
            "narrative": f"方案{i}的完整描述文本，体现空间和形态。",
            "design_keywords": ["轻盈", "通透"],
            "massing_hint": "中庭围合体量",
            "material_hint": "浅色石材+玻璃",
            "mood_hint": "清晨柔光",
        }
        for i in (1, 2, 3)
    ]
    outline = Outline(
        project_id=project.id,
        version=1,
        status="confirmed",
        total_pages=40,
        deck_title="Test Deck",
        spec_json={"slides": [], "concept_proposals": concept_proposals},
    )
    db.add(outline)
    db.commit()
    return project


# ── Helpers ────────────────────────────────────────────────────────────────────


def _concept_assets(db, project_id):
    return (
        db.query(Asset)
        .filter(Asset.project_id == project_id)
        .filter(Asset.logical_key.like("concept.%"))
        .all()
    )


def _make_fake_client(tmp_path: Path, *, fail: bool = False):
    """Build a MagicMock that mimics RunningHubClient's async methods."""
    client = MagicMock()
    client.aclose = AsyncMock(return_value=None)

    if fail:
        client.upload_image = AsyncMock(side_effect=RunningHubError("offline"))
        client.run_workflow = AsyncMock(side_effect=RunningHubError("offline"))
        return client

    async def fake_upload(path):
        return f"uploaded-{Path(path).name}"

    async def fake_run(node_overrides, dest_path, **_kwargs):
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"\x89PNG\r\n\x1a\nrendered")
        return RunningHubResult(
            task_id="task-mock",
            file_url=f"https://cdn.mock/{dest.name}",
            file_type="png",
            local_path=dest,
        )

    client.upload_image = AsyncMock(side_effect=fake_upload)
    client.run_workflow = AsyncMock(side_effect=fake_run)
    return client


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_concept_render_success_persists_nine_assets(db, project_with_outline, tmp_path, monkeypatch):
    asset_root = tmp_path / "assets"
    monkeypatch.setattr("agent.concept_render.settings.running_hub_key", "fake")
    monkeypatch.setattr("agent.concept_render.settings.running_hub_workflow_id", "wf-1")
    monkeypatch.setattr("agent.concept_render.settings.running_hub_asset_dir", str(asset_root))

    fake = _make_fake_client(tmp_path)
    with patch("agent.concept_render.RunningHubClient", return_value=fake):
        stats = await run_concept_render(project_with_outline.id, db)

    assert stats.total == 9
    assert stats.generated == 9
    assert stats.placeholders == 0

    assets = _concept_assets(db, project_with_outline.id)
    assert len(assets) == 9

    keys = sorted(a.logical_key for a in assets)
    expected = sorted(
        f"concept.{i}.{v}"
        for i in (1, 2, 3)
        for v in ("aerial", "ext_perspective", "int_perspective")
    )
    assert keys == expected

    for asset in assets:
        assert asset.status == "ready"
        assert asset.source_info["source"] == "runninghub"
        assert asset.render_role in {"aerial", "ext_perspective", "int_perspective"}
        assert Path(asset.image_url).exists()


@pytest.mark.asyncio
async def test_concept_render_falls_back_to_placeholders_on_failure(
    db, project_with_outline, tmp_path, monkeypatch
):
    asset_root = tmp_path / "assets"
    monkeypatch.setattr("agent.concept_render.settings.running_hub_key", "fake")
    monkeypatch.setattr("agent.concept_render.settings.running_hub_workflow_id", "wf-1")
    monkeypatch.setattr("agent.concept_render.settings.running_hub_asset_dir", str(asset_root))

    fake = _make_fake_client(tmp_path, fail=True)
    with patch("agent.concept_render.RunningHubClient", return_value=fake):
        stats = await run_concept_render(project_with_outline.id, db)

    assert stats.total == 9
    assert stats.generated == 0
    assert stats.placeholders == 9

    assets = _concept_assets(db, project_with_outline.id)
    assert len(assets) == 9
    for asset in assets:
        assert asset.status == "fallback"
        assert asset.source_info["source"] == "placeholder"
        assert asset.config_json["generation_failed"] is True
        assert Path(asset.image_url).exists()


@pytest.mark.asyncio
async def test_concept_render_skipped_when_disabled(db, project_with_outline, monkeypatch):
    monkeypatch.setattr("agent.concept_render.settings.concept_render_enabled", False)
    stats = await run_concept_render(project_with_outline.id, db)
    assert stats.total == 0
    assert _concept_assets(db, project_with_outline.id) == []
