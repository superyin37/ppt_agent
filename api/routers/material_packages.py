import threading
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_db
from api.exceptions import ProjectNotFoundError
from api.response import APIResponse
from db.models.material_item import MaterialItem
from db.models.material_package import MaterialPackage
from db.models.project import Project
from schema.common import ProjectStatus
from schema.material_package import LocalMaterialPackageIngestRequest, MaterialItemRead, MaterialPackageRead
from tool.material_pipeline import ingest_local_material_package

router = APIRouter()


@router.post("/{project_id}/material-packages/ingest-local", response_model=APIResponse[MaterialPackageRead])
def ingest_local_package(project_id: UUID, body: LocalMaterialPackageIngestRequest, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise ProjectNotFoundError(str(project_id))

    package = ingest_local_material_package(project_id, body.local_path, db)
    db.commit()
    db.refresh(package)
    return APIResponse(data=MaterialPackageRead.model_validate(package))


@router.get("/{project_id}/material-packages/latest", response_model=APIResponse[MaterialPackageRead])
def get_latest_package(project_id: UUID, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise ProjectNotFoundError(str(project_id))

    package = (
        db.query(MaterialPackage)
        .filter(MaterialPackage.project_id == project_id)
        .order_by(MaterialPackage.version.desc())
        .first()
    )
    if not package:
        return APIResponse(data=None)
    return APIResponse(data=MaterialPackageRead.model_validate(package))


@router.get("/{project_id}/material-packages/{package_id}/manifest", response_model=APIResponse[dict])
def get_package_manifest(project_id: UUID, package_id: UUID, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise ProjectNotFoundError(str(project_id))

    package = (
        db.query(MaterialPackage)
        .filter(MaterialPackage.project_id == project_id, MaterialPackage.id == package_id)
        .first()
    )
    if not package:
        return APIResponse(data=None)
    return APIResponse(data=package.manifest_json or {})


@router.get("/{project_id}/material-packages/{package_id}/items", response_model=APIResponse[list[MaterialItemRead]])
def list_package_items(project_id: UUID, package_id: UUID, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise ProjectNotFoundError(str(project_id))

    items = (
        db.query(MaterialItem)
        .filter(MaterialItem.package_id == package_id)
        .order_by(MaterialItem.logical_key.asc(), MaterialItem.created_at.asc())
        .all()
    )
    return APIResponse(data=[MaterialItemRead.model_validate(item) for item in items])


@router.post("/{project_id}/material-packages/{package_id}/regenerate", response_model=APIResponse[dict], status_code=202)
def regenerate_from_package(project_id: UUID, package_id: UUID, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise ProjectNotFoundError(str(project_id))

    package = (
        db.query(MaterialPackage)
        .filter(MaterialPackage.project_id == project_id, MaterialPackage.id == package_id)
        .first()
    )
    if not package:
        return APIResponse(data={"queued": False, "reason": "material package not found"})

    from api.routers.outlines import _outline_worker

    project.status = ProjectStatus.ASSET_GENERATING.value
    project.current_phase = "outline_generation"
    db.commit()

    threading.Thread(target=_outline_worker, args=(str(project_id),), daemon=True).start()
    return APIResponse(data={"queued": True, "package_id": str(package_id), "status": "outline generation started"})
