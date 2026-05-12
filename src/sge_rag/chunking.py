from __future__ import annotations

import hashlib
import re
from typing import Callable, List, Tuple

from .models import Article, ArticleChunk


def approximate_token_count(text: str) -> int:
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, int(len(text.split()) * 1.3))


def split_markdown_blocks(markdown: str) -> List[str]:
    blocks = [block.strip() for block in re.split(r"\n\s*\n", markdown or "") if block.strip()]
    return blocks


def heading_level_and_text(block: str) -> Tuple[int, str]:
    first_line = block.strip().splitlines()[0] if block.strip() else ""
    match = re.match(r"^(#{1,6})\s+(.+)$", first_line)
    if not match:
        return 0, ""
    return len(match.group(1)), match.group(2).strip()


def chunk_article(
    article: Article,
    target_tokens: int = 850,
    overlap_tokens: int = 120,
    token_counter: Callable[[str], int] = approximate_token_count,
) -> List[ArticleChunk]:
    markdown = article.content_markdown.strip()
    if not markdown:
        return []

    blocks = split_markdown_blocks(markdown)
    chunks: List[ArticleChunk] = []
    current_blocks: List[str] = []
    current_tokens = 0
    heading_path: List[str] = []
    chunk_heading_path: List[str] = []

    def emit() -> None:
        nonlocal current_blocks, current_tokens, chunk_heading_path
        text = "\n\n".join(current_blocks).strip()
        if not text:
            return
        chunk_index = len(chunks)
        raw_id = "%s:%s:%s" % (article.slug, chunk_index, article.content_hash[:12])
        chunk_id = hashlib.sha1(raw_id.encode("utf-8")).hexdigest()
        chunks.append(
            ArticleChunk(
                id=chunk_id,
                article_id=article.id,
                slug=article.slug,
                title=article.title,
                source_url=article.source_url,
                published_at=article.published_at,
                categories=article.categories,
                tags=article.tags,
                heading_path=list(chunk_heading_path),
                chunk_index=chunk_index,
                content_hash=article.content_hash,
                text=build_embedding_text(article, chunk_heading_path, text),
            )
        )

        if overlap_tokens <= 0:
            current_blocks = []
            current_tokens = 0
            return

        overlap: List[str] = []
        overlap_count = 0
        for block in reversed(current_blocks):
            block_tokens = token_counter(block)
            if overlap and overlap_count + block_tokens > overlap_tokens:
                break
            overlap.insert(0, block)
            overlap_count += block_tokens
        current_blocks = overlap
        current_tokens = overlap_count

    for block in blocks:
        level, heading_text = heading_level_and_text(block)
        if level:
            heading_path = heading_path[: level - 1] + [heading_text]
        block_tokens = token_counter(block)
        if current_blocks and current_tokens + block_tokens > target_tokens:
            emit()
            chunk_heading_path = list(heading_path)
        if not current_blocks:
            chunk_heading_path = list(heading_path)
        current_blocks.append(block)
        current_tokens += block_tokens

    if current_blocks:
        emit()

    return chunks


def build_embedding_text(article: Article, heading_path: List[str], body: str) -> str:
    parts = ["Title: %s" % article.title]
    if article.excerpt:
        parts.append("Summary: %s" % article.excerpt)
    if article.categories:
        parts.append("Categories: %s" % ", ".join(article.categories))
    if heading_path:
        parts.append("Section: %s" % " > ".join(heading_path))
    parts.append(body)
    return "\n\n".join(parts).strip()

