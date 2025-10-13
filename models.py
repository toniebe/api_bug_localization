# models.py
from typing import List, Optional
from pydantic import BaseModel

class Bug(BaseModel):
    id: int
    summary: Optional[str] = None
    assigned_to: Optional[str] = None
    status: Optional[str] = None
    resolution: Optional[str] = None
    topic: Optional[int] = None
    topic_label: Optional[str] = None
    topic_score: Optional[float] = None

class SimilarBug(BaseModel):
    bug: Bug
    similarity: float
    relation: Optional[str] = None

class DevRec(BaseModel):
    developer: str
    freq: int
    score: float

class TopicStat(BaseModel):
    topic: str
    count: int

class DeveloperProfile(BaseModel):
    assigned_to: str
    dominant_topic: Optional[int] = None
    recent_bugs: List[Bug] = []
