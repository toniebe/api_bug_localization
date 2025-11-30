from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routes.auth_routes import router as auth_router
from app.routes.search_routes import router as search_router
from app.core import firebase  # noqa
from app.routes.project_routes import router as project_router
from app.routes.organization_routes import router as organization_router
from app.routes.bug_routes import router as bug_router
from app.routes.data_routes import router as data_router
from app.routes.ltr_routes import router as ltr_router


app = FastAPI(
    title="EasyFix API",
    description="Platform bug resolution berbasis AI yang dirancang untuk mentransformasi cara tim rekayasa perangkat lunak menangani debugging.",
    version="0.0.1",
)

allowed_origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", tags=["health"])
def healthcheck():
    return {"status": "ok", "service": "easyfix", "version": "0.0.1"}

app.include_router(auth_router)
app.include_router(search_router)
app.include_router(project_router)
app.include_router(organization_router)
app.include_router(bug_router)
app.include_router(data_router)
app.include_router(ltr_router)