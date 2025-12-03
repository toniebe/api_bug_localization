# app/models/feedback.py
from pydantic import BaseModel


class BugFeedbackCreate(BaseModel):
    organization: str     
    project: str          
    bug_id: str
    topic_id: str         
    query: str
    is_relevant: bool