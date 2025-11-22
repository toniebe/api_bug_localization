# app/firebase.py
from pathlib import Path
import json

import firebase_admin
from firebase_admin import credentials, auth as fb_auth, firestore
from app.config import settings

# 1) Production: dari ENV JSON
if settings.FIREBASE_SERVICE_ACCOUNT_JSON:
    try:
        sa_info = json.loads(settings.FIREBASE_SERVICE_ACCOUNT_JSON)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            "FIREBASE_SERVICE_ACCOUNT_JSON bukan JSON valid"
        ) from e

    cred_obj = credentials.Certificate(sa_info)

# 2) Development: fallback dari file lokal
else:
    sa_path = Path(settings.GOOGLE_APPLICATION_CREDENTIALS)
    if not sa_path.exists():
        raise RuntimeError(
            f"Firebase service account JSON tidak ditemukan: {sa_path}. "
            f"Set FIREBASE_SERVICE_ACCOUNT_JSON atau GOOGLE_APPLICATION_CREDENTIALS."
        )
    cred_obj = credentials.Certificate(str(sa_path))

# Inisialisasi Firebase Admin sekali saja
if not firebase_admin._apps:
    firebase_admin.initialize_app(
        cred_obj,
        {"projectId": settings.FIREBASE_PROJECT_ID},
    )

db = firestore.client()
auth = fb_auth
