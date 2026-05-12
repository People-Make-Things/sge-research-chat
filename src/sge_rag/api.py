from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import Settings, get_settings
from .models import IngestStats, QueryRequest, QueryResponse, RetrieveResponse
from .pipeline import ingest_articles
from .retrieval import Retriever

app = FastAPI(title="Social Growth Engineers RAG", version="0.1.0")
WEB_DIST_DIR = Path(__file__).resolve().parents[2] / "web" / "dist"
_retriever_lock = Lock()


class IngestRequest(BaseModel):
    limit: Optional[int] = Field(default=None, ge=1)
    force: bool = False
    fetcher: Optional[str] = None


@lru_cache(maxsize=1)
def _cached_retriever() -> Retriever:
    return Retriever(get_settings())


def get_retriever() -> Retriever:
    with _retriever_lock:
        return _cached_retriever()


def clear_retriever_cache() -> None:
    with _retriever_lock:
        _cached_retriever.cache_clear()


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    collection_count = None
    try:
        retriever = get_retriever()
        collection_count = retriever.store.count()
    except Exception:
        collection_count = None
    return {
        "ok": True,
        "collection": settings.collection_name,
        "collection_count": collection_count,
    }


@app.post("/ingest", response_model=IngestStats)
async def ingest(request: IngestRequest) -> IngestStats:
    settings = Settings()
    stats = await ingest_articles(
        settings,
        limit=request.limit,
        force=request.force,
        fetcher_kind=request.fetcher,
    )
    clear_retriever_cache()
    return stats


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    filters = request.filters
    retriever = get_retriever()
    return retriever.query(
        request.query,
        top_k=request.top_k,
        categories=filters.categories if filters else None,
        after=filters.after if filters else None,
        mode=request.mode,
    )


@app.post("/retrieve", response_model=RetrieveResponse)
def retrieve(request: QueryRequest) -> RetrieveResponse:
    filters = request.filters
    retriever = get_retriever()
    chunks = retriever.retrieve(
        request.query,
        top_k=request.top_k,
        categories=filters.categories if filters else None,
        after=filters.after if filters else None,
    )
    return RetrieveResponse(sources=retriever.sources_from_chunks(chunks), chunks=chunks)


if WEB_DIST_DIR.exists():
    assets_dir = WEB_DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="web-assets")

    @app.get("/", include_in_schema=False)
    def web_index() -> FileResponse:
        return FileResponse(WEB_DIST_DIR / "index.html")

    @app.get("/{path:path}", include_in_schema=False)
    def web_fallback(path: str) -> FileResponse:
        candidate = WEB_DIST_DIR / path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(WEB_DIST_DIR / "index.html")
