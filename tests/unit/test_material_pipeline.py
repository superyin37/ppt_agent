from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from db.models.asset import Asset
from db.models.material_item import MaterialItem
from tool.material_pipeline import (
    _build_item_payload,
    _group_chart_variants,
    build_manifest,
    build_summary,
    infer_logical_key,
)
from tool.material_resolver import expand_requirement, find_matching_assets, find_matching_items, logical_key_matches


PROJECT1_DIR = Path("test_material/project1")


def _item(logical_key: str, kind: str = "document", title: str = "sample", text: str | None = None) -> MaterialItem:
    return MaterialItem(
        id=uuid4(),
        package_id=uuid4(),
        logical_key=logical_key,
        kind=kind,
        format="md",
        title=title,
        text_content=text,
    )


def _asset(logical_key: str, asset_type: str = "image") -> Asset:
    return Asset(
        id=uuid4(),
        project_id=uuid4(),
        asset_type=asset_type,
        status="ready",
        logical_key=logical_key,
        title=logical_key,
    )


def test_infer_logical_key_for_project1_files():
    assert infer_logical_key(PROJECT1_DIR / "场地四至分析_285.png") == "site.boundary.image"
    assert infer_logical_key(PROJECT1_DIR / "场地poi_285.xlsx") == "site.poi.table"
    assert infer_logical_key(PROJECT1_DIR / "场地坐标_285.md") == "site.coordinate.text"
    assert infer_logical_key(PROJECT1_DIR / "枢纽站点_285.png") == "site.transport.hub.image"
    assert infer_logical_key(PROJECT1_DIR / "参考案例4_archdaily.cn_285.md") == "reference.case.4.source"
    assert infer_logical_key(PROJECT1_DIR / "参考案例4_缩略图_285.png") == "reference.case.4.thumbnail"
    assert infer_logical_key(PROJECT1_DIR / "案例4_评价和分析_285.md") == "reference.case.4.analysis"
    assert infer_logical_key(PROJECT1_DIR / "经济背景 - 城市经济_chart_2_285.svg") == "economy.city.chart.2"


def test_group_chart_variants_groups_html_svg_json():
    files = [
        PROJECT1_DIR / "经济背景 - 城市经济_chart_0_285.html",
        PROJECT1_DIR / "经济背景 - 城市经济_chart_0_285.json",
        PROJECT1_DIR / "经济背景 - 城市经济_chart_0_285.svg",
        PROJECT1_DIR / "场地四至分析_285.png",
    ]
    regular, grouped = _group_chart_variants(files)

    assert regular == [PROJECT1_DIR / "场地四至分析_285.png"]
    assert len(grouped) == 1
    _, variants = grouped[0]
    assert set(variants.keys()) == {"html", "json", "svg"}


def test_build_item_payload_for_chart_bundle_prefers_svg_and_html():
    variants = {
        "html": PROJECT1_DIR / "经济背景 - 城市经济_chart_0_285.html",
        "json": PROJECT1_DIR / "经济背景 - 城市经济_chart_0_285.json",
        "svg": PROJECT1_DIR / "经济背景 - 城市经济_chart_0_285.svg",
    }
    payload = _build_item_payload(variants["svg"], "economy.city.chart.0", variants=variants)

    assert payload["kind"] == "chart_bundle"
    assert payload["format"] == "bundle"
    assert payload["preview_url"].endswith(".svg")
    assert payload["content_url"].endswith(".html")
    assert payload["structured_data"] is not None


def test_manifest_and_summary_include_logical_keys_and_snippets():
    items = [
        _item("reference.case.1.source", text="case source summary"),
        _item("reference.case.1.analysis", text="case analysis summary"),
        _item("economy.city.chart.0", kind="chart_bundle", title="city chart"),
    ]

    manifest = build_manifest(items)
    summary = build_summary(items)

    assert "reference.case.1.source" in manifest["logical_keys"]
    assert summary["case_count"] == 1
    assert summary["chart_count"] == 1
    assert summary["evidence_snippets"][0]["snippet"].startswith("case")


def test_material_resolver_matches_aliases_and_wildcards():
    items = [
        _item("site.transport.hub.image"),
        _item("reference.case.2.thumbnail"),
        _item("reference.case.2.analysis"),
    ]
    assets = [
        _asset("site.transport.hub.image"),
        _asset("reference.case.2.card", asset_type="case_card"),
    ]

    assert expand_requirement("map_hub_stations") == ["site.transport.hub.image"]
    assert logical_key_matches("reference.case.*.thumbnail", "reference.case.2.thumbnail")

    matched_items = find_matching_items(["reference.case.*.thumbnail", "reference.case.*.analysis"], items)
    matched_assets = find_matching_assets(["reference.case.*.card"], assets)

    assert {item.logical_key for item in matched_items} == {
        "reference.case.2.thumbnail",
        "reference.case.2.analysis",
    }
    assert [asset.logical_key for asset in matched_assets] == ["reference.case.2.card"]
