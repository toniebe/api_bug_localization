# firebase_auth.py
from typing import Optional, Dict, Any
import requests
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, EmailStr, field_validator

from firebase_client import auth, db, FIREBASE_WEB_API_KEY, IDT_BASE
from firebase_admin import firestore
import jwt
router = APIRouter(prefix="/auth", tags=["auth"])

# ===== Schemas =====
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

    @field_validator("new_password")
    @classmethod
    def min_len_pwd(cls, v):
        if len(v) < 6:
            raise ValueError("Password minimal 6 karakter.")
        return v

# ===== Dependency =====
def get_current_user(authorization: str = Header(None)) -> Dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.split(" ", 1)[1]
    try:
        decoded = auth.verify_id_token(token)
        return decoded
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

# ===== Routes =====

@router.post("/signup")
async def signup(body: SignUpIn):
    try:
        user = auth.create_user(
            email=body.email,
            password=body.password,
            display_name=body.display_name or None,
            email_verified=False,
            disabled=False,
        )
        db.collection("users").document(user.uid).set({
            "email": body.email,
            "displayName": body.display_name or "",
            "createdAt": firestore.SERVER_TIMESTAMP, 
            "role": "user",
        }, merge=True)
        return {"uid": user.uid, "email": user.email, "displayName": user.display_name}
    except auth.EmailAlreadyExistsError:  # type: ignore
        raise HTTPException(status_code=409, detail="Email sudah terdaftar.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/login")
async def login(body: SignInIn):
    if not FIREBASE_WEB_API_KEY:
        raise HTTPException(500, "FIREBASE_WEB_API_KEY belum di-set")
    url = f"{IDT_BASE}/accounts:signInWithPassword?key={FIREBASE_WEB_API_KEY}"
    payload = {"email": body.email, "password": body.password, "returnSecureToken": True}
    try:
        r = requests.post(url, json=payload, timeout=20)
        if r.status_code != 200:
            msg = r.json().get("error", {}).get("message", "LOGIN_FAILED")
            raise HTTPException(status_code=401, detail=msg)
        data = r.json()
        if "localId" in data:
            db.collection("users").document(data["localId"]).set({
                "lastLoginAt": firestore.SERVER_TIMESTAMP  # type: ignore
            }, merge=True)
        return {
            "idToken": data["idToken"],
            "refreshToken": data.get("refreshToken"),
            "expiresIn": data.get("expiresIn"),
            "uid": data.get("localId"),
            "email": data.get("email"),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/verify-token")
async def verify_token(body: VerifyTokenIn):
    try:
        decoded = auth.verify_id_token(body.id_token)
        return {"uid": decoded["uid"], "claims": decoded.get("claims", {})}
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

@router.get("/me")
async def me(user=Depends(get_current_user)):
    return {"uid": user["uid"], "email": user.get("email"), "claims": user.get("claims", {})}

@router.patch("/profile")
async def update_profile(body: UpdateProfileIn, user=Depends(get_current_user)):
    kwargs = {}
    if body.display_name is not None:
        kwargs["display_name"] = body.display_name
    if body.photo_url is not None:
        kwargs["photo_url"] = body.photo_url
    if not kwargs:
        return {"ok": True, "message": "Nothing to update"}
    try:
        u = auth.update_user(user["uid"], **kwargs)
        db.collection("users").document(u.uid).set({
            "displayName": u.display_name or "",
            "photoURL": u.photo_url or "",
            "updatedAt": firestore.SERVER_TIMESTAMP,  # type: ignore
        }, merge=True)
        return {"uid": u.uid, "displayName": u.display_name, "photoURL": u.photo_url}
    except Exception as e:
        raise HTTPException(400, str(e))

@router.post("/change-password")
async def change_password(body: ChangePasswordIn):
    if not FIREBASE_WEB_API_KEY:
        raise HTTPException(500, "FIREBASE_WEB_API_KEY belum di-set")
    url = f"{IDT_BASE}/accounts:update?key={FIREBASE_WEB_API_KEY}"
    payload = {"idToken": body.id_token, "password": body.new_password, "returnSecureToken": True}
    try:
        r = requests.post(url, json=payload, timeout=20)
        if r.status_code != 200:
            msg = r.json().get("error", {}).get("message", "UPDATE_PASSWORD_FAILED")
            raise HTTPException(status_code=400, detail=msg)
        return r.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/send-password-reset")
async def send_password_reset(email: EmailStr):
    if not FIREBASE_WEB_API_KEY:
        raise HTTPException(500, "FIREBASE_WEB_API_KEY belum di-set")
    url = f"{IDT_BASE}/accounts:sendOobCode?key={FIREBASE_WEB_API_KEY}"
    payload = {"requestType": "PASSWORD_RESET", "email": str(email)}
    try:
        r = requests.post(url, json=payload, timeout=20)
        if r.status_code != 200:
            msg = r.json().get("error", {}).get("message", "SEND_RESET_FAILED")
            raise HTTPException(status_code=400, detail=msg)
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))
