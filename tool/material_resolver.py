from __future__ import annotations

import re
from typing import Iterable

from db.models.asset import Asset
from db.models.material_item import MaterialItem
from schema.page_slot import InputRequirement


INPUT_ALIAS_PATTERNS: dict[str, list[str]] = {
    "brief_doc": [],
    "project_name": [],
    "project_brief_data": [],
    "concept_description": [],
    "web_search_policy": [],
    "web_search_planning": [],
    "web_search_competitors": [],
    "map_hub_stations": ["site.transport.hub.image"],
    "map_transport_nodes": ["site.transport.external.image", "site.transport.station.image"],
    "map_infra_plan": ["site.infrastructure.plan.image"],
    "map_site_boundary": ["site.boundary.image"],
    "poi_data": ["site.poi.table", "site.poi.stats", "site.poi.summary"],
    "site_coordinate": ["site.coordinate.text"],
    "case_thumbnail": ["reference.case.*.thumbnail"],
    "case_meta": ["reference.case.*.analysis", "reference.case.*.card", "reference.case.*.source"],
    "chart_gdp": ["economy.city.chart.*"],
    "chart_population": ["economy.city.chart.*"],
    "chart_urbanization": ["economy.city.chart.*"],
    "chart_tertiary": ["economy.industry.chart.*"],
    "chart_industry_structure": ["economy.industry.chart.*"],
    "chart_retail": ["economy.consumption.chart.*"],
    "chart_income_expense": ["economy.consumption.chart.*"],
    # Concept render outputs (see ADR-005)
    "concept_aerial": ["concept.*.aerial"],
    "concept_ext_perspective": ["concept.*.ext_perspective"],
    "concept_int_perspective": ["concept.*.int_perspective"],
    "concept_image": ["concept.*.aerial", "concept.*.ext_perspective", "concept.*.int_perspective"],
}


def expand_requirement(requirement: InputRequirement | str) -> list[str]:
    key = requirement.logical_key_pattern if isinstance(requirement, InputRequirement) else requirement
    return INPUT_ALIAS_PATTERNS.get(key, [key])


def logical_key_matches(pattern: str, logical_key: str) -> bool:
    regex = re.escape(pattern).replace("\\*", "[^.]+")
    return re.fullmatch(regex, logical_key) is not None


def find_matching_items(patterns: Iterable[str], items: Iterable[MaterialItem]) -> list[MaterialItem]:
    matches = []
    for item in items:
        if any(logical_key_matches(pattern, item.logical_key) for pattern in patterns):
            matches.append(item)
    return matches


def find_matching_assets(patterns: Iterable[str], assets: Iterable[Asset]) -> list[Asset]:
    matches = []
    for asset in assets:
        if asset.logical_key and any(logical_key_matches(pattern, asset.logical_key) for pattern in patterns):
            matches.append(asset)
    return matches


def summarize_evidence(items: list[MaterialItem], max_items: int = 5) -> list[str]:
    snippets = []
    for item in items[:max_items]:
        if item.text_content:
            snippets.append(item.text_content[:240])
        elif item.title:
            snippets.append(item.title)
    return snippets
