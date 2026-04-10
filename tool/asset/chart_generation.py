"""
Chart generation tool — Phase 6
Generates statistical charts (bar/line/pie/radar) using matplotlib.
Pure local rendering, no network dependencies.
"""
import io
import logging
from typing import Optional
from pydantic import BaseModel
from tool._base import ToolError

logger = logging.getLogger(__name__)

# Design system colour palettes (matches tokens.css)
COLOR_SCHEMES: dict[str, list[str]] = {
    "primary":    ["#1a56db", "#0e9f6e", "#e74694", "#ff5a1f", "#9061f9"],
    "secondary":  ["#6b7280", "#374151", "#9ca3af", "#4b5563", "#d1d5db"],
    "monochrome": ["#111827", "#374151", "#6b7280", "#9ca3af", "#d1d5db"],
    "warm":       ["#c2410c", "#ea580c", "#fb923c", "#fdba74", "#fed7aa"],
}


class ChartGenerationInput(BaseModel):
    chart_type: str             # bar / line / pie / radar
    title: str
    data: list[dict]            # [{label, value} | {x, y}]
    x_label: Optional[str] = None
    y_label: Optional[str] = None
    color_scheme: str = "primary"
    width_px: int = 800
    height_px: int = 500


class ChartGenerationOutput(BaseModel):
    image_bytes: bytes
    image_format: str = "png"
    data_json: dict


def chart_generation(input: ChartGenerationInput) -> ChartGenerationOutput:
    """
    Render chart as PNG bytes using matplotlib.
    timeout: 10s
    """
    try:
        import matplotlib
        matplotlib.use("Agg")   # non-interactive backend
        import matplotlib.pyplot as plt
        import matplotlib.font_manager as fm
    except ImportError:
        raise ToolError("MISSING_DEPENDENCY", "matplotlib not installed", retryable=False)

    colors = COLOR_SCHEMES.get(input.color_scheme, COLOR_SCHEMES["primary"])
    dpi = 96
    w = input.width_px / dpi
    h = input.height_px / dpi

    fig, ax = plt.subplots(figsize=(w, h), dpi=dpi)
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#f9fafb")
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(colors="#6b7280")
    for spine in ["bottom", "left"]:
        ax.spines[spine].set_color("#e5e7eb")

    chart_type = input.chart_type.lower()

    if chart_type == "bar":
        _render_bar(ax, input.data, colors)
    elif chart_type == "line":
        _render_line(ax, input.data, colors)
    elif chart_type == "pie":
        _render_pie(ax, input.data, colors)
    elif chart_type == "radar":
        plt.close(fig)
        fig = _render_radar(input.data, colors, dpi, w, h)
    else:
        raise ToolError("UNKNOWN_CHART_TYPE", f"不支持的图表类型: {chart_type}", retryable=False)

    # Labels
    if chart_type not in ("pie", "radar"):
        ax.set_title(input.title, fontsize=14, color="#111827", pad=12)
        if input.x_label:
            ax.set_xlabel(input.x_label, color="#6b7280")
        if input.y_label:
            ax.set_ylabel(input.y_label, color="#6b7280")

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    image_bytes = buf.read()

    return ChartGenerationOutput(
        image_bytes=image_bytes,
        image_format="png",
        data_json={"chart_type": chart_type, "title": input.title, "data": input.data},
    )


def _render_bar(ax, data: list[dict], colors: list[str]):
    labels = [str(d.get("label", d.get("x", i))) for i, d in enumerate(data)]
    values = [float(d.get("value", d.get("y", 0))) for d in data]
    bar_colors = [colors[i % len(colors)] for i in range(len(labels))]
    bars = ax.bar(labels, values, color=bar_colors, width=0.6, zorder=3)
    ax.yaxis.grid(True, color="#e5e7eb", zorder=0)
    # Value labels on bars
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(values) * 0.01,
            f"{val:,.0f}",
            ha="center", va="bottom", fontsize=9, color="#374151",
        )


def _render_line(ax, data: list[dict], colors: list[str]):
    # Support multiple series: [{series: str, points: [{x, y}]}] or flat [{x, y}]
    if data and "series" in data[0]:
        for i, series in enumerate(data):
            pts = series.get("points", [])
            xs = [str(p.get("x", i)) for i, p in enumerate(pts)]
            ys = [float(p.get("y", 0)) for p in pts]
            ax.plot(xs, ys, marker="o", color=colors[i % len(colors)],
                    linewidth=2, label=series.get("series", f"系列{i+1}"))
        ax.legend(framealpha=0.8)
    else:
        xs = [str(d.get("x", d.get("label", i))) for i, d in enumerate(data)]
        ys = [float(d.get("y", d.get("value", 0))) for d in data]
        ax.plot(xs, ys, marker="o", color=colors[0], linewidth=2)
    ax.yaxis.grid(True, color="#e5e7eb", zorder=0)


def _render_pie(ax, data: list[dict], colors: list[str]):
    labels = [str(d.get("label", d.get("x", i))) for i, d in enumerate(data)]
    values = [float(d.get("value", d.get("y", 0))) for d in data]
    pie_colors = [colors[i % len(colors)] for i in range(len(labels))]
    ax.pie(values, labels=labels, colors=pie_colors, autopct="%1.1f%%",
           startangle=90, pctdistance=0.8)
    ax.set_aspect("equal")


def _render_radar(data: list[dict], colors: list[str], dpi, w, h):
    import numpy as np
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch

    labels = [str(d.get("label", d.get("x", i))) for i, d in enumerate(data)]
    values = [float(d.get("value", d.get("y", 0))) for d in data]
    n = len(labels)
    if n < 3:
        # Fallback to bar if not enough points for radar
        fig, ax = plt.subplots(figsize=(w, h), dpi=dpi)
        _render_bar(ax, data, colors)
        return fig

    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    values_plot = values + [values[0]]
    angles_plot = angles + [angles[0]]

    fig, ax = plt.subplots(figsize=(w, h), dpi=dpi, subplot_kw=dict(polar=True))
    fig.patch.set_facecolor("#ffffff")
    ax.plot(angles_plot, values_plot, color=colors[0], linewidth=2)
    ax.fill(angles_plot, values_plot, color=colors[0], alpha=0.25)
    ax.set_xticks(angles)
    ax.set_xticklabels(labels, color="#374151")
    ax.set_facecolor("#f9fafb")
    return fig
