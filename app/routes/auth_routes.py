from typing import List
from fastapi import APIRouter, Depends, HTTPException
from app.models.auth import (
    RegisterRequest, RegisterResponse,
    LoginRequest, LoginResponse,
    MeResponse,VerifyTokenIn,UpdateProfileIn,ChangePasswordIn,PasswordResetIn
)
from app.services.auth_service import (
  register_user, password_login, verify_id_token_logic,
  update_profile_logic, change_password_logic, send_password_reset_logic,
  get_user_roles_from_claims, get_user_roles_from_firestore,set_user_roles, get_optional_user
)
from app.deps import get_current_user, require_roles

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/signup", response_model=RegisterResponse, summary="Register user baru")
def register(req: RegisterRequest, current_user = Depends(get_optional_user)):
    # Publik: siapapun boleh daftar tanpa token
    # Jika mengirim role, wajib admin
    if req.role:
        if not current_user:
            raise HTTPException(status_code=403, detail="Not authenticated")
        decoded = getattr(current_user, "_decoded_token", {})  
        user_roles = get_user_roles_from_claims(decoded)
        if "admin" not in user_roles:
            raise HTTPException(status_code=403, detail="Only admin can assign roles")

    return register_user(req)


@router.post("/login", response_model=LoginResponse, summary="Login email & password")
async def login(req: LoginRequest):
    return await password_login(req.email, req.password)

@router.get("/me", response_model=MeResponse, summary="Profil user saat ini (dengan roles)")
def me(current_user = Depends(get_current_user)):
    decoded = getattr(current_user, "_decoded_token", {})  
    roles = get_user_roles_from_claims(decoded)
    
    if not roles:
        roles = get_user_roles_from_firestore(current_user.uid)
    return MeResponse(
        uid=current_user.uid,
        email=current_user.email,
        display_name=current_user.display_name,
        email_verified=current_user.email_verified,
        roles=roles or [],
    )


@router.post("/verify-token")
def verify_token(body: VerifyTokenIn):
    return verify_id_token_logic(body)

@router.patch("/profile")
def update_profile(body: UpdateProfileIn, current_user = Depends(get_current_user)):
    return update_profile_logic(current_user.uid, body)

@router.post("/change-password")
async def change_password(body: ChangePasswordIn):
    return await change_password_logic(body)

@router.post("/send-password-reset")
async def send_password_reset(body: PasswordResetIn):
    return await send_password_reset_logic(body)

# ===== ADMIN ONLY: Set roles user =====
@router.put("/roles/{uid}", summary="Set roles user (admin only)")
def admin_set_roles(uid: str, roles: List[str], _admin = Depends(require_roles(["admin"]))):
    """
    Contoh body (query or JSON tergantung client):
    roles=["admin","developer"]
    """
    if not roles:
        raise HTTPException(status_code=422, detail="roles cannot be empty")
    set_user_roles(uid, roles)
    return {"ok": True, "uid": uid, "roles": roles, "note": "Ask client to refresh ID token"}
