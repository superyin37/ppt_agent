from __future__ import annotations

from typing import Any

from schema.review import RepairAction, ReviewReport
from schema.slide import BlockContent as LegacyBlockContent
from schema.slide import SlideSpec
from schema.visual_theme import ContentBlock, LayoutSpec, RegionBinding

MAX_TEXT_CHARS = 300
MAX_HEADING_CHARS = 40
MAX_BULLET_POINTS = 5
MAX_IMAGE_BLOCKS = 4
IMAGE_TYPES = {"image", "chart", "map"}

AUTO_ACTIONS = {
    "truncate_text",
    "truncate_bullets",
    "truncate_title",
    "remove_extra_images",
    "fill_footer_defaults",
    "replace_client_name",
}


def _is_layout_spec(spec: LayoutSpec | SlideSpec) -> bool:
    return hasattr(spec, "region_bindings")


def execute_repair(spec: LayoutSpec | SlideSpec, report: ReviewReport) -> tuple[LayoutSpec | SlideSpec, list[str]]:
    logs: list[str] = []
    for action in report.repair_plan:
        if not _is_auto_executable(action):
            logs.append(f"skip (manual): {action.action_type}")
            continue
        spec, log = _apply_action(spec, action)
        logs.append(log)
    return spec, logs


def _apply_action(spec: LayoutSpec | SlideSpec, action: RepairAction) -> tuple[LayoutSpec | SlideSpec, str]:
    if action.action_type == "truncate_text":
        max_chars = action.params.get("max_chars", MAX_TEXT_CHARS)
        return _update_block_text(spec, action.target_block_id, max_chars), f"truncate_text: {action.target_block_id} -> {max_chars}"

    if action.action_type == "truncate_bullets":
        max_bullets = action.params.get("max_bullets", MAX_BULLET_POINTS)
        return _truncate_bullet_block(spec, action.target_block_id, max_bullets), f"truncate_bullets: {action.target_block_id} -> {max_bullets}"

    if action.action_type == "truncate_title":
        max_chars = action.params.get("max_chars", MAX_HEADING_CHARS)
        title = spec.title
        new_title = title[:max_chars] + "…" if len(title) > max_chars else title
        return spec.model_copy(update={"title": new_title}), f"truncate_title: {new_title}"

    if action.action_type == "remove_extra_images":
        return _remove_extra_image_blocks(spec, MAX_IMAGE_BLOCKS), f"remove_extra_images: kept {MAX_IMAGE_BLOCKS}"

    if action.action_type == "replace_client_name":
        correct_name = action.params.get("correct_name", "")
        if action.target_block_id and correct_name:
            block = _find_block(spec, action.target_block_id)
            if block and isinstance(_block_content(block), str):
                return _update_block_content(spec, action.target_block_id, correct_name), f"replace_client_name: {action.target_block_id}"
        return spec, "replace_client_name: skipped"

    if action.action_type == "fill_footer_defaults":
        return spec, "fill_footer_defaults: delegated to caller"

    return spec, f"skip: {action.action_type}"


def _block_id(block: Any) -> str:
    return getattr(block, "block_id", "")


def _block_type(block: Any) -> str:
    raw = getattr(block, "content_type", None) or getattr(block, "block_type", "")
    legacy_map = {"bullet": "bullet-list", "text": "body-text"}
    return legacy_map.get(raw, raw)


def _block_content(block: Any) -> Any:
    return getattr(block, "content", None)


def _find_block(spec: LayoutSpec | SlideSpec, block_id: str) -> Any | None:
    if _is_layout_spec(spec):
        for region in spec.region_bindings:
            for block in region.blocks:
                if block.block_id == block_id:
                    return block
        return None

    for block in spec.blocks:
        if block.block_id == block_id:
            return block
    return None


def _update_block_content(spec: LayoutSpec | SlideSpec, block_id: str, new_content: Any) -> LayoutSpec | SlideSpec:
    if _is_layout_spec(spec):
        regions: list[RegionBinding] = []
        for region in spec.region_bindings:
            blocks = [
                block.model_copy(update={"content": new_content}) if block.block_id == block_id else block
                for block in region.blocks
            ]
            regions.append(region.model_copy(update={"blocks": blocks}))
        return spec.model_copy(update={"region_bindings": regions})

    blocks = [
        block.model_copy(update={"content": new_content}) if block.block_id == block_id else block
        for block in spec.blocks
    ]
    return spec.model_copy(update={"blocks": blocks})


def _update_block_text(spec: LayoutSpec | SlideSpec, block_id: str | None, max_chars: int) -> LayoutSpec | SlideSpec:
    if not block_id:
        return spec
    block = _find_block(spec, block_id)
    if not block or not isinstance(_block_content(block), str):
        return spec

    text = _block_content(block)
    if len(text) <= max_chars:
        return spec
    return _update_block_content(spec, block_id, text[:max_chars] + "…")


def _truncate_bullet_block(spec: LayoutSpec | SlideSpec, block_id: str | None, max_items: int) -> LayoutSpec | SlideSpec:
    if not block_id:
        return spec
    block = _find_block(spec, block_id)
    if not block or not isinstance(_block_content(block), list):
        return spec
    return _update_block_content(spec, block_id, _block_content(block)[:max_items])


def _remove_extra_image_blocks(spec: LayoutSpec | SlideSpec, max_count: int) -> LayoutSpec | SlideSpec:
    if _is_layout_spec(spec):
        image_count = 0
        regions: list[RegionBinding] = []
        for region in spec.region_bindings:
            kept: list[ContentBlock] = []
            for block in region.blocks:
                if _block_type(block) in IMAGE_TYPES:
                    image_count += 1
                    if image_count > max_count:
                        continue
                kept.append(block)
            regions.append(region.model_copy(update={"blocks": kept}))
        return spec.model_copy(update={"region_bindings": regions})

    image_count = 0
    kept: list[LegacyBlockContent] = []
    for block in spec.blocks:
        if _block_type(block) in IMAGE_TYPES:
            image_count += 1
            if image_count > max_count:
                continue
        kept.append(block)
    return spec.model_copy(update={"blocks": kept})


def _is_auto_executable(action: RepairAction) -> bool:
    return action.action_type in AUTO_ACTIONS


def build_repair_plan_from_issues(issues: list[Any]) -> list[RepairAction]:
    actions: list[RepairAction] = []
    for issue in issues:
        if not issue.auto_fixable:
            continue

        if issue.rule_code == "TEXT_OVERFLOW":
            max_chars = MAX_HEADING_CHARS if issue.location == "title" else MAX_TEXT_CHARS
            actions.append(
                RepairAction(
                    action_type="truncate_text",
                    target_block_id=issue.location,
                    params={"max_chars": max_chars},
                )
            )
        elif issue.rule_code == "BULLET_OVERFLOW":
            actions.append(
                RepairAction(
                    action_type="truncate_bullets",
                    target_block_id=issue.location,
                    params={"max_bullets": MAX_BULLET_POINTS},
                )
            )
        elif issue.rule_code == "TITLE_TOO_LONG":
            actions.append(RepairAction(action_type="truncate_title", params={"max_chars": MAX_HEADING_CHARS}))
        elif issue.rule_code == "IMAGE_COUNT_EXCEEDED":
            actions.append(RepairAction(action_type="remove_extra_images"))
        elif issue.rule_code == "FOOTER_DATA_MISSING":
            actions.append(RepairAction(action_type="fill_footer_defaults"))

    return actions
