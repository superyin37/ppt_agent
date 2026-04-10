"""
Map annotation tool — Phase 6
Generates annotated map images via AMap static map API.
Falls back to a blank placeholder when API key is not configured.
"""
import io
import logging
from typing import Optional
from pydantic import BaseModel
from tool._base import ToolError
from config.settings import settings

logger = logging.getLogger(__name__)

AMAP_STATIC_URL = "https://restapi.amap.com/v3/staticmap"

# Marker colour map (AMap colour names)
ICON_COLOR_MAP = {
    "red":    "0xFF3B30",
    "blue":   "0x1a56db",
    "green":  "0x0e9f6e",
    "yellow": "0xF59E0B",
    "purple": "0x9061f9",
}


class AnnotationItem(BaseModel):
    longitude: float
    latitude: float
    label: str = ""
    color: str = "blue"         # red / blue / green / yellow / purple
    icon: Optional[str] = None  # custom icon URL (optional)


class MapAnnotationInput(BaseModel):
    center_lng: float
    center_lat: float
    zoom: int = 14
    width_px: int = 800
    height_px: int = 600
    annotations: list[AnnotationItem] = []
    map_style: str = "light"    # light / dark / satellite


class MapAnnotationOutput(BaseModel):
    image_bytes: bytes
    image_format: str = "png"


async def map_annotation(input: MapAnnotationInput) -> MapAnnotationOutput:
    """
    Fetch annotated static map from AMap.
    Falls back to blank placeholder when API key not configured.
    timeout: 15s
    """
    if not settings.amap_api_key:
        return _placeholder_map(input)

    import httpx

    params = _build_params(input, settings.amap_api_key)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(AMAP_STATIC_URL, params=params)
            resp.raise_for_status()
            # Success response is image bytes; error is JSON
            content_type = resp.headers.get("content-type", "")
            if "image" in content_type:
                return MapAnnotationOutput(image_bytes=resp.content)
            # API returned an error in JSON
            data = resp.json()
            info = data.get("info", "unknown")
            raise ToolError("AMAP_MAP_ERROR", f"静态地图API错误: {info}", retryable=False)
    except httpx.TimeoutException:
        raise ToolError("AMAP_TIMEOUT", "静态地图API超时", retryable=True)
    except ToolError:
        raise
    except Exception as e:
        raise ToolError("AMAP_MAP_ERROR", f"静态地图请求失败: {e}", retryable=True)


def _build_params(input: MapAnnotationInput, api_key: str) -> dict:
    params: dict = {
        "key": api_key,
        "location": f"{input.center_lng},{input.center_lat}",
        "zoom": input.zoom,
        "size": f"{input.width_px}*{input.height_px}",
        "scale": 1,
    }

    # Map style
    if input.map_style == "satellite":
        params["mapstyle"] = "amap://styles/satellite"
    elif input.map_style == "dark":
        params["mapstyle"] = "amap://styles/dark"

    # Markers
    markers_parts = []
    for ann in input.annotations[:20]:  # AMap max 20 markers
        color = ICON_COLOR_MAP.get(ann.color, ICON_COLOR_MAP["blue"])
        label = ann.label[:8] if ann.label else ""  # AMap label max 8 chars
        # Format: mid,color,label:lng,lat
        markers_parts.append(
            f"mid,{color},{label}:{ann.longitude},{ann.latitude}"
        )
    if markers_parts:
        params["markers"] = "|".join(markers_parts)

    return params


def _placeholder_map(input: MapAnnotationInput) -> MapAnnotationOutput:
    """Generate a blank grey PNG placeholder when API key is not set."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches

        fig, ax = plt.subplots(figsize=(input.width_px / 96, input.height_px / 96), dpi=96)
        ax.set_facecolor("#e5e7eb")
        fig.patch.set_facecolor("#e5e7eb")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")

        # Draw site marker
        ax.plot(0.5, 0.5, "s", markersize=14, color="#1a56db", zorder=5)
        ax.text(0.5, 0.55, "项目地块", ha="center", va="bottom", fontsize=11,
                color="#111827", fontweight="bold")

        # Draw annotation markers
        _MCOLOR = {"red": "#FF3B30", "blue": "#1a56db", "green": "#0e9f6e",
                   "yellow": "#F59E0B", "purple": "#9061f9"}
        for i, ann in enumerate(input.annotations[:5]):
            x = 0.3 + (i % 3) * 0.15
            y = 0.3 + (i // 3) * 0.2
            ax.plot(x, y, "o", markersize=8, color=_MCOLOR.get(ann.color, "#1a56db"))
            ax.text(x, y + 0.04, ann.label[:6], ha="center", fontsize=8, color="#374151")

        ax.text(0.5, 0.08, f"[地图预览 — 请配置 AMAP_API_KEY]",
                ha="center", fontsize=9, color="#9ca3af")

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=96, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        logger.info("map_annotation: AMap key not set, returning placeholder image")
        return MapAnnotationOutput(image_bytes=buf.read())
    except ImportError:
        # If matplotlib also missing, return a 1×1 transparent PNG
        empty_png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
            b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        return MapAnnotationOutput(image_bytes=empty_png)
