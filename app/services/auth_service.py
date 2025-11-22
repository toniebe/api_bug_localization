# app/services/auth_service.py
from typing import List, Optional, Dict, Any, Tuple
import httpx
from fastapi import HTTPException
from firebase_admin import firestore 
from fastapi import Header
import asyncio
from app.core.firebase import auth

from app.config import settings
from app.core.firebase import auth, db
from app.models.auth import (
    LoginResponse, RegisterRequest, RegisterResponse,
    UpdateProfileIn, ChangePasswordIn, VerifyTokenIn, PasswordResetIn
)

# =======================
# Identity Toolkit (REST)
# =======================
IDT_BASE = "https://identitytoolkit.googleapis.com/v1"
FIREBASE_SIGNIN_URL = f"{IDT_BASE}/accounts:signInWithPassword"
db = firestore.Client()

# ---------- Core auth ----------

async def get_org_and_project_for_uid(uid: str) -> Tuple[Optional[str], Optional[str]]:
    loop = asyncio.get_running_loop()

    def _query():
        org_q = (
            db.collection("organizations")
            .where("owner_uid", "==", uid)
            .limit(1)
        )
        org_docs = list(org_q.stream())
        if not org_docs:
            return None, None

        org_doc = org_docs[0]
        org_slug = org_doc.id
        org_name = org_doc.to_dict().get("organization_name", org_slug)

        proj_q = org_doc.reference.collection("projects").limit(1)
        proj_docs = list(proj_q.stream())

        if not proj_docs:
            return org_name, None

        proj_doc = proj_docs[0]
        project_name = proj_doc.id
        return org_name, project_name

    return await loop.run_in_executor(None, _query)


async def password_login(email: str, password: str) -> LoginResponse:
    params = {"key": settings.FIREBASE_API_KEY}
    payload = {"email": email, "password": password, "returnSecureToken": True}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(FIREBASE_SIGNIN_URL, params=params, json=payload)
    if r.status_code != 200:
        detail = r.json().get("error", {}).get("message", "LOGIN_FAILED")
        raise HTTPException(status_code=400, detail=f"Firebase login error: {detail}")
    data = r.json()
    org_name, project_name = await get_org_and_project_for_uid(data["localId"])
    return LoginResponse(
        id_token=data["idToken"],
        refresh_token=data["refreshToken"],
        expires_in=int(data["expiresIn"]),
        local_id=data["localId"],
        email=data["email"],
        organization_name=org_name,
        project_name=project_name,
    )


def register_user(req: RegisterRequest) -> RegisterResponse:
    try:
        user = auth.create_user(
            email=req.email,
            password=req.password,
            display_name=req.display_name or "",
            email_verified=False,
            disabled=False,
        )
        roles = [req.role] if getattr(req, "role", None) else ["user"]

        db.collection("users").document(user.uid).set(
            {
                "uid": user.uid,
                "email": req.email,
                "display_name": req.display_name or "",
                "roles": roles,
                "created_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )
        auth.set_custom_user_claims(user.uid, {"roles": roles})
        return RegisterResponse(uid=user.uid, email=req.email, display_name=req.display_name)
    except auth.EmailAlreadyExistsError:  # type: ignore[attr-defined]
        raise HTTPException(status_code=400, detail="Email already exists")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Register failed: {e}")

# ---------- Roles ----------
def set_user_roles(uid: str, roles: List[str]) -> None:
    if not roles:
        roles = ["user"]
    db.collection("users").document(uid).set(
        {"roles": roles, "updated_at": firestore.SERVER_TIMESTAMP},
        merge=True,
    )
    auth.set_custom_user_claims(uid, {"roles": roles})

def get_user_roles_from_claims(decoded_token: dict) -> List[str]:
    # custom claims disisipkan di root token oleh Firebase Admin
    roles = decoded_token.get("roles")
    if isinstance(roles, list):
        return roles
    return []

def get_user_roles_from_firestore(uid: str) -> List[str]:
    doc = db.collection("users").document(uid).get()
    if doc.exists:
        data = doc.to_dict() or {}
        if isinstance(data.get("roles"), list):
            return data["roles"]
    return []

# ---------- Verify token ----------
def verify_id_token_logic(payload: VerifyTokenIn) -> Dict[str, Any]:
    try:
        decoded = auth.verify_id_token(payload.id_token)
        # ambil custom claims yang ada (selain field standar)
        std_keys = {"aud","auth_time","email","email_verified","exp","firebase","iat","iss","sub","uid"}
        claims = {k: v for k, v in decoded.items() if k not in std_keys}
        return {"uid": decoded["uid"], "claims": claims}
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

# ---------- Update profile ----------
def update_profile_logic(user_uid: str, body: UpdateProfileIn) -> Dict[str, Any]:
    kwargs = {}
    if body.display_name is not None:
        kwargs["display_name"] = body.display_name
    if body.photo_url is not None:
        kwargs["photo_url"] = str(body.photo_url)

    if not kwargs:
        return {"ok": True, "message": "Nothing to update"}

    try:
        u = auth.update_user(user_uid, **kwargs)
        db.collection("users").document(u.uid).set(
            {
                "display_name": u.display_name or "",
                "photo_url": u.photo_url or "",
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )
        return {"uid": u.uid, "display_name": u.display_name, "photo_url": u.photo_url}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Update failed: {e}")

# ---------- Change password ----------
async def change_password_logic(body: ChangePasswordIn) -> Dict[str, Any]:
    if not settings.FIREBASE_API_KEY:
        raise HTTPException(status_code=500, detail="FIREBASE_API_KEY belum di-set")
    url = f"{IDT_BASE}/accounts:update"
    params = {"key": settings.FIREBASE_API_KEY}
    payload = {"idToken": body.id_token, "password": body.new_password, "returnSecureToken": True}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, params=params, json=payload)
        if r.status_code != 200:
            msg = r.json().get("error", {}).get("message", "UPDATE_PASSWORD_FAILED")
            raise HTTPException(status_code=400, detail=msg)
        return r.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------- Send password reset ----------
async def send_password_reset_logic(body: PasswordResetIn) -> Dict[str, Any]:
    if not settings.FIREBASE_API_KEY:
        raise HTTPException(status_code=500, detail="FIREBASE_API_KEY belum di-set")
    url = f"{IDT_BASE}/accounts:sendOobCode"
    params = {"key": settings.FIREBASE_API_KEY}
    payload = {"requestType": "PASSWORD_RESET", "email": body.email}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, params=params, json=payload)
        if r.status_code != 200:
            msg = r.json().get("error", {}).get("message", "SEND_RESET_FAILED")
            raise HTTPException(status_code=400, detail=msg)
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



async def get_optional_user(authorization: Optional[str] = Header(None)):
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        try:
            decoded = auth.verify_id_token(parts[1])
            # simpan decoded di obyek user sederhana
            class U: pass
            u = U()
            u.uid = decoded.get("uid")
            u.email = decoded.get("email")
            u._decoded_token = decoded
            return u
        except Exception:
            return None
    return None