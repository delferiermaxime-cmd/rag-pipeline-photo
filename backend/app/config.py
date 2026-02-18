# -*- coding: utf-8 -*--
import json
from typing import List
from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "RAG Local"
    DEBUG: bool = False

    # Base de données
    DATABASE_URL: str = "postgresql+asyncpg://raguser:ragpassword@postgres:5432/ragdb"

    # JWT — SECRET_KEY sans valeur par défaut : plante au démarrage si absent du .env
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24h

    # Qdrant
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "documents"
    EMBEDDING_DIM: int = 1024  # bge-m3:567m

    # Ollama
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_EMBEDDING_MODEL: str = "bge-m3:567m"
    OLLAMA_TIMEOUT: int = 120
    OLLAMA_AVAILABLE_MODELS: List[str] = [
        "gemma3:4b",
        "llama3.1:latest",
        "deepseek-r1:14b",
        "gemma3:12b",
        "gemma3:27b",
    ]

    @field_validator("OLLAMA_AVAILABLE_MODELS", mode="before")
    @classmethod
    def parse_models(cls, v):
        if isinstance(v, str):
            return [m.strip() for m in v.split(",") if m.strip()]
        return v

    # RAG
    CHUNK_SIZE: int = 600
    CHUNK_OVERLAP: int = 50
    TOP_K: int = 5

    # CORS — FIX : validator robuste qui accepte les deux formats :
    #   - virgules  : http://localhost,http://localhost:8080
    #   - JSON list : ["http://localhost","http://localhost:8080"]
    CORS_ORIGINS: List[str] = [
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:8080",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors(cls, v):
        if isinstance(v, str):
            v = v.strip()
            # FIX : détecte le format JSON et le parse correctement
            if v.startswith("["):
                try:
                    return json.loads(v)
                except json.JSONDecodeError:
                    pass
            # Format virgules (format recommandé dans .env.example)
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    # Upload
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50 MB
    UPLOAD_DIR: str = "/tmp/uploads"

    ALLOWED_EXTENSIONS: List[str] = [
        "pdf", "txt", "md",
        "docx", "dotx", "doc",
        "pptx", "ppt",
        "xlsx", "xls",
        "odt", "ods", "odp",
        "html", "htm",
        "csv", "epub",
        "asciidoc", "adoc",
    ]

    @field_validator("ALLOWED_EXTENSIONS", mode="before")
    @classmethod
    def parse_extensions(cls, v):
        if isinstance(v, str):
            return [e.strip().lower().lstrip(".") for e in v.split(",") if e.strip()]
        return v

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 20

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


settings = Settings()
