"""End-to-end orchestration: fetch a site, find its contact page, and pull
out names, phone numbers, business hours and a likely city.

Structured data (schema.org JSON-LD / microdata) is trusted first since the
site is asserting those facts about itself; free-text heuristics fill in
whatever structured data leaves out.
"""
from __future__ import annotations

import time
from typing import List, Optional, Tuple
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from contact_scraper import contact_page_finder, fetcher, structured_data
from contact_scraper.extractors import city as city_extractor
from contact_scraper.extractors import hours as hours_extractor
from contact_scraper.extractors import names as names_extractor
from contact_scraper.extractors import phones as phones_extractor
from contact_scraper.geo_hints import guess_country_from_url
from contact_scraper.models import ContactInfo

DEFAULT_MAX_PAGES = 4
DEFAULT_TIMEOUT = 15
DEFAULT_DELAY = 1.0


def _normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        raise ValueError("empty URL")
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    if not parsed.netloc:
        raise ValueError(f"invalid URL: {url}")
    return url


def _toggle_www(url: str) -> str:
    """example.com <-> www.example.com, keeping scheme/path/query intact."""
    parsed = urlparse(url)
    host = parsed.netloc[4:] if parsed.netloc.lower().startswith("www.") else "www." + parsed.netloc
    return parsed._replace(netloc=host).geturl()


def _visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return soup.get_text("\n", strip=True)


def _dedup_extend(target: List[str], items: List[str]) -> None:
    for item in items:
        if item and item not in target:
            target.append(item)


def _try_candidates(
    candidates: List[str],
    session: requests.Session,
    timeout: int,
    delay: float,
    respect_robots: bool,
    budget: int,
    pages: List[Tuple[str, str]],
    warnings: List[str],
) -> Tuple[Optional[str], int]:
    """Try known candidate URLs (real links found on the homepage) in order,
    stopping at the first that loads."""
    for candidate in candidates:
        if budget <= 0:
            return None, budget
        time.sleep(delay)
        result = fetcher.fetch(candidate, session=session, timeout=timeout, respect_robots=respect_robots)
        budget -= 1
        if result.ok:
            pages.append((result.url, result.html))
            return result.url, budget
        warnings.append(f"no se pudo obtener {candidate}: {result.error}")
    return None, budget


def _try_guesses(
    guess_paths_fn,
    home_url: str,
    session: requests.Session,
    timeout: int,
    delay: float,
    respect_robots: bool,
    budget: int,
    pages: List[Tuple[str, str]],
) -> Tuple[Optional[str], int]:
    """Blindly try common paths, stopping at the first that loads. Lower
    confidence than a real link, so this only runs when the homepage had no
    matching link at all -- see the ordering note in _gather_pages."""
    for guess in guess_paths_fn(home_url):
        if budget <= 0:
            break
        time.sleep(delay)
        result = fetcher.fetch(guess, session=session, timeout=timeout, respect_robots=respect_robots)
        budget -= 1
        if result.ok:
            pages.append((result.url, result.html))
            return result.url, budget
    return None, budget


def _gather_pages(
    url: str,
    session: requests.Session,
    max_pages: int,
    timeout: int,
    delay: float,
    respect_robots: bool,
    warnings: List[str],
) -> Tuple[List[Tuple[str, str]], Optional[str], Optional[str]]:
    """Fetch the homepage plus, within an (max_pages - 1) budget, a contact
    page and an "about us"/team page -- names almost never live on the
    contact page itself, so it gets its own targeted fetch."""
    home = fetcher.fetch(url, session=session, timeout=timeout, respect_robots=respect_robots)
    if not home.ok:
        # Apex vs "www." is a common real-world split: many small sites only
        # have a valid TLS cert / DNS record for one of the two, so a plain
        # failure on one is worth one retry on the other before giving up.
        alt_url = _toggle_www(url)
        alt_home = fetcher.fetch(alt_url, session=session, timeout=timeout, respect_robots=respect_robots)
        if alt_home.ok:
            warnings.append(f"{url} no respondió ({home.error}); se usó {alt_url}")
            home = alt_home
        else:
            warnings.append(f"no se pudo obtener la página principal ({url}): {home.error}")
            return [], None, None

    pages = [(home.url, home.html)]
    budget = max_pages - 1
    if budget <= 0:
        return pages, None, None

    contact_candidates = contact_page_finder.find_contact_links(home.url, home.html, limit=2)
    team_candidates = contact_page_finder.find_team_links(home.url, home.html, limit=1)

    # Real links found on the homepage beat blind path guessing regardless of
    # type: a site with no "Contacto" link but a real "Quiénes somos" link
    # should get its team page fetched before we ever burn budget guessing
    # /contacto paths that may not exist (confirmed on santeclinics.com,
    # which has no contact page at all but does list its team).
    contact_url, budget = _try_candidates(contact_candidates, session, timeout, delay, respect_robots, budget, pages, warnings)
    team_url, budget = _try_candidates(team_candidates, session, timeout, delay, respect_robots, budget, pages, warnings)

    if not contact_candidates:
        warnings.append("no se encontró un enlace de contacto en la página principal; probando rutas comunes")
        contact_url, budget = _try_guesses(contact_page_finder.guess_common_paths, home.url, session, timeout, delay, respect_robots, budget, pages)
    if not team_candidates:
        team_url, budget = _try_guesses(contact_page_finder.guess_team_common_paths, home.url, session, timeout, delay, respect_robots, budget, pages)

    if contact_url is None:
        warnings.append("no se encontró una página de contacto dedicada; se usó solo la página principal")
    if team_url is None:
        warnings.append("no se encontró una página de equipo/sobre nosotros (los nombres solo pueden salir de las páginas ya visitadas)")

    return pages, contact_url, team_url


