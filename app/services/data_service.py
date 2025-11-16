# app/services/data_service.py
from __future__ import annotations
from typing import List, Dict, Any, Optional
from firebase_admin import firestore
from app.core.firebase import db

# ===== Users =====
async def list_users(limit: int = 100, start_after_email: Optional[str] = None) -> List[Dict[str, Any]]:
    q = db.collection("users").order_by("email")
    if start_after_email:
        q = q.start_after({u"email": start_after_email})
    q = q.limit(limit)
    docs = q.stream()
    out = []
    for d in docs:
        data = d.to_dict() or {}
        out.append({
            "uid": d.id,
            "email": data.get("email", ""),
            "display_name": data.get("display_name", ""),
            "role": data.get("role", "member"),
            "status": data.get("status", "active"),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
        })
    return out

# ===== Projects (owner’s projects across orgs) =====
async def list_projects_by_owner(owner_uid: str, limit: int = 100, start_after_key: Optional[str] = None) -> List[Dict[str, Any]]:
    # gunakan collection group query
    q = db.collection_group("projects").where("owner_uid", "==", owner_uid).order_by("slug")
    if start_after_key:
        q = q.start_after({u"slug": start_after_key})
    q = q.limit(limit)

    docs = q.stream()
    out = []
    for d in docs:
        data = d.to_dict() or {}
        # path: organizations/{org_slug}/projects/{proj_slug}
        parts = d.reference.path.split("/")
        org_slug = parts[1] if len(parts) >= 2 else data.get("organization_slug")
        out.append({
            "org_slug": org_slug,
            "project_slug": d.id,
            "project_name": data.get("name", ""),
            "database_name": data.get("database_name", ""),
            "data_collection_name": data.get("data_collection_name", ""),
            "status": data.get("status", "active"),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
            "path": d.reference.path,
        })
    return out

async def get_project_detail(org_slug: str, proj_slug: str, owner_uid: str) -> Dict[str, Any]:
    ref = db.collection("organizations").document(org_slug).collection("projects").document(proj_slug)
    snap = ref.get()
    if not snap.exists:
        raise ValueError("project not found")
    data = snap.to_dict() or {}
    if data.get("owner_uid") != owner_uid:
        raise PermissionError("forbidden")
    data_out = {
        "org_slug": org_slug,
        "project_slug": proj_slug,
        "project_name": data.get("name"),
        "database_name": data.get("database_name"),
        "data_collection_name": data.get("data_collection_name"),
        "status": data.get("status", "active"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "path": ref.path,
    }
    return data_out
