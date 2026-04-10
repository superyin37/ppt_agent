"""
HTML Sanitizer for Composer v3 HTML output.

Removes dangerous elements (scripts, event handlers) while preserving
all visual HTML/CSS/SVG needed for slide rendering.
"""
from __future__ import annotations

import re

# Event handler attributes (on*)
_EVENT_ATTR_RE = re.compile(r'\s+on\w+\s*=\s*["\'][^"\']*["\']', re.IGNORECASE)
# <script> tags and content
_SCRIPT_TAG_RE = re.compile(r'<script[\s>].*?</script\s*>', re.IGNORECASE | re.DOTALL)
# javascript: protocol in URLs
_JS_PROTOCOL_RE = re.compile(r'(href|src|action)\s*=\s*["\']javascript:[^"\']*["\']', re.IGNORECASE)
# @import in style blocks and inline styles
_CSS_IMPORT_RE = re.compile(r'@import\s+[^;]+;', re.IGNORECASE)
# External url() references (allow data: and asset: protocols)
_CSS_EXTERNAL_URL_RE = re.compile(
    r'url\(\s*["\']?(https?://[^)]*)["\']?\s*\)',
    re.IGNORECASE,
)
# <iframe>, <object>, <embed>, <form>, <input> tags
_DANGEROUS_TAGS_RE = re.compile(
    r'<(iframe|object|embed|form|input|textarea|button|select|link)[\s>].*?'
    r'(</\1\s*>|/>)',
    re.IGNORECASE | re.DOTALL,
)
# Self-closing dangerous tags
_DANGEROUS_SELFCLOSE_RE = re.compile(
    r'<(iframe|object|embed|form|input|textarea|button|select|link)\b[^>]*/?>',
    re.IGNORECASE,
)
# <meta http-equiv="refresh">
_META_REFRESH_RE = re.compile(r'<meta\s+[^>]*http-equiv[^>]*>', re.IGNORECASE)


def sanitize_slide_html(html: str) -> str:
    """
    Sanitize LLM-generated HTML for safe slide rendering.

    Removes:
    - <script> tags and content
    - Event handler attributes (onclick, onerror, etc.)
    - javascript: protocol URLs
    - @import CSS rules
    - External url() references (keeps data: and asset: URIs)
    - <iframe>, <object>, <embed>, <form>, <input>, <link> tags
    - <meta http-equiv> tags

    Preserves:
    - All visual HTML elements (<div>, <span>, <h1>-<h6>, <p>, <ul>, <li>, etc.)
    - <style> blocks (with @import stripped)
    - Inline style attributes
    - <svg> and all SVG sub-elements
    - <img> with safe src
    - CSS variables (var(--...))
    - data: URIs for inline SVG/images
    - asset: references (resolved by render engine)
    """
    if not html:
        return ""

    result = html

    # 1. Remove <script> tags and content
    result = _SCRIPT_TAG_RE.sub("", result)

    # 2. Remove event handler attributes
    result = _EVENT_ATTR_RE.sub("", result)

    # 3. Remove javascript: protocol URLs
    result = _JS_PROTOCOL_RE.sub("", result)

    # 4. Remove @import from CSS
    result = _CSS_IMPORT_RE.sub("/* import removed */", result)

    # 5. Remove external url() references (keep data: and asset:)
    result = _CSS_EXTERNAL_URL_RE.sub("url(/* external url removed */)", result)

    # 6. Remove dangerous tags
    result = _DANGEROUS_TAGS_RE.sub("", result)
    result = _DANGEROUS_SELFCLOSE_RE.sub("", result)

    # 7. Remove meta refresh
    result = _META_REFRESH_RE.sub("", result)

    return result.strip()


def validate_slide_structure(html: str) -> list[str]:
    """
    Check that HTML meets basic slide requirements.
    Returns list of warnings (empty = OK).
    """
    warnings: list[str] = []

    if "slide-root" not in html:
        warnings.append("Missing .slide-root container")

    if "<script" in html.lower():
        warnings.append("Script tags detected after sanitization")

    return warnings
