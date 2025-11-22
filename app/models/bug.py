from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


# ==== INPUT dari Bugzilla (seperti contoh kamu) ====

class BugIn(BaseModel):
    id: int
    summary: str
    status: str
    resolution: Optional[str] = None
    product: str
    component: str
    creation_time: datetime
    last_change_time: datetime
    creator: str
    assigned_to: str

    keywords: List[str] = []
    url: str = ""
    depends_on: List[int] = []
    dupe_of: Optional[int] = None

    commit_messages: List[str] = []
    commit_refs: List[str] = []
    files_changed: List[str] = []

    class Config:
        orm_mode = True


# ==== OUTPUT ringkas untuk response API ====

class BugOut(BaseModel):
    bug_id: str
    summary: str
    status: str
    resolution: Optional[str]
    product: str
    component: str
    creator: str
    assigned_to: str
    creation_time: datetime
    last_change_time: datetime

    keywords: List[str] = []
    url: str = ""

    class Config:
        orm_mode = True
