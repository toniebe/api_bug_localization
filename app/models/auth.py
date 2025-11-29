from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from pydantic import BaseModel, EmailStr, field_validator

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    display_name: Optional[str] = None
    # opsional: set role saat register (hanya untuk admin flow nanti)
    role: Optional[str] = None

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RegisterResponse(BaseModel):
    uid: str
    email: EmailStr
    display_name: Optional[str] = None

class LoginResponse(BaseModel):
    id_token: str
    refresh_token: str
    expires_in: int
    local_id: str
    email: EmailStr
    organization_name: Optional[str] = None
    project_name: Optional[str] = None

class MeResponse(BaseModel):
    uid: str
    email: EmailStr
    display_name: Optional[str] = None
    email_verified: bool
    roles: List[str] = []
    
class SignUpIn(BaseModel):
    email: EmailStr
    password: str
    display_name: Optional[str] = None

    @field_validator("password")
    @classmethod
    def min_len(cls, v):
        if len(v) < 6:
            raise ValueError("Password minimal 6 karakter (syarat Firebase).")
        return v

class SignInIn(BaseModel):
    email: EmailStr
    password: str

class VerifyTokenIn(BaseModel):
    id_token: str

class UpdateProfileIn(BaseModel):
    display_name: Optional[str] = None
    photo_url: Optional[str] = None

class ChangePasswordIn(BaseModel):
    id_token: str
    new_password: str
    current_password: str  # <-- TAMBAHAN


class PasswordResetIn(BaseModel):
    email: EmailStr
