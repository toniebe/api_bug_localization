# app/services/project_service.py
import re
from typing import Dict
from firebase_admin import firestore
from app.core.firebase import db

def _slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9 -]+", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "untitled"

def _dbname(org: str, proj: str) -> str:
    to_db = lambda x: re.sub(r"[^a-z0-9]+", "_", x.strip().lower()).strip("_")
    base = f"{to_db(org)}_{to_db(proj)}"
    return base[:63] if len(base) > 63 else base

async def create_project_simple(
    organization_name: str,
    project_name: str,
    owner_uid: str,
) -> Dict[str, str]:
    org_slug  = _slugify(organization_name)
    proj_slug = _slugify(project_name)
    dbname    = _dbname(organization_name, project_name)

    org_ref  = db.collection("organizations").document(org_slug)
    proj_ref = org_ref.collection("projects").document(proj_slug)

    # ---- CEK EXISTENCE PROJECT (under this org) ----
    if proj_ref.get().exists:
        # konsisten dengan permintaan user
        raise ValueError("project already exist")

    # ---- upsert ORGANIZATION ----
    org_ref.set({
        "name": organization_name,
        "slug": org_slug,
        "owner_uid": owner_uid,
        "status": "active",
        "updated_at": firestore.SERVER_TIMESTAMP,
        "created_at": firestore.SERVER_TIMESTAMP,
    }, merge=True)

    # ---- create PROJECT ----
    proj_ref.set({
        "name": project_name,
        "slug": proj_slug,
        "organization_name": organization_name,
        "organization_slug": org_slug,
        "database_name": dbname,
        "data_collection_name": dbname,
        "owner_uid": owner_uid,
        "status": "active",
        "updated_at": firestore.SERVER_TIMESTAMP,
        "created_at": firestore.SERVER_TIMESTAMP,
    }, merge=False)

    return {
        "organization_name": organization_name,
        "project_name": project_name,
        "database_name": dbname,
        "data_collection_name": dbname,
        "org_slug": org_slug,
        "project_slug": proj_slug,
        "project_path": f"organizations/{org_slug}/projects/{proj_slug}",
    }
