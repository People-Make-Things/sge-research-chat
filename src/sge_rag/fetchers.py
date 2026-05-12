from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional, Protocol

import httpx

from .config import Settings
from .errors import SourceAccessError


class Fetcher(Protocol):
    async def __aenter__(self) -> "Fetcher":
        ...

    async def __aexit__(self, exc_type, exc, tb) -> None:
        ...

    async def fetch_text(self, url: str) -> str:
        ...


def is_security_checkpoint(text: str) -> bool:
    checkpoints = (
        "Vercel Security Checkpoint",
        "We're verifying your browser",
        "Enable JavaScript to continue",
    )
    return any(marker in text for marker in checkpoints)


class HttpFetcher:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "HttpFetcher":
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
        }
        self.client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=self.settings.request_timeout_seconds,
            headers=headers,
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self.client:
            await self.client.aclose()

    async def fetch_text(self, url: str) -> str:
        if not self.client:
            raise RuntimeError("HttpFetcher must be used as an async context manager.")
        response = await self.client.get(url)
        text = response.text
        if response.status_code == 403 or is_security_checkpoint(text):
            raise SourceAccessError(
                "HTTP fetch could not access %s. Run `sge-rag login` and retry "
                "with `--fetcher browser`." % url
            )
        response.raise_for_status()
        if is_security_checkpoint(text):
            raise SourceAccessError(
                "HTTP fetch hit the Vercel security checkpoint. Run `sge-rag login` "
                "and retry with `--fetcher browser`."
            )
        return text


class BrowserFetcher:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    async def __aenter__(self) -> "BrowserFetcher":
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise SourceAccessError(
                "Playwright is not installed. Run `pip install -e .` and "
                "`python -m playwright install chromium`."
            ) from exc

        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.settings.browser_headless)
        context_kwargs = {}
        if self.settings.browser_state_path.exists():
            context_kwargs["storage_state"] = str(self.settings.browser_state_path)
        self.context = await self.browser.new_context(**context_kwargs)
        self.page = await self.context.new_page()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def fetch_text(self, url: str) -> str:
        if not self.context or not self.page:
            raise RuntimeError("BrowserFetcher must be used as an async context manager.")
        try:
            request_response = await self.context.request.get(
                url,
                timeout=int(self.settings.request_timeout_seconds * 1000),
            )
            request_text = await request_response.text()
            if request_response.status < 400 and not is_security_checkpoint(request_text):
                return request_text
        except Exception:
            pass

        try:
            response = await self.page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=int(self.settings.request_timeout_seconds * 1000),
            )
        except Exception as exc:
            raise SourceAccessError(
                "Browser fetch timed out or failed for %s. If this keeps happening, "
                "rerun `sge-rag login` and keep the page fully loaded before pressing Enter."
                % url
            ) from exc
        try:
            await self.page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        if response and response.status >= 400:
            raise SourceAccessError("Browser fetch failed for %s with HTTP %s" % (url, response.status))
        content_type = response.headers.get("content-type", "") if response else ""
        if (
            url.endswith(".json")
            or url.endswith(".xml")
            or "/_next/data/" in url
            or "application/json" in content_type
            or "xml" in content_type
        ):
            if response:
                text = await response.text()
            else:
                text = await self.page.locator("body").inner_text(timeout=5000)
        else:
            text = await self.page.content()
        if is_security_checkpoint(text):
            raise SourceAccessError(
                "Browser fetch is still at the security checkpoint. Run `sge-rag login` "
                "again and make sure the saved session can access the site."
            )
        return text


class AutoFetcher:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.active: Optional[Fetcher] = None

    async def __aenter__(self) -> "AutoFetcher":
        if self.settings.browser_state_path.exists():
            self.active = BrowserFetcher(self.settings)
        else:
            self.active = HttpFetcher(self.settings)
        await self.active.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self.active:
            await self.active.__aexit__(exc_type, exc, tb)

    async def fetch_text(self, url: str) -> str:
        if not self.active:
            raise RuntimeError("AutoFetcher must be used as an async context manager.")
        try:
            return await self.active.fetch_text(url)
        except SourceAccessError:
            if isinstance(self.active, BrowserFetcher) or not self.settings.browser_state_path.exists():
                raise
            await self.active.__aexit__(None, None, None)
            self.active = BrowserFetcher(self.settings)
            await self.active.__aenter__()
            return await self.active.fetch_text(url)


def make_fetcher(settings: Settings, kind: Optional[str] = None) -> Fetcher:
    fetcher_kind = kind or settings.fetcher
    if fetcher_kind == "http":
        return HttpFetcher(settings)
    if fetcher_kind == "browser":
        return BrowserFetcher(settings)
    if fetcher_kind == "auto":
        return AutoFetcher(settings)
    raise ValueError("Unsupported fetcher kind: %s" % fetcher_kind)


async def save_browser_login_state(
    login_url: str,
    state_path: Path,
    headless: bool = False,
) -> None:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise SourceAccessError(
            "Playwright is not installed. Run `pip install -e .` and "
            "`python -m playwright install chromium`."
        ) from exc

    state_path.parent.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(login_url, wait_until="domcontentloaded")
        await asyncio.to_thread(input, "Complete login in the browser, then press Enter here...")
        await context.storage_state(path=str(state_path))
        await browser.close()
