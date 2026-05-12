from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Protocol

from .config import Settings
from .embeddings import EmbeddingProvider
from .models import ArticleChunk, RetrievedChunk


def metadata_from_chunk(chunk: ArticleChunk) -> Dict[str, Any]:
    return {
        "article_id": chunk.article_id,
        "slug": chunk.slug,
        "title": chunk.title,
        "source_url": chunk.source_url,
        "published_at": chunk.published_at or "",
        "categories_json": json.dumps(chunk.categories, ensure_ascii=True),
        "categories_text": "|%s|" % "|".join(chunk.categories) if chunk.categories else "",
        "tags_json": json.dumps(chunk.tags, ensure_ascii=True),
        "heading_path_json": json.dumps(chunk.heading_path, ensure_ascii=True),
        "chunk_index": chunk.chunk_index,
        "content_hash": chunk.content_hash,
    }


def decode_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    decoded = dict(metadata)
    for key in ("categories_json", "tags_json", "heading_path_json"):
        target = key.replace("_json", "")
        try:
            decoded[target] = json.loads(str(metadata.get(key) or "[]"))
        except json.JSONDecodeError:
            decoded[target] = []
    return decoded


class VectorStore(Protocol):
    def count(self) -> int:
        ...

    def upsert_chunks(self, chunks: List[ArticleChunk]) -> int:
        ...

    def delete_article(self, slug: str) -> None:
        ...

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        categories: Optional[List[str]] = None,
        after: Optional[str] = None,
    ) -> List[RetrievedChunk]:
        ...


class ChromaVectorStore:
    def __init__(self, settings: Settings, embeddings: EmbeddingProvider) -> None:
        self.settings = settings
        self.embeddings = embeddings
        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError("Install chromadb to use the vector store.") from exc
        self.client = chromadb.PersistentClient(path=str(settings.chroma_dir))
        self.collection = self.client.get_or_create_collection(
            name=settings.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def count(self) -> int:
        return int(self.collection.count())

    def upsert_chunks(self, chunks: List[ArticleChunk]) -> int:
        if not chunks:
            return 0
        ids = [chunk.id for chunk in chunks]
        docs = [chunk.text for chunk in chunks]
        metadatas = [metadata_from_chunk(chunk) for chunk in chunks]
        vectors = self.embeddings.embed_texts(docs)
        self.collection.upsert(
            ids=ids,
            documents=docs,
            metadatas=metadatas,
            embeddings=vectors,
        )
        return len(chunks)

    def delete_article(self, slug: str) -> None:
        try:
            self.collection.delete(where={"slug": slug})
        except Exception:
            return

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        categories: Optional[List[str]] = None,
        after: Optional[str] = None,
    ) -> List[RetrievedChunk]:
        query_embedding = self.embeddings.embed_texts([query_text])[0]
        overfetch = max(top_k * 4, top_k)
        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=overfetch,
            include=["documents", "metadatas", "distances"],
        )
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0]

        chunks: List[RetrievedChunk] = []
        for doc, metadata, chunk_id, distance in zip(docs, metas, ids, distances):
            decoded = decode_metadata(metadata or {})
            if categories:
                existing = set(decoded.get("categories") or [])
                if not existing.intersection(set(categories)):
                    continue
            if after and decoded.get("published_at") and str(decoded["published_at"]) < after:
                continue
            score = None if distance is None else 1.0 - float(distance)
            chunks.append(
                RetrievedChunk(
                    id=str(chunk_id),
                    text=str(doc),
                    score=score,
                    metadata=decoded,
                )
            )
            if len(chunks) >= top_k:
                break
        return chunks


def upstash_vector_from_chunk(chunk: ArticleChunk, vector: List[float]) -> Dict[str, Any]:
    return {
        "id": chunk.id,
        "vector": vector,
        "metadata": metadata_from_chunk(chunk),
        "data": chunk.text,
    }


class UpstashVectorStore:
    def __init__(self, settings: Settings, embeddings: EmbeddingProvider) -> None:
        self.settings = settings
        self.embeddings = embeddings
        if not settings.upstash_vector_rest_url or not settings.upstash_vector_rest_token:
            raise RuntimeError(
                "Set UPSTASH_VECTOR_REST_URL and UPSTASH_VECTOR_REST_TOKEN to use Upstash Vector."
            )
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("Install httpx to use Upstash Vector.") from exc
        self.httpx = httpx
        self.base_url = settings.upstash_vector_rest_url.rstrip("/")
        self.headers = {"Authorization": "Bearer %s" % settings.upstash_vector_rest_token}

    def _request(self, method: str, path: str, payload: Optional[Any] = None) -> Any:
        url = "%s/%s" % (self.base_url, path.lstrip("/"))
        kwargs: Dict[str, Any] = {"headers": self.headers}
        if payload is not None:
            kwargs["json"] = payload
        with self.httpx.Client(timeout=self.settings.request_timeout_seconds) as client:
            response = client.request(method, url, **kwargs)
            response.raise_for_status()
        data = response.json()
        return data.get("result", data)

    def count(self) -> int:
        result = self._request("GET", "info")
        return int(result.get("vectorCount") or result.get("totalVectorCount") or 0)

    def upsert_chunks(self, chunks: List[ArticleChunk]) -> int:
        if not chunks:
            return 0
        vectors = self.embeddings.embed_texts([chunk.text for chunk in chunks])
        batch: List[Dict[str, Any]] = []
        for chunk, vector in zip(chunks, vectors):
            batch.append(upstash_vector_from_chunk(chunk, vector))
            if len(batch) >= 100:
                self._request("POST", "upsert", batch)
                batch = []
        if batch:
            self._request("POST", "upsert", batch)
        return len(chunks)

    def delete_article(self, slug: str) -> None:
        safe_slug = slug.replace("\\", "\\\\").replace("'", "\\'")
        try:
            self._request("POST", "delete", {"filter": "slug = '%s'" % safe_slug})
        except Exception:
            return

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        categories: Optional[List[str]] = None,
        after: Optional[str] = None,
    ) -> List[RetrievedChunk]:
        query_embedding = self.embeddings.embed_texts([query_text])[0]
        overfetch = max(top_k * 4, top_k)
        result = self._request(
            "POST",
            "query",
            {
                "vector": query_embedding,
                "topK": overfetch,
                "includeMetadata": True,
                "includeData": True,
            },
        )
        chunks: List[RetrievedChunk] = []
        for item in result or []:
            metadata = decode_metadata(item.get("metadata") or {})
            if categories:
                existing = set(metadata.get("categories") or [])
                if not existing.intersection(set(categories)):
                    continue
            if after and metadata.get("published_at") and str(metadata["published_at"]) < after:
                continue
            chunks.append(
                RetrievedChunk(
                    id=str(item.get("id") or ""),
                    text=str(item.get("data") or item.get("document") or ""),
                    score=item.get("score"),
                    metadata=metadata,
                )
            )
            if len(chunks) >= top_k:
                break
        return chunks


def make_vector_store(settings: Settings, embeddings: EmbeddingProvider) -> VectorStore:
    if settings.vectorstore == "upstash":
        return UpstashVectorStore(settings, embeddings)
    return ChromaVectorStore(settings, embeddings)
