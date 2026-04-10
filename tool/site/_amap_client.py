"""
Unified AMap (Gaode) REST API client.
All site tools share this module for HTTP calls + error handling.
"""
import logging
import httpx
from tool._base import ToolError
from config.settings import settings

logger = logging.getLogger(__name__)

AMAP_BASE = "https://restapi.amap.com"


async def amap_get(endpoint: str, params: dict) -> dict:
    """
    Execute a GET request to the AMap REST API.
    Raises ToolError on API-level errors or HTTP failures.
    timeout: 10s
    """
    params = dict(params)   # copy
    params["key"] = settings.amap_api_key

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{AMAP_BASE}{endpoint}", params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        raise ToolError("AMAP_TIMEOUT", "高德地图 API 超时", retryable=True)
    except httpx.HTTPStatusError as e:
        raise ToolError("AMAP_HTTP_ERROR", f"高德地图 HTTP 错误: {e.response.status_code}", retryable=True)
    except Exception as e:
        raise ToolError("AMAP_NETWORK_ERROR", f"高德地图网络错误: {e}", retryable=True)

    if str(data.get("status")) != "1":
        info = data.get("info", "unknown")
        infocode = data.get("infocode", "")
        if infocode in ("10003", "10004"):
            raise ToolError("API_LIMIT_EXCEEDED", f"高德API配额超限: {info}", retryable=False)
        raise ToolError("AMAP_API_ERROR", f"高德API错误: {info} ({infocode})", retryable=False)

    return data
