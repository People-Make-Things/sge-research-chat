from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup
from markdownify import markdownify as html_to_markdown

from .discovery import parse_next_data, slug_from_url
from .errors import ArticleExtractionError
from .models import Article


def strip_html(html: Optional[str]) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(" ", strip=True)


def extract_node_names(edges_obj: Optional[Dict[str, Any]], key: str = "slug") -> List[str]:
    if not edges_obj:
        return []
    values: List[str] = []
    for edge in edges_obj.get("edges", []):
        node = edge.get("node", {})
        value = node.get(key) or node.get("name")
        if value:
            values.append(str(value))
    return values


def clean_article_html(content_html: str) -> str:
    soup = BeautifulSoup(content_html or "", "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    for iframe in soup.find_all("iframe"):
        src = iframe.get("src", "").strip()
        replacement = soup.new_tag("p")
        replacement.string = "Embedded media: %s" % src if src else "Embedded media"
        iframe.replace_with(replacement)
    return str(soup)


def html_to_clean_markdown(content_html: str) -> str:
    cleaned_html = clean_article_html(content_html)
    markdown = html_to_markdown(
        cleaned_html,
        heading_style="ATX",
        bullets="-",
        strip=["span"],
    )
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    markdown = re.sub(r"[ \t]+\n", "\n", markdown)
    return markdown.strip()


def content_hash_for(payload: Dict[str, Any]) -> str:
    relevant = {
        "title": payload.get("title"),
        "excerpt": payload.get("excerpt"),
        "date": payload.get("date"),
        "content": payload.get("content"),
        "categories": extract_node_names(payload.get("categories")),
        "tags": extract_node_names(payload.get("tags")),
    }
    encoded = json.dumps(relevant, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def get_featured_image(post: Dict[str, Any]) -> Optional[str]:
    image = post.get("featuredImage")
    if isinstance(image, dict):
        node = image.get("node") or {}
        source = node.get("sourceUrl")
        if source:
            return str(source)
    return None


def get_author_name(post: Dict[str, Any]) -> Optional[str]:
    author = post.get("author")
    if isinstance(author, dict):
        node = author.get("node") or {}
        name = node.get("name")
        if name:
            return str(name)
    return None


def normalize_post_payload(page_props: Dict[str, Any], source_url: str) -> Article:
    post = page_props.get("post")
    if not isinstance(post, dict):
        raise ArticleExtractionError("Page payload does not contain a post object.")

    content_html = post.get("content") or ""
    markdown = html_to_clean_markdown(content_html)
    slug = post.get("slug") or slug_from_url(source_url)
    article_hash = content_hash_for(post)
    return Article(
        id=str(post.get("id") or slug),
        slug=str(slug),
        source_url=source_url,
        title=str(post.get("title") or slug),
        excerpt=strip_html(post.get("excerpt")),
        published_at=post.get("date"),
        author=get_author_name(post),
        categories=extract_node_names(post.get("categories")),
        tags=extract_node_names(post.get("tags")),
        app_links=post.get("appLink") or {},
        featured_image_url=get_featured_image(post),
        is_gated=bool(page_props.get("isGated", False)),
        full_content=bool(post.get("fullContent", False)),
        content_html=content_html,
        content_markdown=markdown,
        content_hash=article_hash,
        ingested_at=datetime.now(timezone.utc),
    )


def normalize_next_json_payload(payload: Dict[str, Any], source_url: str) -> Article:
    page_props = payload.get("pageProps") or payload.get("props", {}).get("pageProps")
    if not isinstance(page_props, dict):
        raise ArticleExtractionError("Next JSON does not contain pageProps.")
    return normalize_post_payload(page_props, source_url)


def normalize_from_html(html: str, source_url: str) -> Article:
    data = parse_next_data(html)
    return normalize_next_json_payload(data, source_url)

