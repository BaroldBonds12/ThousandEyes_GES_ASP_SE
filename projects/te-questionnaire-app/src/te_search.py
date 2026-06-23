"""
ThousandEyes Doc Searcher — fetches real, published pages from
docs.thousandeyes.com and returns cleaned text suitable for LLM context.

URL quality rules
─────────────────
• Only docs.thousandeyes.com content pages are accepted (_is_content_url).
• Navigation, search-result, tag, and root pages are excluded.
• ddgs (metasearch) site: lookup is the primary source; the TE docs search API is
  the fallback.  Both are filtered through _is_content_url before fetching.
"""

from __future__ import annotations

import re
import threading
import time
from typing import Optional
from urllib.parse import urlparse, quote_plus

import requests
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ALLOWED_DOMAINS = frozenset(["docs.thousandeyes.com"])

MAX_CHARS_PER_PAGE  = 5_500   # chars per page fed to the LLM
MAX_PAGES_DEFAULT   = 5       # pages fetched per question
REQUEST_TIMEOUT     = 14      # seconds
INTER_REQUEST_DELAY = 0.3     # polite crawling delay between fetches

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Selectors tried in order to isolate the main body of TE docs pages
_CONTENT_SELECTORS = [
    "article",
    "main",
    ".md-content",
    ".content",
    "#content",
    ".doc-content",
    ".article-content",
    "[role='main']",
]

_STRIP_TAGS = ["script", "style", "nav", "header", "footer", "aside",
               "noscript", ".md-sidebar", ".md-header"]

# ---------------------------------------------------------------------------
# Content-URL filter
# ---------------------------------------------------------------------------
# Known path prefixes that host real documentation content.
# Anything NOT starting with one of these is treated as navigation / chrome.
_CONTENT_PREFIXES = (
    "/product-documentation/",
    "/thousandeyes-basics/",
    "/release-notes/",
    "/api-reference/",
    "/endpoint-agent/",
    "/internet-and-wan-monitoring/",
    "/tests/",
    "/alerts/",
    "/dashboards/",
    "/reports/",
    "/device-layer/",
    "/sharing/",
    "/user-management/",
    "/account-settings/",
    "/integration/",
    "/administrative/",
    "/advanced-troubleshooting/",
    "/migration/",
)

# Paths that are definitively NOT content pages
_NON_CONTENT_FRAGMENTS = ("/search", "/tag/", "/tags/", "/category/",
                          "/page/", "/sitemap", "/#", "/404",
                          "/login", "/register", "/user/")


