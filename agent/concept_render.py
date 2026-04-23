"""Concept Render Agent.

Reads `concept_proposals` from the latest Outline, generates 3 architectural
views per proposal via runninghub (aerial → exterior → interior, serial chain
for consistency), and persists each result as an Asset with logical_key
`concept.{index}.{view}`.

Falls back to a grey placeholder on any failure so the downstream pipeline
never blocks on image-model outages (see ADR-005).
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from config.settings import settings
from db.models.asset import Asset
from db.models.brief_doc import BriefDoc
from db.models.material_item import MaterialItem
from db.models.material_package import MaterialPackage
from db.models.outline import Outline
from db.models.project import ProjectBrief
from schema.common import AssetType
from schema.concept_proposal import (
    ConceptProposal,
    ConceptViewKind,
    concept_logical_key,
)
from tool.image_gen.concept_prompts import (
    ConceptPromptContext,
    build_prompt,
    denoise_for,
    NEGATIVE_PROMPT,
)
from tool.image_gen.placeholder import make_placeholder
from tool.image_gen.runninghub import (
    NodeOverride,
    RunningHubClient,
    RunningHubError,
    RunningHubResult,
)

logger = logging.getLogger(__name__)


SITE_REF_LOGICAL_KEY = "site.boundary.image"
_VIEW_ORDER: tuple[ConceptViewKind, ...] = (
    ConceptViewKind.AERIAL,
    ConceptViewKind.EXT_PERSPECTIVE,
    ConceptViewKind.INT_PERSPECTIVE,
)


@dataclass
class ConceptRenderStats:
    total: int
    generated: int
    placeholders: int


async def run_concept_render(project_id: UUID, db: Session) -> ConceptRenderStats:
    """Entry point. Generates 9 assets (3 proposals × 3 views) for the project."""
    if not settings.concept_render_enabled:
        logger.info("concept_render disabled via settings; skipping project=%s", project_id)
        return ConceptRenderStats(total=0, generated=0, placeholders=0)

    outline = (
        db.query(Outline)
        .filter(Outline.project_id == project_id)
        .order_by(Outline.version.desc())
        .first()
    )
    if not outline:
        raise ValueError(f"no outline found for project {project_id}")

    proposals_raw = (outline.spec_json or {}).get("concept_proposals") or []
    if not proposals_raw:
        logger.warning(
            "outline for project %s has no concept_proposals; skipping concept_render",
            project_id,
        )
        return ConceptRenderStats(total=0, generated=0, placeholders=0)

    proposals = [ConceptProposal(**raw) for raw in proposals_raw]
    proposals.sort(key=lambda p: p.index)

    brief = (
        db.query(ProjectBrief)
        .filter(ProjectBrief.project_id == project_id)
        .order_by(ProjectBrief.version.desc())
        .first()
    )
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
    site_ref_path = _resolve_site_reference(db, package) if package else None

    ctx = _build_prompt_context(brief, brief_doc)

    dest_root = _project_asset_dir(project_id)
    dest_root.mkdir(parents=True, exist_ok=True)

    stats = ConceptRenderStats(total=0, generated=0, placeholders=0)

    _clear_existing_concept_assets(db, project_id)

    can_generate = bool(settings.running_hub_key and settings.running_hub_workflow_id)
    client: Optional[RunningHubClient] = None
    if can_generate:
        client = RunningHubClient(
            api_key=settings.running_hub_key,
            workflow_id=settings.running_hub_workflow_id,
            base_url=settings.running_hub_base_url,
            poll_interval_seconds=settings.running_hub_poll_interval_seconds,
            poll_timeout_seconds=settings.running_hub_poll_timeout_seconds,
        )
    else:
        logger.warning(
            "running_hub key/workflow_id not set; all concept images will use placeholders"
        )

    try:
        tasks = [
            _render_proposal(
                proposal=proposal,
                ctx=ctx,
                site_ref_path=site_ref_path,
                client=client,
                dest_root=dest_root,
            )
            for proposal in proposals
        ]
        results = await asyncio.gather(*tasks, return_exceptions=False)
    finally:
        if client is not None:
            await client.aclose()

    for proposal, per_view in zip(proposals, results):
        for view, outcome in per_view.items():
            stats.total += 1
            if outcome.is_placeholder:
                stats.placeholders += 1
            else:
                stats.generated += 1
            _persist_asset(
                db=db,
                project_id=project_id,
                package_id=package.id if package else None,
                proposal=proposal,
                view=view,
                outcome=outcome,
            )

    db.commit()
    logger.info(
        "concept_render project=%s generated=%d placeholders=%d",
        project_id,
        stats.generated,
        stats.placeholders,
    )
    return stats


# ---------------------------------------------------------------------------
# Per-proposal rendering (serial chain aerial → ext → int)
# ---------------------------------------------------------------------------


@dataclass
class _RenderOutcome:
    local_path: Path
    is_placeholder: bool
    file_url: Optional[str] = None
    task_id: Optional[str] = None
    error: Optional[str] = None


async def _render_proposal(
    *,
    proposal: ConceptProposal,
    ctx: ConceptPromptContext,
    site_ref_path: Optional[Path],
    client: Optional[RunningHubClient],
    dest_root: Path,
) -> dict[ConceptViewKind, _RenderOutcome]:
    outcomes: dict[ConceptViewKind, _RenderOutcome] = {}
    prev_ref: Optional[Path] = site_ref_path

    for view in _VIEW_ORDER:
        dest_path = dest_root / f"concept_{proposal.index}_{view.value}.png"
        outcome = await _render_single_view(
            proposal=proposal,
            view=view,
            ctx=ctx,
            ref_image_path=prev_ref,
            client=client,
            dest_path=dest_path,
        )
        outcomes[view] = outcome
        if not outcome.is_placeholder:
            prev_ref = outcome.local_path

    return outcomes


async def _render_single_view(
    *,
    proposal: ConceptProposal,
    view: ConceptViewKind,
    ctx: ConceptPromptContext,
    ref_image_path: Optional[Path],
    client: Optional[RunningHubClient],
    dest_path: Path,
) -> _RenderOutcome:
    if client is None or ref_image_path is None:
        reason = "runninghub disabled" if client is None else "no reference image"
        return _placeholder_outcome(proposal, view, dest_path, reason)

    prompt = build_prompt(proposal, view, ctx)
    try:
        ref_filename = await client.upload_image(ref_image_path)
        overrides = _build_node_overrides(
            prompt=prompt,
            ref_filename=ref_filename,
            denoise=denoise_for(view),
            seed=_seed_for(proposal.index, view),
        )
        result: RunningHubResult = await client.run_workflow(
            node_overrides=overrides,
            dest_path=dest_path,
        )
        return _RenderOutcome(
            local_path=result.local_path or dest_path,
            is_placeholder=False,
            file_url=result.file_url,
            task_id=result.task_id,
        )
    except RunningHubError as exc:
        logger.warning(
            "runninghub failed for proposal=%s view=%s: %s",
            proposal.index,
            view.value,
            exc,
        )
        return _placeholder_outcome(proposal, view, dest_path, str(exc))
    except Exception as exc:  # network, disk, etc.
        logger.exception(
            "unexpected error in concept render proposal=%s view=%s",
            proposal.index,
            view.value,
        )
        return _placeholder_outcome(proposal, view, dest_path, repr(exc))


def _placeholder_outcome(
    proposal: ConceptProposal,
    view: ConceptViewKind,
    dest_path: Path,
    reason: str,
) -> _RenderOutcome:
    subtitle = f"方案 {proposal.index} · {_view_label(view)}"
    make_placeholder(dest_path, main_text="生成失败", subtitle=subtitle)
    return _RenderOutcome(
        local_path=dest_path,
        is_placeholder=True,
        error=reason,
    )


def _view_label(view: ConceptViewKind) -> str:
    return {
        ConceptViewKind.AERIAL: "鸟瞰图",
        ConceptViewKind.EXT_PERSPECTIVE: "室外人视图",
        ConceptViewKind.INT_PERSPECTIVE: "室内人视图",
    }[view]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_site_reference(db: Session, package: MaterialPackage) -> Optional[Path]:
    item = (
        db.query(MaterialItem)
        .filter(MaterialItem.package_id == package.id)
        .filter(MaterialItem.logical_key == SITE_REF_LOGICAL_KEY)
        .first()
    )
    if not item or not item.source_path:
        logger.warning(
            "material package %s has no %s — aerial ref image unavailable",
            package.id,
            SITE_REF_LOGICAL_KEY,
        )
        return None
    path = Path(item.source_path)
    if not path.exists():
        logger.warning("site boundary image path does not exist: %s", path)
        return None
    return path


def _build_prompt_context(
    brief: Optional[ProjectBrief],
    brief_doc: Optional[BriefDoc],
) -> ConceptPromptContext:
    building_type = brief.building_type if brief else "building"
    style_prefs = ""
    if brief and brief.style_preferences:
        style_prefs = ", ".join(brief.style_preferences)

    site_context = ""
    if brief_doc and brief_doc.outline_json:
        emphasis = brief_doc.outline_json.get("recommended_emphasis") or {}
        site_context = emphasis.get("site_advantage") or ""
        if not site_context:
            site_context = brief_doc.outline_json.get("positioning_statement") or ""

    if not site_context and brief:
        city = brief.city or ""
        site_context = f"{city} urban context" if city else ""

    return ConceptPromptContext(
        building_type=building_type or "building",
        site_context=site_context or "urban site",
        style_prefs=style_prefs or "contemporary",
    )


def _build_node_overrides(
    *,
    prompt: str,
    ref_filename: str,
    denoise: float,
    seed: int,
) -> list[NodeOverride]:
    overrides: list[NodeOverride] = [
        NodeOverride(
            node_id=settings.running_hub_prompt_node_id,
            field_name="text",
            field_value=prompt,
        ),
        NodeOverride(
            node_id=settings.running_hub_init_image_node_id,
            field_name="image",
            field_value=ref_filename,
        ),
        NodeOverride(
            node_id=settings.running_hub_init_image_node_id,
            field_name="denoise",
            field_value=denoise,
        ),
    ]
    if settings.running_hub_negative_prompt_node_id:
        overrides.append(
            NodeOverride(
                node_id=settings.running_hub_negative_prompt_node_id,
                field_name="text",
                field_value=NEGATIVE_PROMPT,
            )
        )
    if settings.running_hub_seed_node_id:
        overrides.append(
            NodeOverride(
                node_id=settings.running_hub_seed_node_id,
                field_name="seed",
                field_value=seed,
            )
        )
    return overrides


def _seed_for(proposal_index: int, view: ConceptViewKind) -> int:
    base = proposal_index * 10_000
    delta = {
        ConceptViewKind.AERIAL: 0,
        ConceptViewKind.EXT_PERSPECTIVE: 17,
        ConceptViewKind.INT_PERSPECTIVE: 43,
    }[view]
    return base + delta


def _project_asset_dir(project_id: UUID) -> Path:
    return Path(settings.running_hub_asset_dir) / str(project_id) / "concepts"


def _clear_existing_concept_assets(db: Session, project_id: UUID) -> None:
    db.query(Asset).filter(
        Asset.project_id == project_id,
        Asset.logical_key.like("concept.%"),
    ).delete(synchronize_session=False)


def _persist_asset(
    *,
    db: Session,
    project_id: UUID,
    package_id: Optional[UUID],
    proposal: ConceptProposal,
    view: ConceptViewKind,
    outcome: _RenderOutcome,
) -> None:
    logical_key = concept_logical_key(proposal.index, view)
    title = f"{proposal.name} · {_view_label(view)}"
    asset = Asset(
        id=uuid.uuid4(),
        project_id=project_id,
        package_id=package_id,
        version=1,
        status="ready" if not outcome.is_placeholder else "fallback",
        asset_type=AssetType.IMAGE.value,
        subtype=f"concept_{view.value}",
        title=title,
        image_url=str(outcome.local_path),
        summary=proposal.design_idea,
        logical_key=logical_key,
        render_role=view.value,
        source_info={
            "source": "runninghub" if not outcome.is_placeholder else "placeholder",
            "task_id": outcome.task_id,
            "file_url": outcome.file_url,
            "local_path": str(outcome.local_path),
        },
        data_json={
            "proposal_index": proposal.index,
            "proposal_name": proposal.name,
            "view": view.value,
        },
        config_json={
            "generation_failed": outcome.is_placeholder,
            "error": outcome.error,
        },
        error_message=outcome.error if outcome.is_placeholder else None,
        is_primary=True,
    )
    db.add(asset)
