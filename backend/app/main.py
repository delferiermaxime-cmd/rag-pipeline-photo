# -*- coding: utf-8 -*-
import asyncio
import logging
import sys
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings
from app.models.database import init_db
from app.routers import admin, auth, chat, documents
from app.services.embedding_service import verify_embedding_model
from app.services.qdrant_service import ensure_collection

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Démarrage RAG Local…")

    # Client HTTP partagé — réutilise le pool de connexions pour tous les appels Ollama
    app.state.http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=5.0),
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    )

    await init_db()
    logger.info("Base de données initialisée")

    # Retry avec backoff exponentiel pour Qdrant/Ollama (peuvent démarrer après le backend)
    for attempt in range(1, 6):
        try:
            # FIX : on passe le client partagé — pas besoin d'en créer un nouveau
            dim = await verify_embedding_model(app.state.http_client)
            await ensure_collection(dim)
            logger.info(f"Qdrant prêt (dim={dim})")
            break
        except Exception as e:
            if attempt == 5:
                logger.error(f"Init Qdrant/Ollama échouée après 5 tentatives : {e}")
            else:
                wait = 2 ** attempt
                logger.warning(f"Init tentative {attempt}/5 échouée : {e}. Retry dans {wait}s…")
                await asyncio.sleep(wait)

    yield

    # Fermeture propre du client HTTP à l'arrêt du serveur
    await app.state.http_client.aclose()
    logger.info("Arrêt propre.")


app = FastAPI(title=settings.APP_NAME, version="1.0.0", lifespan=lifespan)

# CORS depuis settings — configurable via .env
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.APP_NAME}
