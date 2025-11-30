# app/routes/bug_routes.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from typing import Optional, List, Dict, Any
from app.services.recommendation_service import recommend_developers_for_bug

from app.models.bug import BugIn, BugOut
from app.services.bug_service import (
    _dbname,
    BugService,
    get_bug_service,
    list_bugs,
    get_bug_detail,
    list_developers,
    get_developer_detail,
    list_topics,
)

from app.core.firebase import db        # ⬅️ PAKAI db DARI SINI, JANGAN DIOVERRIDE
from firebase_admin import firestore

from app.deps import get_current_user

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


# ===== ADD NEW BUG =====


@router.post(
    "/{organization}/{project}/addNewBug",
    response_model=BugOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add new bug (authorized only). Runs NLP, LTM, and graph relations.",
)
async def add_new_bug_route(
    organization: str,
    project: str,
    payload: BugIn,
    current_user=Depends(get_current_user),
    bug_service: BugService = Depends(get_bug_service)
) -> BugOut:
    """
    Add new bug ke graph (authorized user only)
    - Token required
    - NLTK + LDA (LTM inference)
    - Similar/duplicate detection
    - Insert to Neo4j with relations
    - Log ke Firestore nested: /organizations/{org}/projects/{project}/bug_logs
    """

    if not _uid(current_user):
        raise HTTPException(status_code=401, detail="Not authenticated")

    db_name = _dbname(organization, project)

    # try:
    # 1) Simpan bug ke Neo4j (via service)
    bug = await bug_service.AddNewBug(
        db_name=db_name,
        organization=organization,
        project=project,
        bug=payload,
    )

    # 2) Logging ke Firestore (nested per org/project)
    # try:
    user_uid = _uid(current_user) or "unknown"

    (
        db.collection("organizations")
        .document(organization)
        .collection("projects")
        .document(project)
        .collection("bug_logs")
        .add(
            {
                "user_uid": user_uid,
                "organization": organization,
                "project": project,
                "db_name": db_name,
                "bug_id": bug.bug_id,
                "summary": bug.summary,
                "status": bug.status,
                "action": "ADD_BUG",
                "created_at": firestore.SERVER_TIMESTAMP,
            }
        )
    )
    # except Exception as log_err:
    #     # jangan ganggu main flow kalau logging gagal
    #     print(f"[WARN] Failed to log bug add to Firestore: {log_err}")

    return bug

    # except HTTPException:
    #     raise

    # except Exception as e:
    #     # sementara: print ke log biar tahu 500-nya apa
    #     print(f"[ERROR] addNewBug failed: {e!r}")
    #     raise HTTPException(
    #         status_code=500,
    #         detail="Internal error processing new bug",
    #     )


@router.get("/{bug_id}/recommended-developers")
async def api_recommend_developers_for_bug(
    organization: str,
    project: str,
    bug_id: str,
    limit: int = Query(5, ge=1, le=50),
):
    """
    Rekomendasikan developer paling relevan untuk bug tertentu,
    berdasarkan riwayat pengelolaan bug dengan topic yang sama.
    """
    recs = await recommend_developers_for_bug(organization,project,bug_id=bug_id, limit=limit)

    if not recs:
        # kemungkinan: bug_id tidak punya topic_id, atau belum ada dev yang pernah handle topic itu
        raise HTTPException(
            status_code=404,
            detail="No recommended developers found for this bug (missing topic_id or no history)."
        )

    return {
        "bug_id": bug_id,
        "limit": limit,
        "recommended_developers": recs,
    }
    