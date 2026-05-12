import os

import httpx
import respx

from sge_rag.config import Settings
from sge_rag.embeddings import HashEmbeddingProvider
from sge_rag.models import ArticleChunk
from sge_rag.vectorstore import UpstashVectorStore, metadata_from_chunk, upstash_vector_from_chunk


def sample_chunk() -> ArticleChunk:
    return ArticleChunk(
        id="chunk-1",
        article_id="article-1",
        slug="viral-hook",
        title="Viral Hook",
        source_url="https://example.com/viral-hook",
        published_at="2026-05-10T17:38:00",
        categories=["format", "tiktok"],
        tags=["ugc"],
        heading_path=["Hook"],
        chunk_index=0,
        content_hash="hash",
        text="Title: Viral Hook\n\nA useful source chunk.",
    )


def upstash_settings() -> Settings:
    os.environ["UPSTASH_VECTOR_REST_URL"] = "https://vector.example.com"
    os.environ["UPSTASH_VECTOR_REST_TOKEN"] = "token"
    return Settings(
        _env_file=None,
        embedding_provider="hash",
        vectorstore="upstash",
        upstash_vector_rest_url="https://vector.example.com",
        upstash_vector_rest_token="token",
    )


def test_upstash_payload_preserves_source_metadata():
    chunk = sample_chunk()
    payload = upstash_vector_from_chunk(chunk, [0.1, 0.2])

    assert payload["id"] == chunk.id
    assert payload["data"] == chunk.text
    assert payload["metadata"]["source_url"] == chunk.source_url
    assert payload["metadata"]["categories_json"] == '["format", "tiktok"]'
    assert payload["metadata"]["heading_path_json"] == '["Hook"]'


@respx.mock
def test_upstash_query_maps_results_to_retrieved_chunks():
    chunk = sample_chunk()
    route = respx.post("https://vector.example.com/query").mock(
        return_value=httpx.Response(
            200,
            json={
                "result": [
                    {
                        "id": chunk.id,
                        "score": 0.92,
                        "data": chunk.text,
                        "metadata": metadata_from_chunk(chunk),
                    }
                ]
            },
        )
    )
    store = UpstashVectorStore(upstash_settings(), HashEmbeddingProvider(dimensions=8))

    chunks = store.query("viral hook", top_k=1)

    assert route.called
    assert chunks[0].id == chunk.id
    assert chunks[0].text == chunk.text
    assert chunks[0].score == 0.92
    assert chunks[0].metadata["categories"] == ["format", "tiktok"]
    assert chunks[0].metadata["source_url"] == chunk.source_url


@respx.mock
def test_upstash_delete_article_uses_metadata_filter():
    route = respx.post("https://vector.example.com/delete").mock(
        return_value=httpx.Response(200, json={"result": {"deleted": 2}})
    )
    store = UpstashVectorStore(upstash_settings(), HashEmbeddingProvider(dimensions=8))

    store.delete_article("viral-hook")

    assert route.called
    assert route.calls.last.request.content == b'{"filter":"slug = \'viral-hook\'"}'
