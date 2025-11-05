from fastapi import APIRouter, Depends, HTTPException
from app.models.search import SearchRequest, SearchResult
from app.services.search_service import search_graph
from app.deps import get_current_user

router = APIRouter(prefix="/search", tags=["search"])

@router.post("", response_model=SearchResult, summary="Search bug-commit-developer")
def search(req: SearchRequest, current_user = Depends(get_current_user)):
    """
    - Terima `query` (kalimat/keyword)
    - Preprocess NLTK (tokenize, stopword removal)
    - Query Neo4j (Bug–Commit–Developer)
    - Log transaksi ke Firestore (collection `search_logs`)
    """
    if not req.query.strip():
        raise HTTPException(status_code=422, detail="query must not be empty")

    result = search_graph(req.query, user_uid=current_user.uid, limit=50)
    return result
