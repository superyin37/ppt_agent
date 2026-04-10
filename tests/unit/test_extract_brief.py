"""
Unit tests for extract_project_brief.
LLM call is mocked so tests run without API keys.
"""
import pytest
from unittest.mock import AsyncMock, patch
from tool.input.extract_brief import (
    extract_project_brief,
    ExtractBriefInput,
    _LLMBriefOutput,
    _merge_briefs,
    _compute_missing_fields,
)
from schema.common import BuildingType


# ---------- pure function tests (no mock needed) ----------

def test_merge_briefs_new_wins_over_none():
    existing = {"building_type": "museum", "client_name": None}
    new = {"building_type": None, "client_name": "天津文化集团"}
    merged = _merge_briefs(existing, new)
    assert merged["building_type"] == "museum"      # kept existing (new is None)
    assert merged["client_name"] == "天津文化集团"   # new wins


def test_merge_briefs_no_existing():
    result = _merge_briefs(None, {"building_type": "office"})
    assert result == {"building_type": "office"}


def test_compute_missing_fields_complete():
    brief = {
        "building_type": "museum",
        "client_name": "天津文化集团",
        "site_address": "天津市河西区",
        "style_preferences": ["modern"],
        "gross_floor_area": 12000,
        "site_area": 6000,
        "far": 2.0,
    }
    assert _compute_missing_fields(brief) == []


def test_compute_missing_fields_missing_all():
    missing = _compute_missing_fields({})
    assert "building_type" in missing
    assert "client_name" in missing
    assert "site_address" in missing


def test_compute_missing_fields_only_one_metric():
    brief = {
        "building_type": "office",
        "client_name": "A",
        "site_address": "B",
        "style_preferences": ["x"],
        "gross_floor_area": 10000,
    }
    missing = _compute_missing_fields(brief)
    assert any("far" in m or "site_area" in m or "两项" in m for m in missing)


# ---------- async tests with LLM mock ----------

@pytest.fixture
def llm_museum_response():
    return _LLMBriefOutput(
        extracted={
            "building_type": "museum",
            "client_name": "天津文化集团",
            "style_preferences": ["modern", "minimal"],
            "site_address": "天津市河西区友谊路",
            "province": "天津市",
            "city": "天津市",
            "district": "河西区",
            "gross_floor_area": 12000,
            "site_area": None,
            "far": None,
            "special_requirements": None,
        },
        missing_fields=["site_area_or_far"],
        is_complete=False,
        follow_up="请问用地面积大约是多少平米？或者您知道容积率是多少吗？",
        confirmation_summary=None,
    )


@pytest.fixture
def llm_complete_response():
    return _LLMBriefOutput(
        extracted={
            "building_type": "museum",
            "client_name": "天津文化集团",
            "style_preferences": ["modern", "minimal"],
            "site_address": "天津市河西区友谊路",
            "province": "天津市",
            "city": "天津市",
            "district": "河西区",
            "gross_floor_area": 12000,
            "site_area": 6000,
            "far": 2.0,
            "special_requirements": None,
        },
        missing_fields=[],
        is_complete=True,
        follow_up=None,
        confirmation_summary="项目信息已齐全：天津文化集团博物馆，建面12000㎡，容积率2.0，现代简约风格。",
    )


@pytest.mark.asyncio
async def test_extract_incomplete_returns_follow_up(llm_museum_response):
    with patch("tool.input.extract_brief.call_llm_structured", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = llm_museum_response
        result = await extract_project_brief(ExtractBriefInput(
            raw_text="天津主城区博物馆项目，甲方天津文化集团，约12000平米，现代简约"
        ))

    assert result.is_complete is False
    assert result.extracted.building_type == BuildingType.MUSEUM
    assert result.extracted.client_name == "天津文化集团"
    assert result.follow_up is not None
    assert len(result.missing_fields) > 0


@pytest.mark.asyncio
async def test_extract_complete_returns_summary(llm_complete_response):
    with patch("tool.input.extract_brief.call_llm_structured", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = llm_complete_response
        result = await extract_project_brief(ExtractBriefInput(
            raw_text="用地面积6000平米，容积率2.0"
        ))

    assert result.is_complete is True
    assert result.confirmation_summary is not None
    assert result.follow_up is None
    assert result.extracted.far == 2.0


@pytest.mark.asyncio
async def test_extract_merges_with_existing(llm_complete_response):
    existing = {
        "building_type": "museum",
        "client_name": "天津文化集团",
        "style_preferences": ["modern"],
        "site_address": "天津市河西区",
        "gross_floor_area": 12000,
    }
    with patch("tool.input.extract_brief.call_llm_structured", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = llm_complete_response
        result = await extract_project_brief(ExtractBriefInput(
            raw_text="用地6000平米",
            existing_brief=existing,
        ))

    assert result.extracted.building_type == BuildingType.MUSEUM  # kept from existing
    assert result.extracted.site_area == 6000                     # new from LLM


@pytest.mark.asyncio
async def test_extract_auto_computes_far():
    """When LLM returns gfa+site_area, far should be auto-computed."""
    llm_response = _LLMBriefOutput(
        extracted={
            "building_type": "office",
            "client_name": "某公司",
            "style_preferences": ["modern"],
            "site_address": "上海市浦东新区",
            "province": "上海市",
            "city": "上海市",
            "district": "浦东新区",
            "gross_floor_area": 30000,
            "site_area": 10000,
            "far": None,       # ← not provided
            "special_requirements": None,
        },
        missing_fields=[],
        is_complete=True,
        follow_up=None,
        confirmation_summary="确认：上海办公楼项目",
    )
    with patch("tool.input.extract_brief.call_llm_structured", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = llm_response
        result = await extract_project_brief(ExtractBriefInput(raw_text="test"))

    assert result.extracted.far == 3.0   # 30000 / 10000 = 3.0
