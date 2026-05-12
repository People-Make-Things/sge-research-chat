from sge_rag.models import ArticleChunk
from sge_rag.vectorstore import decode_metadata, metadata_from_chunk


def test_metadata_round_trip_lists():
    chunk = ArticleChunk(
        id="chunk",
        article_id="article",
        slug="slug",
        title="Title",
        source_url="https://example.com/slug",
        published_at="2026-05-10T17:38:00",
        categories=["strategy", "format"],
        tags=["tiktok"],
        heading_path=["A", "B"],
        chunk_index=0,
        content_hash="hash",
        text="text",
    )
    metadata = metadata_from_chunk(chunk)
    decoded = decode_metadata(metadata)
    assert decoded["categories"] == ["strategy", "format"]
    assert decoded["tags"] == ["tiktok"]
    assert decoded["heading_path"] == ["A", "B"]

