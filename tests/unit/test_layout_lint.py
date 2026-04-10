import pytest
import uuid
from tool.review.layout_lint import layout_lint
from schema.slide import SlideSpec, BlockContent, SlideConstraints
from schema.common import LayoutTemplate, ReviewSeverity


def _make_spec(**kwargs) -> SlideSpec:
    defaults = dict(
        project_id=uuid.uuid4(),
        slide_no=1,
        section="封面",
        title="天津博物馆概念方案",
        purpose="建立项目形象",
        key_message="现代、简约、文化",
        layout_template=LayoutTemplate.COVER_HERO,
        blocks=[
            BlockContent(
                block_id="hero_image",
                block_type="image",
                content="https://example.com/hero.jpg",
            )
        ],
    )
    defaults.update(kwargs)
    return SlideSpec(**defaults)


def test_clean_slide_passes():
    spec = _make_spec()
    result = layout_lint(spec)
    assert result.fail_count == 0
    assert result.pass_count == 1


def test_text_overflow_detected():
    long_text = "A" * 300
    spec = _make_spec(
        layout_template=LayoutTemplate.OVERVIEW_KPI,
        blocks=[
            BlockContent(block_id="kpi_items", block_type="text", content=long_text),
        ],
    )
    result = layout_lint(spec)
    rule_codes = {i.rule_code for i in result.issues}
    assert "TEXT_OVERFLOW" in rule_codes
    overflow_issue = next(i for i in result.issues if i.rule_code == "TEXT_OVERFLOW")
    assert overflow_issue.auto_fixable is True
    assert overflow_issue.severity == ReviewSeverity.P1


def test_bullet_overflow_detected():
    spec = _make_spec(
        layout_template=LayoutTemplate.OVERVIEW_KPI,
        blocks=[
            BlockContent(block_id="kpi_items", block_type="bullet", content=["a"] * 8),
        ],
    )
    result = layout_lint(spec)
    rule_codes = {i.rule_code for i in result.issues}
    assert "BULLET_OVERFLOW" in rule_codes


def test_missing_required_block():
    # cover-hero requires hero_image block
    spec = _make_spec(blocks=[
        BlockContent(block_id="body", block_type="text", content="some text that is long enough"),
    ])
    result = layout_lint(spec)
    rule_codes = {i.rule_code for i in result.issues}
    assert "MISSING_REQUIRED_BLOCK" in rule_codes
    p0_issues = [i for i in result.issues if i.severity == ReviewSeverity.P0]
    assert len(p0_issues) >= 1


def test_empty_slide_detected():
    spec = _make_spec(blocks=[
        BlockContent(block_id="block1", block_type="text", content="ok"),  # < 10 chars
    ])
    result = layout_lint(spec)
    rule_codes = {i.rule_code for i in result.issues}
    assert "EMPTY_SLIDE" in rule_codes


def test_title_too_long():
    spec = _make_spec(
        title="这是一个非常非常非常非常非常非常长的页面标题超出了25字的限制",
        layout_template=LayoutTemplate.OVERVIEW_KPI,
        blocks=[BlockContent(block_id="kpi_items", block_type="text", content="短文本")],
    )
    result = layout_lint(spec)
    rule_codes = {i.rule_code for i in result.issues}
    assert "TITLE_TOO_LONG" in rule_codes


def test_key_message_missing():
    spec = _make_spec(
        key_message="",
        blocks=[BlockContent(block_id="hero_image", block_type="image", content="url")],
    )
    result = layout_lint(spec)
    rule_codes = {i.rule_code for i in result.issues}
    assert "KEY_MESSAGE_MISSING" in rule_codes
