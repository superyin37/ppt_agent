import pytest
from tool.input.compute_far import compute_far_metrics, ComputeFARInput
from tool._base import ToolError


def test_compute_far_from_gfa_and_site_area():
    result = compute_far_metrics(ComputeFARInput(gross_floor_area=12000, site_area=6000))
    assert result.far == 2.0
    assert result.computed_field == "far"
    assert result.gross_floor_area == 12000
    assert result.site_area == 6000


def test_compute_site_area_from_gfa_and_far():
    result = compute_far_metrics(ComputeFARInput(gross_floor_area=12000, far=2.0))
    assert result.site_area == 6000.0
    assert result.computed_field == "site_area"


def test_compute_gfa_from_site_area_and_far():
    result = compute_far_metrics(ComputeFARInput(site_area=6000, far=2.0))
    assert result.gross_floor_area == 12000.0
    assert result.computed_field == "gross_floor_area"


def test_far_rounding():
    result = compute_far_metrics(ComputeFARInput(gross_floor_area=10000, site_area=3000))
    assert result.far == 3.333


def test_insufficient_metrics_raises():
    with pytest.raises(ToolError) as exc_info:
        compute_far_metrics(ComputeFARInput(gross_floor_area=12000))
    assert exc_info.value.code == "INSUFFICIENT_METRICS"


def test_only_far_raises():
    with pytest.raises(ToolError):
        compute_far_metrics(ComputeFARInput(far=2.0))


def test_all_none_raises():
    with pytest.raises(ToolError):
        compute_far_metrics(ComputeFARInput())
