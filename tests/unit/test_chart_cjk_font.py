"""Unit tests for CJK font setup in chart_generation (ADR-006).

The chart_generation tool must:
- Probe matplotlib's font list once on first call
- Configure font.sans-serif if a CJK font is present
- Emit a clear warning (but not raise) if none is present
- Render charts with Chinese labels successfully when a CJK font is available
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tool.asset import chart_generation as cg
from tool.asset.chart_generation import (
    ChartGenerationInput,
    chart_generation,
    _ensure_cjk_font_configured,
)


@pytest.fixture(autouse=True)
def _reset_probe_cache():
    cg._cjk_font_resolved = None
    cg._cjk_probe_done = False
    yield
    cg._cjk_font_resolved = None
    cg._cjk_probe_done = False


class _Font:
    def __init__(self, name):
        self.name = name


def test_cjk_font_picked_when_available():
    import matplotlib
    import matplotlib.font_manager as fm

    fake_fonts = [_Font("Arial"), _Font("Microsoft YaHei"), _Font("Comic Sans MS")]
    with patch.object(fm.fontManager, "ttflist", fake_fonts):
        chosen = _ensure_cjk_font_configured()
    assert chosen == "Microsoft YaHei"
    assert "Microsoft YaHei" in matplotlib.rcParams["font.sans-serif"]
    assert matplotlib.rcParams["axes.unicode_minus"] is False


def test_cjk_probe_is_idempotent():
    import matplotlib.font_manager as fm

    fake_fonts = [_Font("PingFang SC")]
    with patch.object(fm.fontManager, "ttflist", fake_fonts):
        first = _ensure_cjk_font_configured()
    # Second call must not re-scan; even with empty ttflist the cache wins.
    with patch.object(fm.fontManager, "ttflist", []):
        second = _ensure_cjk_font_configured()
    assert first == "PingFang SC"
    assert second == "PingFang SC"


def test_no_cjk_font_logs_warning_and_returns_none(caplog):
    import matplotlib.font_manager as fm

    fake_fonts = [_Font("Arial"), _Font("DejaVu Sans")]
    with patch.object(fm.fontManager, "ttflist", fake_fonts):
        with caplog.at_level("WARNING"):
            chosen = _ensure_cjk_font_configured()
    assert chosen is None
    assert any("no CJK font found" in rec.message for rec in caplog.records)


def test_chart_generation_with_chinese_labels_does_not_crash():
    """Smoke: even on systems with no CJK font, chart_generation must still
    produce PNG bytes (just with tofu glyphs). Never raise."""
    out = chart_generation(ChartGenerationInput(
        chart_type="bar",
        title="政策影响矩阵",
        data=[
            {"label": "用地", "value": 90},
            {"label": "业态", "value": 60},
            {"label": "运营", "value": 35},
        ],
        x_label="维度",
        y_label="影响程度",
    ))
    assert out.image_format == "png"
    assert len(out.image_bytes) > 1000
    assert out.image_bytes[:8].startswith(b"\x89PNG")


def test_chart_generation_writes_actual_png_to_disk(tmp_path):
    out = chart_generation(ChartGenerationInput(
        chart_type="pie",
        title="POI 业态构成",
        data=[
            {"label": "餐饮", "value": 12},
            {"label": "零售", "value": 8},
            {"label": "交通", "value": 5},
        ],
    ))
    p = tmp_path / "poi.png"
    p.write_bytes(out.image_bytes)
    assert p.stat().st_size > 1000
