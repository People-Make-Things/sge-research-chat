from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Dict, List, Optional

from pydantic import TypeAdapter

from .chunking import chunk_article
from .config import Settings
from .discovery import article_json_url, discover_article_urls, slug_from_url
from .embeddings import make_embedding_provider
from .errors import ArticleExtractionError
from .fetchers import Fetcher, make_fetcher
from .models import Article, IngestStats
from .normalize import normalize_from_html, normalize_next_json_payload
from .vectorstore import make_vector_store


def manifest_path(settings: Settings) -> Path:
    return settings.data_dir / "manifest.json"


def articles_dir(settings: Settings) -> Path:
    return settings.data_dir / "articles"


def load_manifest(settings: Settings) -> Dict[str, Dict[str, str]]:
    path = manifest_path(settings)
    if not path.exists():
        return {}
    return json.loads(path.read_text("utf-8"))


def save_manifest(settings: Settings, manifest: Dict[str, Dict[str, str]]) -> None:
    manifest_path(settings).write_text(json.dumps(manifest, indent=2, sort_keys=True), "utf-8")


def save_article(settings: Settings, article: Article) -> None:
    path = articles_dir(settings) / ("%s.json" % article.slug)
    path.write_text(json.dumps(article.model_dump(mode="json"), indent=2, ensure_ascii=False), "utf-8")


async def fetch_article(fetcher: Fetcher, base_url: str, build_id: str, url: str) -> Article:
    slug = slug_from_url(url)
    json_url = article_json_url(base_url, build_id, slug)
    try:
        raw = await fetcher.fetch_text(json_url)
        payload = json.loads(raw)
        return normalize_next_json_payload(payload, url)
    except Exception as json_exc:
        try:
            html = await fetcher.fetch_text(url)
            return normalize_from_html(html, url)
        except Exception as html_exc:
            raise ArticleExtractionError(
                "Failed JSON and HTML extraction. JSON error: %s. HTML error: %s"
                % (json_exc, html_exc)
            ) from html_exc


async def ingest_articles(
    settings: Settings,
    limit: Optional[int] = None,
    force: bool = False,
    fetcher_kind: Optional[str] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> IngestStats:
    settings.ensure_dirs()
    manifest = load_manifest(settings)
    embedding_provider = make_embedding_provider(settings)
    vector_store = make_vector_store(settings, embedding_provider)
    stats = IngestStats()

    async with make_fetcher(settings, fetcher_kind) as fetcher:
        build_id, urls = await discover_article_urls(fetcher, settings.base_url)
        if limit:
            urls = urls[:limit]
        stats.discovered_urls = len(urls)
        if progress_callback:
            progress_callback("Discovered %s article URLs." % stats.discovered_urls)

        for index, url in enumerate(urls, start=1):
            try:
                article = await fetch_article(fetcher, settings.base_url, build_id, url)
                previous = manifest.get(article.slug)
                if previous and previous.get("content_hash") == article.content_hash and not force:
                    stats.skipped_articles += 1
                    if progress_callback and (index == 1 or index % 25 == 0 or index == len(urls)):
                        progress_callback(
                            "[%s/%s] skipped=%s indexed=%s failed=%s"
                            % (index, len(urls), stats.skipped_articles, stats.indexed_articles, stats.failed_urls)
                        )
                    continue
                chunks = chunk_article(
                    article,
                    target_tokens=settings.chunk_target_tokens,
                    overlap_tokens=settings.chunk_overlap_tokens,
                )
                if not chunks:
                    stats.skipped_articles += 1
                    manifest[article.slug] = {
                        "content_hash": article.content_hash,
                        "source_url": article.source_url,
                        "status": "empty",
                    }
                    if progress_callback and (index == 1 or index % 25 == 0 or index == len(urls)):
                        progress_callback(
                            "[%s/%s] skipped=%s indexed=%s failed=%s"
                            % (index, len(urls), stats.skipped_articles, stats.indexed_articles, stats.failed_urls)
                        )
                    continue
                save_article(settings, article)
                vector_store.delete_article(article.slug)
                stats.chunks_indexed += vector_store.upsert_chunks(chunks)
                stats.indexed_articles += 1
                manifest[article.slug] = {
                    "content_hash": article.content_hash,
                    "source_url": article.source_url,
                    "status": "indexed",
                }
            except Exception as exc:
                stats.failed_urls += 1
                stats.failures[url] = str(exc)
            if progress_callback and (index == 1 or index % 25 == 0 or index == len(urls)):
                progress_callback(
                    "[%s/%s] skipped=%s indexed=%s failed=%s chunks=%s"
                    % (
                        index,
                        len(urls),
                        stats.skipped_articles,
                        stats.indexed_articles,
                        stats.failed_urls,
                        stats.chunks_indexed,
                    )
                )

    stats.collection_count = vector_store.count()
    save_manifest(settings, manifest)
    return stats


def load_article(path: Path) -> Article:
    adapter = TypeAdapter(Article)
    return adapter.validate_json(path.read_text("utf-8"))


def saved_article_paths(settings: Settings) -> List[Path]:
    return sorted(articles_dir(settings).glob("*.json"))


def backfill_saved_articles(
    settings: Settings,
    limit: Optional[int] = None,
    batch_size: int = 128,
    delete_existing: bool = False,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> IngestStats:
    """Upsert already-normalized article JSON into the configured vector store."""

    settings.ensure_dirs()
    paths = saved_article_paths(settings)
    if limit:
        paths = paths[:limit]
    embedding_provider = make_embedding_provider(settings)
    vector_store = make_vector_store(settings, embedding_provider)
    stats = IngestStats(discovered_urls=len(paths))
    pending_chunks = []

    def flush() -> None:
        nonlocal pending_chunks
        if not pending_chunks:
            return
        stats.chunks_indexed += vector_store.upsert_chunks(pending_chunks)
        pending_chunks = []

    for index, path in enumerate(paths, start=1):
        try:
            article = load_article(path)
            chunks = chunk_article(
                article,
                target_tokens=settings.chunk_target_tokens,
                overlap_tokens=settings.chunk_overlap_tokens,
            )
            if not chunks:
                stats.skipped_articles += 1
                continue
            if delete_existing:
                vector_store.delete_article(article.slug)
            pending_chunks.extend(chunks)
            if len(pending_chunks) >= batch_size:
                flush()
            stats.indexed_articles += 1
        except Exception as exc:
            stats.failed_urls += 1
            stats.failures[str(path)] = str(exc)
        if progress_callback and (index == 1 or index % 25 == 0 or index == len(paths)):
            progress_callback(
                "[%s/%s] backfilled=%s skipped=%s failed=%s chunks=%s"
                % (
                    index,
                    len(paths),
                    stats.indexed_articles,
                    stats.skipped_articles,
                    stats.failed_urls,
                    stats.chunks_indexed,
                )
            )

    flush()
    stats.collection_count = vector_store.count()
    return stats
