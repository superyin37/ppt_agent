"""
Asset generation Celery tasks — Phase 6

Task graph:
  generate_all_assets
    ├── generate_site_assets   (POI map + mobility map)
    ├── generate_chart_assets  (regional stats bar chart)
    └── generate_case_assets   (case comparison metadata)
    └── [chord callback] on_all_assets_complete → advance project status
"""
import logging
import uuid
from celery import group, chord

from tasks.celery_app import app
from db.session import get_db_context
from db.models.project import Project, ProjectBrief
from db.models.site import SiteLocation
from db.models.asset import Asset
from schema.common import AssetType, ProjectStatus

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _save_asset(
    db,
    project_id: str,
    asset_type: str,
    subtype: str,
    title: str,
    image_bytes: bytes | None,
    data_json: dict,
    status: str = "ready",
) -> Asset:
    """Persist a generated asset to DB (image stored via OSS)."""
    image_url = None
    if image_bytes:
        from tool._oss_client import upload_bytes
        key = f"assets/{project_id}/{subtype}_{uuid.uuid4().hex[:8]}.png"
        image_url = upload_bytes(image_bytes, key)

    asset = Asset(
        project_id=uuid.UUID(project_id),
        asset_type=asset_type,
        subtype=subtype,
        title=title,
        image_url=image_url,
        data_json=data_json,
        status=status,
    )
    db.add(asset)
    db.flush()
    return asset


def _get_brief(db, project_id: str) -> ProjectBrief | None:
    return (
        db.query(ProjectBrief)
        .filter(ProjectBrief.project_id == project_id)
        .order_by(ProjectBrief.version.desc())
        .first()
    )


def _get_site(db, project_id: str) -> SiteLocation | None:
    return (
        db.query(SiteLocation)
        .filter(SiteLocation.project_id == project_id)
        .first()
    )


# ── Main orchestrator ──────────────────────────────────────────────────────────

@app.task(bind=True, max_retries=3, name="tasks.asset_tasks.generate_all_assets")
def generate_all_assets(self, project_id: str):
    """
    Orchestrate parallel asset generation via Celery chord.
    Triggers: generate_site_assets, generate_chart_assets, generate_case_assets
    On completion: on_all_assets_complete callback advances project status.
    """
    try:
        # Update project status to ASSET_GENERATING
        with get_db_context() as db:
            project = db.get(Project, uuid.UUID(project_id))
            if project:
                project.status = ProjectStatus.ASSET_GENERATING.value
                project.current_phase = "asset_generation"

        subtasks = group([
            generate_site_assets.s(project_id),
            generate_chart_assets.s(project_id),
            generate_case_assets.s(project_id),
        ])
        callback = on_all_assets_complete.s(project_id)
        chord(subtasks)(callback)
        logger.info(f"generate_all_assets: chord dispatched for project {project_id}")
    except Exception as exc:
        logger.exception(f"generate_all_assets failed: {exc}")
        self.retry(exc=exc, countdown=2 ** self.request.retries)


# ── Sub-tasks ──────────────────────────────────────────────────────────────────

