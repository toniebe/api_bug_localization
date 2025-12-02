from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from app.models.user import UserProjectInfo
from google.cloud import firestore
from app.deps import get_current_user
router = APIRouter(prefix="/user", tags=["user"])


def get_db() -> firestore.Client:
    return firestore.Client()

@router.get("/projects/{email}", response_model=List[UserProjectInfo])
async def get_projects_by_user(
    email: str,
    db: firestore.Client = Depends(get_db),
    current_user = Depends(get_current_user),
):
    uid = getattr(current_user, "uid", None)
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    users_ref = db.collection("users")
    query = users_ref.where("email", "==", email).limit(1)
    user_docs = list(query.stream())

    if not user_docs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User with that email not found",
        )

    user_doc = user_docs[0]
    user_data = user_doc.to_dict()
    user_uid = user_data.get("uid") or user_doc.id

    # ---- 2. Ambil list projects dari user doc ----
    projects_meta = user_data.get("projects", [])

    result: List[UserProjectInfo] = []

    for p in projects_meta:
        org_id = p.get("org_id")
        project_id = p.get("project_id")
        role = p.get("role")

        if not org_id or not project_id:
            continue

        project_ref = (
            db.collection("organizations")
              .document(org_id)
              .collection("projects")
              .document(project_id)
        )
        project_snap = project_ref.get()

        if not project_snap.exists:
            # kalau project sudah dihapus, skip
            continue

        project_data = project_snap.to_dict()

        result.append(
            UserProjectInfo(
                org_id=org_id,
                project_id=project_id,
                organization_name=project_data.get("organization_name"),
                project_name=project_data.get("project_name"),
                role=role,
            )
        )

    return result
