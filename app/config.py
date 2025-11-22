from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
import os
from typing import ClassVar


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
DEFAULT_SA_PATH = BASE_DIR / "serviceAccountKey.json"
load_dotenv(ENV_PATH)

class Settings(BaseSettings):
    #FIREBASE
    FIREBASE_API_KEY: str = Field(...)
    FIREBASE_PROJECT_ID: str | None = None
    GOOGLE_APPLICATION_CREDENTIALS: str = str(DEFAULT_SA_PATH)
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    FIREBASE_SERVICE_ACCOUNT_JSON: str | None = None

    #Neo4j
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "neo4j2025"
    
    ## ML Engine
    BASE_DIR: ClassVar[Path] = Path(__file__).resolve().parent.parent.parent
    ML_ENGINE_DIR: Path = Path(os.getenv("ML_ENGINE_DIR", BASE_DIR / "ml_engine")).resolve()

    ML_PYTHON_BIN: str = os.getenv("ML_PYTHON_BIN", "python")
    ML_MAIN_SCRIPT: str = os.getenv("ML_MAIN_SCRIPT", "main.py")

    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()
