# app/routes/new_project_routes.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from app.deps import get_current_user
from app.services.project_service import create_project_simple

router = APIRouter(prefix="/api", tags=["projects"])

class CreateProjectRequest(BaseModel):
    organization_name: str = Field(..., min_length=1, max_length=120)
    project_name: str = Field(..., min_length=1, max_length=120)

def _uid(user):
    return user["uid"] if isinstance(user, dict) else getattr(user, "uid", None)

@router.post("/createProjects", summary="Create project (simple write)")
async def create_project_endpoint(req: CreateProjectRequest, user=Depends(get_current_user)):
    uid = _uid(user)
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        result = await create_project_simple(req.organization_name, req.project_name, uid)
        return {"status": "ok", "message": "Project created", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")
