from typing import Optional, List
from fastapi import Header, HTTPException, Depends

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.firebase import auth
from app.services.auth_service import get_user_roles_from_claims

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        decoded = auth.verify_id_token(token)
        uid = decoded["uid"]
        user = auth.get_user(uid)
        user._decoded_token = decoded  
        return user
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

def require_roles(required: List[str]):
    """
    Dependency generator: enforce minimal one role match.
    Contoh pakai: Depends(require_roles(["admin"]))
    """
    def _checker(current_user = Depends(get_current_user)):
        decoded = getattr(current_user, "_decoded_token", {})  # type: ignore[attr-defined]
        user_roles = set(get_user_roles_from_claims(decoded))
        if not user_roles:
            # fallback: jika token belum di-refresh, coba pakai custom claims tersimpan lain waktu (opsional)
            user_roles = set()
        if not user_roles.intersection(set(required)):
            raise HTTPException(status_code=403, detail="Forbidden: insufficient role")
        return current_user
    return _checker