@app.task(bind=True, max_retries=2, name="tasks.asset_tasks.generate_site_assets")
def generate_site_assets(self, project_id: str) -> dict:
    """
    Generate site-related assets:
    1. POI map (annotated map of nearby facilities)
    2. Mobility map (transit accessibility)
    """
    import asyncio
    generated = []
    errors = []

    try:
        with get_db_context() as db:
            site = _get_site(db, project_id)
            if not site or not site.longitude or not site.latitude:
                logger.warning(f"generate_site_assets: no geocoded site for project {project_id}")
                return {"generated": [], "skipped": "no_site_location"}

            lng, lat = float(site.longitude), float(site.latitude)

        # 1. POI retrieval + map
        try:
            from tool.site.poi_retrieval import poi_retrieval, POIRetrievalInput
            from tool.asset.map_annotation import map_annotation, MapAnnotationInput, AnnotationItem

            poi_result = asyncio.run(poi_retrieval(POIRetrievalInput(
                longitude=lng, latitude=lat, radius_meters=1000,
            )))
            annotations = [
                AnnotationItem(
                    longitude=p.longitude,
                    latitude=p.latitude,
                    label=p.name[:8],
                    color=_category_color(p.category),
                )
                for p in poi_result.pois[:15]
            ]
            # Add site marker
            annotations.insert(0, AnnotationItem(
                longitude=lng, latitude=lat, label="项目地块", color="red",
            ))
            map_result = asyncio.run(map_annotation(MapAnnotationInput(
                center_lng=lng, center_lat=lat, zoom=14,
                width_px=800, height_px=600,
                annotations=annotations,
            )))
            with get_db_context() as db:
                _save_asset(db, project_id, AssetType.MAP.value, "poi_map",
                            "周边配套POI地图", map_result.image_bytes,
                            {"pois": [p.model_dump() for p in poi_result.pois],
                             "summary": poi_result.summary})
            generated.append("poi_map")
        except Exception as e:
            logger.warning(f"POI map generation failed: {e}")
            errors.append(f"poi_map: {e}")

        # 2. Mobility analysis + map
        try:
            from tool.site.mobility_analysis import mobility_analysis, MobilityAnalysisInput
            from tool.asset.map_annotation import map_annotation, MapAnnotationInput, AnnotationItem

            mob_result = asyncio.run(mobility_analysis(MobilityAnalysisInput(
                longitude=lng, latitude=lat,
            )))
            metro_annotations = [
                AnnotationItem(longitude=s.distance_meters, latitude=lat,  # approximate
                               label=s.name[:8], color="blue")
                for s in mob_result.metro_stations[:5]
            ]
            map_result = asyncio.run(map_annotation(MapAnnotationInput(
                center_lng=lng, center_lat=lat, zoom=13,
                width_px=800, height_px=600,
                annotations=[AnnotationItem(longitude=lng, latitude=lat, label="项目", color="red")]
                             + metro_annotations,
            )))
            with get_db_context() as db:
                _save_asset(db, project_id, AssetType.MAP.value, "mobility_map",
                            "交通可达性分析图", map_result.image_bytes,
                            {"traffic_score": mob_result.traffic_score,
                             "summary": mob_result.summary,
                             "metro_stations": [s.model_dump() for s in mob_result.metro_stations],
                             "bus_lines": [b.model_dump() for b in mob_result.bus_lines]})
            generated.append("mobility_map")
        except Exception as e:
            logger.warning(f"Mobility map generation failed: {e}")
            errors.append(f"mobility_map: {e}")

    except Exception as exc:
        logger.exception(f"generate_site_assets error: {exc}")
        self.retry(exc=exc, countdown=5)

    return {"generated": generated, "errors": errors}


@app.task(bind=True, max_retries=2, name="tasks.asset_tasks.generate_chart_assets")
def generate_chart_assets(self, project_id: str) -> dict:
    """
    Generate statistical chart assets.
    Currently generates: 建筑规模对比图 (scale comparison bar chart)
    """
    generated = []
    errors = []

    try:
        with get_db_context() as db:
            brief = _get_brief(db, project_id)
            if not brief:
                return {"generated": [], "skipped": "no_brief"}
            brief_data = {
                "building_type": brief.building_type,
                "gross_floor_area": float(brief.gross_floor_area) if brief.gross_floor_area else None,
                "city": brief.city,
            }

        # Scale comparison chart: project GFA vs typical reference ranges
        try:
            from tool.asset.chart_generation import chart_generation, ChartGenerationInput
            gfa = brief_data.get("gross_floor_area")
            building_type = brief_data.get("building_type", "building")

            chart_data = _build_scale_chart_data(gfa, building_type)
            chart_result = chart_generation(ChartGenerationInput(
                chart_type="bar",
                title=f"{building_type}规模参考对比",
                data=chart_data,
                x_label="规模类别",
                y_label="建筑面积（㎡）",
                color_scheme="primary",
                width_px=800,
                height_px=500,
            ))
            with get_db_context() as db:
                _save_asset(db, project_id, AssetType.CHART.value, "scale_comparison",
                            "建筑规模对比图", chart_result.image_bytes,
                            chart_result.data_json)
            generated.append("scale_comparison_chart")
        except Exception as e:
            logger.warning(f"Scale chart generation failed: {e}")
            errors.append(f"scale_chart: {e}")

    except Exception as exc:
        logger.exception(f"generate_chart_assets error: {exc}")
        self.retry(exc=exc, countdown=5)

    return {"generated": generated, "errors": errors}


