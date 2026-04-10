"""
Render Exporter — Phase 7
Playwright-based screenshot + PDF export.
Falls back to HTML-to-file when Playwright is unavailable.
"""
import io
import logging
import tempfile
import os
from pathlib import Path

logger = logging.getLogger(__name__)


async def screenshot_slide(
    html: str,
    width_px: int = 1920,
    height_px: int = 1080,
) -> bytes:
    """
    Render HTML to PNG bytes using Playwright headless Chromium.
    Falls back to a blank placeholder PNG if Playwright is not installed.
    timeout: 30s
    """
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": width_px, "height": height_px})

            # Write HTML to a temp file and navigate to it via file:// protocol
            # so that Chromium allows loading other file:// resources (local images).
            tmp = tempfile.NamedTemporaryFile(
                suffix=".html", delete=False, mode="w", encoding="utf-8",
            )
            try:
                tmp.write(html)
                tmp.close()
                file_url = Path(tmp.name).as_uri()
                await page.goto(file_url, wait_until="networkidle")
                await page.wait_for_timeout(500)
                screenshot = await page.screenshot(
                    type="png",
                    clip={"x": 0, "y": 0, "width": width_px, "height": height_px},
                )
            finally:
                os.unlink(tmp.name)

            await browser.close()
            return screenshot
    except ImportError:
        logger.warning("playwright not installed — returning placeholder PNG")
        return _blank_placeholder_png(width_px, height_px)
    except Exception as e:
        logger.error(f"screenshot_slide failed: {e}")
        return _blank_placeholder_png(width_px, height_px)


async def _screenshot_one_page(browser, html: str, width_px: int, height_px: int) -> bytes:
    """Take a screenshot using a new tab on an existing browser (no extra launch)."""
    page = await browser.new_page(viewport={"width": width_px, "height": height_px})
    tmp = tempfile.NamedTemporaryFile(
        suffix=".html", delete=False, mode="w", encoding="utf-8",
    )
    try:
        tmp.write(html)
        tmp.close()
        file_url = Path(tmp.name).as_uri()
        await page.goto(file_url, wait_until="networkidle")
        await page.wait_for_timeout(500)
        screenshot = await page.screenshot(
            type="png",
            clip={"x": 0, "y": 0, "width": width_px, "height": height_px},
        )
    finally:
        os.unlink(tmp.name)
        await page.close()
    return screenshot


async def screenshot_slides_batch(
    html_list: list[str],
    width_px: int = 1920,
    height_px: int = 1080,
    concurrency: int = 4,
) -> list[bytes]:
    """
    Batch-screenshot multiple slides using ONE browser instance.
    Runs up to `concurrency` tabs in parallel via asyncio.Semaphore.
    Returns a list of PNG bytes in the same order as html_list.
    """
    import asyncio

    if not html_list:
        return []

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning("playwright not installed — returning placeholder PNGs")
        return [_blank_placeholder_png(width_px, height_px) for _ in html_list]

    sem = asyncio.Semaphore(concurrency)

    async def _guarded(browser, html: str) -> bytes:
        async with sem:
            try:
                return await _screenshot_one_page(browser, html, width_px, height_px)
            except Exception as e:
                logger.error(f"screenshot_slides_batch tab error: {e}")
                return _blank_placeholder_png(width_px, height_px)

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            results = await asyncio.gather(
                *[_guarded(browser, html) for html in html_list]
            )
            await browser.close()
        return list(results)
    except Exception as e:
        logger.error(f"screenshot_slides_batch failed: {e}")
        return [_blank_placeholder_png(width_px, height_px) for _ in html_list]


async def compile_pdf(screenshot_bytes_list: list[bytes]) -> bytes:
    """
    Combine multiple PNG screenshots into a single PDF.
    Uses Playwright to compose an HTML wrapper → PDF export.
    Falls back to concatenating as a simple multi-page PDF via PIL/Pillow.
    timeout: 120s
    """
    if not screenshot_bytes_list:
        raise ValueError("No screenshots provided for PDF compilation")

    try:
        return await _compile_pdf_playwright(screenshot_bytes_list)
    except Exception as e:
        logger.warning(f"Playwright PDF compile failed ({e}), trying Pillow fallback")
        return _compile_pdf_pillow(screenshot_bytes_list)


async def _compile_pdf_playwright(screenshot_bytes_list: list[bytes]) -> bytes:
    """Build a PDF from a list of PNG bytes using Playwright's pdf() API."""
    import base64
    from playwright.async_api import async_playwright

    # Embed each screenshot as a base64 data URL
    slides_html = "\n".join([
        f'<div style="page-break-after: always; width: 1920px; height: 1080px; overflow: hidden;">'
        f'<img src="data:image/png;base64,{base64.b64encode(png).decode()}" '
        f'style="width: 100%; height: 100%; object-fit: contain;"></div>'
        for png in screenshot_bytes_list
    ])
    full_html = f"""<!DOCTYPE html>
<html><head>
<style>
  @page {{ size: 1920px 1080px; margin: 0; }}
  body {{ margin: 0; padding: 0; background: white; }}
  div {{ width: 1920px; height: 1080px; overflow: hidden; }}
  img {{ display: block; width: 100%; height: 100%; }}
</style>
</head><body>{slides_html}</body></html>"""

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        await page.set_content(full_html, wait_until="load")
        pdf_bytes = await page.pdf(
            width="1920px", height="1080px",
            print_background=True,
        )
        await browser.close()
    return pdf_bytes


def _compile_pdf_pillow(screenshot_bytes_list: list[bytes]) -> bytes:
    """Fallback PDF compilation using Pillow."""
    try:
        from PIL import Image
        images = []
        for png_bytes in screenshot_bytes_list:
            img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
            images.append(img)
        buf = io.BytesIO()
        if len(images) == 1:
            images[0].save(buf, format="PDF")
        else:
            images[0].save(buf, format="PDF", save_all=True, append_images=images[1:])
        buf.seek(0)
        return buf.read()
    except ImportError:
        raise RuntimeError("Neither playwright nor Pillow is available for PDF compilation")


def _blank_placeholder_png(width: int, height: int) -> bytes:
    """Generate a blank grey PNG as a rendering placeholder."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        dpi = 96
        fig, ax = plt.subplots(figsize=(width / dpi, height / dpi), dpi=dpi)
        ax.set_facecolor("#f3f4f6")
        fig.patch.set_facecolor("#f3f4f6")
        ax.axis("off")
        ax.text(0.5, 0.5, "Slide Rendering Placeholder\n(Playwright not available)",
                ha="center", va="center", fontsize=24, color="#9ca3af",
                transform=ax.transAxes)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf.read()
    except Exception:
        # Minimal 1×1 white PNG
        return (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
            b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
