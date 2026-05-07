"""Unit tests for embed_image filter behaviour (ADR-006).

The filter must produce a debuggable visible placeholder on every failure
path instead of a silent empty src. These tests pin that contract.
"""
from __future__ import annotations

import base64
from pathlib import Path
from uuid import uuid4

import pytest

from render import jinja_env as je
from render.jinja_env import _embed_image_filter, _missing_asset_data_uri, set_asset_resolver


@pytest.fixture(autouse=True)
def _reset_resolver():
    """Each test starts with a fresh resolver state."""
    je._asset_resolver = None
    yield
    je._asset_resolver = None


def _decode_data_uri(uri: str) -> str:
    assert uri.startswith("data:image/svg+xml;base64,")
    payload = uri.split(",", 1)[1]
    return base64.b64decode(payload).decode("utf-8")


def test_passthrough_for_http_https_data():
    assert _embed_image_filter("https://x/y.png") == "https://x/y.png"
    assert _embed_image_filter("http://x/y.png") == "http://x/y.png"
    assert _embed_image_filter("data:image/png;base64,xxx") == "data:image/png;base64,xxx"


def test_passthrough_for_existing_file_uri(tmp_path):
    real = tmp_path / "real.png"
    real.write_bytes(b"\x89PNG\r\n")
    uri = real.as_uri()
    assert _embed_image_filter(uri) == uri


def test_url_encoded_chinese_filename_passes_through(tmp_path):
    """`Path.as_uri()` percent-encodes non-ASCII filenames; the existence
    check must decode them before stat() or every Chinese-named asset will
    be misreported as missing."""
    real = tmp_path / "周边交通_285.png"
    real.write_bytes(b"\x89PNG\r\n")
    uri = real.as_uri()
    # Sanity: URL contains percent escapes
    assert "%" in uri
    # Filter must recognise the file as existing and return the URI unchanged
    assert _embed_image_filter(uri) == uri


def test_missing_file_uri_returns_placeholder():
    fake_uri = "file:///definitely/not/here.png"
    out = _embed_image_filter(fake_uri)
    assert out.startswith("data:image/svg+xml;base64,")
    svg = _decode_data_uri(out)
    assert "missing asset" in svg
    assert "file_missing" in svg


def test_uuid_without_resolver_returns_placeholder():
    uid = str(uuid4())
    out = _embed_image_filter(uid)
    svg = _decode_data_uri(out)
    assert "no_resolver" in svg
    assert uid in svg


def test_uuid_with_resolver_miss_returns_placeholder():
    set_asset_resolver(lambda _id: "")
    uid = str(uuid4())
    out = _embed_image_filter(uid)
    svg = _decode_data_uri(out)
    assert "not_found" in svg
    assert uid in svg


def test_uuid_with_resolver_hit_returns_url(tmp_path):
    real = tmp_path / "ok.png"
    real.write_bytes(b"\x89PNG\r\n")
    uri = real.as_uri()
    set_asset_resolver(lambda _id: uri)
    assert _embed_image_filter(str(uuid4())) == uri


def test_uuid_with_resolver_pointing_to_missing_file_returns_placeholder():
    set_asset_resolver(lambda _id: "file:///not/real/anywhere.png")
    out = _embed_image_filter(str(uuid4()))
    svg = _decode_data_uri(out)
    assert "file_missing" in svg


def test_uuid_with_resolver_crash_returns_placeholder():
    def boom(_id):
        raise RuntimeError("oops")
    set_asset_resolver(boom)
    out = _embed_image_filter(str(uuid4()))
    svg = _decode_data_uri(out)
    assert "resolver_error" in svg


def test_existing_local_path_returns_file_uri(tmp_path):
    real = tmp_path / "a.png"
    real.write_bytes(b"\x89PNG\r\n")
    out = _embed_image_filter(str(real))
    assert out == real.as_uri()


def test_missing_local_path_returns_placeholder():
    out = _embed_image_filter("/totally/made/up/path.png")
    svg = _decode_data_uri(out)
    assert "path_missing" in svg


def test_none_and_empty_pass_through_as_empty():
    assert _embed_image_filter(None) == ""
    assert _embed_image_filter("") == ""


def test_label_truncated_in_placeholder():
    # Make a long pseudo-id and ensure it gets cut so the SVG stays small.
    long_label = "x" * 500
    out = _missing_asset_data_uri(long_label, reason="test")
    svg = _decode_data_uri(out)
    assert "x…" in svg or "x" * 80 in svg
    # SVG should not contain the full 500-char label.
    assert "x" * 500 not in svg


def test_placeholder_escapes_html_in_label():
    out = _missing_asset_data_uri("<script>alert(1)</script>", reason="x")
    svg = _decode_data_uri(out)
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg
