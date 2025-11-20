from typing import List, Optional
from pydantic import BaseModel

class Bug(BaseModel):
    bug_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[str] = None
    score: Optional[float] = None

class Developer(BaseModel):
    developer_id: str
    name: str
    email: Optional[str] = None
    total_fixed_bugs: Optional[int] = None
    bug_ids: List[str] = []

class Commit(BaseModel):
    commit_id: str
    hash: str
    message: str
    repository: Optional[str] = None
    committed_at: Optional[str] = None
    bug_ids: List[str] = []

class RelationEdge(BaseModel):
    source_type: str   # "bug" | "developer" | "commit"
    source_id: str
    target_type: str   # "bug" | "developer" | "commit"
    target_id: str
    relation_type: str # e.g. "ASSIGNED_TO", "FIXED_IN"

class SearchBugsRequest(BaseModel):
    query: str
    limit: int = 20

class SearchBugsResponse(BaseModel):
    query: str
    limit: int
    bugs: List[Bug]
    developers: List[Developer]
    commits: List[Commit]
    edges: List[RelationEdge]  # 👈 graph info
