"""Unit tests for SlideData schemas + truncate_to_schema (ADR-006).

Each of the 11 component types gets:
- a happy-path validation case
- one constraint-violation case
- one truncate_to_schema repair case (where applicable)
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from schema.slide_data import (
    COMPONENT_SCHEMA,
    CaseCardData,
    ChartData,
    ComponentType,
    ConceptSchemeData,
    ContentBulletsData,
    CoverData,
    EndingData,
    ImageGridData,
    PolicyListData,
    TableData,
    TocData,
    TransitionData,
    truncate_to_schema,
)


# ─── Happy path ────────────────────────────────────────────────────────────


def test_cover_happy_path():
    m = CoverData(
        title="测试标题",
        slogan="A short slogan",
        en="ENGLISH SUBTITLE",
        meta_lines=[{"label": "BUILDING", "value": "Office"}],
        year=2026,
    )
    assert m.component_type is ComponentType.COVER
    assert m.year == 2026


def test_toc_happy_path():
    m = TocData(
        title="目录",
        entries=[
            {"no": "01", "label": "背景研究", "en": "BG", "page_range": "03 — 12"},
            {"no": "02", "label": "场地分析", "en": "SITE", "page_range": "13 — 19"},
        ],
    )
    assert len(m.entries) == 2


def test_transition_happy_path():
    m = TransitionData(title="背景研究", subtitle_en="Background", section_no="01")
    assert m.section_no == "01"


def test_policy_list_happy_path():
    m = PolicyListData(
        title="政策分析",
        policies=[{"title": "城市更新条例", "publish_year": "2024"}],
    )
    assert len(m.policies) == 1


def test_chart_happy_path_with_path():
    m = ChartData(
        title="GDP 增速",
        bullets=["2023 同比 +5.2%", "第三产业占比 60%"],
        chart_path="/abs/path/chart.png",
    )
    assert m.chart_path is not None


def test_chart_happy_path_with_spec():
    m = ChartData(
        title="GDP 增速",
        bullets=["a"],
        chart_spec={
            "chart_type": "bar",
            "chart_title": "GDP",
            "data": [{"label": "2023", "value": 5.2}],
        },
    )
    assert m.chart_spec.chart_type == "bar"


def test_table_happy_path():
    m = TableData(
        title="对比",
        headers=["项目", "规模", "亮点"],
        rows=[["A", "5万㎡", "中庭"], ["B", "3万㎡", "屋顶花园"]],
    )
    assert len(m.headers) == 3 and len(m.rows) == 2


def test_image_grid_happy_path():
    m = ImageGridData(
        title="区位",
        images=[{"path": "/a.png", "caption": "枢纽"}, {"path": "/b.png"}],
        caption="三张地图",
    )
    assert len(m.images) == 2


def test_content_bullets_happy_path():
    m = ContentBulletsData(
        title="设计策略",
        lede="项目以三大策略统领",
        bullets=[
            {"title": "策略一", "body": "一段说明"},
            {"title": "策略二", "body": "一段说明"},
            {"title": "策略三", "body": "一段说明"},
        ],
    )
    assert len(m.bullets) == 3


def test_case_card_happy_path():
    m = CaseCardData(
        title="参考案例",
        case_idx=0,
        case_name="蛇形画廊",
        scale="600㎡",
        highlights="木构 + 玻璃",
        inspiration="结构表现",
    )
    assert m.case_idx == 0


def test_concept_scheme_happy_path():
    m = ConceptSchemeData(
        scheme_idx=0,
        scheme_name="云上之城",
        view="aerial",
        view_label="AERIAL · 鸟瞰图",
        idea="退台呼应山势",
        analysis="一段方案分析",
    )
    assert m.view == "aerial"


def test_ending_happy_path():
    m = EndingData(
        title="THANK YOU",
        en="GRACIAS",
        tagline="see you next time",
        signature_parts=["Project", "Agent", "2026"],
    )
    assert len(m.signature_parts) == 3


# ─── Constraint violations ────────────────────────────────────────────────


def test_cover_title_too_long():
    with pytest.raises(ValidationError):
        CoverData(
            title="x" * 50,
            slogan="ok",
            en="OK",
            year=2026,
        )


def test_content_bullets_too_few_bullets():
    with pytest.raises(ValidationError):
        ContentBulletsData(
            title="t",
            bullets=[{"title": "a", "body": "b"}],
        )


def test_content_bullets_too_many_bullets():
    with pytest.raises(ValidationError):
        ContentBulletsData(
            title="t",
            bullets=[{"title": "a", "body": "b"}] * 10,
        )


def test_table_too_many_rows():
    with pytest.raises(ValidationError):
        TableData(title="t", headers=["a"], rows=[["x"]] * 20)


def test_concept_scheme_invalid_view():
    with pytest.raises(ValidationError):
        ConceptSchemeData(
            scheme_idx=0,
            scheme_name="x",
            view="invalid_view",  # type: ignore[arg-type]
            view_label="x",
        )


# ─── Truncate fallback ────────────────────────────────────────────────────


def test_truncate_string_field():
    data = {
        "title": "太长" * 100,
        "slogan": "long" * 50,
        "en": "EN" * 60,
        "year": 2026,
        "meta_lines": [],
    }
    truncated = truncate_to_schema(data, CoverData)
    cv = CoverData.model_validate(truncated)
    assert len(cv.title) <= 24
    assert cv.title.endswith("…")


def test_truncate_list_field():
    data = {
        "title": "ok",
        "lede": "ok",
        "bullets": [{"title": "a", "body": "b"}] * 30,
    }
    truncated = truncate_to_schema(data, ContentBulletsData)
    cv = ContentBulletsData.model_validate(truncated)
    assert len(cv.bullets) == 6


def test_truncate_nested_field():
    data = {
        "title": "policies",
        "policies": [
            {"title": "x" * 200, "content": "y" * 500, "impact": "z" * 200}
        ] * 10,
    }
    truncated = truncate_to_schema(data, PolicyListData)
    pl = PolicyListData.model_validate(truncated)
    assert len(pl.policies) == 5
    for p in pl.policies:
        assert len(p.title) <= 60
        assert len(p.content) <= 120


def test_truncate_no_op_when_within_limits():
    data = {"title": "background", "subtitle_en": "BG", "sub": "sub", "section_no": "01"}
    truncated = truncate_to_schema(data, TransitionData)
    assert truncated["title"] == "background"  # untouched


# ─── COMPONENT_SCHEMA registry sanity ─────────────────────────────────────


def test_component_schema_covers_all_enum_values():
    enum_values = set(ComponentType)
    registered = set(COMPONENT_SCHEMA.keys())
    assert enum_values == registered, f"missing: {enum_values - registered}"


@pytest.mark.parametrize("ct", list(ComponentType))
def test_component_schema_returns_correct_type(ct):
    cls = COMPONENT_SCHEMA[ct]
    # The discriminator literal should equal the enum value.
    field = cls.model_fields["component_type"]
    # In Pydantic v2 with Literal[Enum.MEMBER], default holds the enum member.
    assert field.default == ct
