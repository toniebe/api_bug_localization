from pydantic import BaseModel
from typing import Optional

class UserProjectInfo(BaseModel):
    org_id: str
    project_id: str