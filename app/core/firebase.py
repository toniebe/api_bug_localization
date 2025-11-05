from pathlib import Path
import firebase_admin
from firebase_admin import credentials, auth as fb_auth, firestore
from app.config import settings

# Validasi service account path biar error lebih jelas
sa_path = Path(settings.GOOGLE_APPLICATION_CREDENTIALS)
if not sa_path.exists():
    raise RuntimeError(
        f"Firebase service account JSON tidak ditemukan: {sa_path}. "
        f"Atur GOOGLE_APPLICATION_CREDENTIALS di .env atau taruh file di lokasi tersebut."
    )

if not firebase_admin._apps:
    cred = credentials.Certificate(str(sa_path))
    firebase_admin.initialize_app(cred, {"projectId": settings.FIREBASE_PROJECT_ID})

db = firestore.client()
auth = fb_auth
