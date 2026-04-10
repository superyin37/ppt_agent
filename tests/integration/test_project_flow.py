"""
Integration tests — full project pipeline with mocked LLM calls.
Tests against a real PostgreSQL database (same as docker-compose).
Requires: DATABASE_URL in .env pointing to a running Postgres.

Run: pytest tests/integration/ -v
"""
import pytest
import pytest_asyncio
import asyncio
from uuid import uuid4
from unittest.mock import AsyncMock, patch, MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from config.settings import settings
from db.base import Base
from db.session import SessionLocal
from db.models.project import Project, ProjectBrief
from db.models.outline import Outline
from db.models.slide import Slide
from db.models.review import Review
from schema.common import ProjectStatus, SlideStatus, LayoutTemplate
from schema.project import ProjectBriefData
from schema.common import BuildingType


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    """Real DB session — rolls back after each test."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def project(db):
    """Create a test project."""
    p = Project(name="Test Cultural Center", status=ProjectStatus.INIT.value)
    db.add(p)
    db.flush()
    return p


@pytest.fixture
def confirmed_brief(db, project):
    """Create a confirmed project brief."""
    brief = ProjectBrief(
        project_id=project.id,
        version=1,
        status="confirmed",
        building_type="cultural",
        client_name="苏州市住建局",
        style_preferences=["modern", "minimal"],
        gross_floor_area=80000.0,
        site_area=60000.0,
        far=1.33,
        site_address="苏州市工业园区",
        province="江苏省",
        city="苏州市",
        district="工业园区",
        missing_fields=[],
    )
    db.add(brief)
    project.status = ProjectStatus.INTAKE_CONFIRMED.value
    db.flush()
    return brief


# ── Project CRUD ──────────────────────────────────────────────────────────────

def test_create_project(db):
    p = Project(name="Integration Test Project", status=ProjectStatus.INIT.value)
    db.add(p)
    db.flush()
    assert p.id is not None
    assert p.status == "INIT"


def test_project_status_transitions(db, project):
    project.status = ProjectStatus.INTAKE_IN_PROGRESS.value
    db.flush()
    assert project.status == "INTAKE_IN_PROGRESS"

    project.status = ProjectStatus.INTAKE_CONFIRMED.value
    db.flush()
    assert project.status == "INTAKE_CONFIRMED"


def test_brief_creation(db, project):
    brief = ProjectBrief(
        project_id=project.id,
        version=1,
        status="draft",
        building_type="museum",
        client_name="Test Client",
        style_preferences=["modern"],
        missing_fields=["gross_floor_area"],
    )
    db.add(brief)
    db.flush()
    assert brief.id is not None
    assert brief.style_preferences == ["modern"]
    assert brief.missing_fields == ["gross_floor_area"]


# ── Intake Agent (mocked LLM) ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_intake_agent_with_mock_llm(db, project):
    """run_intake should create/update a ProjectBrief row."""
    from agent.intake import run_intake
    from tool.input.extract_brief import ExtractBriefOutput

    mock_extract_output = ExtractBriefOutput(
        extracted=ProjectBriefData(
            building_type=BuildingType.CULTURAL,
            client_name="苏州市政府",
            style_preferences=["modern", "minimal"],
            gross_floor_area=80000.0,
            site_area=60000.0,
            far=1.33,
            site_address="苏州市工业园区",
            province="江苏省",
            city="苏州市",
            district="工业园区",
            missing_fields=[],
            is_complete=True,
        ),
        is_complete=True,
        missing_fields=[],
        follow_up="",
    )

    with patch("agent.intake.extract_project_brief", new_callable=AsyncMock,
               return_value=mock_extract_output):
        result = await run_intake(
            project_id=project.id,
            raw_text="苏州市工业园区文化馆，甲方苏州市政府，建筑面积8万㎡，用地6万㎡，现代简约风格",
            db=db,
        )

    assert result.is_complete is True
    assert result.brief.building_type == BuildingType.CULTURAL
    assert result.brief.client_name == "苏州市政府"

    # Verify DB row was written
    brief_row = db.query(ProjectBrief).filter(ProjectBrief.project_id == project.id).first()
    assert brief_row is not None
    assert brief_row.building_type == "cultural"
    assert brief_row.client_name == "苏州市政府"


# ── Reference search (no LLM needed) ─────────────────────────────────────────

def test_reference_cases_in_db(db):
    """Verify seed data is present."""
    from db.models.reference import ReferenceCase
    count = db.query(ReferenceCase).count()
    assert count >= 5, f"Expected at least 5 cases, got {count}"


def test_reference_cases_have_embeddings(db):
    """Verify embedding column is populated."""
    from db.models.reference import ReferenceCase
    from sqlalchemy import text
    result = db.execute(
        text("SELECT COUNT(*) FROM reference_cases WHERE embedding IS NOT NULL")
    ).scalar()
    assert result >= 5


@pytest.mark.asyncio
async def test_reference_search_returns_results(db):
    """Vector search should return results for a museum brief."""
    from tool.reference.search import search_cases, CaseSearchInput

    result = search_cases(CaseSearchInput(
        query_text="博物馆 现代 文化 在地性",
        building_type="museum",
        top_k=3,
    ), db)
    assert len(result.cases) > 0
    assert all(c.building_type == "museum" for c in result.cases)


@pytest.mark.asyncio
async def test_reference_search_filters_by_type(db):
    """Tag-based search should respect building_type filter."""
    from tool.reference.search import search_cases, CaseSearchInput

    result = search_cases(CaseSearchInput(
        query_text="office modern",
        building_type="office",
        top_k=5,
    ), db)
    assert all(c.building_type == "office" for c in result.cases)


# ── Outline Agent (mocked LLM) ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_outline_generation_with_mock_llm(db, project, confirmed_brief):
    """generate_outline should create an Outline DB row."""
    from agent.outline import generate_outline, _OutlineLLMOutput, _SlotAssignmentLLM

    mock_llm_output = _OutlineLLMOutput(
        deck_title="苏州文化馆建筑方案汇报",
        total_pages=3,
        assignments=[
            _SlotAssignmentLLM(
                slot_id="cover",
                slide_no=1,
                section="封面",
                title="项目概述",
                content_directive="苏州新地标文化综合体封面，展示项目标题与形象图",
                is_cover=True,
                layout_hint="full-bleed",
                estimated_content_density="low",
            ),
            _SlotAssignmentLLM(
                slot_id="toc",
                slide_no=2,
                section="目录",
                title="目录",
                content_directive="列出各章节标题与页码",
                layout_hint="split-h",
                estimated_content_density="low",
            ),
            _SlotAssignmentLLM(
                slot_id="design-strategies",
                slide_no=3,
                section="设计策略",
                title="设计策略",
                content_directive="在地文化+现代表达，三条核心策略",
                layout_hint="triptych",
                estimated_content_density="medium",
            ),
        ],
    )

    with patch("agent.outline.call_llm_with_limit", new_callable=AsyncMock,
               return_value=mock_llm_output):
        outline_orm = await generate_outline(project.id, db)

    assert outline_orm.id is not None
    assert outline_orm.deck_title == "苏州文化馆建筑方案汇报"
    assert outline_orm.total_pages == 3

    saved = db.query(Outline).filter(Outline.project_id == project.id).first()
    assert saved is not None
    assert saved.spec_json["total_pages"] == 3


@pytest.mark.asyncio
async def test_outline_generation_uses_actual_assignment_count(db, project, confirmed_brief):
    """generate_outline should trust the actual assignment list over a mismatched total_pages field."""
    from agent.outline import generate_outline, _OutlineLLMOutput, _SlotAssignmentLLM

    mock_llm_output = _OutlineLLMOutput(
        deck_title="Mismatch Deck",
        total_pages=99,
        assignments=[
            _SlotAssignmentLLM(
                slot_id="cover",
                slide_no=1,
                section="封面",
                title="封面",
                content_directive="封面说明",
                is_cover=True,
                layout_hint="full-bleed",
                estimated_content_density="low",
            ),
            _SlotAssignmentLLM(
                slot_id="toc",
                slide_no=2,
                section="目录",
                title="目录",
                content_directive="目录说明",
                layout_hint="split-h",
                estimated_content_density="low",
            ),
        ],
    )

    with patch("agent.outline.call_llm_with_limit", new_callable=AsyncMock, return_value=mock_llm_output):
        outline_orm = await generate_outline(project.id, db)

    assert outline_orm.total_pages == 2
    assert len(outline_orm.spec_json["slides"]) == 2
    assert outline_orm.spec_json["total_pages"] == 2


# ── Composer Agent (mocked LLM) ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_composer_creates_slides(db, project, confirmed_brief):
    """compose_all_slides should create Slide rows with LayoutSpec for each outline entry."""
    from agent.outline import generate_outline, _OutlineLLMOutput, _SlotAssignmentLLM
    from agent.composer import compose_all_slides, _ComposerLLMOutput, _BlockLLM, _RegionLLM

    mock_outline_llm = _OutlineLLMOutput(
        deck_title="Test Deck",
        total_pages=2,
        assignments=[
            _SlotAssignmentLLM(
                slot_id="cover", slide_no=1, section="封面", title="项目概述",
                content_directive="介绍背景，展示封面",
                layout_hint="full-bleed 封面", is_cover=True,
                estimated_content_density="low",
            ),
            _SlotAssignmentLLM(
                slot_id="toc", slide_no=2, section="指标", title="核心数据",
                content_directive="展示核心指标数据",
                layout_hint="grid 指标卡片",
                estimated_content_density="medium",
            ),
        ],
    )

    mock_llm_output = _ComposerLLMOutput(
        slide_no=1, section="封面", title="项目概述",
        is_cover=True, is_chapter_divider=False,
        primitive_type="full-bleed",
        primitive_params={
            "content_anchor": "bottom-left", "use_overlay": True,
            "overlay_direction": "bottom", "background_type": "gradient",
        },
        region_bindings=[_RegionLLM(region_id="content", blocks=[
            _BlockLLM(block_id="title", content_type="heading", content="项目概述"),
        ])],
        visual_focus="content",
    )

    # Create outline first
    with patch("agent.outline.call_llm_with_limit", new_callable=AsyncMock,
               return_value=mock_outline_llm):
        outline = await generate_outline(project.id, db)

    # Compose slides
    with patch("agent.composer.call_llm_with_limit", new_callable=AsyncMock,
               return_value=mock_llm_output):
        slides = await compose_all_slides(project.id, db)

    assert len(slides) == 2
    saved_slides = db.query(Slide).filter(Slide.project_id == project.id).all()
    assert len(saved_slides) == 2
    assert all(s.status == SlideStatus.SPEC_READY.value for s in saved_slides)
    # spec_json should be a LayoutSpec
    from schema.visual_theme import LayoutSpec
    spec = LayoutSpec.model_validate(saved_slides[0].spec_json)
    assert spec.slide_no == 1


# ── Render Engine (no LLM) ────────────────────────────────────────────────────

def test_render_engine_produces_html(db, project, confirmed_brief):
    """render_slide_html should produce valid HTML using new LayoutSpec + VisualTheme API."""
    from render.engine import render_slide_html
    from tests.helpers.theme_factory import make_default_theme
    from schema.visual_theme import (
        LayoutSpec, ContentBlock, RegionBinding,
        SplitHLayout,
    )

    theme = make_default_theme(project.id)
    spec = LayoutSpec(
        slide_no=1,
        primitive=SplitHLayout(
            primitive="split-h", left_ratio=6, right_ratio=4,
            left_content_type="image", right_content_type="text",
            divider="line", dominant_side="left",
        ),
        region_bindings=[
            RegionBinding(region_id="left", blocks=[
                ContentBlock(block_id="img", content_type="image", content=""),
            ]),
            RegionBinding(region_id="right", blocks=[
                ContentBlock(block_id="title", content_type="heading", content="苏州文化馆建筑方案"),
                ContentBlock(block_id="body", content_type="body-text", content="现代文化综合体"),
            ]),
        ],
        visual_focus="left",
        section="封面",
        title="苏州文化馆建筑方案",
    )
    html = render_slide_html(spec, theme, deck_meta={
        "deck_title": "苏州文化馆",
        "client_name": "苏州市住建局",
        "total_slides": 10,
    })
    assert "<!DOCTYPE html>" in html
    assert "苏州文化馆建筑方案" in html
    assert "苏州市住建局" in html


# ── Critic Agent (mocked LLM) ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_critic_rule_layer_no_llm(db, project, confirmed_brief):
    """Rule layer (layout_lint) runs without any LLM calls."""
    from agent.critic import review_slide
    from schema.slide import SlideSpec, BlockContent
    from schema.review import ReviewDecision

    # Well-formed spec — should pass
    spec = SlideSpec(
        project_id=project.id,
        slide_no=1,
        section="封面",
        title="项目概述",
        purpose="展示背景",
        key_message="苏州文化馆",
        layout_template=LayoutTemplate.OVERVIEW_KPI,
        blocks=[
            BlockContent(block_id="kpi_items", block_type="kpi", content=[
                {"value": "80000㎡", "label": "建筑面积"},
                {"value": "1.33", "label": "容积率"},
            ]),
        ],
    )
    brief = {"building_type": "cultural", "client_name": "苏州市住建局"}

    sem_out = MagicMock(issues=[], repair_actions=[])
    with patch("agent.critic.semantic_check", new_callable=AsyncMock, return_value=sem_out):
        _, report = await review_slide(spec, brief, layers=["rule", "semantic"])

    assert report.final_decision == ReviewDecision.PASS


@pytest.mark.asyncio
async def test_critic_detects_missing_key_message(db, project):
    """Critic should flag empty key_message."""
    from agent.critic import review_slide
    from schema.slide import SlideSpec, BlockContent
    from schema.review import ReviewDecision

    spec = SlideSpec(
        project_id=project.id,
        slide_no=2,
        section="指标",
        title="项目数据",
        purpose="展示数据",
        key_message="",   # empty — R008
        layout_template=LayoutTemplate.OVERVIEW_KPI,
        blocks=[
            BlockContent(block_id="kpi_items", block_type="kpi", content=[
                {"value": "80000", "label": "面积"},
            ]),
        ],
    )

    sem_out = MagicMock(issues=[], repair_actions=[])
    with patch("agent.critic.semantic_check", new_callable=AsyncMock, return_value=sem_out):
        _, report = await review_slide(spec, {}, layers=["rule"])

    issue_codes = [i.rule_code for i in report.issues]
    assert "KEY_MESSAGE_MISSING" in issue_codes


# ── Full pipeline smoke test ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_pipeline_smoke(db, project, confirmed_brief):
    """
    Smoke test: brief → outline → compose → render → review.
    All LLM calls are mocked. Verifies data flows correctly through all layers.
    """
    from agent.outline import generate_outline, _OutlineLLMOutput, _SlotAssignmentLLM
    from agent.composer import compose_all_slides
    from render.engine import render_slide_html
    from agent.critic import review_slide
    from schema.review import ReviewDecision

    # 1. Generate outline
    mock_outline_llm = _OutlineLLMOutput(
        deck_title="苏州文化馆方案汇报",
        total_pages=2,
        assignments=[
            _SlotAssignmentLLM(
                slot_id="cover", slide_no=1, section="封面", title="项目概述",
                content_directive="封面介绍，苏州新文化地标",
                layout_hint="full-bleed 封面", is_cover=True,
                estimated_content_density="low",
            ),
            _SlotAssignmentLLM(
                slot_id="toc", slide_no=2, section="指标", title="项目指标",
                content_directive="展示核心数据，80000㎡综合文化场馆",
                layout_hint="grid 指标卡片",
                estimated_content_density="medium",
            ),
        ],
    )

    with patch("agent.outline.call_llm_with_limit", new_callable=AsyncMock,
               return_value=mock_outline_llm):
        outline = await generate_outline(project.id, db)

    assert outline.total_pages == 2

    # 2. Compose slides — mock returns _ComposerLLMOutput
    from agent.composer import _ComposerLLMOutput, _BlockLLM, _RegionLLM

    call_count = 0
    async def mock_llm_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        slide_no = call_count
        return _ComposerLLMOutput(
            slide_no=slide_no, section="封面" if slide_no == 1 else "指标",
            title="项目概述" if slide_no == 1 else "项目指标",
            is_cover=(slide_no == 1), is_chapter_divider=False,
            primitive_type="single-column",
            primitive_params={"max_width_ratio": 0.7, "v_align": "center", "has_pull_quote": False},
            region_bindings=[_RegionLLM(region_id="content", blocks=[
                _BlockLLM(block_id="title", content_type="heading",
                          content="苏州新文化地标" if slide_no == 1 else "80000㎡综合文化场馆"),
            ])],
            visual_focus="content",
        )

    with patch("agent.composer.call_llm_with_limit", new_callable=AsyncMock,
               side_effect=mock_llm_side_effect):
        slides = await compose_all_slides(project.id, db)

    assert len(slides) == 2

    # 3. Render — use new LayoutSpec API with default theme
    from tests.helpers.theme_factory import make_default_theme
    from schema.visual_theme import (
        LayoutSpec, ContentBlock, RegionBinding, SingleColumnLayout,
    )

    default_theme = make_default_theme(project.id)
    for i, slide in enumerate(slides):
        # Build a minimal LayoutSpec from the old spec_json for rendering test
        spec_data = slide.spec_json
        layout_spec = LayoutSpec(
            slide_no=spec_data.get("slide_no", i + 1),
            primitive=SingleColumnLayout(
                primitive="single-column", max_width_ratio=0.8,
                v_align="center", has_pull_quote=False,
            ),
            region_bindings=[RegionBinding(region_id="content", blocks=[
                ContentBlock(block_id="title", content_type="heading",
                             content=spec_data.get("title", "")),
            ])],
            visual_focus="content",
            section=spec_data.get("section", ""),
            title=spec_data.get("title", ""),
        )
        html = render_slide_html(layout_spec, default_theme)
        assert "<!DOCTYPE html>" in html
        assert len(html) > 200

    # 4. Verify spec_json is valid LayoutSpec
    from schema.visual_theme import LayoutSpec as LayoutSpecSchema
    layout_specs = [LayoutSpecSchema.model_validate(s.spec_json) for s in slides]
    assert layout_specs[0].slide_no == 1
    assert layout_specs[1].slide_no == 2

    print(f"\n✓ Full pipeline smoke: outline={outline.deck_title}, "
          f"slides={len(slides)}, primitive_types="
          f"[{layout_specs[0].primitive.primitive}, {layout_specs[1].primitive.primitive}]")
