"""Locate the contact page linked from a site's homepage.

Many small-business sites put everything (phone, hours, address) in the
homepage footer, but when there's a dedicated "Contacto" page it is usually
more complete and more reliable, so the scraper looks for one and, when
found, reads both.
"""
from __future__ import annotations

import unicodedata
from typing import List, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

_KEYWORDS = [
    "contactenos", "contactanos", "contáctanos", "contáctenos",
    "contact us", "contact-us", "contact_us", "contacto", "contact",
    "escribenos", "escríbenos", "escribanos", "atencion al cliente",
    "atención al cliente", "ponte en contacto", "hablemos",
]

# Tried only when no contact-like link is found anywhere on the homepage.
_COMMON_PATHS = [
    "/contacto", "/contacto.html", "/contactenos", "/contactanos",
    "/contact", "/contact-us", "/contact.html", "/es/contacto",
    "/pages/contacto", "/nosotros/contacto",
]


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    return value.lower().strip()


def _score(text: str, href: str) -> int:
    norm_text = _normalize(text)
    norm_href = _normalize(href).replace("-", "").replace("_", "")
    score = 0
    for kw in _KEYWORDS:
        kw_norm = _normalize(kw)
        if kw_norm in norm_text:
            score += 3
        if kw_norm.replace(" ", "") in norm_href:
            score += 2
    return score


def find_contact_links(base_url: str, html: str, limit: int = 2) -> List[str]:
    """Return up to `limit` absolute, same-site URLs that look like contact pages, best first."""
    soup = BeautifulSoup(html, "lxml")
    base_netloc = urlparse(base_url).netloc
    scored: List[Tuple[int, str]] = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#") or href.lower().startswith(("mailto:", "tel:", "javascript:")):
            continue
        text = a.get_text(" ", strip=True)
        score = _score(text, href)
        if score <= 0:
            continue

        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https") or parsed.netloc != base_netloc:
            continue  # skip off-site links (e.g. a social-media "contact us")
        if absolute in seen:
            continue

        seen.add(absolute)
        scored.append((score, absolute))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [url for _, url in scored[:limit]]


def guess_common_paths(base_url: str) -> List[str]:
    """Common contact-page paths to try when the homepage has no matching link."""
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return [origin + path for path in _COMMON_PATHS]
