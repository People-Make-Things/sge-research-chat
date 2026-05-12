from sge_rag.chunking import chunk_article
from sge_rag.normalize import html_to_clean_markdown, normalize_next_json_payload


def sample_payload():
    return {
        "pageProps": {
            "isGated": False,
            "post": {
                "id": "post-1",
                "title": "The Language-Test Format Behind 26M Views",
                "excerpt": "<p>A language app built a content machine.</p>",
                "slug": "the-language-test-format-behind-26m-views",
                "date": "2026-05-10T17:38:00",
                "appLink": {"appLink": "https://apps.apple.com/example"},
                "featuredImage": {"node": {"sourceUrl": "https://example.com/image.png"}},
                "author": {"node": {"name": "SGE Team"}},
                "categories": {
                    "edges": [
                        {"node": {"name": "format", "slug": "format"}},
                        {"node": {"name": "gated", "slug": "gated"}},
                    ]
                },
                "tags": {"edges": [{"node": {"name": "TikTok", "slug": "tiktok"}}]},
                "content": """
                <h2>Setup</h2>
                <p>LangAI found a format that feels like a fun comprehension test.</p>
                <iframe src="https://www.socialgrowthengineers.com/embed/video/abc"></iframe>
                <h2>Why it works</h2>
                <p>It works as a challenge, a lesson, and a comment magnet at the same time.</p>
                """,
                "fullContent": True,
            },
        }
    }


def test_html_to_markdown_preserves_media_reference():
    markdown = html_to_clean_markdown('<p>Hello</p><iframe src="https://example.com/embed"></iframe>')
    assert "Hello" in markdown
    assert "Embedded media: https://example.com/embed" in markdown


def test_normalize_next_json_payload():
    article = normalize_next_json_payload(
        sample_payload(),
        "https://www.socialgrowthengineers.com/the-language-test-format-behind-26m-views",
    )
    assert article.title == "The Language-Test Format Behind 26M Views"
    assert article.categories == ["format", "gated"]
    assert article.tags == ["tiktok"]
    assert article.full_content is True
    assert article.featured_image_url == "https://example.com/image.png"
    assert article.content_hash


def test_chunk_article_outputs_metadata():
    article = normalize_next_json_payload(
        sample_payload(),
        "https://www.socialgrowthengineers.com/the-language-test-format-behind-26m-views",
    )
    chunks = chunk_article(article, target_tokens=40, overlap_tokens=10, token_counter=lambda text: len(text.split()))
    assert chunks
    assert all(chunk.text for chunk in chunks)
    assert chunks[0].source_url.endswith(article.slug)
    assert chunks[0].categories == ["format", "gated"]

