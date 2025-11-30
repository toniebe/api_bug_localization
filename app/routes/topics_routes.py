from fastapi import APIRouter, Query, HTTPException
from typing import Dict, Any
import re
from app.services.bug_service import  list_topics
from app.services.recommendation_topic_service import recommend_developers_for_topic

from fastapi import APIRouter, Depends, HTTPException, Query
from app.deps import get_current_user

router = APIRouter(
    prefix="/api/topics/{organization}/{project}",
    tags=["Topics"],
)


def _uid(u):
    return u["uid"] if isinstance(u, dict) else getattr(u, "uid", None)

# ===== TOPICS =====
@router.get("/", summary="Get all topics (by org & project Neo4j db)")
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
    
@router.get("/recommended-developers/{topic_id}")
async def api_recommend_developers_for_topic(
    organization: str,
    project: str,
    topic_id: int,
    limit: int = Query(10, ge=1, le=100),
    user=Depends(get_current_user),
) -> Dict[str, Any]:
    
    if not _uid(user):
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = await recommend_developers_for_topic(
        organization_name=organization,
        project_name=project,
        topic_id=topic_id,
        limit=limit,
    )

    if result["total_recommended"] == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No developers found for topic_id={topic_id}",
        )

    return result
