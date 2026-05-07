from pathlib import Path
import subprocess
import uuid

from render import exporter


def test_screenshot_slide_sync_uses_chrome_cli(monkeypatch):
    render_tmp = Path("tmp") / f"test_exporter_chromium_cli_{uuid.uuid4().hex}"
    render_tmp.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(exporter, "_BROWSER_RENDER_TMP", render_tmp)

    def fake_render(args, timeout_s):
        assert timeout_s == 30
        screenshot_arg = next(arg for arg in args if arg.startswith("--screenshot="))
        Path(screenshot_arg.split("=", 1)[1]).write_bytes(b"PNGDATA")
        return Path("chrome.exe"), subprocess.CompletedProcess(["chrome.exe"], 0)

    monkeypatch.setattr(exporter, "_render_with_chromium_cli", fake_render)

    assert exporter._screenshot_slide_sync("<html></html>", 640, 360) == b"PNGDATA"


def test_render_with_chromium_cli_tries_next_candidate(monkeypatch):
    render_tmp = Path("tmp") / f"test_exporter_chromium_cli_{uuid.uuid4().hex}"
    render_tmp.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(exporter, "_BROWSER_RENDER_TMP", render_tmp)

    bad = Path("bad-chrome.exe")
    good = Path("good-chrome.exe")
    calls = []

    monkeypatch.setattr(exporter, "_find_chromium_executables", lambda: [bad, good])

    def fake_run(chrome, args, timeout_s):
        calls.append(chrome)
        if chrome == bad:
            return subprocess.CompletedProcess(
                [str(chrome)],
                1,
                stderr=b"first browser failed",
            )
        return subprocess.CompletedProcess([str(chrome)], 0)

    monkeypatch.setattr(exporter, "_run_chromium_once", fake_run)

    chrome, result = exporter._render_with_chromium_cli(["--screenshot=out.png"], 30)

    assert chrome == good
    assert result.returncode == 0
    assert calls == [bad, good]
