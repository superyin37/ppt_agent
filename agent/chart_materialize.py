"""Local chart materialization for template mode.

This is intentionally small: it wraps the existing matplotlib-based
`tool.asset.chart_generation` helper and writes a PNG under repo-local `tmp/`.
The later chart brief can expand this with font probing and DB Asset backfill.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from tool.asset.chart_generation import ChartGenerationInput, chart_generation

logger = logging.getLogger(__name__)


def materialize_chart_png(
    *,
    chart_type: str,
    title: str,
    data: list[dict],
    output_path: Path,
    x_label: Optional[str] = None,
    y_label: Optional[str] = None,
) -> Optional[str]:
    if not data:
        return None

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result = chart_generation(
            ChartGenerationInput(
                chart_type=chart_type,
                title=title,
                data=data,
                x_label=x_label,
                y_label=y_label,
                color_scheme="monochrome",
                width_px=960,
                height_px=540,
            )
        )
        output_path.write_bytes(result.image_bytes)
        return str(output_path)
    except Exception as exc:
        logger.warning("chart materialization failed for %s: %s", title, exc)
        return None
