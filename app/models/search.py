from pydantic import BaseModel, Field
from typing import List, Optional

class SearchRequest(BaseModel):
    query: str = Field(min_length=1, description="Keyword atau kalimat pencarian")

class DeveloperOut(BaseModel):
    id: str
    name: Optional[str] = None
    email: Optional[str] = None

class CommitOut(BaseModel):
    id: str
    message: Optional[str] = None
    sha: Optional[str] = None
    author: Optional[DeveloperOut] = None

class BugOut(BaseModel):
    id: str
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    assigned_to: Optional[DeveloperOut] = None
    commits: List[CommitOut] = []

class SearchResult(BaseModel):
    query: str
    tokens: List[str]
    total_bugs: int
    total_commits: int
    total_developers: int
    bugs: List[BugOut] = []
