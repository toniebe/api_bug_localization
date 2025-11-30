from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import re
from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from app.services.bug_service import (
    _dbname,
    list_developers,
    get_developer_detail
)

from app.deps import get_current_user

from app.services.developer_topics_service import get_developer_topics

router = APIRouter(
    prefix="/api/developers/{organization}/{project}",
    tags=["Developers"],
)



def _uid(u):
    return u["uid"] if isinstance(u, dict) else getattr(u, "uid", None)

# ===== DEVELOPERS =====
@router.get("/", summary="Get all developers (by org & project Neo4j db)")
async def api_list_developers(
    organization_name: str = Query(...),
    project_name: str      = Query(...),
    limit: int             = Query(50, ge=1, le=200),
    offset: int            = Query(0, ge=0),
    user=Depends(get_current_user),
):
    if not _uid(user):
        raise HTTPException(status_code=401, detail="Not authenticated")

    items = await list_developers(
        organization_name=organization_name,
        project_name=project_name,
        limit=limit,
        offset=offset,
    )
    return {
        "status": "ok",
        "organization_name": organization_name,
        "project_name": project_name,
        "items": items,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{dev_key}", summary="Get developer detail (by org & project Neo4j db)")
async def api_developer_detail(
    dev_key: str = Path(..., description="dev_id atau email"),
    organization_name: str = Query(...),
    project_name: str      = Query(...),
    user=Depends(get_current_user),
):
    if not _uid(user):
        raise HTTPException(status_code=401, detail="Not authenticated")

    data = await get_developer_detail(
        organization_name=organization_name,
        project_name=project_name,
        dev_key=dev_key,
    )
    if not data:
        raise HTTPException(status_code=404, detail="developer not found")

    return {
        "status": "ok",
        "organization_name": organization_name,
        "project_name": project_name,
        **data,
    }



@router.get("/topics/{developer_id}")
async def api_get_developer_topics(
    organization: str,
    project: str,
    developer_id: str,
    user=Depends(get_current_user),
) -> Dict[str, Any]:
    
    if not _uid(user):
        raise HTTPException(status_code=401, detail="Not authenticated")
    dbname = _dbname(organization, project)

    data = await get_developer_topics(
        database=dbname,
        developer_id=developer_id,
    )

    if not data:
        raise HTTPException(
            status_code=404,
            detail=f"No topics found for developer_id={developer_id}",
        )

    return data
