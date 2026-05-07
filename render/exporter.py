"""
Render Exporter - Phase 7
Chrome/Chromium-based screenshot + PDF export.
Falls back to placeholders/Pillow when browser rendering is unavailable.
"""
import io
import logging
import tempfile
import os
import asyncio
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)
_REPO_ROOT = Path(__file__).resolve().parents[1]
_BROWSER_RENDER_TMP = _REPO_ROOT / "tmp" / "browser_render"


def _ensure_browser_tmp() -> Path:
    _BROWSER_RENDER_TMP.mkdir(parents=True, exist_ok=True)
    return _BROWSER_RENDER_TMP


def _write_temp_html(html: str) -> Path:
    tmp_dir = _ensure_browser_tmp()
    fd, name = tempfile.mkstemp(suffix=".html", prefix="slide_", dir=tmp_dir)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(html)
    return Path(name)


def _new_temp_dir(prefix: str) -> Path:
    tmp_dir = _ensure_browser_tmp()
    return Path(tempfile.mkdtemp(prefix=prefix, dir=tmp_dir))


def _find_chromium_executables() -> list[Path]:
    """Return browser executables in preference order for local HTML rendering."""
    candidates: list[Path] = []

    for env_name in ("CHROME_EXECUTABLE", "CHROMIUM_EXECUTABLE", "HTML_RENDERER_CHROME"):
        value = os.environ.get(env_name)
        if value:
            candidates.append(Path(value))

    if os.name == "nt":
        program_files = [
            os.environ.get("PROGRAMFILES"),
            os.environ.get("PROGRAMFILES(X86)"),
            os.environ.get("LOCALAPPDATA"),
        ]
        for root in filter(None, program_files):
            base = Path(root)
            candidates.extend([
                base / "Google" / "Chrome" / "Application" / "chrome.exe",
                base / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            ])

        # Keep Playwright-managed Chromium as a last resort on Windows. Some
        # sandboxed environments can launch system Chrome but hang on CFT.
        browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
        browsers_root = Path(browsers_path) if browsers_path else Path()
        if not browsers_path:
            local_app_data = os.environ.get("LOCALAPPDATA")
            browsers_root = Path(local_app_data) / "ms-playwright" if local_app_data else Path()
        if browsers_root:
            candidates.extend(sorted(
                browsers_root.glob("chromium-*/chrome-win*/chrome.exe"),
                reverse=True,
            ))
    else:
        for name in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge"):
            found = shutil.which(name)
            if found:
                candidates.append(Path(found))

    seen: set[str] = set()
    existing: list[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        key = str(resolved).lower() if os.name == "nt" else str(resolved)
        if key not in seen and resolved.exists():
            seen.add(key)
            existing.append(resolved)
    return existing


def _chromium_base_args(profile_dir: Path) -> list[str]:
    return [
        "--headless=new",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--disable-background-networking",
        "--disable-breakpad",
        "--disable-crash-reporter",
        "--no-first-run",
        "--no-default-browser-check",
        "--no-sandbox",
        "--allow-file-access-from-files",
        f"--user-data-dir={profile_dir}",
    ]


def _run_chromium_once(chrome: Path, args: list[str], timeout_s: int) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [str(chrome), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_s,
        check=False,
    )


def _render_with_chromium_cli(args: list[str], timeout_s: int) -> tuple[Path, subprocess.CompletedProcess[bytes]]:
    errors: list[str] = []
    for chrome in _find_chromium_executables():
        profile_dir = _new_temp_dir("chrome_profile_")
        try:
            result = _run_chromium_once(
                chrome,
                [*_chromium_base_args(profile_dir), *args],
                timeout_s,
            )
        except subprocess.TimeoutExpired:
            errors.append(f"{chrome}: timed out after {timeout_s}s")
            continue
        finally:
            shutil.rmtree(profile_dir, ignore_errors=True)
        if result.returncode == 0:
            return chrome, result
        stderr = result.stderr[-1000:].decode("utf-8", errors="replace").replace("\r", " ")
        errors.append(f"{chrome}: exit {result.returncode}; {stderr}")
    if not errors:
        raise RuntimeError("No Chrome/Chromium executable found for HTML rendering")
    raise RuntimeError("Chrome/Chromium rendering failed: " + " | ".join(errors))


async def screenshot_slide(
    html: str,
    width_px: int = 1920,
    height_px: int = 1080,
) -> bytes:
    """
    Render HTML to PNG bytes using headless Chrome/Chromium.
    Falls back to a blank placeholder PNG if no browser can render it.
    timeout: 30s
    """
    try:
        return await asyncio.to_thread(_screenshot_slide_sync, html, width_px, height_px)
    except Exception as e:
        logger.error(f"screenshot_slide failed: {e}")
        return _blank_placeholder_png(width_px, height_px)


def _screenshot_slide_sync(html: str, width_px: int, height_px: int) -> bytes:
    tmp_path = _write_temp_html(html)
    screenshot_fd, screenshot_name = tempfile.mkstemp(
        suffix=".png",
        prefix="slide_",
        dir=_ensure_browser_tmp(),
    )
    os.close(screenshot_fd)
    screenshot_path = Path(screenshot_name)
    try:
        args = [
            f"--window-size={width_px},{height_px}",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=1500",
            f"--screenshot={screenshot_path}",
            tmp_path.as_uri(),
        ]
        chrome, _ = _render_with_chromium_cli(args, timeout_s=30)
        if not screenshot_path.exists() or screenshot_path.stat().st_size == 0:
            raise RuntimeError(f"{chrome} did not create screenshot output")
        return screenshot_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)
        screenshot_path.unlink(missing_ok=True)


