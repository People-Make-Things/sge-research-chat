from sge_rag.config import Settings
from sge_rag.models import RetrievedChunk
from sge_rag.retrieval import build_context, model_for_mode


def test_model_for_mode_defaults_to_fast_and_supports_deep():
    settings = Settings(fast_model="gpt-5.4-mini", deep_model="gpt-5.5")

    assert model_for_mode(settings, "fast") == "gpt-5.4-mini"
    assert model_for_mode(settings, "deep") == "gpt-5.5"


def test_build_context_trims_large_chunks_but_keeps_source_metadata():
    chunk = RetrievedChunk(
        id="chunk",
        text="A" * 500,
        score=0.8,
        metadata={
            "title": "Useful Source",
            "source_url": "https://example.com/source",
            "published_at": "2026-05-10",
            "categories": ["format"],
        },
    )

    context = build_context([chunk], max_chars=220, max_chunk_chars=80)

    assert "Useful Source" in context
    assert "https://example.com/source" in context
    assert "[trimmed]" in context
    assert len(context) <= 220