def _is_content_url(url: str) -> bool:
    """
    Return True only for real ThousandEyes documentation content pages.

    Rejects:  search result pages, tag/category indexes, home page,
              navigation anchors, and anything outside ALLOWED_DOMAINS.
    """
    try:
        parsed = urlparse(url)
        host   = parsed.netloc.lower().lstrip("www.")
        if host not in ALLOWED_DOMAINS:
            return False

        path = parsed.path.rstrip("/")
        if not path or path in ("/", ""):
            return False

        # Explicitly exclude non-content paths
        for frag in _NON_CONTENT_FRAGMENTS:
            if path.startswith(frag) or path == frag.rstrip("/"):
                return False

        # Must start with a known content prefix OR have ≥ 2 meaningful path
        # segments (handles docs.thousandeyes.com/<section>/<article>).
        parts = [p for p in path.split("/") if p]
        starts_with_prefix = any(path.startswith(p) for p in _CONTENT_PREFIXES)
        return starts_with_prefix or len(parts) >= 2

    except Exception:
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class TESearcher:
    """Search ThousandEyes documentation and return page text for LLM context."""

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)
        self._page_cache: dict[str, str] = {}
        self._cache_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Primary: search + fetch full page content for LLM context
    # ------------------------------------------------------------------

    def search_and_fetch(self, question: str,
                         max_pages: int = MAX_PAGES_DEFAULT) -> str:
        """
        Find the most relevant docs.thousandeyes.com pages for *question*
        and return their cleaned text joined with separators.

        Only real content pages (not search or nav pages) are fetched.
        """
        urls = self._collect_content_urls(question)

        context_parts: list[str] = []
        fetched = 0
        for url in urls:
            if fetched >= max_pages:
                break
            content = self._fetch_page(url)
            if content:
                context_parts.append(f"[Source: {url}]\n{content}")
                fetched += 1
                time.sleep(INTER_REQUEST_DELAY)

        return "\n\n---\n\n".join(context_parts)

    # ------------------------------------------------------------------
    # Fast URL-only lookup (no page fetching) — used for cache enrichment
    # ------------------------------------------------------------------

    def get_source_url(self, question: str) -> Optional[str]:
        """
        Return just the first real docs.thousandeyes.com content URL for
        *question*, without fetching any page content.

        Called by processor.py for cached answers that are missing a URL.
        """
        try:
            urls = self._collect_content_urls(question, limit=6)
            return urls[0] if urls else None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Internal URL collection
    # ------------------------------------------------------------------

    def _collect_content_urls(self, question: str,
                               limit: int = 20) -> list[str]:
        """
        Collect and deduplicate real content page URLs for *question*.
        DuckDuckGo is tried first; the TE docs search API is the fallback.
        All URLs are filtered through _is_content_url().
        """
        raw: list[str] = []

        # Strategy 1 — DuckDuckGo site:docs.thousandeyes.com search
        try:
            raw.extend(self._ddg_search(question))
        except Exception:
            pass

        # Strategy 2 — ThousandEyes docs built-in search API (fallback /
        # supplement when DDG returns few results)
        if len([u for u in raw if _is_content_url(u)]) < 3:
            try:
                raw.extend(self._te_docs_api_search(question))
            except Exception:
                pass

        # Deduplicate, filter, and cap
        seen: set[str] = set()
        unique: list[str] = []
        for url in raw:
            norm = url.rstrip("/").split("?")[0]   # ignore query strings
            if norm not in seen and _is_content_url(url):
                seen.add(norm)
                unique.append(url.rstrip("/"))
                if len(unique) >= limit:
                    break

        return unique

    def _ddg_search(self, query: str) -> list[str]:
        """Metasearch (ddgs) site:docs.thousandeyes.com lookup (no API key)."""
        from ddgs import DDGS

        te_query = f"site:docs.thousandeyes.com {query}"
        urls: list[str] = []
        try:
            results = DDGS().text(te_query, max_results=8, backend="duckduckgo")
            for result in results or []:
                href = result.get("href", "")
                if href:
                    urls.append(href)
        except Exception:
            pass
        return urls

    def _te_docs_api_search(self, query: str) -> list[str]:
        """
        Hit the docs.thousandeyes.com MkDocs search JSON endpoint.

        MkDocs sites expose /search/search_index.json and a lightweight
        search endpoint.  We try the JSON API first and fall back to
        scraping result links from the HTML search page.
        """
        urls: list[str] = []

        # ── Try the MkDocs search index JSON ────────────────────────────
        # (not all TE docs versions expose it, but when present it's fast)
        try:
            resp = self._session.get(
                "https://docs.thousandeyes.com/search/search_index.json",
                timeout=8,
            )
            if resp.status_code == 200:
                data = resp.json()
                q_lower = query.lower()
                scored: list[tuple[int, str]] = []
                for doc in data.get("docs", []):
                    loc   = doc.get("location", "")
                    title = (doc.get("title", "") + " " + doc.get("text", "")).lower()
                    hits  = sum(1 for word in q_lower.split() if word in title)
                    if hits and loc and not loc.startswith("search"):
                        full = (
                            f"https://docs.thousandeyes.com/{loc.lstrip('/')}"
                        )
                        scored.append((hits, full))
                scored.sort(key=lambda x: x[0], reverse=True)
                urls.extend(u for _, u in scored[:10])
        except Exception:
            pass

        # ── Fallback: scrape HTML search results page ────────────────────
        if len([u for u in urls if _is_content_url(u)]) < 3:
            try:
                encoded = quote_plus(query[:120])
                resp = self._session.get(
                    f"https://docs.thousandeyes.com/search?q={encoded}",
                    timeout=REQUEST_TIMEOUT,
                )
                soup = BeautifulSoup(resp.text, "lxml")

                # MkDocs search results are typically inside <article> or
                # elements with class "md-search-result__item" or similar.
                # We look for anchors with /product-documentation/… paths.
                for tag in soup.find_all("a", href=True):
                    href: str = tag["href"]
                    if href.startswith("/"):
                        href = f"https://docs.thousandeyes.com{href}"
                    if _is_content_url(href) and href not in urls:
                        urls.append(href)
            except Exception:
                pass

        return urls

    # ------------------------------------------------------------------
    # Page fetching
    # ------------------------------------------------------------------

    def _fetch_page(self, url: str) -> Optional[str]:
        """Fetch a single URL and return cleaned main-content text."""
        with self._cache_lock:
            if url in self._page_cache:
                return self._page_cache[url]

        try:
            resp = self._session.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                return None

            soup = BeautifulSoup(resp.text, "lxml")

            # Strip navigation chrome
            for tag in soup(_STRIP_TAGS):
                tag.decompose()

            # Isolate main content
            content_elem = None
            for selector in _CONTENT_SELECTORS:
                content_elem = soup.select_one(selector)
                if content_elem:
                    break

            raw   = (content_elem or soup).get_text(separator="\n", strip=True)
            lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
            text  = "\n".join(lines)

            if len(text) > MAX_CHARS_PER_PAGE:
                text = text[:MAX_CHARS_PER_PAGE] + "\n[…content truncated…]"

            with self._cache_lock:
                self._page_cache[url] = text
            return text

        except Exception:
            return None

    # ------------------------------------------------------------------
    # Legacy alias kept for any code that calls _is_allowed directly
    # ------------------------------------------------------------------

    @staticmethod
    def _is_allowed(url: str) -> bool:
        return _is_content_url(url)
