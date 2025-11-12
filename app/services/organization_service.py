# app/services/organization_service.py
from __future__ import annotations
import re
from typing import Dict, List, Optional
from firebase_admin import firestore
from app.core.firebase import db

def _slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9 -]+", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "untitled"

# ===== CREATE =====
async def create_organization(name: str, owner_uid: str) -> Dict[str, str]:
    org_slug = _slugify(name)
    org_ref = db.collection("organizations").document(org_slug)

    # Cek exist
    if org_ref.get().exists:
        raise ValueError("organization already exist")

    org_ref.set({
        "name": name,
        "slug": org_slug,
        "owner_uid": owner_uid,
        "status": "active",
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }, merge=False)

    return {"organization_name": name, "org_slug": org_slug, "path": f"organizations/{org_slug}"}

# ===== READ (LIST) =====
async def list_organizations(owner_uid: str, limit: int = 50, start_after: Optional[str] = None) -> List[Dict]:
    q = (db.collection("organizations")
           .where("owner_uid", "==", owner_uid)
           .order_by("slug"))
    if start_after:
        q = q.start_after({u"slug": start_after})
    q = q.limit(limit)

    docs = q.stream()
    out: List[Dict] = []
    for d in docs:
        data = d.to_dict() or {}
        out.append({
            "org_slug": d.id,
            "organization_name": data.get("name", ""),
            "status": data.get("status", ""),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
            "path": f"organizations/{d.id}",
        })
    return out

# ===== READ (DETAIL) =====
async def get_organization(org_slug: str, owner_uid: str) -> Dict:
    ref = db.collection("organizations").document(org_slug)
    snap = ref.get()
    if not snap.exists:
        raise ValueError("organization not found")
    data = snap.to_dict() or {}
    if data.get("owner_uid") != owner_uid:
        raise PermissionError("forbidden")
    return {
        "org_slug": org_slug,
        "organization_name": data.get("name", ""),
        "status": data.get("status", ""),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "path": f"organizations/{org_slug}",
    }

# ===== UPDATE (name/status) =====
async def update_organization(org_slug: str, owner_uid: str, *, name: Optional[str] = None, status: Optional[str] = None) -> Dict:
    ref = db.collection("organizations").document(org_slug)
    snap = ref.get()
    if not snap.exists:
        raise ValueError("organization not found")
    data = snap.to_dict() or {}
    if data.get("owner_uid") != owner_uid:
        raise PermissionError("forbidden")

    payload: Dict = {"updated_at": firestore.SERVER_TIMESTAMP}
    if name:
        payload["name"] = name  # slug tidak diubah agar path tetap stabil
    if status:
        payload["status"] = status  # misal: active|archived|deleted

    ref.update(payload)
    return await get_organization(org_slug, owner_uid)

# ===== DELETE (soft delete) =====
async def delete_organization(org_slug: str, owner_uid: str) -> Dict:
    ref = db.collection("organizations").document(org_slug)
    snap = ref.get()
    if not snap.exists:
        raise ValueError("organization not found")
    data = snap.to_dict() or {}
    if data.get("owner_uid") != owner_uid:
        raise PermissionError("forbidden")

    # Soft delete: status=deleted + deleted_at
    ref.update({
        "status": "deleted",
        "deleted_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    })
    return {"org_slug": org_slug, "status": "deleted"}
