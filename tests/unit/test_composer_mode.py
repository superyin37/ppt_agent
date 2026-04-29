from agent.composer import ComposerMode, resolve_composer_mode
from config.settings import settings


def test_resolve_composer_mode_defaults_to_config(monkeypatch):
    monkeypatch.setattr(settings, "composer_mode", "html")

    assert resolve_composer_mode() == ComposerMode.HTML


def test_resolve_composer_mode_keeps_structured_override(monkeypatch):
    monkeypatch.setattr(settings, "composer_mode", "html")

    assert resolve_composer_mode("structured") == ComposerMode.STRUCTURED


def test_resolve_composer_mode_falls_back_to_html(monkeypatch):
    monkeypatch.setattr(settings, "composer_mode", "unknown")

    assert resolve_composer_mode() == ComposerMode.HTML
