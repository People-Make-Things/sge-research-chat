from __future__ import annotations

from typing import List, Literal, Optional

from .config import Settings
from .embeddings import make_embedding_provider
from .models import QueryResponse, QuerySource, RetrievedChunk
from .vectorstore import make_vector_store


SYSTEM_PROMPT = """You answer only from the provided Social Growth Engineers context.
If the context is insufficient, say what is missing. Cite sources inline using [1], [2], etc.
Keep the answer concise, practical, and grounded in the retrieved articles."""


def trim_text(text: str, max_chars: Optional[int] = None) -> str:
    if max_chars is None or len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 18)].rstrip() + "\n[trimmed]"


def build_context(
    chunks: List[RetrievedChunk],
    max_chars: Optional[int] = None,
    max_chunk_chars: Optional[int] = None,
) -> str:
    parts = []
    used_chars = 0
    for index, chunk in enumerate(chunks, start=1):
        metadata = chunk.metadata
        chunk_text = trim_text(chunk.text, max_chunk_chars)
        part = (
            "[%d] %s\nURL: %s\nDate: %s\nCategories: %s\n\n%s"
            % (
                index,
                metadata.get("title", "Untitled"),
                metadata.get("source_url", ""),
                metadata.get("published_at", ""),
                ", ".join(metadata.get("categories") or []),
                chunk_text,
            )
        )
        if max_chars is not None and used_chars + len(part) > max_chars:
            remaining = max_chars - used_chars
            if remaining <= 80:
                break
            part = trim_text(part, remaining)
            parts.append(part)
            break
        parts.append(part)
        used_chars += len(part) + 7
    return "\n\n---\n\n".join(parts)


def model_for_mode(settings: Settings, mode: Literal["fast", "deep"] = "fast") -> str:
    return settings.deep_model if mode == "deep" else settings.fast_model


def answer_with_openai(
    settings: Settings,
    query: str,
    chunks: List[RetrievedChunk],
    mode: Literal["fast", "deep"] = "fast",
) -> str:
    if not chunks:
        return "I could not find relevant Social Growth Engineers context for that question."
    try:
        from openai import OpenAI
    except ImportError:
        return fallback_answer(chunks)

    client = OpenAI()
    context = build_context(
        chunks,
        max_chars=12000 if mode == "deep" else 6500,
        max_chunk_chars=1800 if mode == "deep" else 1200,
    )
    response = client.chat.completions.create(
        model=model_for_mode(settings, mode),
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Question: %s\n\nContext:\n%s" % (query, context)},
        ],
        temperature=0.2,
    )
    content = response.choices[0].message.content
    return content or fallback_answer(chunks)


def fallback_answer(chunks: List[RetrievedChunk]) -> str:
    if not chunks:
        return "No matching chunks were found."
    titles = []
    seen = set()
    for chunk in chunks:
        title = str(chunk.metadata.get("title") or "Untitled")
        if title in seen:
            continue
        seen.add(title)
        titles.append(title)
    return (
        "I found relevant context, but no answer model is configured. "
        "Top matching sources: %s." % "; ".join(titles[:5])
    )


class Retriever:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.embedding_provider = make_embedding_provider(settings)
        self.store = make_vector_store(settings, self.embedding_provider)

    def retrieve(
        self,
        query_text: str,
        top_k: int = 5,
        categories: Optional[List[str]] = None,
        after: Optional[str] = None,
    ) -> List[RetrievedChunk]:
        return self.store.query(query_text, top_k=top_k, categories=categories, after=after)

    @staticmethod
    def sources_from_chunks(chunks: List[RetrievedChunk]) -> List[QuerySource]:
        return [
            QuerySource(
                title=str(chunk.metadata.get("title") or "Untitled"),
                source_url=str(chunk.metadata.get("source_url") or ""),
                slug=str(chunk.metadata.get("slug") or ""),
                published_at=str(chunk.metadata.get("published_at") or "") or None,
                categories=chunk.metadata.get("categories") or [],
                chunk_id=chunk.id,
                score=chunk.score,
            )
            for chunk in chunks
        ]

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        categories: Optional[List[str]] = None,
        after: Optional[str] = None,
        answer: bool = True,
        mode: Literal["fast", "deep"] = "fast",
    ) -> QueryResponse:
        chunks = self.retrieve(query_text, top_k=top_k, categories=categories, after=after)
        sources = self.sources_from_chunks(chunks)
        response_answer = (
            answer_with_openai(self.settings, query_text, chunks, mode=mode) if answer else fallback_answer(chunks)
        )
        return QueryResponse(answer=response_answer, sources=sources, chunks=chunks)
