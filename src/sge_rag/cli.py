from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import List, Optional

import typer

from .config import Settings
from .errors import SgeRagError
from .fetchers import save_browser_login_state
from .pipeline import backfill_saved_articles, ingest_articles
from .retrieval import Retriever

app = typer.Typer(help="Social Growth Engineers RAG tools.")


@app.command()
def login(
    url: str = typer.Option(
        "https://www.socialgrowthengineers.com/login",
        "--url",
        help="Login URL to open before saving browser state.",
    ),
    state_path: Optional[str] = typer.Option(None, "--state-path", help="Where to write Playwright storage state."),
) -> None:
    """Open a real browser, let you log in, and save auth state for ingestion."""

    settings = Settings()
    path = settings.browser_state_path if state_path is None else Path(state_path)
    try:
        asyncio.run(save_browser_login_state(url, path, headless=False))
    except SgeRagError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo("Saved browser auth state to %s" % path)


@app.command()
def ingest(
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Limit number of article URLs for smoke tests."),
    force: bool = typer.Option(False, "--force", help="Re-index even when content hash is unchanged."),
    fetcher: Optional[str] = typer.Option(None, "--fetcher", help="auto, http, or browser."),
    embedding_provider: Optional[str] = typer.Option(None, "--embedding-provider", help="openai or hash."),
    vectorstore: Optional[str] = typer.Option(None, "--vectorstore", help="chroma or upstash."),
) -> None:
    """Discover, normalize, chunk, embed, and index articles."""

    settings = Settings()
    if embedding_provider:
        settings.embedding_provider = embedding_provider  # type: ignore[assignment]
    if vectorstore:
        settings.vectorstore = vectorstore  # type: ignore[assignment]
    try:
        stats = asyncio.run(
            ingest_articles(
                settings,
                limit=limit,
                force=force,
                fetcher_kind=fetcher,
                progress_callback=typer.echo,
            )
        )
    except SgeRagError as exc:
        typer.echo("Ingestion failed: %s" % exc, err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(stats.model_dump(mode="json"), indent=2))


@app.command()
def query(
    question: str = typer.Argument(..., help="Question to answer from the RAG index."),
    top_k: int = typer.Option(5, "--top-k", "-k", min=1, max=20),
    category: List[str] = typer.Option([], "--category", "-c", help="Category filter; repeatable."),
    after: Optional[str] = typer.Option(None, "--after", help="ISO date lower bound, e.g. 2026-01-01."),
    no_answer: bool = typer.Option(False, "--no-answer", help="Return retrieval fallback instead of LLM answer."),
    mode: str = typer.Option("fast", "--mode", help="fast or deep answer model mode."),
    embedding_provider: Optional[str] = typer.Option(None, "--embedding-provider", help="openai or hash."),
    vectorstore: Optional[str] = typer.Option(None, "--vectorstore", help="chroma or upstash."),
) -> None:
    """Run a local RAG query."""

    settings = Settings()
    if embedding_provider:
        settings.embedding_provider = embedding_provider  # type: ignore[assignment]
    if vectorstore:
        settings.vectorstore = vectorstore  # type: ignore[assignment]
    retriever = Retriever(settings)
    response = retriever.query(
        question,
        top_k=top_k,
        categories=category or None,
        after=after,
        answer=not no_answer,
        mode=mode,  # type: ignore[arg-type]
    )
    typer.echo(json.dumps(response.model_dump(mode="json"), indent=2))


@app.command("backfill-vectors")
def backfill_vectors(
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Limit saved article JSON files to upsert."),
    embedding_provider: Optional[str] = typer.Option(None, "--embedding-provider", help="openai or hash."),
    vectorstore: Optional[str] = typer.Option(None, "--vectorstore", help="chroma or upstash."),
) -> None:
    """Upsert the existing data/articles JSON files into the configured vector store."""

    settings = Settings()
    if embedding_provider:
        settings.embedding_provider = embedding_provider  # type: ignore[assignment]
    if vectorstore:
        settings.vectorstore = vectorstore  # type: ignore[assignment]
    try:
        stats = backfill_saved_articles(settings, limit=limit, progress_callback=typer.echo)
    except SgeRagError as exc:
        typer.echo("Backfill failed: %s" % exc, err=True)
        raise typer.Exit(code=1) from exc
    except RuntimeError as exc:
        typer.echo("Backfill failed: %s" % exc, err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(stats.model_dump(mode="json"), indent=2))


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
    reload: bool = typer.Option(False, "--reload"),
) -> None:
    """Start the FastAPI app."""

    import uvicorn

    uvicorn.run("sge_rag.api:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
