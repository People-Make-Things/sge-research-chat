from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class Article(BaseModel):
    id: str
    slug: str
    source_url: str
    title: str
    excerpt: str = ""
    published_at: Optional[str] = None
    author: Optional[str] = None
    categories: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    app_links: Dict[str, Optional[str]] = Field(default_factory=dict)
    featured_image_url: Optional[str] = None
    is_gated: bool = False
    full_content: bool = False
    content_html: str = ""
    content_markdown: str = ""
    content_hash: str
    ingested_at: datetime


class ArticleChunk(BaseModel):
    id: str
    article_id: str
    slug: str
    title: str
    source_url: str
    published_at: Optional[str] = None
    categories: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    heading_path: List[str] = Field(default_factory=list)
    chunk_index: int
    content_hash: str
    text: str


class IngestStats(BaseModel):
    discovered_urls: int = 0
    indexed_articles: int = 0
    skipped_articles: int = 0
    failed_urls: int = 0
    chunks_indexed: int = 0
    collection_count: int = 0
    failures: Dict[str, str] = Field(default_factory=dict)


class QueryFilters(BaseModel):
    categories: Optional[List[str]] = None
    after: Optional[str] = None


class QueryRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=20)
    filters: Optional[QueryFilters] = None
    mode: Literal["fast", "deep"] = "fast"


class RetrievedChunk(BaseModel):
    id: str
    text: str
    score: Optional[float] = None
    metadata: Dict[str, Any]


class QuerySource(BaseModel):
    title: str
    source_url: str
    slug: str
    published_at: Optional[str] = None
    categories: List[str] = Field(default_factory=list)
    chunk_id: str
    score: Optional[float] = None


class QueryResponse(BaseModel):
    answer: str
    sources: List[QuerySource]
    chunks: List[RetrievedChunk]


class RetrieveResponse(BaseModel):
    sources: List[QuerySource]
    chunks: List[RetrievedChunk]
