"""
Unit tests for Phase 6 tool layer:
  - chart_generation: all chart types, color schemes, data shapes
  - poi_retrieval: mock output when no API key
  - mobility_analysis: mock output + score computation
  - map_annotation: placeholder generation
"""
import pytest
from unittest.mock import patch, AsyncMock


# ── Chart generation ───────────────────────────────────────────────────────────

from tool.asset.chart_generation import chart_generation, ChartGenerationInput, COLOR_SCHEMES


def test_bar_chart_returns_png():
    result = chart_generation(ChartGenerationInput(
        chart_type="bar",
        title="测试柱状图",
        data=[{"label": "A", "value": 100}, {"label": "B", "value": 200}],
    ))
    assert result.image_format == "png"
    assert result.image_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    assert result.data_json["chart_type"] == "bar"


def test_line_chart_returns_png():
    result = chart_generation(ChartGenerationInput(
        chart_type="line",
        title="折线图",
        data=[{"x": "2020", "y": 1000}, {"x": "2021", "y": 1500}, {"x": "2022", "y": 1300}],
    ))
    assert result.image_format == "png"
    assert len(result.image_bytes) > 100


def test_pie_chart_returns_png():
    result = chart_generation(ChartGenerationInput(
        chart_type="pie",
        title="饼图",
        data=[{"label": "商业", "value": 40}, {"label": "居住", "value": 35}, {"label": "公共", "value": 25}],
    ))
    assert result.image_format == "png"
    assert len(result.image_bytes) > 100


def test_radar_chart_returns_png():
    result = chart_generation(ChartGenerationInput(
        chart_type="radar",
        title="雷达图",
        data=[
            {"label": "交通", "value": 80},
            {"label": "教育", "value": 60},
            {"label": "商业", "value": 70},
            {"label": "医疗", "value": 50},
            {"label": "环境", "value": 90},
        ],
    ))
    assert result.image_format == "png"
    assert len(result.image_bytes) > 100


def test_unknown_chart_type_raises():
    from tool._base import ToolError
    with pytest.raises(ToolError) as exc_info:
        chart_generation(ChartGenerationInput(
            chart_type="scatter",
            title="不支持的图表",
            data=[{"label": "A", "value": 1}],
        ))
    assert exc_info.value.code == "UNKNOWN_CHART_TYPE"


def test_all_color_schemes_valid():
    """Ensure all defined color schemes produce a valid PNG."""
    for scheme in COLOR_SCHEMES:
        result = chart_generation(ChartGenerationInput(
            chart_type="bar",
            title=f"颜色方案: {scheme}",
            data=[{"label": "X", "value": 50}],
            color_scheme=scheme,
        ))
        assert len(result.image_bytes) > 100, f"color_scheme={scheme} produced empty output"


def test_data_json_matches_input():
    data = [{"label": "测试", "value": 99}]
    result = chart_generation(ChartGenerationInput(
        chart_type="bar", title="数据验证", data=data,
    ))
    assert result.data_json["data"] == data
    assert result.data_json["title"] == "数据验证"


# ── POI retrieval (mock mode) ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_poi_retrieval_mock_output():
    """When AMAP_API_KEY is empty, should return mock POIs."""
    from tool.site.poi_retrieval import poi_retrieval, POIRetrievalInput
    with patch("tool.site.poi_retrieval.settings") as mock_settings:
        mock_settings.amap_api_key = ""
        result = await poi_retrieval(POIRetrievalInput(
            longitude=121.47, latitude=31.23, radius_meters=1000,
        ))
    assert len(result.pois) > 0
    assert "模拟" in result.summary
    assert result.by_category is not None


@pytest.mark.asyncio
async def test_poi_retrieval_builds_by_category():
    from tool.site.poi_retrieval import poi_retrieval, POIRetrievalInput
    with patch("tool.site.poi_retrieval.settings") as mock_settings:
        mock_settings.amap_api_key = ""
        result = await poi_retrieval(POIRetrievalInput(
            longitude=116.40, latitude=39.91,
        ))
    # by_category should group pois
    all_pois = [p for items in result.by_category.values() for p in items]
    assert len(all_pois) == len(result.pois)


# ── Mobility analysis (mock mode) ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mobility_analysis_mock_output():
    from tool.site.mobility_analysis import mobility_analysis, MobilityAnalysisInput
    with patch("tool.site.mobility_analysis.settings") as mock_settings:
        mock_settings.amap_api_key = ""
        result = await mobility_analysis(MobilityAnalysisInput(
            longitude=121.47, latitude=31.23,
        ))
    assert result.traffic_score >= 0
    assert result.traffic_score <= 100
    assert len(result.metro_stations) > 0
    assert result.summary != ""


def test_traffic_score_computation():
    from tool.site.mobility_analysis import (
        _compute_traffic_score, MetroStation, BusLine,
    )
    # Good score: nearby metro + many buses
    metro = [MetroStation(name="A站", distance_meters=200)]
    buses = [BusLine(name=f"路{i}", stop_name="站", distance_meters=100) for i in range(10)]
    score = _compute_traffic_score(metro, buses)
    assert score >= 80

    # Poor score: no metro, no bus
    score_poor = _compute_traffic_score([], [])
    assert score_poor == 0


def test_traffic_score_capped_at_100():
    from tool.site.mobility_analysis import (
        _compute_traffic_score, MetroStation, BusLine,
    )
    metro = [MetroStation(name="A站", distance_meters=100)]
    buses = [BusLine(name=f"路{i}", stop_name="站", distance_meters=50) for i in range(20)]
    score = _compute_traffic_score(metro, buses)
    assert score <= 100


# ── Map annotation (placeholder mode) ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_map_annotation_placeholder():
    from tool.asset.map_annotation import map_annotation, MapAnnotationInput
    with patch("tool.asset.map_annotation.settings") as mock_settings:
        mock_settings.amap_api_key = ""
        result = await map_annotation(MapAnnotationInput(
            center_lng=121.47, center_lat=31.23, zoom=14,
        ))
    # Should return a valid PNG
    assert result.image_format == "png"
    assert result.image_bytes[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.asyncio
async def test_map_annotation_with_annotations():
    from tool.asset.map_annotation import map_annotation, MapAnnotationInput, AnnotationItem
    with patch("tool.asset.map_annotation.settings") as mock_settings:
        mock_settings.amap_api_key = ""
        result = await map_annotation(MapAnnotationInput(
            center_lng=116.40, center_lat=39.91, zoom=15,
            annotations=[
                AnnotationItem(longitude=116.40, latitude=39.91, label="项目", color="red"),
                AnnotationItem(longitude=116.41, latitude=39.92, label="地铁站", color="blue"),
            ],
        ))
    assert len(result.image_bytes) > 100
