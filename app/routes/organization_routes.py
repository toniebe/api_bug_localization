# app/routes/organization_routes.py
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from app.deps import get_current_user
from app.services.organization_service import (
    create_organization, list_organizations, get_organization,
    update_organization, delete_organization
)

router = APIRouter(prefix="/api/organizations", tags=["organizations"])

class OrgCreateReq(BaseModel):
    organization_name: str = Field(..., min_length=1, max_length=120)

class OrgUpdateReq(BaseModel):
    organization_name: Optional[str] = Field(None, min_length=1, max_length=120)
    status: Optional[str] = Field(None, description="active|archived|deleted")

def _uid(user) -> str | None:
    return user["uid"] if isinstance(user, dict) else getattr(user, "uid", None)

# CREATE
@router.post("", summary="Create organization")
async def create_org(req: OrgCreateReq, user=Depends(get_current_user)):
    uid = _uid(user)
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        result = await create_organization(req.organization_name, uid)
        return {"status": "ok", "message": "Organization created", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")

# LIST (owner)
@router.get("", summary="List organizations (owner)")
async def list_orgs(
    limit: int = Query(50, ge=1, le=200),
    start_after: Optional[str] = Query(None, description="Pagination cursor: last org_slug"),
    user=Depends(get_current_user),
):
    uid = _uid(user)
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        items = await list_organizations(uid, limit=limit, start_after=start_after)
        return {"status": "ok", "items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")

# GET (detail)
@router.get("/{org_slug}", summary="Get organization detail")
async def get_org(org_slug: str = Path(...), user=Depends(get_current_user)):
    uid = _uid(user)
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        data = await get_organization(org_slug, uid)
        return {"status": "ok", **data}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError:
        raise HTTPException(status_code=403, detail="forbidden")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")

# UPDATE
@router.patch("/{org_slug}", summary="Update organization (name/status)")
async def patch_org(org_slug: str, req: OrgUpdateReq, user=Depends(get_current_user)):
    uid = _uid(user)
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        data = await update_organization(org_slug, uid, name=req.organization_name, status=req.status)
        return {"status": "ok", "message": "Organization updated", **data}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError:
        raise HTTPException(status_code=403, detail="forbidden")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")

# DELETE (soft)
@router.delete("/{org_slug}", summary="Delete organization (soft)")
async def delete_org(org_slug: str, user=Depends(get_current_user)):
    uid = _uid(user)
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        data = await delete_organization(org_slug, uid)
        return {"status": "ok", "message": "Organization deleted", **data}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError:
        raise HTTPException(status_code=403, detail="forbidden")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")
