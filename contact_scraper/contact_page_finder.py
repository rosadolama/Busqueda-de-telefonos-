"""Locate the contact page -- and the "about us"/team page -- linked from a
site's homepage.

Many small-business sites put everything (phone, hours, address) in the
homepage footer, but when there's a dedicated "Contacto" page it is usually
more complete and more reliable, so the scraper looks for one and, when
found, reads both. Separately, staff/person names are rarely on the contact
page at all -- they live on "Sobre Nosotros" / "Quiénes somos" / "Equipo"
pages instead, so that gets its own keyword-scored search using the same
logic.
"""
from __future__ import annotations

import unicodedata
from typing import List, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

_CONTACT_KEYWORDS = [
    "contactenos", "contactanos", "contáctanos", "contáctenos",
    "contact us", "contact-us", "contact_us", "contacto", "contact",
    "escribenos", "escríbenos", "escribanos", "atencion al cliente",
    "atención al cliente", "ponte en contacto", "hablemos",
]

_TEAM_KEYWORDS = [
    "sobre nosotros", "quienes somos", "quiénes somos", "nuestro equipo",
    "conoce a nuestro equipo", "conoce al equipo", "conoce nuestro equipo",
    "nuestros profesionales", "nuestros especialistas", "equipo médico",
    "equipo medico", "nosotros", "equipo", "about us", "about-us",
    "who we are", "our team", "meet the team", "team",
]

# Tried only when no matching link is found anywhere on the homepage.
_CONTACT_COMMON_PATHS = [
    "/contacto", "/contacto.html", "/contactenos", "/contactanos",
    "/contact", "/contact-us", "/contact.html", "/es/contacto",
    "/pages/contacto", "/nosotros/contacto",
]

_TEAM_COMMON_PATHS = [
    "/nosotros", "/sobre-nosotros", "/quienes-somos", "/equipo",
    "/nuestro-equipo", "/about", "/about-us", "/team", "/es/about-us",
    "/es/nosotros", "/nosotros/equipo",
]


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    return value.lower().strip()


def _score(text: str, href: str, keywords: List[str]) -> int:
    norm_text = _normalize(text)
    norm_href = _normalize(href).replace("-", "").replace("_", "")
    score = 0
    for kw in keywords:
        kw_norm = _normalize(kw)
        if kw_norm in norm_text:
            score += 3
        if kw_norm.replace(" ", "") in norm_href:
            score += 2
    return score


def _find_links(base_url: str, html: str, keywords: List[str], limit: int) -> List[str]:
    """Return up to `limit` absolute, same-site URLs whose link text/href match
    `keywords`, best first."""
    soup = BeautifulSoup(html, "lxml")
    base_netloc = urlparse(base_url).netloc
    scored: List[Tuple[int, str]] = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#") or href.lower().startswith(("mailto:", "tel:", "javascript:")):
            continue
        text = a.get_text(" ", strip=True)
        score = _score(text, href, keywords)
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


def find_contact_links(base_url: str, html: str, limit: int = 2) -> List[str]:
    """Return up to `limit` absolute, same-site URLs that look like contact pages, best first."""
    return _find_links(base_url, html, _CONTACT_KEYWORDS, limit)


def find_team_links(base_url: str, html: str, limit: int = 1) -> List[str]:
    """Return up to `limit` absolute, same-site URLs that look like an "about us"/team page."""
    return _find_links(base_url, html, _TEAM_KEYWORDS, limit)


def guess_common_paths(base_url: str) -> List[str]:
    """Common contact-page paths to try when the homepage has no matching link."""
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return [origin + path for path in _CONTACT_COMMON_PATHS]


def guess_team_common_paths(base_url: str) -> List[str]:
    """Common "about us"/team page paths to try when the homepage has no matching link."""
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return [origin + path for path in _TEAM_COMMON_PATHS]
