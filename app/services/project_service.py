# app/services/project_service.py
import re
from typing import Dict, Any
from firebase_admin import firestore
from app.core.firebase import db

from pathlib import Path
from typing import Dict, Any

from neo4j import GraphDatabase
from app.config import settings

# sudah ada sebelumnya:
ML_ENGINE_DIR = Path(settings.ML_ENGINE_DIR)
ML_PYTHON_BIN = settings.ML_PYTHON_BIN
ML_MAIN_SCRIPT = settings.ML_MAIN_SCRIPT
ML_DATASOURCE_BASE = ML_ENGINE_DIR / "datasource"

def _slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9 -]+", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "untitled"

def _dbname(org: str, proj: str) -> str:
    clean = lambda x: re.sub(r"[^a-z0-9]+", "", x.strip().lower())
    base = f"{clean(org)}{clean(proj)}"
    # Firestore & Neo4j naming-safe + panjang aman
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


async def get_organization(organization_name: str) -> Dict[str, Any]:
    """
    Ambil data organisasi berdasarkan nama (bukan slug).
    Raise ValueError jika tidak ditemukan.
    """
    org_slug = _slugify(organization_name)
    org_ref = db.collection("organizations").document(org_slug)
    org_doc = org_ref.get()

    if not org_doc.exists:
        raise ValueError(f"Organization '{organization_name}' not found")

    data = org_doc.to_dict() or {}
    return {
        "organization_name": organization_name,
        "org_slug": org_slug,
        "organization_path": f"organizations/{org_slug}",
        "data": data,
    }


async def get_project(organization_name: str, project_name: str) -> Dict[str, Any]:
    """
    Ambil data project di bawah suatu organisasi.
    Raise ValueError jika organization atau project tidak ditemukan.
    """
    org_info = await get_organization(organization_name)
    org_slug = org_info["org_slug"]

    proj_slug = _slugify(project_name)
    proj_ref = (
        db.collection("organizations")
        .document(org_slug)
        .collection("projects")
        .document(proj_slug)
    )
    proj_doc = proj_ref.get()

    if not proj_doc.exists:
        raise ValueError(
            f"Project '{project_name}' not found under organization '{organization_name}'"
        )

    proj_data = proj_doc.to_dict() or {}
    return {
        "organization_name": organization_name,
        "project_name": project_name,
        "org_slug": org_slug,
        "project_slug": proj_slug,
        "project_path": f"organizations/{org_slug}/projects/{proj_slug}",
        "data": proj_data,
    }

async def get_ml_status(organization_name: str, project_name: str):
    """
    Ambil status process ML engine dari field `ml_status` di Firestore.
    Raise ValueError jika org atau project tidak ditemukan.
    """
    proj_info = await get_project(organization_name, project_name)
    project_data = proj_info["data"]

    ml_status = project_data.get("ml_status")
    return {
        "org_slug": proj_info["org_slug"],
        "project_slug": proj_info["project_slug"],
        "ml_status": ml_status or {},
    }




def check_ml_environment(database_name: str) -> Dict[str, Any]:
    """
    Cek environment sebelum menjalankan ML engine:
    - Folder ML engine ada?
    - File datasource <database_name>.jsonl ada?
    - Koneksi ke Neo4j OK?
    """
    result: Dict[str, Any] = {
        "ok": True,
        "ml_engine_dir_ok": True,
        "datasource_ok": True,
        "neo4j_ok": True,
        "datasource_path": None,
        "neo4j_error": None,
    }

    # 1) cek folder ML engine
    if not ML_ENGINE_DIR.is_dir():
        result["ok"] = False
        result["ml_engine_dir_ok"] = False
        return result

    # 2) cek file datasource
    datasource_path = ML_DATASOURCE_BASE / f"{database_name}.jsonl"
    result["datasource_path"] = str(datasource_path)

    if not datasource_path.exists():
        result["ok"] = False
        result["datasource_ok"] = False
        # lanjut cek Neo4j juga supaya user dapat info lengkap

    # 3) cek koneksi Neo4j + database
    try:
        driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
        with driver:
            with driver.session(database=database_name) as session:
                session.run("RETURN 1 AS ok").single()
    except Exception as e:
        result["ok"] = False
        result["neo4j_ok"] = False
        result["neo4j_error"] = f"{e.__class__.__name__}: {e}"

    return result
