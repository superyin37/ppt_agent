from pydantic import BaseModel
from typing import Optional
import httpx
from tool._base import ToolError
from config.settings import settings


class GeocodeInput(BaseModel):
    address: str
    city: Optional[str] = None


class GeocodeOutput(BaseModel):
    longitude: float
    latitude: float
    formatted_address: str
    province: str
    city: str
    district: str
    confidence: float   # 0~1


async def geocode_address(input: GeocodeInput) -> GeocodeOutput:
    """
    调用高德地图地理编码 API，将地址转换为经纬度。
    timeout: 5s
    """
    params = {
        "key": settings.amap_api_key,
        "address": input.address,
        "output": "json",
    }
    if input.city:
        params["city"] = input.city

    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(
                "https://restapi.amap.com/v3/geocode/geo",
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.TimeoutException:
            raise ToolError("NETWORK_ERROR", "地理编码请求超时", retryable=True)
        except httpx.HTTPError as e:
            raise ToolError("NETWORK_ERROR", f"地理编码网络错误: {e}", retryable=True)

    if data.get("status") != "1" or not data.get("geocodes"):
        raise ToolError("ADDRESS_NOT_FOUND", f"地址 '{input.address}' 无法解析", retryable=False)

    geo = data["geocodes"][0]
    lng_str, lat_str = geo["location"].split(",")

    # 置信度从 level 字段估算
    level_confidence = {
        "省": 0.3, "市": 0.5, "区县": 0.65,
        "开发区": 0.7, "乡镇": 0.75, "村庄": 0.8,
        "道路": 0.85, "兴趣点": 0.9, "门牌号": 0.95,
    }
    confidence = level_confidence.get(geo.get("level", ""), 0.6)

    return GeocodeOutput(
        longitude=float(lng_str),
        latitude=float(lat_str),
        formatted_address=geo.get("formatted_address", input.address),
        province=geo.get("province", ""),
        city=geo.get("city", "") or geo.get("province", ""),
        district=geo.get("district", ""),
        confidence=confidence,
    )
