"""Jinja2 environment for template-mode rendering (ADR-006).

The environment loads from `templates/packs/<pack_name>/` and exposes one
custom filter, `embed_image`, that resolves either:

- a UUID-as-str → looks up Asset.image_url in DB (deferred — caller injects
  resolver via `set_asset_resolver`), or
- a filesystem path → returned as `file://...` URI.

When resolution fails (missing UUID, file does not exist, resolver crash),
the filter returns an inline SVG data URI with a visible "missing asset"
label so the screenshot shows a debuggable grey block instead of a broken
`<img>` icon. Every failure is logged with enough context to trace which
slide/asset caused it.

Returns environments are cached per pack so we don't pay loader setup cost
on every slide.
"""
from __future__ import annotations

import base64
import logging
import threading
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import unquote, urlparse
from uuid import UUID

from jinja2 import (
    ChoiceLoader,
    Environment,
    FileSystemLoader,
    StrictUndefined,
    select_autoescape,
)

logger = logging.getLogger(__name__)


# Repository root is two levels up from this file (render/jinja_env.py).
_REPO_ROOT = Path(__file__).resolve().parents[1]
_PACKS_ROOT = _REPO_ROOT / "templates" / "packs"

_env_cache: dict[str, Environment] = {}
_env_lock = threading.Lock()

# Asset resolver injected by the renderer (avoids importing DB code here).
# Signature: (asset_id_or_path: str) -> str (file:// URL or http:// URL).
_asset_resolver: Optional[Callable[[str], str]] = None


def set_asset_resolver(fn: Callable[[str], str]) -> None:
    """Inject the asset id → URL resolver. Idempotent. Safe to call repeatedly."""
    global _asset_resolver
    _asset_resolver = fn


def get_jinja_env(pack_name: str) -> Environment:
    """Return a (cached) Environment for the given template pack.

    Uses StrictUndefined so missing context keys fail loudly during rendering
    rather than silently producing empty strings — important for catching
    SlideData ↔ template drift.
    """
    with _env_lock:
        env = _env_cache.get(pack_name)
        if env is not None:
            return env

        pack_dir = _PACKS_ROOT / pack_name
        if not pack_dir.is_dir():
            raise FileNotFoundError(
                f"template pack not found: {pack_dir} (looked in {_PACKS_ROOT})"
            )

        env = Environment(
            loader=ChoiceLoader([
                FileSystemLoader(str(pack_dir / "components")),
                FileSystemLoader(str(pack_dir)),
            ]),
            autoescape=select_autoescape(["html", "j2"]),
            trim_blocks=True,
            lstrip_blocks=True,
            undefined=StrictUndefined,
        )
        env.filters["embed_image"] = _embed_image_filter
        _env_cache[pack_name] = env
        return env


def list_components(pack_name: str) -> list[str]:
    """Return the component names available in this pack (without `.html.j2`)."""
    pack_dir = _PACKS_ROOT / pack_name / "components"
    if not pack_dir.is_dir():
        return []
    return sorted(
        p.stem.replace(".html", "")
        for p in pack_dir.glob("*.html.j2")
        if not p.name.startswith("_")
    )


def reset_cache() -> None:
    """Clear the env cache. Useful in tests when reloading templates."""
    with _env_lock:
        _env_cache.clear()


# ─────────────────────────────────────────────
# Filters
# ─────────────────────────────────────────────


