import uuid
import pytest
from tool.review.repair_plan import execute_repair, build_repair_plan_from_issues
from schema.slide import SlideSpec, BlockContent
from schema.review import ReviewReport, RepairAction, ReviewIssue
from schema.common import LayoutTemplate, ReviewSeverity, ReviewDecision


def _make_spec_with_long_text() -> SlideSpec:
    return SlideSpec(
        project_id=uuid.uuid4(),
        slide_no=1,
        section="分析",
        title="短标题",
        purpose="test",
        key_message="key",
        layout_template=LayoutTemplate.OVERVIEW_KPI,
        blocks=[
            BlockContent(
                block_id="body",
                block_type="text",
                content="A" * 300,
            )
        ],
    )


def _make_report(actions: list[RepairAction]) -> ReviewReport:
    return ReviewReport(
        target_type="slide",
        target_id=uuid.uuid4(),
        review_layer="rule",
        severity=ReviewSeverity.P1,
        final_decision=ReviewDecision.REPAIR_REQUIRED,
        repair_plan=actions,
    )


def test_truncate_text():
    spec = _make_spec_with_long_text()
    report = _make_report([
        RepairAction(action_type="truncate_text", target_block_id="body", params={"max_chars": 200})
    ])
    repaired, logs = execute_repair(spec, report)
    body_block = next(b for b in repaired.blocks if b.block_id == "body")
    assert len(str(body_block.content)) <= 201  # 200 + ellipsis
    assert "truncate_text" in logs[0]


def test_truncate_bullets():
    spec = SlideSpec(
        project_id=uuid.uuid4(),
        slide_no=2,
        section="分析",
        title="标题",
        purpose="test",
        key_message="key",
        layout_template=LayoutTemplate.OVERVIEW_KPI,
        blocks=[
            BlockContent(block_id="items", block_type="bullet", content=["a", "b", "c", "d", "e", "f", "g"])
        ],
    )
    report = _make_report([
        RepairAction(action_type="truncate_bullets", target_block_id="items", params={"max_bullets": 5})
    ])
    repaired, logs = execute_repair(spec, report)
    items_block = next(b for b in repaired.blocks if b.block_id == "items")
    assert len(items_block.content) == 5


def test_truncate_title():
    spec = SlideSpec(
        project_id=uuid.uuid4(),
        slide_no=3,
        section="封面",
        title="这是一个非常非常非常非常非常长的标题",
        purpose="test",
        key_message="key",
        layout_template=LayoutTemplate.COVER_HERO,
        blocks=[BlockContent(block_id="hero_image", block_type="image", content="url")],
    )
    report = _make_report([
        RepairAction(action_type="truncate_title", params={"max_chars": 25})
    ])
    repaired, logs = execute_repair(spec, report)
    assert len(repaired.title) <= 26  # 25 + ellipsis


def test_non_auto_action_skipped():
    spec = _make_spec_with_long_text()
    report = _make_report([
        RepairAction(action_type="escalate")  # not in AUTO_ACTIONS
    ])
    repaired, logs = execute_repair(spec, report)
    assert repaired == spec
    assert "skip (manual)" in logs[0]


def test_build_repair_plan_from_issues():
    issues = [
        ReviewIssue(
            issue_id="R001_body",
            rule_code="TEXT_OVERFLOW",
            layer="rule",
            severity=ReviewSeverity.P1,
            message="too long",
            location="body",
            suggested_fix="truncate",
            auto_fixable=True,
        ),
        ReviewIssue(
            issue_id="R003_hero",
            rule_code="MISSING_REQUIRED_BLOCK",
            layer="rule",
            severity=ReviewSeverity.P0,
            message="missing",
            location=None,
            suggested_fix="add block",
            auto_fixable=False,
        ),
    ]
    actions = build_repair_plan_from_issues(issues)
    # Only auto_fixable issue should produce an action
    assert len(actions) == 1
    assert actions[0].action_type == "truncate_text"
    assert actions[0].target_block_id == "body"