async def screenshot_slides_batch(
    html_list: list[str],
    width_px: int = 1920,
    height_px: int = 1080,
    concurrency: int = 4,
) -> list[bytes]:
    """
    Batch-screenshot multiple slides using one browser instance.

    The `concurrency` argument is kept for API compatibility. The implementation
    uses Chrome's CLI path to avoid Playwright driver subprocess pipe failures on
    Windows.
    """
    if not html_list:
        return []

    try:
        return await asyncio.to_thread(
            _screenshot_slides_batch_sync,
            html_list,
            width_px,
            height_px,
        )
    except Exception as e:
        logger.error(f"screenshot_slides_batch failed: {e}")
        return [_blank_placeholder_png(width_px, height_px) for _ in html_list]


def _screenshot_slides_batch_sync(
    html_list: list[str],
    width_px: int,
    height_px: int,
) -> list[bytes]:
    results: list[bytes] = []
    for html in html_list:
        try:
            results.append(_screenshot_slide_sync(html, width_px, height_px))
        except Exception as e:
            logger.error(f"screenshot_slides_batch item error: {e}")
            results.append(_blank_placeholder_png(width_px, height_px))
    return results


async def compile_pdf(screenshot_bytes_list: list[bytes]) -> bytes:
    """
    Combine multiple PNG screenshots into a single PDF.
    Uses Chrome/Chromium to compose an HTML wrapper and export PDF.
    Falls back to concatenating as a simple multi-page PDF via PIL/Pillow.
    timeout: 120s
    """
    if not screenshot_bytes_list:
        raise ValueError("No screenshots provided for PDF compilation")

    try:
        return await _compile_pdf_chromium(screenshot_bytes_list)
    except Exception as e:
        logger.warning(f"Chrome PDF compile failed ({e}), trying Pillow fallback")
        return _compile_pdf_pillow(screenshot_bytes_list)


async def _compile_pdf_chromium(screenshot_bytes_list: list[bytes]) -> bytes:
    """Build a PDF from a list of PNG bytes using Chrome's PDF API."""
    return await asyncio.to_thread(_compile_pdf_chromium_sync, screenshot_bytes_list)


def _compile_pdf_chromium_sync(screenshot_bytes_list: list[bytes]) -> bytes:
    """Build a PDF from a list of PNG bytes using Chrome's headless CLI."""
    import base64

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

    tmp_path = _write_temp_html(full_html)
    pdf_fd, pdf_name = tempfile.mkstemp(
        suffix=".pdf",
        prefix="slides_",
        dir=_ensure_browser_tmp(),
    )
    os.close(pdf_fd)
    pdf_path = Path(pdf_name)
    try:
        args = [
            "--print-to-pdf-no-header",
            f"--print-to-pdf={pdf_path}",
            tmp_path.as_uri(),
        ]
        chrome, _ = _render_with_chromium_cli(args, timeout_s=60)
        if not pdf_path.exists() or pdf_path.stat().st_size == 0:
            raise RuntimeError(f"{chrome} did not create PDF output")
        return pdf_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)
        pdf_path.unlink(missing_ok=True)


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
        raise RuntimeError("Neither Chrome/Chromium nor Pillow is available for PDF compilation")


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
        ax.text(0.5, 0.5, "Slide Rendering Placeholder\n(Chrome not available)",
                ha="center", va="center", fontsize=24, color="#9ca3af",
                transform=ax.transAxes)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf.read()
    except Exception:
        # Minimal 1x1 white PNG
        return (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
            b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