def _embed_image_filter(value) -> str:
    """Resolve a SlideData image reference to something an <img src> can load.

    Accepts:
    - UUID-as-str → resolved via injected `_asset_resolver`
    - absolute or repo-relative file path → file:// URI (existence verified)
    - already-prefixed URL (file:/, http:/, https:/, data:) → passed through
      (file:/ existence still verified on disk)

    On any failure path, returns an inline SVG data URI marked
    "missing asset: <id-or-path>" instead of an empty src, so the screenshot
    reveals the gap visually. Every fallback path emits a WARN log.

    Returns empty string for None / empty input so templates can `{% if %}` guard.
    """
    if value is None or value == "":
        return ""

    if isinstance(value, UUID):
        value = str(value)
    if not isinstance(value, str):
        value = str(value)

    if value.startswith(("http:", "https:", "data:")):
        return value

    if value.startswith("file:"):
        local = _file_uri_to_path(value)
        if local is None or local.exists():
            return value
        logger.warning("embed_image: file:// target does not exist on disk: %s", value)
        return _missing_asset_data_uri(value, reason="file_missing")

    if _looks_like_uuid(value):
        if _asset_resolver is None:
            logger.warning(
                "embed_image: UUID-like value %r but no asset_resolver registered",
                value,
            )
            return _missing_asset_data_uri(value, reason="no_resolver")
        try:
            resolved = _asset_resolver(value)
        except Exception as exc:  # resolver bug shouldn't break the whole render
            logger.warning("embed_image: asset_resolver crashed for %s: %s", value, exc)
            return _missing_asset_data_uri(value, reason="resolver_error")
        if not resolved:
            logger.warning("embed_image: asset_resolver returned empty for id=%s", value)
            return _missing_asset_data_uri(value, reason="not_found")
        if resolved.startswith("file:"):
            local = _file_uri_to_path(resolved)
            if local is not None and not local.exists():
                logger.warning(
                    "embed_image: asset %s points at missing file %s", value, resolved,
                )
                return _missing_asset_data_uri(value, reason="file_missing")
        return resolved

    # Treat as filesystem path
    p = Path(value)
    if not p.is_absolute():
        p = (_REPO_ROOT / p).resolve()
    if not p.exists():
        logger.warning("embed_image: path does not exist: %s (raw=%r)", p, value)
        return _missing_asset_data_uri(value, reason="path_missing")
    return p.as_uri()


def _looks_like_uuid(s: str) -> bool:
    if len(s) != 36 or s.count("-") != 4:
        return False
    try:
        UUID(s)
        return True
    except ValueError:
        return False


def _file_uri_to_path(uri: str) -> Optional[Path]:
    """Best-effort conversion of a file:// URI back to a local Path.

    Uses urllib.parse.urlparse + unquote so percent-encoded characters
    (e.g. Chinese filenames materialised by `path.as_uri()`) decode back
    correctly. Without this, files like `周边交通_285.png` come back as
    `%E5%91%A8%E8%BE%B9...` and stat() incorrectly reports them missing.
    """
    if not uri.startswith("file:"):
        return None
    parsed = urlparse(uri)
    raw = unquote(parsed.path)
    raw = raw.lstrip("/")
    try:
        return Path(raw)
    except Exception:
        return None


_PLACEHOLDER_LABEL_LIMIT = 80


def _missing_asset_data_uri(identifier: str, *, reason: str) -> str:
    """Build a small grey SVG with a debug label, returned as a data URI.

    Browsers render data URIs without a network round-trip; this keeps the
    failed asset visible in the screenshot so QA can spot it during review
    rather than silently shipping a broken image icon.
    """
    label = identifier.strip()
    if len(label) > _PLACEHOLDER_LABEL_LIMIT:
        label = label[: _PLACEHOLDER_LABEL_LIMIT - 1] + "…"
    safe_label = (
        label.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    safe_reason = reason.replace("<", "&lt;").replace(">", "&gt;")
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 450" '
        'width="800" height="450" preserveAspectRatio="xMidYMid slice">'
        '<rect width="800" height="450" fill="#e5e7eb"/>'
        '<rect x="0" y="0" width="800" height="6" fill="#9ca3af"/>'
        '<text x="400" y="208" text-anchor="middle" font-family="-apple-system,'
        'Segoe UI,Roboto,sans-serif" font-size="22" fill="#374151">'
        'missing asset</text>'
        f'<text x="400" y="244" text-anchor="middle" font-family="ui-monospace,'
        f'Menlo,Consolas,monospace" font-size="14" fill="#6b7280">{safe_label}</text>'
        f'<text x="400" y="280" text-anchor="middle" font-family="ui-monospace,'
        f'Menlo,Consolas,monospace" font-size="12" fill="#9ca3af">[{safe_reason}]'
        '</text>'
        '</svg>'
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


def _path_to_file_uri(path_str: str) -> str:
    """Legacy helper kept for backward compatibility. Prefer the in-line
    handling inside `_embed_image_filter` which validates existence."""
    p = Path(path_str)
    if not p.is_absolute():
        p = (_REPO_ROOT / p).resolve()
    return p.as_uri()
