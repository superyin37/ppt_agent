"""
POI retrieval tool — Phase 6
Uses AMap /v3/place/around to fetch nearby points of interest.
Falls back to mock data when AMAP_API_KEY is empty.
"""
import logging
from typing import Optional
from pydantic import BaseModel
from tool._base import ToolError
from config.settings import settings

logger = logging.getLogger(__name__)

# AMap type codes for each category
CATEGORY_TYPE_MAP = {
    "教育": "141201|141202|141203",
    "医疗": "090100|090200|090300",
    "商业": "060000|061000|062000",
    "交通": "150200|150300|150500",
    "文化": "080100|080200|080300",
    "公园": "110101|110102|110104",
}

DEFAULT_CATEGORIES = ["教育", "医疗", "商业", "交通", "文化", "公园"]


class POIItem(BaseModel):
    name: str
    category: str
    distance_meters: float
    longitude: float
    latitude: float


class POIRetrievalInput(BaseModel):
    longitude: float
    latitude: float
    radius_meters: int = 1000
    categories: list[str] = DEFAULT_CATEGORIES


class POIRetrievalOutput(BaseModel):
    pois: list[POIItem]
    summary: str
    by_category: dict[str, list[POIItem]] = {}


async def poi_retrieval(input: POIRetrievalInput) -> POIRetrievalOutput:
    """
    Retrieve nearby POIs via AMap API.
    Falls back to empty/mock output when API key is not configured.
    timeout: 10s
    """
    if not settings.amap_api_key:
        return _mock_output(input)

    from tool.site._amap_client import amap_get

    pois: list[POIItem] = []
    for category in input.categories:
        type_code = CATEGORY_TYPE_MAP.get(category, "")
        try:
            data = await amap_get("/v3/place/around", {
                "location": f"{input.longitude},{input.latitude}",
                "radius": input.radius_meters,
                "types": type_code,
                "offset": 10,
                "page": 1,
                "extensions": "base",
            })
            for poi in data.get("pois", []):
                loc = poi.get("location", "").split(",")
                if len(loc) != 2:
                    continue
                pois.append(POIItem(
                    name=poi.get("name", ""),
                    category=category,
                    distance_meters=float(poi.get("distance", 0)),
                    longitude=float(loc[0]),
                    latitude=float(loc[1]),
                ))
        except ToolError as e:
            logger.warning(f"POI retrieval failed for category={category}: {e.message}")

    by_category: dict[str, list[POIItem]] = {}
    for poi in pois:
        by_category.setdefault(poi.category, []).append(poi)

    summary = _build_summary(by_category, input.radius_meters)
    return POIRetrievalOutput(pois=pois, summary=summary, by_category=by_category)


def _build_summary(by_category: dict[str, list[POIItem]], radius: int) -> str:
    parts = []
    for cat, items in by_category.items():
        if items:
            parts.append(f"{len(items)}个{cat}设施")
    if not parts:
        return f"周边{radius}m内暂无明显配套设施"
    return f"周边{radius}m内有" + "、".join(parts)


def _mock_output(input: POIRetrievalInput) -> POIRetrievalOutput:
    """Return placeholder output when API key is not configured."""
    logger.info("poi_retrieval: AMap key not set, returning mock output")
    mock_pois = [
        POIItem(name="地铁站（模拟）", category="交通", distance_meters=350.0,
                longitude=input.longitude + 0.003, latitude=input.latitude + 0.001),
        POIItem(name="商业综合体（模拟）", category="商业", distance_meters=600.0,
                longitude=input.longitude - 0.005, latitude=input.latitude),
        POIItem(name="小学（模拟）", category="教育", distance_meters=800.0,
                longitude=input.longitude + 0.007, latitude=input.latitude - 0.002),
    ]
    by_category: dict[str, list[POIItem]] = {}
    for p in mock_pois:
        by_category.setdefault(p.category, []).append(p)
    return POIRetrievalOutput(
        pois=mock_pois,
        summary=f"周边{input.radius_meters}m内有1个交通设施、1个商业设施、1个教育设施（模拟数据）",
        by_category=by_category,
    )
