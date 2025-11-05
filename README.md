# EasyFix Backend — FastAPI + Firebase + Neo4j

### Fitur Utama
- Auth: register, login (Firebase Identity Toolkit), verify token, update profile, change password, password rese
- RBAC: custom claims roles (admin, developer, user)
- Search: terima keyword/sentence → NLTK preprocess → query Neo4j (Bug–Commit–Developer)
- Audit: setiap pencarian dicatat ke Firestore (search_logs)
- Swagger/OpenAPI: /docs & /redoc

### Instalasi

Install dependencies
`pip install -r requirements.txt`

Siapkan .env (template)
```
# Firebase
FIREBASE_API_KEY=AIzaSyXXXX...       
FIREBASE_PROJECT_ID=your-project-id
GOOGLE_APPLICATION_CREDENTIALS=serviceAccountKey.json
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

# Neo4j
NEO4J_URI=bolt://localhost:7687    
NEO4J_USER=neo4j
NEO4J_PASSWORD=YourNeo4jPassword
NEO4J_DATABASE=neo4j                   
```
Letakkan serviceAccountKey.json di root project (selevel .env).

#### Run Aplikasi

Selalu jalankan dari root (folder yang sama dengan .env):

`uvicorn app.main:app --reload --port 8000`

Swagger UI: http://localhost:8000/docs

ReDoc: http://localhost:8000/redoc

##### alur Auth
- Register (default role user; role khusus hanya oleh admin)
- Login → dapat id_token: Gunakan id_token sebagai Bearer untuk endpoint terproteksi
- Authorize di Swagger
    Klik Authorize (ikon gembok)
    Tempel hanya JWT (tanpa kata Bearer ); Swagger akan menambahkannya otomatis.

#### Endpoint Utama
1. Health
    GET / → status service

2. Auth
    - POST /auth/register — register user (admin dapat set role)
    - POST /auth/login — login; return id_token, refresh_token, dll
    - GET /auth/me — info profil & roles (Authorization: Bearer <id_token>)
    - POST /auth/verify-token — verifikasi id_token (body)
    - PATCH /auth/profile — update display_name / photo_url
    - POST /auth/change-password — ganti password (body: id_token, new_password)
    - POST /auth/send-password-reset — kirim email reset
    - PUT /auth/roles/{uid} — set roles (admin only)

3. Search (Neo4j)
    - POST /search — body: {"query": "<keyword or sentence>"}
        Preprocess NLTK → query Neo4j (Bug–Commit–Developer)
        
        Log transaksi ke Firestore: search_logs
