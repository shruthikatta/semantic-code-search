import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import indexing, search
from app.core.config import get_settings
from app.core.es_client import get_es
from app.core.index_schema import ensure_index

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("scs")

settings = get_settings()

app = FastAPI(
    title="Semantic Code Search",
    version="0.1.0",
    description="Hybrid (BM25 + dense vector) Python code search over AST-aware chunks.",
)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["http://localhost:3000"],
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(indexing.router)
app.include_router(search.router)


@app.on_event("startup")
def on_startup() -> None:
    try:
        es = get_es()
        if es.ping():
            created = ensure_index(es)
            log.info("Elasticsearch reachable. index=%s created=%s", settings.es_index, created)
        else:
            log.warning("Elasticsearch ping failed at %s", settings.elasticsearch_url)
    except Exception as exc:  # noqa: BLE001 - keep startup resilient
        log.warning("Skipping index bootstrap: %s", exc)


@app.get("/health")
def health() -> dict:
    es_ok = False
    try:
        es_ok = bool(get_es().ping())
    except Exception:  # noqa: BLE001
        es_ok = False
    return {
        "status": "ok" if es_ok else "degraded",
        "elasticsearch": es_ok,
        "index": settings.es_index,
        "embedding_model": settings.embedding_model,
        "embedding_dim": settings.embedding_dim,
    }
