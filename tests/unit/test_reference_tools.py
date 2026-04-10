"""
Unit tests for Phase 5 Reference Agent tools:
  - _embedding: _mock_embedding, build_embedding_text, build_query_text
  - search: _tag_search fallback logic (no DB needed)
  - rerank: fallback behavior
  - preference_summary: fallback tag-frequency summariser
"""
import math
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


# ── Embedding ─────────────────────────────────────────────────────────────────

from tool.reference._embedding import (
    _mock_embedding,
    build_embedding_text,
    build_query_text,
    VECTOR_DIM,
)


def test_mock_embedding_dimension():
    vec = _mock_embedding("hello world")
    assert len(vec) == VECTOR_DIM


def test_mock_embedding_l2_normalized():
    vec = _mock_embedding("some architectural text")
    norm = math.sqrt(sum(v * v for v in vec))
    assert abs(norm - 1.0) < 1e-5


def test_mock_embedding_deterministic():
    text = "苏州博物馆 museum modern minimal"
    v1 = _mock_embedding(text)
    v2 = _mock_embedding(text)
    assert v1 == v2


def test_mock_embedding_different_texts_differ():
    v1 = _mock_embedding("museum")
    v2 = _mock_embedding("office building")
    # Vectors should differ
    assert v1 != v2


def test_build_embedding_text_includes_type():
    case = {
        "building_type": "museum",
        "architect": "贝聿铭",
        "location": "苏州",
        "country": "中国",
        "style_tags": ["modern", "minimal"],
        "feature_tags": ["光线", "庭院"],
        "scale_category": "medium",
        "gfa_sqm": 19000,
        "summary": "苏州博物馆新馆",
    }
    text = build_embedding_text(case)
    assert "museum" in text
    assert "贝聿铭" in text
    assert "modern" in text


def test_build_embedding_text_omits_empty_fields():
    case = {"building_type": "office"}
    text = build_embedding_text(case)
    # Should not include empty tags or blank summary
    assert "、" not in text or text.count("、") == 0


def test_build_query_text_includes_brief_fields():
    brief = {
        "building_type": "museum",
        "style_preferences": ["minimal", "cultural"],
        "city": "上海",
        "district": "浦东",
        "gross_floor_area": 50000,
        "special_requirements": "绿色建筑",
    }
    text = build_query_text(brief)
    assert "museum" in text
    assert "minimal" in text
    assert "上海" in text


# ── Search fallback ────────────────────────────────────────────────────────────

from tool.reference.search import CaseSearchInput, CaseSearchOutput, _tag_search


def _make_mock_db_with_cases(cases):
    """Helper: mock SQLAlchemy session returning given case objects."""
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.all.return_value = cases
    mock_db = MagicMock()
    mock_db.query.return_value = mock_query
    return mock_db


def _make_case_orm(building_type="museum", style_tags=None, feature_tags=None):
    case = MagicMock(spec=[])  # spec=[] prevents auto-creating attributes
    case.id = uuid4()
    case.title = "Test Case"
    case.architect = "Test Architect"
    case.location = "Test Location"
    case.building_type = building_type
    case.style_tags = style_tags or ["modern"]
    case.feature_tags = feature_tags or ["庭院"]
    case.scale_category = "medium"
    case.gfa_sqm = 20000
    case.country = "中国"
    case.summary = "Test summary"
    case.images = []
    case.year_completed = 2020
    case.is_active = True
    return case


def test_tag_search_returns_cases():
    orm_case = _make_case_orm()
    mock_db = _make_mock_db_with_cases([orm_case])

    inp = CaseSearchInput(building_type="museum", style_tags=["modern"], top_k=5)
    result = _tag_search(inp, mock_db, exclude_ids=[])
    assert isinstance(result, CaseSearchOutput)
    assert len(result.cases) == 1
    assert result.cases[0].building_type.value == "museum"
    assert result.used_vector_search is False


def test_tag_search_empty_db():
    mock_db = _make_mock_db_with_cases([])
    inp = CaseSearchInput(building_type="office", top_k=5)
    result = _tag_search(inp, mock_db, exclude_ids=[])
    assert result.cases == []


