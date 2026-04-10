from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from config.ppt_blueprint import PPT_BLUEPRINT
from db.models.asset import Asset
from db.models.material_item import MaterialItem
from db.models.material_package import MaterialPackage
from db.models.outline import Outline
from db.models.slide_material_binding import SlideMaterialBinding
from schema.outline import OutlineSpec, OutlineSlideEntry
from schema.page_slot import PageSlot, PageSlotGroup, normalize_slot_id
from tool.material_resolver import expand_requirement, find_matching_assets, find_matching_items, summarize_evidence

logger = logging.getLogger(__name__)


def _all_blueprint_slots() -> dict[str, PageSlot]:
    mapping: dict[str, PageSlot] = {}
    for item in PPT_BLUEPRINT:
        if isinstance(item, PageSlot):
            mapping[item.slot_id] = item
        elif isinstance(item, PageSlotGroup):
            mapping[item.slot_template.slot_id] = item.slot_template
    return mapping


def _find_slot(slot_id: str) -> Optional[PageSlot]:
    return _all_blueprint_slots().get(normalize_slot_id(slot_id))


def _collect_required_patterns(entry: OutlineSlideEntry) -> list[str]:
    if entry.required_input_keys:
        patterns: list[str] = []
        for key in entry.required_input_keys:
            patterns.extend(expand_requirement(key))
        return patterns

    slot = _find_slot(entry.slot_id)
    if not slot:
        return []
    patterns: list[str] = []
    for req in slot.required_inputs:
        patterns.extend(expand_requirement(req))
    return patterns


def _build_binding(
    project_id: UUID,
    outline_id: UUID,
    package_id: UUID,
    entry: OutlineSlideEntry,
    items: list[MaterialItem],
    assets: list[Asset],
    existing_version: int = 0,
) -> SlideMaterialBinding:
    required_patterns = _collect_required_patterns(entry)
    matched_items = find_matching_items(required_patterns, items)
    matched_assets = find_matching_assets(required_patterns, assets)
    missing_patterns = [
        pattern for pattern in required_patterns
        if not any(item.logical_key and item.logical_key.startswith(pattern.rstrip("*")) for item in matched_items)
    ]
    required_count = len(required_patterns) or 1
    coverage_score = round((required_count - len(missing_patterns)) / required_count, 4)
    source_item_ids = [str(item.id) for item in matched_items]
    derived_asset_ids = [str(asset.id) for asset in matched_assets]
    evidence_snippets = summarize_evidence(matched_items)

    return SlideMaterialBinding(
        project_id=project_id,
        package_id=package_id,
        outline_id=outline_id,
        slide_no=entry.slide_no,
        slot_id=entry.slot_id or normalize_slot_id(entry.title),
        version=existing_version + 1,
        status="ready",
        must_use_item_ids=source_item_ids,
        optional_item_ids=[],
        derived_asset_ids=derived_asset_ids,
        evidence_snippets=evidence_snippets,
        coverage_score=coverage_score,
        missing_requirements=missing_patterns,
        binding_reason=f"Matched {len(matched_items)} items and {len(matched_assets)} assets for slide {entry.slide_no}",
    )


def bind_outline_slides(project_id: UUID, outline_id: UUID, db: Session) -> list[SlideMaterialBinding]:
    outline = db.get(Outline, outline_id)
    if not outline:
        raise ValueError(f"Outline not found: {outline_id}")

    package = (
        db.query(MaterialPackage)
        .filter(MaterialPackage.project_id == project_id)
        .order_by(MaterialPackage.version.desc())
        .first()
    )
    if not package:
        logger.info("bind_outline_slides: no material package found; skipping binding")
        return []

    items = db.query(MaterialItem).filter(MaterialItem.package_id == package.id).all()
    assets = db.query(Asset).filter(Asset.package_id == package.id).all()
    spec = OutlineSpec.model_validate(outline.spec_json)

    db.query(SlideMaterialBinding).filter(
        SlideMaterialBinding.project_id == project_id,
        SlideMaterialBinding.outline_id == outline_id,
    ).delete(synchronize_session=False)

    bindings = []
    for entry in spec.slides:
        prev = (
            db.query(SlideMaterialBinding)
            .filter(
                SlideMaterialBinding.project_id == project_id,
                SlideMaterialBinding.package_id == package.id,
                SlideMaterialBinding.slide_no == entry.slide_no,
            )
            .order_by(SlideMaterialBinding.version.desc())
            .first()
        )
        version = prev.version if prev else 0
        binding = _build_binding(project_id, outline_id, package.id, entry, items, assets, existing_version=version)
        db.add(binding)
        db.flush()
        bindings.append(binding)

    return bindings
