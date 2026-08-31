"""Polite HTTP fetching: sane headers, size caps, timeouts and robots.txt checks."""
from __future__ import annotations

import urllib.robotparser
from dataclasses import dataclass
from typing import Dict, Optional
from urllib.parse import urlparse

import requests

USER_AGENT = (
    "ContactScraperBot/1.0 (+https://github.com/rosadolama/Busqueda-de-telefonos-; "
    "extracts publicly listed contact info, respects robots.txt)"
)

MAX_BYTES = 5 * 1024 * 1024  # 5 MB safety cap per page
DEFAULT_TIMEOUT = 15

_robots_cache: Dict[str, urllib.robotparser.RobotFileParser] = {}


@dataclass
class FetchResult:
    url: str
    status_code: Optional[int]
    html: Optional[str]
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.html is not None


def _robots_for(base_url: str, timeout: int) -> urllib.robotparser.RobotFileParser:
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if origin in _robots_cache:
        return _robots_cache[origin]

    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(origin + "/robots.txt")
    try:
        resp = requests.get(
            origin + "/robots.txt",
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
        )
        if resp.status_code == 200:
            rp.parse(resp.text.splitlines())
        else:
            # No robots.txt (or an error fetching it) means no restrictions declared.
            rp.parse([])
    except requests.RequestException:
        rp.parse([])

    _robots_cache[origin] = rp
    return rp


def is_allowed(url: str, timeout: int = DEFAULT_TIMEOUT) -> bool:
    """Check robots.txt for the given URL. Fails open (allowed) if robots.txt is unreachable."""
    try:
        rp = _robots_for(url, timeout)
        return rp.can_fetch(USER_AGENT, url)
    except Exception:
        return True


def fetch(
    url: str,
    session: Optional[requests.Session] = None,
    timeout: int = DEFAULT_TIMEOUT,
    respect_robots: bool = True,
) -> FetchResult:
    """Fetch a URL, returning HTML text on success or an error message on failure.

    Only http/https schemes are fetched. Response bodies are capped at MAX_BYTES
    and non-HTML content types are rejected to avoid downloading large binaries.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return FetchResult(url=url, status_code=None, html=None, error="unsupported scheme")

    if respect_robots and not is_allowed(url, timeout=timeout):
        return FetchResult(url=url, status_code=None, html=None, error="disallowed by robots.txt")

    http = session or requests.Session()
    try:
        resp = http.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "es,en;q=0.8"},
            timeout=timeout,
            stream=True,
        )
    except requests.RequestException as exc:
        return FetchResult(url=url, status_code=None, html=None, error=str(exc))

    with resp:
        content_type = resp.headers.get("Content-Type", "")
        if resp.status_code != 200:
            return FetchResult(url=url, status_code=resp.status_code, html=None, error=f"HTTP {resp.status_code}")
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            return FetchResult(url=url, status_code=resp.status_code, html=None, error=f"non-HTML content-type: {content_type or 'unknown'}")

        chunks = []
        total = 0
        for chunk in resp.iter_content(chunk_size=65536):
            total += len(chunk)
            if total > MAX_BYTES:
                return FetchResult(url=url, status_code=resp.status_code, html=None, error="response too large")
            chunks.append(chunk)

        raw = b"".join(chunks)
        encoding = resp.encoding or "utf-8"
        try:
            html = raw.decode(encoding, errors="replace")
        except (LookupError, TypeError):
            html = raw.decode("utf-8", errors="replace")

        return FetchResult(url=resp.url, status_code=resp.status_code, html=html)
