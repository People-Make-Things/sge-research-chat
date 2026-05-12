from sge_rag.discovery import (
    article_json_url,
    is_article_url,
    parse_build_id,
    parse_sitemap_index,
    parse_sitemap_urls,
)


def test_parse_build_id_from_next_data():
    html = '<script id="__NEXT_DATA__" type="application/json">{"buildId":"abc123"}</script>'
    assert parse_build_id(html) == "abc123"


def test_parse_sitemap_index():
    xml = """<?xml version="1.0"?>
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap><loc>https://www.socialgrowthengineers.com/sitemap-1.xml</loc></sitemap>
    </sitemapindex>
    """
    assert parse_sitemap_index(xml) == ["https://www.socialgrowthengineers.com/sitemap-1.xml"]


def test_parse_sitemap_urls():
    xml = """<?xml version="1.0"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://www.socialgrowthengineers.com/a-real-article</loc></url>
      <url><loc>https://www.socialgrowthengineers.com/apps</loc></url>
    </urlset>
    """
    assert parse_sitemap_urls(xml) == [
        "https://www.socialgrowthengineers.com/a-real-article",
        "https://www.socialgrowthengineers.com/apps",
    ]


def test_is_article_url_filters_utility_pages():
    base = "https://www.socialgrowthengineers.com"
    assert is_article_url("https://www.socialgrowthengineers.com/a-real-article", base)
    assert not is_article_url("https://www.socialgrowthengineers.com/apps", base)
    assert not is_article_url("https://www.socialgrowthengineers.com/category/strategy", base)
    assert not is_article_url("https://other.example.com/a-real-article", base)


def test_article_json_url():
    assert article_json_url("https://www.socialgrowthengineers.com", "build", "slug") == (
        "https://www.socialgrowthengineers.com/_next/data/build/slug.json?slug=slug"
    )