# ── Rerank fallback ────────────────────────────────────────────────────────────

from schema.reference import ReferenceCase, BuildingType
from tool.reference.rerank import RerankInput, rerank_cases


def _make_ref_case(building_type="museum"):
    return ReferenceCase(
        id=uuid4(),
        title="Sample Case",
        building_type=BuildingType(building_type),
        style_tags=["modern"],
        feature_tags=["庭院"],
        scale_category="medium",
        gfa_sqm=20000,
        country="中国",
        summary="A test case",
        images=[],
    )


@pytest.mark.asyncio
async def test_rerank_no_rerank_needed_when_fewer_than_top_k():
    """When len(cases) <= top_k, skip LLM call and return as-is."""
    cases = [_make_ref_case() for _ in range(4)]
    inp = RerankInput(cases=cases, brief={"building_type": "museum"}, top_k=8)
    result = await rerank_cases(inp)
    assert len(result.cases) == 4
    assert result.recommendation_reason != ""


@pytest.mark.asyncio
async def test_rerank_fallback_on_llm_error():
    """When LLM raises, fall back to original order."""
    cases = [_make_ref_case() for _ in range(10)]
    inp = RerankInput(cases=cases, brief={"building_type": "museum"}, top_k=5)

    with patch("tool.reference.rerank.call_llm_structured", new=AsyncMock(side_effect=Exception("LLM error"))):
        result = await rerank_cases(inp)

    assert len(result.cases) == 5
    assert result.cases == cases[:5]


# ── Preference summary fallback ────────────────────────────────────────────────

from tool.reference.preference_summary import (
    PreferenceSummaryInput,
    _fallback_summary,
    summarise_preferences,
)


def test_fallback_summary_empty_selections():
    inp = PreferenceSummaryInput(selections=[], brief={})
    # _fallback_summary with empty selections returns empty lists
    result = _fallback_summary(inp)
    assert result.dominant_styles == []
    assert result.dominant_features == []


def test_fallback_summary_counts_tags():
    selections = [
        {"selected_tags": ["modern", "minimal", "庭院"], "selection_reason": None},
        {"selected_tags": ["modern", "庭院", "光线"], "selection_reason": None},
        {"selected_tags": ["minimal", "cultural"], "selection_reason": None},
    ]
    inp = PreferenceSummaryInput(selections=selections, brief={})
    result = _fallback_summary(inp)
    # "modern" (2x) and "minimal" (2x) should appear in styles
    assert "modern" in result.dominant_styles or "minimal" in result.dominant_styles
    # narrative hint should be set
    assert result.narrative_hint != ""


def test_fallback_summary_feature_tags_excluded_from_styles():
    """Tags not in style_keywords should go to features, not styles."""
    selections = [
        {"selected_tags": ["庭院", "光线", "悬挑", "现代感"], "selection_reason": None},
    ]
    inp = PreferenceSummaryInput(selections=selections, brief={})
    result = _fallback_summary(inp)
    # None of these are in style_keywords, so styles should be empty
    assert result.dominant_styles == []
    assert len(result.dominant_features) > 0


@pytest.mark.asyncio
async def test_summarise_preferences_empty_returns_hint():
    inp = PreferenceSummaryInput(selections=[], brief={})
    result = await summarise_preferences(inp)
    assert "尚未选择" in result.narrative_hint


@pytest.mark.asyncio
async def test_summarise_preferences_fallback_on_error():
    selections = [
        {"case_id": str(uuid4()), "case_title": "苏州博物馆", "selected_tags": ["modern", "minimal"], "selection_reason": "喜欢"},
    ]
    inp = PreferenceSummaryInput(selections=selections, brief={"building_type": "museum"})

    with patch("tool.reference.preference_summary.call_llm_structured", new=AsyncMock(side_effect=Exception("LLM error"))):
        result = await summarise_preferences(inp)

    # Should fall back to tag frequency
    assert result.narrative_hint != ""
    assert "modern" in result.dominant_styles or "minimal" in result.dominant_styles
