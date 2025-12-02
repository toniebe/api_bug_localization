# app/routes/new_project_routes.py
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from pydantic import BaseModel, Field
from app.deps import get_current_user
from app.services.project_service import (
    create_project_simple,
    get_organization,
    get_project,
    get_ml_status,
    check_ml_environment,
)
from app.services.ml_runner_service import schedule_pipeline_for_project
import os
from fastapi import Query
from app.services.project_service import _slugify
from google.cloud import firestore
from app.models.project import AddProjectMemberRequest, ProjectMemberResponse


def get_db() -> firestore.Client:
    return firestore.Client() 

router = APIRouter(prefix="/api", tags=["projects"])

class CreateProjectRequest(BaseModel):
    organization_name: str = Field(..., min_length=1, max_length=120)
    project_name: str = Field(..., min_length=1, max_length=120)

def _uid(user):
    return user["uid"] if isinstance(user, dict) else getattr(user, "uid", None)

@router.post("/createProjects", summary="Create project (simple write)")
async def create_project_endpoint(req: CreateProjectRequest,   bg: BackgroundTasks, user=Depends(get_current_user)):
    uid = _uid(user)
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        # 1) Create Firestore project
        result = await create_project_simple(
            req.organization_name,
            req.project_name,
            uid,
        )

        return {
            "status": "ok",
            "message": "Project created",
            **result
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")
    
@router.post("/projects/start-ml", summary="Start ML Engine for Existing Project")
async def start_ml_engine(
    bg: BackgroundTasks,
    organization_name: str = Query(...),
    project_name: str = Query(...),
    user=Depends(get_current_user),
):
    uid = user.uid
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
     # cek organisasi
    try:
        org_info = await get_organization(organization_name)
        proj_info = await get_project(organization_name, project_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    
    database_name = proj_info["data"]["database_name"]
    if not database_name:
        raise HTTPException(
            status_code=500,
            detail="Project missing database_name field"
        )

    #ENV CHECK sebelum jalanin ML engine
    env_check = check_ml_environment(database_name)

    if not env_check["ok"]:
        #Jangan jalankan pipeline kalau env salah
        raise HTTPException(
            status_code=400,
            detail={
                "message": "ML environment check failed",
                **env_check,
            },
        )
    schedule_pipeline_for_project(
        bg=bg,
        org_slug=org_info["org_slug"],
        project_slug=proj_info["project_slug"],
        database_name=database_name,
        extra_env={},  # semua config ambil dari settings
    )

    return {
        "status": "ok",
        "message": "ML engine started",
        "organization": organization_name,
        "project": project_name,
        "org_slug": org_info["org_slug"],
        "project_slug": proj_info["project_slug"],
        "database_name": database_name,
    }

@router.get("/organizations/getOrganization", summary="Get organization detail by name")
async def get_organization_endpoint(
    organization_name: str = Query(...),
    user = Depends(get_current_user),
):
    uid = getattr(user, "uid", None)
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        org_info = await get_organization(organization_name)
        return {
            "status": "ok",
            **org_info,
        }
    except ValueError as e:
        # organisasi tidak ditemukan
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/projects/getProject", summary="Get project detail by organization & project name")
async def get_project_endpoint(
    organization_name: str = Query(...),
    project_name: str = Query(...),
    user = Depends(get_current_user),
):
    uid = getattr(user, "uid", None)
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        proj_info = await get_project(organization_name, project_name)
        return {
            "status": "ok",
            **proj_info,
        }
    except ValueError as e:
        # bisa karena org tidak ada atau project tidak ada
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/projects/check", summary="Check organization & project existence")
async def check_organization_and_project(
    organization_name: str = Query(...),
    project_name: str = Query(...),
    user = Depends(get_current_user),
):
    uid = getattr(user, "uid", None)
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")

    org_exists = False
    project_exists = False
    org_info = None
    proj_info = None

    # cek organisasi
    try:
        org_info = await get_organization(organization_name)
        org_exists = True
    except ValueError:
        org_exists = False

    # kalau org ada, baru cek project
    if org_exists:
        try:
            proj_info = await get_project(organization_name, project_name)
            project_exists = True
        except ValueError:
            project_exists = False

    return {
        "status": "ok",
        "organization_name": organization_name,
        "project_name": project_name,
        "organization_exists": org_exists,
        "project_exists": project_exists,
        "org": org_info if org_exists else None,
        "project": proj_info if project_exists else None,
    }

@router.get("/projects/ml-status", summary="Check ML Engine Status for a Project")
async def get_ml_status_endpoint(
    organization_name: str = Query(...),
    project_name: str = Query(...),
    user=Depends(get_current_user),
):
    uid = getattr(user, "uid", None)
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        status_info = await get_ml_status(organization_name, project_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {
        "status": "ok",
        "organization": organization_name,
        "project": project_name,
        "org_slug": status_info["org_slug"],
        "project_slug": status_info["project_slug"],
        "ml_status": status_info["ml_status"],
    }

@router.get("/projects/check-ml-env", summary="Check ML environment for a project")
async def check_ml_env_endpoint(
    organization_name: str = Query(...),
    project_name: str = Query(...),
    user=Depends(get_current_user),
):
    uid = getattr(user, "uid", None)
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # 1) pastikan project exist (akses db via service)
    try:
        proj_info = await get_project(organization_name, project_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    project_data = proj_info["data"]
    database_name = project_data.get("database_name")
    if not database_name:
        raise HTTPException(
            status_code=500,
            detail="Project missing database_name field"
        )

    # 2) cek environment ML untuk database_name ini
    env_check = check_ml_environment(database_name)

    return {
        "status": "ok",
        "organization": organization_name,
        "project": project_name,
        "org_slug": proj_info["org_slug"],
        "project_slug": proj_info["project_slug"],
        "database_name": database_name,
        "environment": env_check,
    }



@router.post("/{org_id}/{project_id}/members")
async def add_project_member(
    org_id: str,
    project_id: str,
    payload: AddProjectMemberRequest,
    db: firestore.Client = Depends(get_db),
    user = Depends(get_current_user),   
):
    uid = getattr(user, "uid", None)
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # ---- 1. Load project ----
    project_ref = (
            db.collection("organizations")
            .document(org_id)
            .collection("projects")
            .document(project_id)
        )
    project_snap = project_ref.get()

    if not project_snap.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    project_data = project_snap.to_dict()

    if not project_snap.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    project_data = project_snap.to_dict()

    # ---- 2. Authorization (simple example) ----
    # Only owner can add members (adjust as you like)
    # owner_uid = project_data.get("owner_uid")
    # if current_user.uid != owner_uid:
    #     raise HTTPException(
    #         status_code=status.HTTP_403_FORBIDDEN,
    #         detail="Only project owner can add members",
    #     )

    # ---- 3. Check target user exists ----
    users_ref = db.collection("users")
    query = users_ref.where("email", "==", payload.email).limit(1)
    user_docs = list(query.stream())

    if not user_docs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User with that email not found",
        )

    user_doc = user_docs[0]
    user_data = user_doc.to_dict()

    # Ambil uid: bisa dari document id atau field "uid"
    target_uid = user_data.get("uid") or user_doc.id

    # ---- 4. Update project.members (array of uid) ----
    project_ref.set(
        {
            "members": firestore.ArrayUnion([target_uid])
        },
        merge=True,
    )

    # ---- 5. (Opsional) update user.projects ----
    user_ref = db.collection("users").document(target_uid)
    user_ref.set(
        {
            "projects": firestore.ArrayUnion([{
                "org_id": org_id,
                "project_id": project_id,
            }])
        },
        merge=True,
    )

    # ---- 6. Return response sederhana ----
    return {
        "organization_id": org_id,
        "project_id": project_id,
        "user_uid": target_uid,
        "email": payload.email,
        "role": payload.role or "member",
        "message": "User added to project successfully",
    }