import math
from pydantic import BaseModel
from typing import Optional


class NormalizePolygonInput(BaseModel):
    geojson: dict   # GeoJSON Polygon


class NormalizePolygonOutput(BaseModel):
    geojson: dict
    area_sqm: float
    perimeter_m: float
    centroid_lng: float
    centroid_lat: float


def _haversine_distance(p1: list[float], p2: list[float]) -> float:
    """计算两点之间的球面距离（米）"""
    R = 6_371_000
    lng1, lat1 = math.radians(p1[0]), math.radians(p1[1])
    lng2, lat2 = math.radians(p2[0]), math.radians(p2[1])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _polygon_area_sqm(coords: list[list[float]]) -> float:
    """使用 Shoelace 公式（平面近似）计算面积"""
    # 转换为米坐标（中心投影近似）
    if not coords:
        return 0.0
    lat_rad = math.radians(sum(c[1] for c in coords) / len(coords))
    m_per_deg_lat = 111_320
    m_per_deg_lng = 111_320 * math.cos(lat_rad)

    pts = [(c[0] * m_per_deg_lng, c[1] * m_per_deg_lat) for c in coords]
    n = len(pts)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += pts[i][0] * pts[j][1]
        area -= pts[j][0] * pts[i][1]
    return abs(area) / 2


def normalize_polygon(input: NormalizePolygonInput) -> NormalizePolygonOutput:
    """
    验证并标准化 GeoJSON Polygon，计算面积和周长。
    纯本地计算，无网络依赖。
    """
    geojson = input.geojson
    if geojson.get("type") != "Polygon":
        raise ValueError("geojson 必须为 Polygon 类型")

    rings = geojson.get("coordinates", [])
    if not rings:
        raise ValueError("Polygon 坐标为空")

    outer_ring = rings[0]

    # 确保环闭合
    if outer_ring[0] != outer_ring[-1]:
        outer_ring = outer_ring + [outer_ring[0]]

    geojson = {**geojson, "coordinates": [outer_ring] + rings[1:]}

    area = _polygon_area_sqm(outer_ring[:-1])

    perimeter = sum(
        _haversine_distance(outer_ring[i], outer_ring[i + 1])
        for i in range(len(outer_ring) - 1)
    )

    centroid_lng = sum(c[0] for c in outer_ring[:-1]) / (len(outer_ring) - 1)
    centroid_lat = sum(c[1] for c in outer_ring[:-1]) / (len(outer_ring) - 1)

    return NormalizePolygonOutput(
        geojson=geojson,
        area_sqm=round(area, 2),
        perimeter_m=round(perimeter, 2),
        centroid_lng=round(centroid_lng, 7),
        centroid_lat=round(centroid_lat, 7),
    )
