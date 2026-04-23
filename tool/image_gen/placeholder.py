"""Fallback placeholder image generator — grey background + watermark text.

Used when runninghub generation fails. Ensures the rendering pipeline never
blocks on image-model outages.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont


DEFAULT_SIZE = (1920, 1080)
_BG_COLOR = (200, 200, 200)
_FG_COLOR = (110, 110, 110)


def make_placeholder(
    dest: Path,
    main_text: str = "生成失败",
    subtitle: Optional[str] = None,
    size: tuple[int, int] = DEFAULT_SIZE,
) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    image = Image.new("RGB", size, _BG_COLOR)
    draw = ImageDraw.Draw(image)

    main_font = _load_font(size[1] // 12)
    sub_font = _load_font(size[1] // 28)

    _draw_centered(draw, main_text, main_font, size, y_ratio=0.42)
    if subtitle:
        _draw_centered(draw, subtitle, sub_font, size, y_ratio=0.55)

    _draw_watermark(draw, size)

    image.save(dest, format="PNG")
    return dest


def _draw_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    size: tuple[int, int],
    y_ratio: float,
) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (size[0] - text_w) // 2
    y = int(size[1] * y_ratio) - text_h // 2
    draw.text((x, y), text, fill=_FG_COLOR, font=font)


def _draw_watermark(draw: ImageDraw.ImageDraw, size: tuple[int, int]) -> None:
    wm_font = _load_font(size[1] // 48)
    draw.text(
        (size[0] - 320, size[1] - 60),
        "concept render placeholder",
        fill=(150, 150, 150),
        font=wm_font,
    )


def _load_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",      # Microsoft YaHei (has CJK)
        "C:/Windows/Fonts/simhei.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()