def scrape(
    url: str,
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
    timeout: int = DEFAULT_TIMEOUT,
    delay: float = DEFAULT_DELAY,
    respect_robots: bool = True,
    use_spacy: bool = False,
) -> ContactInfo:
    """Fetch `url`, locate its contact page, and extract contact details from both."""
    warnings: List[str] = []
    url = _normalize_url(url)

    with requests.Session() as session:
        pages, contact_url, team_url = _gather_pages(url, session, max_pages, timeout, delay, respect_robots, warnings)

    if not pages:
        return ContactInfo(source_url=url, warnings=warnings)

    json_ld_nodes = []
    micro_phones: List[str] = []
    micro_address = {"locality": None, "region": None, "country": None, "raw": None}
    meta_city: Optional[str] = None

    phones: List[str] = []
    names: List[str] = []
    hours_raw: List[str] = []
    address_snippet: Optional[str] = None
    combined_text_parts: List[str] = []

    for page_url, html in pages:
        soup = BeautifulSoup(html, "lxml")
        json_ld_nodes.extend(structured_data.extract_json_ld(soup))

        micro = structured_data.extract_microdata(soup)
        _dedup_extend(micro_phones, micro["phones"])
        if micro["address"]["raw"] and not micro_address["raw"]:
            micro_address = micro["address"]
        if meta_city is None:
            meta_city = structured_data.extract_meta_geo(soup)

        text = _visible_text(html)
        combined_text_parts.append(text)

        _dedup_extend(phones, phones_extractor.extract_phones(text, html=html, source_url=page_url))
        _dedup_extend(names, names_extractor.extract_names(text, use_spacy=use_spacy))
        _dedup_extend(hours_raw, hours_extractor.extract_hours(text))
        if address_snippet is None:
            address_snippet = city_extractor.find_address_snippet(text)

    combined_text = "\n".join(combined_text_parts)
    structured = structured_data.summarize_structured_data(json_ld_nodes)

    # Structured data first: the site is asserting these facts about itself.
    # Run it through the same phonenumbers formatting as the regex path so
    # e.g. JSON-LD's "+57 300 111 2222" and a tel: link's "+573001112222"
    # collapse into one entry instead of two differently-spaced duplicates.
    structured_phones: List[str] = []
    for raw in list(structured["phones"]) + micro_phones:
        formatted = phones_extractor.canonicalize(raw, url)
        if formatted and formatted not in structured_phones:
            structured_phones.append(formatted)
    phones = structured_phones + [p for p in phones if p not in structured_phones]

    # Sites don't always keep their schema.org Person "name" tidy -- some
    # dump the raw display string in there, honorific and decorative emoji
    # included (e.g. "Dr. Ignacio Navarro 🇺🇸 🇪🇸"). Clean it the same way a
    # human reading the page would, so it collapses with the regex-extracted
    # "Ignacio Navarro" instead of appearing twice.
    structured_names: List[str] = []
    for raw in structured["names"]:
        cleaned = names_extractor.clean_person_name(raw)
        if cleaned and cleaned not in structured_names:
            structured_names.append(cleaned)
    names = structured_names + [n for n in names if n not in structured_names]

    hours_raw = structured["hours"] + [h for h in hours_raw if h not in structured["hours"]]

    address = structured["address"] if structured["address"]["raw"] else micro_address
    city = address["locality"] or meta_city
    country = address["country"]
    address_raw = address["raw"] or address_snippet

    if not city:
        preferred_country = country or guess_country_from_url(url) or phones_extractor.guess_region_from_phones(phones)
        guess = city_extractor.guess_city(combined_text, preferred_country=preferred_country, address_snippet=address_snippet)
        if guess:
            city = guess["city"]
            country = country or guess["countrycode"]
            address_raw = address_raw or guess["evidence"]

    if not country:
        country = guess_country_from_url(url) or phones_extractor.guess_region_from_phones(phones)

    if not phones:
        warnings.append("no se encontró ningún número de teléfono")
    if not hours_raw:
        warnings.append("no se encontró un horario de atención")
    if not names:
        warnings.append("no se encontraron nombres de personas (es común: muchas páginas solo listan datos de la empresa)")
    if not city:
        warnings.append("no se pudo determinar una ciudad probable")

    return ContactInfo(
        source_url=url,
        contact_page_url=contact_url,
        team_page_url=team_url,
        names=names,
        phones=phones,
        hours=hours_extractor.best_hours_text(hours_raw),
        hours_raw=hours_raw,
        city=city,
        country=country,
        address_raw=address_raw,
        warnings=warnings,
    )
