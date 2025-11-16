# app/routes/bug_routes.py
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from typing import Optional
from app.deps import get_current_user
from app.services.bug_service import (
    list_bugs,
    get_bug_detail,
    list_developers,
    get_developer_detail,
    list_topics,
)

router = APIRouter(prefix="/api/bug", tags=["bug"])

def _uid(u):
    return u["uid"] if isinstance(u, dict) else getattr(u, "uid", None)

# ===== BUGS =====
@router.get("/bugs", summary="Get all bugs (by org & project Neo4j db)")
async def api_list_bugs(
    organization_name: str = Query(..., description="Organization name"),
    project_name: str      = Query(..., description="Project name"),
    limit: int             = Query(50, ge=1, le=200),
    offset: int            = Query(0, ge=0),
    user=Depends(get_current_user),
):
    if not _uid(user):
        raise HTTPException(status_code=401, detail="Not authenticated")

    items = await list_bugs(
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


@router.get("/bugs/{bug_id}", summary="Get bug detail (by org & project Neo4j db)")
async def api_bug_detail(
    bug_id: str,
    organization_name: str = Query(...),
    project_name: str      = Query(...),
    user=Depends(get_current_user),
):
    if not _uid(user):
        raise HTTPException(status_code=401, detail="Not authenticated")

    data = await get_bug_detail(
        organization_name=organization_name,
        project_name=project_name,
        bug_id=bug_id,
    )
    if not data:
        raise HTTPException(status_code=404, detail="bug not found")

    return {
        "status": "ok",
        "organization_name": organization_name,
        "project_name": project_name,
        **data,
    }


# ===== DEVELOPERS =====
@router.get("/developers", summary="Get all developers (by org & project Neo4j db)")
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


@router.get("/developers/{dev_key}", summary="Get developer detail (by org & project Neo4j db)")
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


# ===== TOPICS =====
@router.get("/topics", summary="Get all topics (by org & project Neo4j db)")
async def api_list_topics(
    organization_name: str = Query(...),
    project_name: str      = Query(...),
    limit: int             = Query(100, ge=1, le=500),
    offset: int            = Query(0, ge=0),
    user=Depends(get_current_user),
):
    if not _uid(user):
        raise HTTPException(status_code=401, detail="Not authenticated")

    items = await list_topics(
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
