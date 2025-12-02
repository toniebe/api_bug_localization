# app/models/project.py
from pydantic import BaseModel, EmailStr
from typing import Optional

class AddProjectMemberRequest(BaseModel):
    email: EmailStr
    role: Optional[str] = "member"

class ProjectMemberResponse(BaseModel):
    project_id: str
    user_uid: str
    role: str
