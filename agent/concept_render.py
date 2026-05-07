"""Concept Render Agent.

Reads `concept_proposals` from the latest Outline, generates 3 architectural
views per proposal via runninghub (aerial → exterior → interior, serial chain
for consistency), and persists each result as an Asset with logical_key
`concept.{index}.{view}`.

By default it falls back to a grey placeholder on failure so the background
pipeline can keep moving. E2E/acceptance runs can enable strict mode to fail
when any required concept image is still a placeholder.
"""
from __future__ import annotations

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
)
from tool.image_gen.placeholder import make_placeholder
from tool.image_gen.runninghub import (
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
    reused: int = 0
    failures: list[dict[str, str]] | None = None


class ConceptRenderStrictError(RuntimeError):
    """Raised when strict concept rendering leaves one or more placeholders."""

    def __init__(self, stats: ConceptRenderStats) -> None:
        self.stats = stats
        failures = stats.failures or []
        failure_text = "; ".join(
            f"{item.get('logical_key')}: {item.get('error')}" for item in failures[:5]
        )
        super().__init__(
            "concept render strict gate failed: "
            f"generated={stats.generated}/{stats.total}, placeholders={stats.placeholders}"
            + (f" ({failure_text})" if failure_text else "")
        )


async def run_concept_render(
    project_id: UUID,
    db: Session,
    *,
    strict: bool = False,
    reuse_existing: bool = True,
) -> ConceptRenderStats:
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

    stats = ConceptRenderStats(total=0, generated=0, placeholders=0, reused=0, failures=[])

    existing_ready = _load_existing_ready_concept_outcomes(db, project_id) if reuse_existing else {}
    if reuse_existing:
        _clear_failed_concept_assets(db, project_id)
    else:
        _clear_existing_concept_assets(db, project_id)

    can_generate = bool(settings.running_hub_key)
    client: Optional[RunningHubClient] = None
    if can_generate:
        client = RunningHubClient(
            api_key=settings.running_hub_key,
            base_url=settings.running_hub_base_url,
            model_path=settings.running_hub_model_path,
            query_path=settings.running_hub_query_path,
            poll_interval_seconds=settings.running_hub_poll_interval_seconds,
            poll_timeout_seconds=settings.running_hub_poll_timeout_seconds,
        )
    else:
        logger.warning(
            "running_hub key not set; all concept images will use placeholders"
        )

    try:
        results = []
        for proposal in proposals:
            results.append(
                await _render_proposal(
                    proposal=proposal,
                    ctx=ctx,
                    site_ref_path=site_ref_path,
                    client=client,
                    dest_root=dest_root,
                    existing_ready=existing_ready,
                )
            )
    finally:
        if client is not None:
            await client.aclose()

    for proposal, per_view in zip(proposals, results):
        for view, outcome in per_view.items():
            stats.total += 1
            if outcome.is_placeholder:
                stats.placeholders += 1
                if stats.failures is not None:
                    stats.failures.append(
                        {
                            "logical_key": concept_logical_key(proposal.index, view),
                            "error": outcome.error or "placeholder generated",
                        }
                    )
            else:
                stats.generated += 1
                if outcome.reused:
                    stats.reused += 1
            if not outcome.reused:
                _persist_asset(
                    db=db,
                    project_id=project_id,
                    package_id=package.id if package else None,
                    proposal=proposal,
                    view=view,
                    outcome=outcome,
                )

    if strict and stats.placeholders:
        raise ConceptRenderStrictError(stats)

    db.commit()
    logger.info(
        "concept_render project=%s generated=%d placeholders=%d reused=%d",
        project_id,
        stats.generated,
        stats.placeholders,
        stats.reused,
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
    reused: bool = False


async def _render_proposal(
    *,
    proposal: ConceptProposal,
    ctx: ConceptPromptContext,
    site_ref_path: Optional[Path],
    client: Optional[RunningHubClient],
    dest_root: Path,
    existing_ready: dict[str, _RenderOutcome],
) -> dict[ConceptViewKind, _RenderOutcome]:
    outcomes: dict[ConceptViewKind, _RenderOutcome] = {}
    prev_ref: Optional[Path] = site_ref_path

    for view in _VIEW_ORDER:
        dest_path = dest_root / f"concept_{proposal.index}_{view.value}.png"
        logical_key = concept_logical_key(proposal.index, view)
        if logical_key in existing_ready:
            outcome = existing_ready[logical_key]
            outcomes[view] = outcome
            prev_ref = outcome.local_path
            logger.info("reusing existing concept asset %s from %s", logical_key, outcome.local_path)
            continue

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
    attempts = max(1, int(getattr(settings, "running_hub_generation_retries", 1) or 1))
    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            result = await client.run_image_to_image(
                image_path=ref_image_path,
                prompt=prompt,
                dest_path=dest_path,
                aspect_ratio="16:9",
                resolution="1k",
            )
            return _RenderOutcome(
                local_path=result.local_path or dest_path,
                is_placeholder=False,
                file_url=result.file_url,
                task_id=result.task_id,
            )
        except RunningHubError as exc:
            last_error = str(exc)
            logger.warning(
                "runninghub failed for proposal=%s view=%s attempt=%d/%d: %s",
                proposal.index,
                view.value,
                attempt,
                attempts,
                exc,
            )
        except Exception as exc:  # network, disk, etc.
            last_error = repr(exc)
            logger.exception(
                "unexpected error in concept render proposal=%s view=%s attempt=%d/%d",
                proposal.index,
                view.value,
                attempt,
                attempts,
            )

    return _placeholder_outcome(proposal, view, dest_path, last_error or "runninghub failed")


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


def _project_asset_dir(project_id: UUID) -> Path:
    return Path(settings.running_hub_asset_dir) / str(project_id) / "concepts"


def _clear_existing_concept_assets(db: Session, project_id: UUID) -> None:
    db.query(Asset).filter(
        Asset.project_id == project_id,
        Asset.logical_key.like("concept.%"),
    ).delete(synchronize_session=False)


def _clear_failed_concept_assets(db: Session, project_id: UUID) -> None:
    db.query(Asset).filter(
        Asset.project_id == project_id,
        Asset.logical_key.like("concept.%"),
        Asset.status != "ready",
    ).delete(synchronize_session=False)


def _load_existing_ready_concept_outcomes(
    db: Session,
    project_id: UUID,
) -> dict[str, _RenderOutcome]:
    outcomes: dict[str, _RenderOutcome] = {}
    assets = (
        db.query(Asset)
        .filter(Asset.project_id == project_id)
        .filter(Asset.logical_key.like("concept.%"))
        .filter(Asset.status == "ready")
        .all()
    )
    for asset in assets:
        logical_key = asset.logical_key or ""
        if not logical_key:
            continue
        source_info = asset.source_info or {}
        config_json = asset.config_json or {}
        if source_info.get("source") != "runninghub" or config_json.get("generation_failed"):
            continue
        if not asset.image_url:
            continue
        path = Path(asset.image_url)
        if not path.exists():
            logger.warning("existing concept asset file is missing; will regenerate %s", logical_key)
            continue
        outcomes[logical_key] = _RenderOutcome(
            local_path=path,
            is_placeholder=False,
            file_url=source_info.get("file_url"),
            task_id=source_info.get("task_id"),
            reused=True,
        )
    return outcomes


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
    db.query(Asset).filter(
        Asset.project_id == project_id,
        Asset.logical_key == logical_key,
    ).delete(synchronize_session=False)
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
