# app/models/dashboard.py
from pydantic import BaseModel

class DashboardSummary(BaseModel):
    bug_count: int
    developer_count: int
    commit_count: int
