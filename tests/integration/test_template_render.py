"""Integration tests: each of the 11 templates renders cleanly from a fixture
SlideData payload (ADR-006).

These tests do NOT involve LLM, DB, or Playwright — they assert that the
Jinja2 environment + component templates + SlideData schemas form a
self-consistent unit. Preview HTML is written to pytest's temporary directory
so the tests do not depend on a writable fixed artifact folder.

Render assertions are deliberately shallow (output non-empty, contains
expected anchor text). Full visual-regression is out of PR-1 scope.
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from render.jinja_env import get_jinja_env, set_asset_resolver
from schema.slide_data import (
    CaseCardData,
    ChartData,
    ConceptSchemeData,
    ContentBulletsData,
    CoverData,
    EndingData,
    ImageGridData,
    PolicyListData,
    TableData,
    TocData,
    TransitionData,
)


PACK = "minimalist_architecture"

# Stub asset resolver: pretend every UUID maps to a placeholder file.
_PLACEHOLDER = "file:///placeholder.png"
set_asset_resolver(lambda _id: _PLACEHOLDER)


@pytest.fixture(scope="module")
def env():
    return get_jinja_env(PACK)


@pytest.fixture(scope="module")
def out_dir():
    p = Path("tmp") / "test_template_render_components" / uuid4().hex
    p.mkdir(parents=True, exist_ok=True)
    return p


def _render(env, component: str, data: dict, **extra_ctx) -> str:
    tpl = env.get_template(f"{component}.html.j2")
    ctx = {
        "page": 1,
        "total_pages": 40,
        "section": "01",
        "section_en": "TEST SECTION",
        "project_title": "Sample Project",
        "title": data.get("title", "TITLE"),
        "subtitle_en": "",
        "data": data,
    }
    ctx.update(extra_ctx)
    return tpl.render(**ctx)


def _save(out_dir: Path, name: str, html: str):
    """Wrap the snippet in a minimal HTML doc for browser preview."""
    page = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>:root {"
        "  --color-bg:#f4f1ea; --color-text-primary:#15192a; --color-text-secondary:#73788a;"
        "  --color-accent:#2b3b63; --color-surface:#ffffff; --color-border:#15192a22;"
        "  --font-heading:'PingFang SC',sans-serif; --font-body:'PingFang SC',sans-serif; --font-en:Georgia,serif;"
        "}</style></head><body>" + html + "</body></html>"
    )
    (out_dir / f"{name}.html").write_text(page, encoding="utf-8")


def test_render_cover(env, out_dir):
    data = CoverData(
        title="某项目设计建议书",
        slogan="A modern architecture proposal",
        en="DESIGN PROPOSAL",
        meta_lines=[
            {"label": "BUILDING", "value": "Office"},
            {"label": "AREA", "value": "5万㎡"},
            {"label": "FAR", "value": "3.0"},
        ],
        year=2026,
        signature={"line1": "Prepared by", "role": "Architect Agent", "date": "2026-05-01"},
    ).model_dump()
    html = _render(env, "cover", data, section="00", section_en="")
    assert "某项目设计建议书" in html
    assert "/ 40" in html
    _save(out_dir, "cover", html)


def test_render_toc(env, out_dir):
    data = TocData(
        title="目录",
        entries=[
            {"no": "01", "label": "背景研究", "en": "BACKGROUND", "page_range": "03 — 12"},
            {"no": "02", "label": "场地分析", "en": "SITE", "page_range": "13 — 19"},
            {"no": "03", "label": "概念方案", "en": "CONCEPT", "page_range": "20 — 28"},
        ],
    ).model_dump()
    html = _render(env, "toc", data)
    assert "03 — 12" in html
    _save(out_dir, "toc", html)


def test_render_transition(env, out_dir):
    data = TransitionData(
        title="背景研究",
        subtitle_en="Background Research",
        sub="政策与文化",
        section_no="01",
    ).model_dump()
    html = _render(env, "transition", data, subtitle_en="Background Research")
    assert "01" in html and "背景研究" in html
    _save(out_dir, "transition", html)


def test_render_policy_list(env, out_dir):
    data = PolicyListData(
        title="相关政策梳理",
        policies=[
            {
                "title": "城市更新行动方案",
                "publish_year": "2024",
                "content": "推动重点片区有机更新",
                "impact": "本项目位于试点片区",
                "source_url": "https://example.com/doc1",
            },
            {
                "title": "TOD 综合开发指引",
                "publish_year": "2023",
                "content": "围绕枢纽站点高强度开发",
                "impact": "鼓励商业 + 公共空间复合",
            },
        ],
    ).model_dump()
    html = _render(env, "policy_list", data)
    assert "城市更新" in html
    _save(out_dir, "policy_list", html)


def test_render_chart(env, out_dir):
    data = ChartData(
        title="政策影响矩阵",
        bullets=["土地：高影响", "业态：中影响", "指标：高影响", "运营：低影响"],
        chart_path="/tmp/fake_chart.png",
    ).model_dump()
    html = _render(env, "chart", data)
    assert "KEY READINGS" in html
    _save(out_dir, "chart", html)


def test_render_table(env, out_dir):
    data = TableData(
        title="同类项目对比",
        headers=["项目", "规模", "特色", "启示"],
        rows=[
            ["A 中心", "5万㎡", "中庭", "公共性"],
            ["B 广场", "3万㎡", "屋顶花园", "绿化策略"],
            ["C 大厦", "8万㎡", "立面网格", "材质语言"],
        ],
        note="数据综合公开资料整理",
    ).model_dump()
    html = _render(env, "table", data)
    assert "<table>" in html
    _save(out_dir, "table", html)


def test_render_image_grid(env, out_dir):
    data = ImageGridData(
        title="场地区位",
        images=[
            {"path": "/tmp/a.png", "caption": "枢纽站点"},
            {"path": "/tmp/b.png", "caption": "外部交通"},
            {"path": "/tmp/c.png", "caption": "周边设施"},
        ],
        caption="三张地图共同勾勒场地的对外联系",
    ).model_dump()
    html = _render(env, "image_grid", data)
    assert "枢纽站点" in html
    _save(out_dir, "image_grid", html)


def test_render_content_bullets(env, out_dir):
    data = ContentBulletsData(
        title="设计策略",
        lede="项目以三大策略统领整体设计",
        bullets=[
            {"title": "整合性", "body": "整合周边交通与公共空间"},
            {"title": "在地性", "body": "回应地域文化与气候"},
            {"title": "灵活性", "body": "支持多种业态混合"},
        ],
    ).model_dump()
    html = _render(env, "content_bullets", data)
    assert "整合性" in html and "灵活性" in html
    _save(out_dir, "content_bullets", html)


def test_render_case_card(env, out_dir):
    data = CaseCardData(
        title="参考案例",
        case_idx=0,
        case_name="蛇形画廊 2024",
        thumbnail="/tmp/case.png",
        scale="400㎡，单层",
        highlights="木构装配 + 半透明屋面",
        inspiration="启发本项目的活动空间策略",
    ).model_dump()
    html = _render(env, "case_card", data)
    assert "蛇形画廊" in html
    _save(out_dir, "case_card", html)


def test_render_concept_scheme(env, out_dir):
    data = ConceptSchemeData(
        scheme_idx=0,
        scheme_name="云上之城",
        view="aerial",
        view_label="AERIAL · 鸟瞰",
        image="/tmp/concept_aerial.png",
        idea="退台呼应远山",
        analysis="方案通过逐层退台形成与远山的对话",
    ).model_dump()
    html = _render(env, "concept_scheme", data)
    assert "云上之城" in html
    _save(out_dir, "concept_scheme", html)


def test_render_ending(env, out_dir):
    data = EndingData(
        title="THANK YOU",
        en="GRACIAS",
        tagline="see you in the next chapter",
        signature_parts=["Sample Project", "AGENT", "2026"],
    ).model_dump()
    html = _render(env, "ending", data)
    assert "THANK YOU" in html
    _save(out_dir, "ending", html)


def test_chrome_total_pages_dynamic(env):
    """Verify the `/ NN` chrome marker reflects total_pages, not 40."""
    data = TransitionData(title="x", section_no="01").model_dump()
    html = _render(env, "transition", data, total_pages=8, page=3, section="01")
    assert "/ 08" in html
    assert "/ 40" not in html
