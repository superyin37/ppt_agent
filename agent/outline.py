"""
Outline Agent.

Prefers a material-package context when available while staying compatible with
legacy asset-driven projects.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.orm import Session

from config.llm import STRONG_MODEL, call_llm_with_limit
from config.ppt_blueprint import PPT_BLUEPRINT
from db.models.asset import Asset
from db.models.brief_doc import BriefDoc
from db.models.material_item import MaterialItem
from db.models.material_package import MaterialPackage
from db.models.outline import Outline
from db.models.project import Project, ProjectBrief
from schema.common import ProjectStatus
from schema.outline import OutlineSlideEntry, OutlineSpec
from schema.page_slot import PageSlot, PageSlotGroup, SlotAssignment, normalize_slot_id
from tool.material_resolver import expand_requirement, find_matching_items

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "outline_system_v2.md"


class _SlotAssignmentLLM(BaseModel):
    slot_id: str
    slide_no: int
    section: str
    title: str
    content_directive: str
    asset_keys: list[str] = []
    layout_hint: str = ""
    is_cover: bool = False
    is_chapter_divider: bool = False
    estimated_content_density: str = "medium"


class _OutlineLLMOutput(BaseModel):
    deck_title: str
    total_pages: int
    assignments: list[_SlotAssignmentLLM]


def _slot_map() -> dict[str, PageSlot]:
    mapping: dict[str, PageSlot] = {}
    for item in PPT_BLUEPRINT:
        if isinstance(item, PageSlot):
            mapping[item.slot_id] = item
        elif isinstance(item, PageSlotGroup):
            mapping[item.slot_template.slot_id] = item.slot_template
    return mapping


def _find_slot(slot_id: str) -> Optional[PageSlot]:
    return _slot_map().get(normalize_slot_id(slot_id))


def _load_system_prompt(brief: ProjectBrief, brief_doc: Optional[BriefDoc]) -> str:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    outline_json = brief_doc.outline_json if brief_doc else {}
    return (
        template
        .replace("{building_type}", brief.building_type or "building")
        .replace("{project_name}", brief.client_name or "未命名项目")
        .replace("{client_name}", brief.client_name or "")
        .replace("{city}", brief.city or "")
        .replace("{province}", brief.province or "")
        .replace("{positioning_statement}", outline_json.get("positioning_statement", ""))
        .replace("{narrative_arc}", outline_json.get("narrative_arc", ""))
    )


def _build_blueprint_summary(reference_count: int) -> str:
    lines = ["<blueprint>"]
    for item in PPT_BLUEPRINT:
        if isinstance(item, PageSlot):
            lines.append(
                json.dumps({
                    "slot_id": item.slot_id,
                    "title": item.title,
                    "chapter": item.chapter,
                    "is_cover": item.is_cover,
                    "is_chapter_divider": item.is_chapter_divider,
                    "layout_hint": item.layout_hint,
                    "required_inputs": item.required_input_keys,
                }, ensure_ascii=False)
            )
        else:
            count = reference_count if item.group_id == "reference-case-pages" else item.repeat_count_min
            for i in range(1, count + 1):
                lines.append(
                    json.dumps({
                        "slot_id": f"{item.slot_template.slot_id}-{i}",
                        "title": f"{item.slot_template.title} {i}/{count}",
                        "chapter": item.slot_template.chapter,
                        "layout_hint": item.slot_template.layout_hint,
                        "required_inputs": item.slot_template.required_input_keys,
                    }, ensure_ascii=False)
                )
    lines.append("</blueprint>")
    return "\n".join(lines)


def _build_user_message(
    brief: ProjectBrief,
    brief_doc: Optional[BriefDoc],
    assets: list[Asset],
    package: Optional[MaterialPackage],
    material_items: list[MaterialItem],
    reference_count: int,
) -> str:
    parts = [
        f"<project_brief>\n{json.dumps({'building_type': brief.building_type, 'client_name': brief.client_name, 'city': brief.city, 'style_preferences': brief.style_preferences or []}, ensure_ascii=False, indent=2)}\n</project_brief>",
    ]
    if brief_doc:
        parts.append(f"<brief_doc>\n{json.dumps(brief_doc.outline_json, ensure_ascii=False, indent=2)}\n</brief_doc>")
    parts.append(_build_blueprint_summary(reference_count))
    parts.append(f"<reference_count>{reference_count}</reference_count>")

    if package:
        parts.append(f"<material_package>\n{json.dumps({'summary': package.summary_json or {}, 'manifest': package.manifest_json or {}}, ensure_ascii=False, indent=2)}\n</material_package>")
    else:
        asset_summary = [{"key": str(a.id), "type": a.asset_type, "subtype": a.subtype, "title": a.title} for a in assets]
        parts.append(f"<available_assets>\n{json.dumps(asset_summary, ensure_ascii=False, indent=2)}\n</available_assets>")

    if material_items:
        snippets = [
            {"logical_key": item.logical_key, "title": item.title, "snippet": (item.text_content or "")[:200]}
            for item in material_items
            if item.text_content
        ][:15]
        parts.append(f"<material_snippets>\n{json.dumps(snippets, ensure_ascii=False, indent=2)}\n</material_snippets>")
    return "\n\n".join(parts)


def _compute_coverage(slot_id: str, material_items: list[MaterialItem]) -> tuple[str, list[str]]:
    slot = _find_slot(slot_id)
    if not slot or not slot.required_inputs:
        return "not_applicable", []
    required_patterns = []
    missing = []
    for req in slot.required_inputs:
        patterns = expand_requirement(req)
        if not patterns:
            continue
        required_patterns.extend(patterns)
        if not find_matching_items(patterns, material_items):
            missing.extend(patterns)
    if not required_patterns:
        return "not_applicable", []
    if not missing:
        return "complete", []
    if len(missing) < len(required_patterns):
        return "partial", missing
    return "missing", missing


async def generate_outline(project_id: UUID, db: Session) -> Outline:
    brief = (
        db.query(ProjectBrief)
        .filter(ProjectBrief.project_id == project_id)
        .order_by(ProjectBrief.version.desc())
        .first()
    )
    if not brief:
        raise ValueError(f"No brief found for project {project_id}")

    brief_doc = (
        db.query(BriefDoc)
        .filter(BriefDoc.project_id == project_id)
        .order_by(BriefDoc.version.desc())
        .first()
    )
    package = (
        db.query(MaterialPackage)
        .filter(MaterialPackage.project_id == project_id)
        .order_by(MaterialPackage.version.desc())
        .first()
    )
    material_items = db.query(MaterialItem).filter(MaterialItem.package_id == package.id).all() if package else []
    assets = db.query(Asset).filter(Asset.project_id == project_id).all()

    if package:
        case_numbers = {
            item.logical_key.split(".")[2]
            for item in material_items
            if item.logical_key.startswith("reference.case.") and item.logical_key.endswith(".source")
        }
        reference_count = max(2, min(5, len(case_numbers) or 3))
    else:
        reference_count = sum(1 for asset in assets if asset.asset_type == "reference" and asset.subtype == "selected")
        reference_count = max(2, min(5, reference_count or 3))

    system_prompt = _load_system_prompt(brief, brief_doc)
    user_message = _build_user_message(brief, brief_doc, assets, package, material_items, reference_count)

    logger.info("generate_outline: calling LLM for project=%s package=%s", project_id, getattr(package, "id", None))
    try:
        result: _OutlineLLMOutput = await call_llm_with_limit(
            system_prompt=system_prompt,
            user_message=user_message,
            output_schema=_OutlineLLMOutput,
            model=STRONG_MODEL,
            temperature=0.4,
            max_tokens=16000,
        )
    except Exception as exc:
        logger.error("Outline LLM failed: %s", exc)
        result = _fallback_outline(brief, reference_count)

    assignments = [
        SlotAssignment(
            slot_id=a.slot_id,
            slide_no=a.slide_no,
            section=a.section,
            title=a.title,
            content_directive=a.content_directive,
            asset_keys=a.asset_keys,
            layout_hint=a.layout_hint,
            is_cover=a.is_cover,
            is_chapter_divider=a.is_chapter_divider,
            estimated_content_density=a.estimated_content_density,
        )
        for a in result.assignments
    ]

    coverage_by_slide: dict[str, dict] = {}
    slot_binding_hints: dict[str, dict] = {}
    slides: list[OutlineSlideEntry] = []
    for assignment in assignments:
        slot = _find_slot(assignment.slot_id)
        required_input_keys = slot.required_input_keys if slot else []
        coverage_status, missing_patterns = _compute_coverage(assignment.slot_id, material_items)
        recommended_scope = [item.logical_key for item in material_items[:20] if normalize_slot_id(assignment.slot_id) in item.logical_key]
        coverage_by_slide[str(assignment.slide_no)] = {
            "slot_id": assignment.slot_id,
            "coverage_status": coverage_status,
            "missing_patterns": missing_patterns,
        }
        slot_binding_hints[str(assignment.slide_no)] = {
            "required_input_keys": required_input_keys,
            "recommended_binding_scope": recommended_scope[:10],
        }
        slides.append(
            OutlineSlideEntry(
                slot_id=assignment.slot_id,
                slide_no=assignment.slide_no,
                section=assignment.section,
                title=assignment.title,
                purpose=assignment.content_directive[:120],
                key_message=assignment.content_directive,
                required_assets=assignment.asset_keys,
                required_input_keys=required_input_keys,
                coverage_status=coverage_status,
                recommended_binding_scope=recommended_scope[:10],
                layout_hint=assignment.layout_hint,
                estimated_content_density=assignment.estimated_content_density,
                is_cover=assignment.is_cover,
                is_chapter_divider=assignment.is_chapter_divider,
            )
        )

    actual_total_pages = len(slides)
    if result.total_pages != actual_total_pages:
        logger.warning(
            "Outline total_pages mismatch for project %s: llm=%s actual=%s; using actual slide count",
            project_id,
            result.total_pages,
            actual_total_pages,
        )

    spec = OutlineSpec(
        project_id=project_id,
        deck_title=result.deck_title,
        theme=brief.building_type or "modern",
        total_pages=actual_total_pages,
        sections=list(dict.fromkeys(slide.section for slide in slides)),
        slides=slides,
    )

    existing = (
        db.query(Outline)
        .filter(Outline.project_id == project_id)
        .order_by(Outline.version.desc())
        .first()
    )
    new_version = (existing.version + 1) if existing else 1

    outline = Outline(
        project_id=project_id,
        package_id=package.id if package else None,
        version=new_version,
        status="draft",
        deck_title=spec.deck_title,
        theme=spec.theme,
        total_pages=spec.total_pages,
        spec_json=spec.model_dump(mode="json"),
        coverage_json=coverage_by_slide,
        slot_binding_hints_json=slot_binding_hints,
    )
    db.add(outline)

    project = db.get(Project, project_id)
    if project:
        project.status = ProjectStatus.OUTLINE_READY.value
        project.current_phase = "outline_review"

    db.commit()
    db.refresh(outline)
    return outline


def _fallback_outline(brief: ProjectBrief, reference_count: int) -> _OutlineLLMOutput:
    client = brief.client_name or "项目"
    building_type = brief.building_type or "building"
    assignments: list[_SlotAssignmentLLM] = []
    slide_no = 1
    for item in PPT_BLUEPRINT:
        if isinstance(item, PageSlot):
            slots = [(item.slot_id, item.title, item)]
        else:
            count = reference_count if item.group_id == "reference-case-pages" else item.repeat_count_min
            slots = [
                (f"{item.slot_template.slot_id}-{i}", f"{item.slot_template.title} {i}/{count}", item.slot_template)
                for i in range(1, count + 1)
            ]
        for slot_id, title, slot in slots:
            assignments.append(
                _SlotAssignmentLLM(
                    slot_id=slot_id,
                    slide_no=slide_no,
                    section=slot.chapter,
                    title=title,
                    content_directive=f"[{client} {building_type}] {slot.content_task[:220]}",
                    asset_keys=[],
                    layout_hint=slot.layout_hint,
                    is_cover=slot.is_cover,
                    is_chapter_divider=slot.is_chapter_divider,
                    estimated_content_density="medium",
                )
            )
            slide_no += 1
    return _OutlineLLMOutput(
        deck_title=f"{client} {building_type.title()} 设计建议书",
        total_pages=len(assignments),
        assignments=assignments,
    )
