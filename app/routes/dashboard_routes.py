# app/api/v1/endpoints/dashboard.py
from fastapi import APIRouter, Query, HTTPException, Depends
from app.models.dashboard import DashboardSummary
from app.services.dashboard_service import get_basic_counts

from app.deps import get_current_user
router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _uid(u):
    return u["uid"] if isinstance(u, dict) else getattr(u, "uid", None)

@router.get("/", response_model=DashboardSummary)
async def get_dashboard_summary(
    organization: str = Query(..., description="Organization name"),
    project: str = Query(..., description="Project name"),
    user=Depends(get_current_user),
):
    
    if not _uid(user):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    """
    Return simple counts for dashboard cards:
    - total bugs
    - total developers
    - total commits
    """
    counts = await get_basic_counts(organization=organization, project=project)
    return DashboardSummary(**counts)
