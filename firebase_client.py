# firebase_client.py
import os
from dotenv import load_dotenv

import firebase_admin
from firebase_admin import credentials, auth as fb_auth, firestore

load_dotenv()

def _init_firebase_app():
    if firebase_admin._apps:
        return firebase_admin.get_app()

    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if cred_path and os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
    else:
        cred = credentials.ApplicationDefault()

    return firebase_admin.initialize_app(cred, {
        "projectId": os.getenv("FIREBASE_PROJECT_ID")
    })

# Init sekali
_init_firebase_app()

auth = fb_auth
db = firestore.client()
FIREBASE_WEB_API_KEY = os.getenv("FIREBASE_WEB_API_KEY")
IDT_BASE = "https://identitytoolkit.googleapis.com/v1"
