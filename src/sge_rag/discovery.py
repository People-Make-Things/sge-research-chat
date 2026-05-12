from __future__ import annotations

import json
import re
from typing import Iterable, List, Sequence, Tuple
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree
from xml.etree.ElementTree import ParseError

from bs4 import BeautifulSoup

from .errors import ArticleExtractionError
from .fetchers import Fetcher

SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"

NON_ARTICLE_SLUGS = {
    "",
    "about",
    "advertise",
    "apps",
    "auth",
    "case-studies",
    "join",
    "login",
    "mysge",
    "privacy-policy",
    "reports",
    "resources",
    "search",
    "terms-of-service",
    "trends",
}

NON_ARTICLE_PREFIXES = (
    "admin",
    "api",
    "apps/",
    "auth/",
    "author/",
    "category/",
    "embed/",
    "jobs/",
    "_next/",
)


def parse_next_data(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        raise ArticleExtractionError("Could not find __NEXT_DATA__ script.")
    return json.loads(script.string)


def parse_build_id(html: str) -> str:
    try:
        data = parse_next_data(html)
        build_id = data.get("buildId")
        if build_id:
            return str(build_id)
    except Exception:
        pass
    match = re.search(r'"buildId"\s*:\s*"([^"]+)"', html)
    if match:
        return match.group(1)
    raise ArticleExtractionError("Could not find Next.js buildId.")


def parse_sitemap_index(xml_text: str) -> List[str]:
    try:
        root = ElementTree.fromstring(xml_text)
    except ParseError:
        return re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml_text)
    locs: List[str] = []
    for sitemap in root.findall("%ssitemap" % SITEMAP_NS):
        loc = sitemap.find("%sloc" % SITEMAP_NS)
        if loc is not None and loc.text:
            locs.append(loc.text.strip())
    return locs


def parse_sitemap_urls(xml_text: str) -> List[str]:
    try:
        root = ElementTree.fromstring(xml_text)
    except ParseError:
        return re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml_text)
    locs: List[str] = []
    for url in root.findall("%surl" % SITEMAP_NS):
        loc = url.find("%sloc" % SITEMAP_NS)
        if loc is not None and loc.text:
            locs.append(loc.text.strip())
    return locs


def slug_from_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed.path.strip("/")


def is_article_url(url: str, base_url: str) -> bool:
    parsed = urlparse(url)
    base = urlparse(base_url)
    if parsed.netloc and parsed.netloc != base.netloc:
        return False
    slug = parsed.path.strip("/")
    if slug in NON_ARTICLE_SLUGS:
        return False
    if any(slug.startswith(prefix) for prefix in NON_ARTICLE_PREFIXES):
        return False
    if "/" in slug:
        return False
    return bool(slug)


def article_json_url(base_url: str, build_id: str, slug: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", "_next/data/%s/%s.json?slug=%s" % (build_id, slug, slug))


async def discover_article_urls(fetcher: Fetcher, base_url: str) -> Tuple[str, List[str]]:
    home_html = await fetcher.fetch_text(base_url.rstrip("/") + "/")
    build_id = parse_build_id(home_html)
    sitemap_xml = await fetcher.fetch_text(base_url.rstrip("/") + "/sitemap.xml")
    sitemap_urls = parse_sitemap_index(sitemap_xml)
    if not sitemap_urls:
        sitemap_urls = [base_url.rstrip("/") + "/sitemap.xml"]

    discovered: List[str] = []
    for sitemap_url in sitemap_urls:
        xml_text = await fetcher.fetch_text(sitemap_url)
        for url in parse_sitemap_urls(xml_text):
            if is_article_url(url, base_url):
                discovered.append(url)

    if not discovered:
        discovered.extend(extract_article_urls_from_html(home_html, base_url))

    return build_id, dedupe(discovered)


def extract_article_urls_from_html(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: List[str] = []
    for link in soup.find_all("a", href=True):
        href = str(link["href"])
        absolute = urljoin(base_url.rstrip("/") + "/", href)
        if is_article_url(absolute, base_url):
            urls.append(absolute)
    return dedupe(urls)


def dedupe(items: Iterable[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
