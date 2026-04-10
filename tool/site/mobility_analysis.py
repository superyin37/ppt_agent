"""
Mobility analysis tool — Phase 6
Analyses transit accessibility around a site using AMap APIs.
Falls back to mock data when AMAP_API_KEY is empty.
"""
import logging
from pydantic import BaseModel
from tool._base import ToolError
from config.settings import settings

logger = logging.getLogger(__name__)


class MobilityAnalysisInput(BaseModel):
    longitude: float
    latitude: float
    radius_meters: int = 1500


class MetroStation(BaseModel):
    name: str
    distance_meters: float
    lines: list[str] = []


class BusLine(BaseModel):
    name: str
    stop_name: str
    distance_meters: float


class MobilityAnalysisOutput(BaseModel):
    metro_stations: list[MetroStation]
    bus_lines: list[BusLine]
    traffic_score: int          # 0–100
    summary: str


async def mobility_analysis(input: MobilityAnalysisInput) -> MobilityAnalysisOutput:
    """
    Analyse transit accessibility.
    Uses AMap POI search for metro & bus stops.
    Falls back to mock output when API key is not configured.
    timeout: 15s
    """
    if not settings.amap_api_key:
        return _mock_output(input)

    from tool.site._amap_client import amap_get

    metro_stations: list[MetroStation] = []
    bus_lines: list[BusLine] = []

    # --- Metro stations (type 150200) ---
    try:
        metro_data = await amap_get("/v3/place/around", {
            "location": f"{input.longitude},{input.latitude}",
            "radius": input.radius_meters,
            "types": "150200",
            "offset": 10,
            "page": 1,
        })
        for poi in metro_data.get("pois", []):
            metro_stations.append(MetroStation(
                name=poi.get("name", ""),
                distance_meters=float(poi.get("distance", 0)),
                lines=_extract_metro_lines(poi),
            ))
    except ToolError as e:
        logger.warning(f"Metro search failed: {e.message}")

    # --- Bus stops (type 150300) ---
    try:
        bus_data = await amap_get("/v3/place/around", {
            "location": f"{input.longitude},{input.latitude}",
            "radius": 500,
            "types": "150300",
            "offset": 15,
            "page": 1,
        })
        seen_lines: set[str] = set()
        for poi in bus_data.get("pois", []):
            stop_name = poi.get("name", "")
            for biz in poi.get("biz_ext", {}).get("bus_lines", []):
                line_name = biz.get("name", "")
                if line_name and line_name not in seen_lines:
                    bus_lines.append(BusLine(
                        name=line_name,
                        stop_name=stop_name,
                        distance_meters=float(poi.get("distance", 0)),
                    ))
                    seen_lines.add(line_name)
    except ToolError as e:
        logger.warning(f"Bus search failed: {e.message}")

    score = _compute_traffic_score(metro_stations, bus_lines)
    summary = _build_summary(metro_stations, bus_lines, score)
    return MobilityAnalysisOutput(
        metro_stations=metro_stations,
        bus_lines=bus_lines,
        traffic_score=score,
        summary=summary,
    )


def _extract_metro_lines(poi: dict) -> list[str]:
    """Extract metro line names from POI biz_ext."""
    lines = []
    for biz in poi.get("biz_ext", {}).get("metro_lines", []):
        name = biz.get("name", "")
        if name:
            lines.append(name)
    return lines


def _compute_traffic_score(metro: list[MetroStation], bus: list[BusLine]) -> int:
    score = 0
    # Metro score: up to 60 points
    if metro:
        closest = min(s.distance_meters for s in metro)
        if closest <= 300:
            score += 60
        elif closest <= 600:
            score += 45
        elif closest <= 1000:
            score += 30
        else:
            score += 15
    # Bus score: up to 40 points
    bus_count = len(bus)
    if bus_count >= 10:
        score += 40
    elif bus_count >= 5:
        score += 30
    elif bus_count >= 2:
        score += 20
    elif bus_count >= 1:
        score += 10
    return min(score, 100)


def _build_summary(
    metro: list[MetroStation],
    bus: list[BusLine],
    score: int,
) -> str:
    parts = []
    if metro:
        closest = min(metro, key=lambda s: s.distance_meters)
        parts.append(f"最近地铁站「{closest.name}」距离 {int(closest.distance_meters)}m")
    else:
        parts.append("1500m内无地铁站")
    if bus:
        parts.append(f"附近公交线路 {len(bus)} 条")
    parts.append(f"交通便利性评分 {score}/100")
    return "；".join(parts)


def _mock_output(input: MobilityAnalysisInput) -> MobilityAnalysisOutput:
    logger.info("mobility_analysis: AMap key not set, returning mock output")
    return MobilityAnalysisOutput(
        metro_stations=[
            MetroStation(name="某地铁站（模拟）", distance_meters=450.0, lines=["地铁X号线"]),
        ],
        bus_lines=[
            BusLine(name="公交123路（模拟）", stop_name="某公交站", distance_meters=200.0),
            BusLine(name="公交456路（模拟）", stop_name="某公交站", distance_meters=200.0),
        ],
        traffic_score=65,
        summary="最近地铁站「某地铁站（模拟）」距离 450m；附近公交线路 2 条；交通便利性评分 65/100（模拟数据）",
    )
