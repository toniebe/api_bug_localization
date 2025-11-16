# app/routes/data_routes.py
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from typing import Optional
from app.deps import get_current_user
from app.services.data_service import (
    list_users, list_projects_by_owner, get_project_detail
)

router = APIRouter(prefix="/api", tags=["data"])

def _uid(u): 
    return u["uid"] if isinstance(u, dict) else getattr(u, "uid", None)

# USERS
@router.get("/users", summary="Get all users (Firestore)")
async def api_list_users(
    limit: int = Query(100, ge=1, le=500),
    start_after_email: Optional[str] = Query(None),
    user=Depends(get_current_user)
):
    if not _uid(user): raise HTTPException(status_code=401, detail="Not authenticated")
    items = await list_users(limit=limit, start_after_email=start_after_email)
    return {"status": "ok", "items": items, "limit": limit, "start_after_email": start_after_email}

# PROJECT DETAIL
@router.get("/projects/{org_slug}/{proj_slug}", summary="Get project detail (Firestore)")
async def api_project_detail(
    org_slug: str = Path(...),
    proj_slug: str = Path(...),
    user=Depends(get_current_user)
):
    uid = _uid(user)
    if not uid: raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        data = await get_project_detail(org_slug, proj_slug, uid)
        return {"status": "ok", **data}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError:
        raise HTTPException(status_code=403, detail="forbidden")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")
