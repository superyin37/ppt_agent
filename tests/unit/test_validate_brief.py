import pytest
from tool.input.validate_brief import validate_project_brief, ValidateBriefInput
from schema.project import ProjectBriefData
from schema.common import BuildingType


def _make_brief(**kwargs) -> ProjectBriefData:
    defaults = dict(
        building_type=BuildingType.MUSEUM,
        client_name="天津文化集团",
        site_address="天津市河西区",
        gross_floor_area=12000,
        site_area=6000,
    )
    defaults.update(kwargs)
    return ProjectBriefData(**defaults)


def test_valid_brief():
    brief = _make_brief()
    result = validate_project_brief(ValidateBriefInput(brief=brief))
    assert result.is_valid is True
    assert result.errors == []


def test_missing_building_type():
    brief = _make_brief(building_type=None)
    result = validate_project_brief(ValidateBriefInput(brief=brief))
    assert not result.is_valid
    assert any("building_type" in e for e in result.errors)


def test_missing_client_name():
    brief = _make_brief(client_name=None)
    result = validate_project_brief(ValidateBriefInput(brief=brief))
    assert not result.is_valid


def test_missing_site_address():
    brief = _make_brief(site_address=None)
    result = validate_project_brief(ValidateBriefInput(brief=brief))
    assert not result.is_valid


def test_insufficient_metrics():
    brief = _make_brief(gross_floor_area=None, site_area=None, far=None)
    result = validate_project_brief(ValidateBriefInput(brief=brief))
    assert not result.is_valid
    assert any("两项" in e for e in result.errors)


def test_single_metric_insufficient():
    brief = _make_brief(site_area=None)
    # Only gfa provided, far=None => only 1 metric
    result = validate_project_brief(ValidateBriefInput(brief=brief))
    assert not result.is_valid


def test_two_metrics_valid():
    brief = _make_brief(site_area=None, far=2.0)
    result = validate_project_brief(ValidateBriefInput(brief=brief))
    assert result.is_valid


def test_large_area_warning():
    brief = _make_brief(gross_floor_area=600_000, site_area=200_000)
    result = validate_project_brief(ValidateBriefInput(brief=brief))
    assert result.is_valid
    assert any("50万" in w for w in result.warnings)


def test_extreme_far_warning():
    brief = _make_brief(site_area=6000, far=20.0)
    result = validate_project_brief(ValidateBriefInput(brief=brief))
    assert result.is_valid
    assert any("容积率" in w for w in result.warnings)
