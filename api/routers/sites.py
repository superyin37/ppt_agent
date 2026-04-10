from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from api.deps import get_db
from api.response import APIResponse
from api.exceptions import ProjectNotFoundError, InvalidGeoJSONError
from schema.site import SitePointInput, SitePolygonInput, SiteRead
from db.models.project import Project
from db.models.site import SiteLocation, SitePolygon
from tool.input.normalize_polygon import normalize_polygon, NormalizePolygonInput

router = APIRouter()


@router.post("/{project_id}/site/point", response_model=APIResponse[dict])
def submit_site_point(project_id: UUID, body: SitePointInput, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise ProjectNotFoundError(str(project_id))

    # Remove existing point for this project
    db.query(SiteLocation).filter(SiteLocation.project_id == project_id).delete()

    location = SiteLocation(
        project_id=project_id,
        longitude=body.longitude,
        latitude=body.latitude,
    )
    db.add(location)
    db.commit()
    db.refresh(location)

    return APIResponse(data={
        "longitude": location.longitude,
        "latitude": location.latitude,
        "address_resolved": location.address_resolved,
        "poi_name": location.poi_name,
    })


@router.post("/{project_id}/site/polygon", response_model=APIResponse[dict])
def submit_site_polygon(project_id: UUID, body: SitePolygonInput, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise ProjectNotFoundError(str(project_id))

    try:
        result = normalize_polygon(NormalizePolygonInput(geojson=body.geojson))
    except ValueError as e:
        raise InvalidGeoJSONError(str(e))

    # Get latest version number
    latest = (
        db.query(SitePolygon)
        .filter(SitePolygon.project_id == project_id)
        .order_by(SitePolygon.version.desc())
        .first()
    )
    new_version = (latest.version + 1) if latest else 1

    polygon = SitePolygon(
        project_id=project_id,
        version=new_version,
        geojson=result.geojson,
        area_calculated=result.area_sqm,
        perimeter=result.perimeter_m,
    )
    db.add(polygon)
    db.commit()
    db.refresh(polygon)

    return APIResponse(data={
        "area_calculated": polygon.area_calculated,
        "perimeter": polygon.perimeter,
        "geojson": polygon.geojson,
        "version": polygon.version,
    })


@router.get("/{project_id}/site", response_model=APIResponse[SiteRead])
def get_site(project_id: UUID, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise ProjectNotFoundError(str(project_id))

    location = (
        db.query(SiteLocation)
        .filter(SiteLocation.project_id == project_id)
        .first()
    )
    polygon = (
        db.query(SitePolygon)
        .filter(SitePolygon.project_id == project_id)
        .order_by(SitePolygon.version.desc())
        .first()
    )

    return APIResponse(data=SiteRead(
        project_id=project_id,
        longitude=location.longitude if location else None,
        latitude=location.latitude if location else None,
        address_resolved=location.address_resolved if location else None,
        geojson=polygon.geojson if polygon else None,
        area_calculated=polygon.area_calculated if polygon else None,
    ))
