import uuid
import pytest
from tool.slide.content_fit import check_content_density
from schema.slide import SlideSpec, BlockContent, SlideConstraints
from schema.common import LayoutTemplate


def _make_spec(blocks: list[BlockContent], constraints: SlideConstraints | None = None) -> SlideSpec:
    return SlideSpec(
        project_id=uuid.uuid4(),
        slide_no=1,
        section="分析",
        title="标题",
        purpose="test",
        key_message="key",
        layout_template=LayoutTemplate.OVERVIEW_KPI,
        blocks=blocks,
        constraints=constraints or SlideConstraints(),
    )


def test_empty_slide_is_low():
    spec = _make_spec([])
    result = check_content_density(spec)
    assert result.density_level == "low"
    assert result.total_text_chars == 0


def test_medium_density():
    spec = _make_spec([
        BlockContent(block_id="t", block_type="text", content="A" * 100),  # 100/200 = 50%
        BlockContent(block_id="img", block_type="image", content="url"),   # 1/4 = 25%
    ])
    result = check_content_density(spec)
    assert result.density_level == "medium"


def test_overflow_detected():
    spec = _make_spec([
        BlockContent(block_id="t", block_type="text", content="A" * 500),  # way over 200
    ])
    result = check_content_density(spec)
    assert result.exceeds_text_limit is True
    assert result.density_level == "overflow"
    assert len(result.recommendations) > 0


def test_image_overflow():
    blocks = [
        BlockContent(block_id=f"img{i}", block_type="image", content=f"url{i}")
        for i in range(6)
    ]
    spec = _make_spec(blocks)
    result = check_content_density(spec)
    assert result.exceeds_image_limit is True


def test_bullet_counting():
    spec = _make_spec([
        BlockContent(block_id="b", block_type="bullet", content=["点1", "点2", "点3"]),
    ])
    result = check_content_density(spec)
    assert result.total_bullets == 3


def test_normalize_polygon_area():
    from tool.input.normalize_polygon import normalize_polygon, NormalizePolygonInput
    # Simple square ~ 1km x 1km near Beijing
    geojson = {
        "type": "Polygon",
        "coordinates": [[
            [116.39, 39.90],
            [116.40, 39.90],
            [116.40, 39.91],
            [116.39, 39.91],
            [116.39, 39.90],
        ]]
    }
    result = normalize_polygon(NormalizePolygonInput(geojson=geojson))
    # ~1km x ~1km = ~1,000,000 sqm, actual will vary due to projection
    assert result.area_sqm > 100_000  # at least 0.1 km²
    assert result.perimeter_m > 3000   # at least 3km perimeter
    assert result.centroid_lng == pytest.approx(116.395, abs=0.01)
    assert result.centroid_lat == pytest.approx(39.905, abs=0.01)