@app.task(bind=True, max_retries=2, name="tasks.asset_tasks.generate_case_assets")
def generate_case_assets(self, project_id: str) -> dict:
    """
    Generate case comparison asset — a summary of the selected reference cases.
    Stored as a data_json asset (no image), used by Composer to generate case slide.
    """
    generated = []
    errors = []

    try:
        from db.models.reference import ProjectReferenceSelection, ReferenceCase as ReferenceCaseORM

        with get_db_context() as db:
            selections = (
                db.query(ProjectReferenceSelection)
                .filter(ProjectReferenceSelection.project_id == project_id)
                .order_by(ProjectReferenceSelection.rank)
                .all()
            )
            if not selections:
                return {"generated": [], "skipped": "no_selections"}

            cases_data = []
            for sel in selections:
                case = db.get(ReferenceCaseORM, sel.case_id)
                if case:
                    cases_data.append({
                        "case_id": str(case.id),
                        "title": case.title,
                        "architect": case.architect,
                        "location": case.location,
                        "building_type": case.building_type,
                        "style_tags": case.style_tags or [],
                        "feature_tags": case.feature_tags or [],
                        "scale_category": case.scale_category,
                        "gfa_sqm": float(case.gfa_sqm) if case.gfa_sqm else None,
                        "year_completed": case.year_completed,
                        "summary": case.summary,
                        "selected_tags": sel.selected_tags or [],
                        "selection_reason": sel.selection_reason,
                        "rank": sel.rank,
                    })

            _save_asset(db, project_id, AssetType.CASE_COMPARISON.value, "case_comparison",
                        "参考案例对比", None, {"cases": cases_data})
            generated.append("case_comparison")

    except Exception as exc:
        logger.exception(f"generate_case_assets error: {exc}")
        self.retry(exc=exc, countdown=5)

    return {"generated": generated, "errors": errors}


# ── Chord callback ─────────────────────────────────────────────────────────────

@app.task(name="tasks.asset_tasks.on_all_assets_complete")
def on_all_assets_complete(results: list, project_id: str):
    """
    Called after all sub-tasks complete.
    Advances project status to OUTLINE_READY and triggers outline generation.
    """
    total_generated = sum(len(r.get("generated", [])) for r in results if isinstance(r, dict))
    total_errors = sum(len(r.get("errors", [])) for r in results if isinstance(r, dict))

    logger.info(
        f"on_all_assets_complete: project={project_id} "
        f"generated={total_generated} errors={total_errors}"
    )

    with get_db_context() as db:
        project = db.get(Project, uuid.UUID(project_id))
        if project:
            if total_generated > 0:
                project.status = ProjectStatus.OUTLINE_READY.value
                project.current_phase = "outline"
                logger.info(f"Project {project_id} advanced to OUTLINE_READY")
            else:
                project.status = ProjectStatus.FAILED.value
                logger.error(f"Project {project_id} set to FAILED — no assets generated")

    return {
        "project_id": project_id,
        "total_generated": total_generated,
        "total_errors": total_errors,
    }


# ── Utilities ──────────────────────────────────────────────────────────────────

def _category_color(category: str) -> str:
    mapping = {
        "交通": "blue",
        "教育": "green",
        "医疗": "red",
        "商业": "yellow",
        "文化": "purple",
        "公园": "green",
    }
    return mapping.get(category, "blue")


def _build_scale_chart_data(project_gfa: float | None, building_type: str) -> list[dict]:
    """Build scale comparison data: small / medium / large benchmarks + project."""
    benchmarks = {
        "museum":    [("小型", 5000),  ("中型", 30000), ("大型", 100000)],
        "office":    [("小型", 10000), ("中型", 50000), ("大型", 200000)],
        "cultural":  [("小型", 5000),  ("中型", 40000), ("大型", 120000)],
        "education": [("小型", 8000),  ("中型", 30000), ("大型", 80000)],
        "hospital":  [("小型", 20000), ("中型", 80000), ("大型", 200000)],
        "hotel":     [("小型", 10000), ("中型", 40000), ("大型", 150000)],
        "retail":    [("小型", 5000),  ("中型", 30000), ("大型", 100000)],
        "mixed":     [("小型", 20000), ("中型", 80000), ("大型", 300000)],
    }
    items = benchmarks.get(building_type, benchmarks["museum"])
    data = [{"label": label, "value": value} for label, value in items]
    if project_gfa:
        data.append({"label": "本项目", "value": project_gfa})
    return data
