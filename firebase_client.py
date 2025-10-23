# firebase_client.py
import os, json, base64, re
import firebase_admin
from firebase_admin import credentials, auth as fb_auth, firestore

def _init_firebase_app():
    if firebase_admin._apps:
        return firebase_admin.get_app()

    b64 = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not b64:
        raise RuntimeError("ENV GOOGLE_APPLICATION_CREDENTIALS tidak ditemukan (harus base64 JSON).")

    # bersihkan whitespace yang kadang ikut ter-copy
    b64 = re.sub(r"\s+", "", b64)

    # tambahkan padding '=' bila kurang
    missing = len(b64) % 4
    if missing:
        b64 += "=" * (4 - missing)

    try:
        raw = base64.b64decode(b64).decode("utf-8")
        info = json.loads(raw)
    except Exception as e:
        raise RuntimeError(f"Gagal decode/parse GOOGLE_APPLICATION_CREDENTIALS: {e}")

    if info.get("type") != "service_account":
        raise RuntimeError("JSON bukan 'service_account' key.")

    project_id = os.getenv("FIREBASE_PROJECT_ID")  # opsional
    cred = credentials.Certificate(info)
    return firebase_admin.initialize_app(cred, {"projectId": project_id} if project_id else None)

# Init sekali
_init_firebase_app()

auth = fb_auth
db = firestore.client()
FIREBASE_WEB_API_KEY = os.getenv("FIREBASE_WEB_API_KEY")
IDT_BASE = "https://identitytoolkit.googleapis.com/v1"
