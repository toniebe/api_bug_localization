# routers/search_bugs.py
import time
from fastapi import APIRouter, Depends, HTTPException
from google.cloud import firestore

from app.models.search import SearchBugsRequest, SearchBugsResponse
from app.services.search_service import search_relevant_bugs  

from app.deps import get_current_user

router = APIRouter(prefix="/api/projects", tags=["search"])
db = firestore.Client()

@router.post(
    "/{organization}/{project}/search-bugs",
    response_model=SearchBugsResponse,
)
async def search_bugs_endpoint(
    organization: str,
    project: str,
    body: SearchBugsRequest,
    current_user=Depends(get_current_user),
):
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")

    t0 = time.perf_counter()

    bugs, developers, commits,edges = await search_relevant_bugs(
        organization = organization,
        project = project,
        query=body.query,
        limit=body.limit,
    )

    took_ms = int((time.perf_counter() - t0) * 1000)

    # Logging ke Firestore
    try:
        db.collection("search_logs").add({
            "user_uid": getattr(current_user, "uid", None),
            "organization": organization,
            "project": project,
            "query": body.query,
            "limit": body.limit,
            "result_counts": {
                "bugs": len(bugs),
                "developers": len(developers),
                "commits": len(commits),
            },
            "took_ms": took_ms,
            "created_at": firestore.SERVER_TIMESTAMP,
        })
    except Exception as e:
        print("[WARN][search_logs] Failed to log search:", e)

    return SearchBugsResponse(
        query=body.query,
        limit=body.limit,
        bugs=bugs,
        developers=developers,
        commits=commits,
         edges=edges, 
    )
