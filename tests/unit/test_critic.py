"""
Unit tests for Phase 8: Critic Agent + semantic check.
Tests: _evaluate, review_slide (mocked), _vision_review (mocked), SemanticCheck (mocked LLM).
"""
import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from schema.slide import SlideSpec, BlockContent, SlideConstraints, StyleTokens
from schema.common import LayoutTemplate, ReviewSeverity, ReviewDecision
from schema.review import (
    DesignAdvice,
    DesignDimension,
    DesignSuggestion,
    ReviewIssue,
    ReviewReport,
    RepairAction,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_spec(
    template: LayoutTemplate = LayoutTemplate.OVERVIEW_KPI,
    blocks: list[BlockContent] | None = None,
    title: str = "测试标题",
    key_message: str = "核心信息",
) -> SlideSpec:
    return SlideSpec(
        project_id=uuid4(),
        slide_no=1,
        section="测试章节",
        title=title,
        purpose="展示目的",
        key_message=key_message,
        layout_template=template,
        blocks=blocks or [
            BlockContent(
                block_id="kpi_items",
                block_type="kpi",
                content=[{"value": "10万㎡", "label": "建筑面积"}],
            )
        ],
    )


def _make_issue(
    severity: ReviewSeverity = ReviewSeverity.P2,
    auto_fixable: bool = False,
    rule_code: str = "R001",
    layer: str = "rule",
) -> ReviewIssue:
    return ReviewIssue(
        issue_id=f"{rule_code}_1_0",
        rule_code=rule_code,
        layer=layer,
        severity=severity,
        message="测试问题",
        suggested_fix="修复建议",
        auto_fixable=auto_fixable,
    )


# ── _evaluate tests ───────────────────────────────────────────────────────────

from agent.critic import _evaluate


def test_evaluate_no_issues_returns_pass():
    sev, dec = _evaluate([])
    assert sev == ReviewSeverity.PASS
    assert dec == ReviewDecision.PASS


def test_evaluate_p2_only_returns_repair_required():
    issues = [_make_issue(ReviewSeverity.P2)]
    sev, dec = _evaluate(issues)
    assert sev == ReviewSeverity.P2
    assert dec == ReviewDecision.REPAIR_REQUIRED


def test_evaluate_p1_returns_repair_required():
    issues = [_make_issue(ReviewSeverity.P1)]
    sev, dec = _evaluate(issues)
    assert sev == ReviewSeverity.P1
    assert dec == ReviewDecision.REPAIR_REQUIRED


def test_evaluate_p0_fixable_returns_repair_required():
    issues = [_make_issue(ReviewSeverity.P0, auto_fixable=True)]
    sev, dec = _evaluate(issues)
    assert sev == ReviewSeverity.P0
    assert dec == ReviewDecision.REPAIR_REQUIRED


def test_evaluate_p0_non_fixable_escalates():
    issues = [_make_issue(ReviewSeverity.P0, auto_fixable=False)]
    sev, dec = _evaluate(issues)
    assert sev == ReviewSeverity.P0
    assert dec == ReviewDecision.ESCALATE_HUMAN


def test_evaluate_mixed_p0_nonfixable_and_p1_escalates():
    issues = [
        _make_issue(ReviewSeverity.P0, auto_fixable=False),
        _make_issue(ReviewSeverity.P1),
    ]
    sev, dec = _evaluate(issues)
    assert dec == ReviewDecision.ESCALATE_HUMAN


def test_evaluate_p0_fixable_with_p1_returns_p0_repair():
    issues = [
        _make_issue(ReviewSeverity.P0, auto_fixable=True),
        _make_issue(ReviewSeverity.P1),
    ]
    sev, dec = _evaluate(issues)
    assert sev == ReviewSeverity.P0
    assert dec == ReviewDecision.REPAIR_REQUIRED


# ── review_slide integration (mocked) ────────────────────────────────────────

@pytest.mark.asyncio
async def test_review_slide_no_issues_returns_pass():
    from agent.critic import review_slide
    from tool.review.layout_lint import LayoutLintOutput

    spec = _make_spec()
    brief = {"building_type": "museum", "client_name": "测试甲方"}

    lint_out = LayoutLintOutput(issues=[], pass_count=1, fail_count=0)
    sem_out = MagicMock()
    sem_out.issues = []
    sem_out.repair_actions = []

    with (
        patch("agent.critic.layout_lint", return_value=lint_out),
        patch("agent.critic.semantic_check", new_callable=AsyncMock, return_value=sem_out),
    ):
        repaired, report = await review_slide(spec, brief, layers=["rule", "semantic"])

    assert report.final_decision == ReviewDecision.PASS
    assert report.severity == ReviewSeverity.PASS
    assert report.issues == []


@pytest.mark.asyncio
async def test_review_slide_p1_rule_issue_triggers_repair():
    from agent.critic import review_slide
    from tool.review.layout_lint import LayoutLintOutput
    from tool.review.repair_plan import build_repair_plan_from_issues, execute_repair

    p1_issue = _make_issue(ReviewSeverity.P1, auto_fixable=True, rule_code="R001")
    lint_out = LayoutLintOutput(issues=[p1_issue], pass_count=0, fail_count=1)
    sem_out = MagicMock()
    sem_out.issues = []
    sem_out.repair_actions = []

    spec = _make_spec()
    brief = {"building_type": "museum"}

    with (
        patch("agent.critic.layout_lint", return_value=lint_out),
        patch("agent.critic.semantic_check", new_callable=AsyncMock, return_value=sem_out),
    ):
        repaired, report = await review_slide(spec, brief, layers=["rule", "semantic"])

    assert report.final_decision in (ReviewDecision.REPAIR_REQUIRED, ReviewDecision.PASS)


@pytest.mark.asyncio
async def test_review_slide_only_rule_layer():
    from agent.critic import review_slide
    from tool.review.layout_lint import LayoutLintOutput

    lint_out = LayoutLintOutput(issues=[], pass_count=1, fail_count=0)
    spec = _make_spec()

    with patch("agent.critic.layout_lint", return_value=lint_out):
        repaired, report = await review_slide(spec, {}, layers=["rule"])

    assert "rule" in report.review_layer
    assert "semantic" not in report.review_layer


@pytest.mark.asyncio
async def test_review_slide_vision_layer_called_with_screenshot():
    from agent.critic import review_slide
    from tool.review.layout_lint import LayoutLintOutput

    lint_out = LayoutLintOutput(issues=[], pass_count=1, fail_count=0)
    sem_out = MagicMock(issues=[], repair_actions=[])
    vision_issues = [_make_issue(ReviewSeverity.P2, rule_code="V001", layer="vision")]

    spec = _make_spec()

    with (
        patch("agent.critic.layout_lint", return_value=lint_out),
        patch("agent.critic.semantic_check", new_callable=AsyncMock, return_value=sem_out),
        patch("agent.critic._vision_review", new_callable=AsyncMock, return_value=vision_issues),
    ):
        _, report = await review_slide(
            spec, {}, layers=["rule", "semantic", "vision"],
            screenshot_url="https://example.com/slide1.png",
        )

    assert any(i.layer == "vision" for i in report.issues)


@pytest.mark.asyncio
async def test_review_slide_vision_skipped_without_screenshot():
    from agent.critic import review_slide
    from tool.review.layout_lint import LayoutLintOutput

    lint_out = LayoutLintOutput(issues=[], pass_count=1, fail_count=0)
    sem_out = MagicMock(issues=[], repair_actions=[])
    mock_vision = AsyncMock()

    spec = _make_spec()

    with (
        patch("agent.critic.layout_lint", return_value=lint_out),
        patch("agent.critic.semantic_check", new_callable=AsyncMock, return_value=sem_out),
        patch("agent.critic._vision_review", mock_vision),
    ):
        # No screenshot_url → vision skipped even if in layers
        await review_slide(spec, {}, layers=["rule", "semantic", "vision"])

    mock_vision.assert_not_called()


@pytest.mark.asyncio
async def test_review_slide_semantic_failure_is_swallowed():
    """Semantic check failure should not crash review_slide."""
    from agent.critic import review_slide
    from tool.review.layout_lint import LayoutLintOutput

    lint_out = LayoutLintOutput(issues=[], pass_count=1, fail_count=0)
    spec = _make_spec()

    with (
        patch("agent.critic.layout_lint", return_value=lint_out),
        patch(
            "agent.critic.semantic_check",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM timeout"),
        ),
    ):
        _, report = await review_slide(spec, {}, layers=["rule", "semantic"])

    # Should still complete, just without semantic issues
    assert report is not None


# ── _vision_review tests ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_vision_review_returns_issues():
    from agent.critic import _vision_review

    mock_result = MagicMock()
    mock_result.issues = [
        {"rule_code": "V001", "severity": "P2", "message": "视觉压迫", "auto_fixable": False},
    ]

    with patch("config.llm.call_llm_multimodal", new_callable=AsyncMock, return_value=mock_result):
        issues = await _vision_review("https://example.com/slide.png", 1)

    assert len(issues) == 1
    assert issues[0].rule_code == "V001"
    assert issues[0].layer == "vision"
    assert issues[0].severity == ReviewSeverity.P2


@pytest.mark.asyncio
async def test_vision_review_invalid_severity_defaults_to_p2():
    from agent.critic import _vision_review

    mock_result = MagicMock()
    mock_result.issues = [
        {"rule_code": "V002", "severity": "INVALID", "message": "模糊图片", "auto_fixable": False},
    ]

    with patch("config.llm.call_llm_multimodal", new_callable=AsyncMock, return_value=mock_result):
        issues = await _vision_review("https://example.com/slide.png", 2)

    assert issues[0].severity == ReviewSeverity.P2


@pytest.mark.asyncio
async def test_vision_review_llm_error_returns_empty():
    from agent.critic import _vision_review

    with patch(
        "config.llm.call_llm_multimodal",
        new_callable=AsyncMock,
        side_effect=RuntimeError("network error"),
    ):
        issues = await _vision_review("https://example.com/slide.png", 1)

    assert issues == []


# ── semantic_check tests ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_semantic_check_returns_empty_on_llm_failure():
    from tool.review.semantic_check import semantic_check, SemanticCheckInput

    spec = _make_spec()
    inp = SemanticCheckInput(spec=spec, brief={"client_name": "测试甲方"})

    with patch("tool.review.semantic_check.call_llm_with_limit", new_callable=AsyncMock,
               side_effect=RuntimeError("timeout")):
        result = await semantic_check(inp)

    assert len(result.issues) == 1
    assert result.issues[0].rule_code == "SEMANTIC_SKIPPED"
    assert result.issues[0].severity == ReviewSeverity.P2
    assert result.issues[0].auto_fixable is False
    assert result.repair_actions == []


@pytest.mark.asyncio
async def test_semantic_check_converts_llm_output_to_issues():
    from tool.review.semantic_check import semantic_check, SemanticCheckInput, _SemanticOutput, _SemanticIssue

    spec = _make_spec()
    inp = SemanticCheckInput(spec=spec, brief={"client_name": "正确甲方名"})

    llm_out = _SemanticOutput(
        issues=[
            _SemanticIssue(
                rule_code="S007",
                severity="P1",
                message="甲方名称错误",
                location="body_b1",
                auto_fixable=True,
                suggested_fix="替换为正确名称",
            )
        ],
        overall_ok=False,
    )

    with patch("tool.review.semantic_check.call_llm_with_limit", new_callable=AsyncMock,
               return_value=llm_out):
        result = await semantic_check(inp)

    assert len(result.issues) == 1
    assert result.issues[0].rule_code == "S007"
    assert result.issues[0].severity == ReviewSeverity.P1
    assert result.issues[0].layer == "semantic"


@pytest.mark.asyncio
async def test_semantic_check_s007_creates_repair_action():
    from tool.review.semantic_check import semantic_check, SemanticCheckInput, _SemanticOutput, _SemanticIssue

    spec = _make_spec()
    brief = {"client_name": "XX市住建局"}
    inp = SemanticCheckInput(spec=spec, brief=brief)

    llm_out = _SemanticOutput(
        issues=[
            _SemanticIssue(
                rule_code="S007",
                severity="P1",
                message="甲方名称拼写错误",
                location="body_block",
                auto_fixable=True,
                suggested_fix="",
            )
        ],
        overall_ok=False,
    )

    with patch("tool.review.semantic_check.call_llm_with_limit", new_callable=AsyncMock,
               return_value=llm_out):
        result = await semantic_check(inp)

    assert len(result.repair_actions) == 1
    assert result.repair_actions[0].action_type == "replace_client_name"
    assert result.repair_actions[0].params["correct_name"] == "XX市住建局"


@pytest.mark.asyncio
async def test_semantic_check_invalid_severity_defaults_to_p2():
    from tool.review.semantic_check import semantic_check, SemanticCheckInput, _SemanticOutput, _SemanticIssue

    spec = _make_spec()
    inp = SemanticCheckInput(spec=spec, brief={})

    llm_out = _SemanticOutput(
        issues=[
            _SemanticIssue(rule_code="S001", severity="GARBAGE", message="面积不符", auto_fixable=False)
        ],
        overall_ok=False,
    )

    with patch("tool.review.semantic_check.call_llm_with_limit", new_callable=AsyncMock,
               return_value=llm_out):
        result = await semantic_check(inp)

    assert result.issues[0].severity == ReviewSeverity.P2


@pytest.mark.asyncio
async def test_semantic_check_retries_with_fast_model_on_invalid_critic_model():
    from tool.review.semantic_check import (
        SemanticCheckInput,
        _SemanticIssue,
        _SemanticOutput,
        semantic_check,
    )

    spec = _make_spec()
    inp = SemanticCheckInput(spec=spec, brief={})
    llm_out = _SemanticOutput(
        issues=[_SemanticIssue(rule_code="S001", severity="P2", message="ok", auto_fixable=False)],
        overall_ok=False,
    )
    mocked_call = AsyncMock(side_effect=[RuntimeError("openai/gpt-4.5 is not a valid model ID"), llm_out])

    with (
        patch("tool.review.semantic_check.CRITIC_MODEL", "openai/gpt-4.5"),
        patch("tool.review.semantic_check.FAST_MODEL", "claude-sonnet-4-6"),
        patch("tool.review.semantic_check.call_llm_with_limit", new=mocked_call),
    ):
        result = await semantic_check(inp)

    assert len(result.issues) == 1
    assert mocked_call.await_count == 2
    assert mocked_call.await_args_list[0].kwargs["model"] == "openai/gpt-4.5"
    assert mocked_call.await_args_list[1].kwargs["model"] == "claude-sonnet-4-6"


# ── report capping tests ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_review_slide_caps_issues_at_5():
    from agent.critic import review_slide
    from tool.review.layout_lint import LayoutLintOutput

    many_issues = [
        _make_issue(ReviewSeverity.P2, rule_code=f"R00{i}") for i in range(8)
    ]
    lint_out = LayoutLintOutput(issues=many_issues, pass_count=0, fail_count=8)
    sem_out = MagicMock(issues=[], repair_actions=[])
    spec = _make_spec()

    with (
        patch("agent.critic.layout_lint", return_value=lint_out),
        patch("agent.critic.semantic_check", new_callable=AsyncMock, return_value=sem_out),
    ):
        _, report = await review_slide(spec, {}, layers=["rule", "semantic"])

    assert len(report.issues) <= 5


# ── design advisor gate tests ─────────────────────────────────────────────────

def test_design_advice_to_issues_triggers_repair_gate():
    from agent.critic import _design_advice_to_issues

    advice = DesignAdvice(
        slide_no=3,
        dimensions=[
            DesignDimension(dimension="focal_point", score=5.8, comment="焦点弱"),
            DesignDimension(dimension="polish", score=5.9, comment="完成度不足"),
        ],
        overall_score=6.2,
        suggestions=[
            DesignSuggestion(
                code="D012",
                category="focal_point",
                severity="recommended",
                message="重点页冲击力不足",
            ),
        ],
    )

    issues = _design_advice_to_issues(advice, page_type="cover")
    codes = {issue.rule_code for issue in issues}

    assert "D000_DESIGN_SCORE_LOW" in codes
    assert "D007" in codes
    assert "D009" in codes
    assert "D012" in codes
    assert all(issue.auto_fixable for issue in issues)


def test_design_advice_gate_can_be_disabled(monkeypatch):
    from agent.critic import _design_advice_to_issues
    from config.settings import settings

    monkeypatch.setattr(settings, "design_review_gate_enabled", False)
    advice = DesignAdvice(slide_no=1, overall_score=1.0)

    assert _design_advice_to_issues(advice, page_type="cover") == []
