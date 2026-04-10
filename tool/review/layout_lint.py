from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from schema.common import LayoutTemplate, ReviewSeverity
from schema.review import ReviewIssue
from schema.slide import SlideSpec
from schema.visual_theme import ContentBlock, LayoutSpec

MAX_TEXT_CHARS = 300
MAX_HEADING_CHARS = 40
MAX_TITLE_CHARS = 25
MAX_BULLET_POINTS = 5
MAX_IMAGE_BLOCKS = 4

TEXT_TYPES = {"body-text", "subheading", "quote", "caption", "label", "text"}
IMAGE_TYPES = {"image", "chart", "map"}


class LayoutLintOutput(BaseModel):
    issues: list[ReviewIssue]
    pass_count: int
    fail_count: int


def _is_layout_spec(spec: LayoutSpec | SlideSpec) -> bool:
    return hasattr(spec, "region_bindings")


def _block_id(block: Any) -> str:
    return getattr(block, "block_id", "")


def _block_type(block: Any) -> str:
    raw = getattr(block, "content_type", None) or getattr(block, "block_type", "")
    legacy_map = {
        "text": "body-text",
        "bullet": "bullet-list",
        "image": "image",
        "chart": "chart",
        "map": "map",
        "kpi": "kpi-value",
        "caption": "caption",
        "label": "label",
    }
    return legacy_map.get(raw, raw)


def _block_content(block: Any) -> Any:
    return getattr(block, "content", None)


def _block_source_refs(block: Any) -> list[str]:
    refs = getattr(block, "source_refs", None)
    return refs or []


def _all_blocks(spec: LayoutSpec | SlideSpec) -> list[Any]:
    if _is_layout_spec(spec):
        return [block for rb in spec.region_bindings for block in rb.blocks]
    return list(spec.blocks)


def _spec_title(spec: LayoutSpec | SlideSpec) -> str:
    return getattr(spec, "title", "") or ""


def _spec_key_message(spec: LayoutSpec | SlideSpec) -> str:
    return getattr(spec, "key_message", "") or ""


def _has_regions(spec: LayoutSpec | SlideSpec) -> bool:
    if _is_layout_spec(spec):
        return bool(spec.region_bindings)
    return bool(spec.blocks)


def _check_required_blocks_legacy(spec: SlideSpec, all_blocks: list[Any]) -> list[ReviewIssue]:
    issues: list[ReviewIssue] = []
    block_ids = {_block_id(block) for block in all_blocks}

    if spec.layout_template == LayoutTemplate.COVER_HERO and "hero_image" not in block_ids:
        issues.append(
            ReviewIssue(
                issue_id="R003_cover_hero",
                rule_code="MISSING_REQUIRED_BLOCK",
                layer="rule",
                severity=ReviewSeverity.P0,
                message="cover-hero requires a hero_image block",
                location=None,
                suggested_fix="Add a hero_image block or switch layout template.",
                auto_fixable=False,
            )
        )
    return issues


