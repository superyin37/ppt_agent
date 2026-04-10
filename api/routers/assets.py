from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional

from api.deps import get_db
from api.response import APIResponse
from api.exceptions import ProjectNotFoundError
from schema.asset import AssetRead
from schema.common import AssetType
from db.models.project import Project
from db.models.asset import Asset as AssetModel

router = APIRouter()


@router.post("/{project_id}/assets/generate", response_model=APIResponse[dict], status_code=202)
def trigger_asset_generation(project_id: UUID, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise ProjectNotFoundError(str(project_id))

    from tasks.asset_tasks import generate_all_assets
    task = generate_all_assets.delay(str(project_id))
    return APIResponse(data={
        "job_id": task.id,
        "status": "queued",
        "message": "资产生成任务已进入队列",
    })


@router.get("/{project_id}/assets", response_model=APIResponse[list[AssetRead]])
def list_assets(
    project_id: UUID,
    asset_type: Optional[str] = Query(None),
    asset_status: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project:
        raise ProjectNotFoundError(str(project_id))

    query = db.query(AssetModel).filter(AssetModel.project_id == project_id)
    if asset_type:
        query = query.filter(AssetModel.asset_type == asset_type)
    if asset_status:
        query = query.filter(AssetModel.status == asset_status)

    assets = query.order_by(AssetModel.created_at).all()

    return APIResponse(data=[
        AssetRead(
            id=a.id,
            project_id=a.project_id,
            version=a.version,
            status=a.status,
            asset_type=AssetType(a.asset_type),
            subtype=a.subtype,
            title=a.title,
            data_json=a.data_json,
            config_json=a.config_json,
            image_url=a.image_url,
            summary=a.summary,
            package_id=a.package_id,
            source_item_id=a.source_item_id,
            logical_key=a.logical_key,
            variant=a.variant,
            render_role=a.render_role,
            created_at=a.created_at,
        )
        for a in assets
    ])