def _check_primitive_requirements(spec: LayoutSpec, all_blocks: list[Any]) -> list[ReviewIssue]:
    issues: list[ReviewIssue] = []
    primitive_type = spec.primitive.primitive
    content_types = {_block_type(block) for block in all_blocks if _block_content(block)}

    if primitive_type == "grid":
        expected = spec.primitive.columns * spec.primitive.rows
        actual = sum(len(rb.blocks) for rb in spec.region_bindings)
        if actual < max(1, expected // 2):
            issues.append(
                ReviewIssue(
                    issue_id="R003_grid_sparse",
                    rule_code="GRID_UNDERFILLED",
                    layer="rule",
                    severity=ReviewSeverity.P2,
                    message=f"grid expects about {expected} cells but only has {actual} blocks",
                    location=None,
                    suggested_fix="Fill more grid cells or switch to a denser layout.",
                    auto_fixable=False,
                )
            )

    elif primitive_type == "timeline":
        text_blocks = [
            block for block in all_blocks
            if _block_type(block) in {"body-text", "caption", "label"} and _block_content(block)
        ]
        if len(text_blocks) < spec.primitive.node_count:
            issues.append(
                ReviewIssue(
                    issue_id="R003_timeline_nodes",
                    rule_code="TIMELINE_UNDERFILLED",
                    layer="rule",
                    severity=ReviewSeverity.P1,
                    message=f"timeline expects {spec.primitive.node_count} nodes but only has {len(text_blocks)} text blocks",
                    location=None,
                    suggested_fix="Add node content or use a non-timeline layout.",
                    auto_fixable=False,
                )
            )

    elif primitive_type == "full-bleed" and spec.primitive.background_type == "image":
        if IMAGE_TYPES.isdisjoint(content_types):
            issues.append(
                ReviewIssue(
                    issue_id="R003_fullbleed_image",
                    rule_code="MISSING_REQUIRED_BLOCK",
                    layer="rule",
                    severity=ReviewSeverity.P1,
                    message="full-bleed image backgrounds require an image/chart/map block",
                    location=None,
                    suggested_fix="Add a visual block or use a non-image background.",
                    auto_fixable=False,
                )
            )

    return issues


def layout_lint(spec: LayoutSpec | SlideSpec) -> LayoutLintOutput:
    issues: list[ReviewIssue] = []
    all_blocks = _all_blocks(spec)

    for block in all_blocks:
        block_type = _block_type(block)
        content = _block_content(block)
        block_id = _block_id(block)

        if block_type == "heading" and isinstance(content, str) and len(content) > MAX_HEADING_CHARS:
            issues.append(
                ReviewIssue(
                    issue_id=f"R001_{block_id}",
                    rule_code="TEXT_OVERFLOW",
                    layer="rule",
                    severity=ReviewSeverity.P1,
                    message=f"heading block {block_id} is too long: {len(content)} chars",
                    location=block_id,
                    suggested_fix=f"Shorten the heading to at most {MAX_HEADING_CHARS} characters.",
                    auto_fixable=True,
                )
            )

        if block_type in TEXT_TYPES and isinstance(content, str) and len(content) >= MAX_TEXT_CHARS:
            issues.append(
                ReviewIssue(
                    issue_id=f"R001b_{block_id}",
                    rule_code="TEXT_OVERFLOW",
                    layer="rule",
                    severity=ReviewSeverity.P1,
                    message=f"text block {block_id} is too long: {len(content)} chars",
                    location=block_id,
                    suggested_fix=f"Trim the text to at most {MAX_TEXT_CHARS} characters.",
                    auto_fixable=True,
                )
            )

        if block_type == "bullet-list" and isinstance(content, list) and len(content) > MAX_BULLET_POINTS:
            issues.append(
                ReviewIssue(
                    issue_id=f"R002_{block_id}",
                    rule_code="BULLET_OVERFLOW",
                    layer="rule",
                    severity=ReviewSeverity.P1,
                    message=f"bullet block {block_id} has {len(content)} items",
                    location=block_id,
                    suggested_fix=f"Reduce to at most {MAX_BULLET_POINTS} bullet points.",
                    auto_fixable=True,
                )
            )

    if _is_layout_spec(spec):
        issues.extend(_check_primitive_requirements(spec, all_blocks))
    else:
        issues.extend(_check_required_blocks_legacy(spec, all_blocks))

    image_blocks = [block for block in all_blocks if _block_type(block) in IMAGE_TYPES]
    if len(image_blocks) > MAX_IMAGE_BLOCKS:
        issues.append(
            ReviewIssue(
                issue_id="R005_images",
                rule_code="IMAGE_COUNT_EXCEEDED",
                layer="rule",
                severity=ReviewSeverity.P2,
                message=f"slide contains {len(image_blocks)} visual blocks",
                location=None,
                suggested_fix=f"Reduce visuals to at most {MAX_IMAGE_BLOCKS}.",
                auto_fixable=True,
            )
        )

    for block in image_blocks:
        if _is_layout_spec(spec) and _block_content(block) and not _block_source_refs(block):
            issues.append(
                ReviewIssue(
                    issue_id=f"R009_{_block_id(block)}",
                    rule_code="VISUAL_SOURCE_MISSING",
                    layer="rule",
                    severity=ReviewSeverity.P2,
                    message=f"visual block {_block_id(block)} has content but no source reference",
                    location=_block_id(block),
                    suggested_fix="Attach a source_refs entry for the bound material asset.",
                    auto_fixable=False,
                )
            )

    non_empty = [block for block in all_blocks if _block_content(block) and len(str(_block_content(block))) >= 5]
    if not non_empty:
        issues.append(
            ReviewIssue(
                issue_id="R006_empty",
                rule_code="EMPTY_SLIDE",
                layer="rule",
                severity=ReviewSeverity.P0,
                message="slide has no meaningful content",
                location=None,
                suggested_fix="Add content blocks before rendering.",
                auto_fixable=False,
            )
        )

    title = _spec_title(spec)
    if title and len(title) > MAX_TITLE_CHARS:
        issues.append(
            ReviewIssue(
                issue_id="R007_title",
                rule_code="TITLE_TOO_LONG",
                layer="rule",
                severity=ReviewSeverity.P2,
                message=f"title is too long: {len(title)} chars",
                location="title",
                suggested_fix=f"Shorten the title to at most {MAX_TITLE_CHARS} characters.",
                auto_fixable=True,
            )
        )

    key_message = _spec_key_message(spec)
    if not key_message:
        issues.append(
            ReviewIssue(
                issue_id="R008_key_message",
                rule_code="KEY_MESSAGE_MISSING",
                layer="rule",
                severity=ReviewSeverity.P2,
                message="key_message is empty",
                location="key_message",
                suggested_fix="Add a concise key message for the slide.",
                auto_fixable=False,
            )
        )

    if _is_layout_spec(spec):
        has_heading = any(
            _block_type(block) in {"heading", "subheading"} and _block_content(block)
            for block in all_blocks
        )
        if not has_heading:
            issues.append(
                ReviewIssue(
                    issue_id="R010_heading",
                    rule_code="HEADING_MISSING",
                    layer="rule",
                    severity=ReviewSeverity.P2,
                    message="layout is missing a heading or subheading block",
                    location=None,
                    suggested_fix="Add a heading or subheading block.",
                    auto_fixable=False,
                )
            )

    if not _has_regions(spec):
        issues.append(
            ReviewIssue(
                issue_id="R012_no_regions",
                rule_code="NO_REGION_BINDINGS",
                layer="rule",
                severity=ReviewSeverity.P0,
                message="slide spec has no content regions",
                location=None,
                suggested_fix="Populate regions or blocks before review.",
                auto_fixable=False,
            )
        )

    total_text = sum(
        len(str(_block_content(block)))
        for block in all_blocks
        if _block_type(block) in TEXT_TYPES | {"heading"} and isinstance(_block_content(block), str)
    )
    if total_text > MAX_TEXT_CHARS * 3:
        issues.append(
            ReviewIssue(
                issue_id="R015_density",
                rule_code="EXCESSIVE_DENSITY",
                layer="rule",
                severity=ReviewSeverity.P1,
                message=f"slide contains too much text: {total_text} chars",
                location=None,
                suggested_fix="Split the content across multiple slides or trim copy.",
                auto_fixable=False,
            )
        )

    return LayoutLintOutput(
        issues=issues,
        pass_count=0 if issues else 1,
        fail_count=len(issues),
    )
