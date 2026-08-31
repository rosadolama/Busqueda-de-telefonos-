"""Phone number extraction using Google's libphonenumber (via the `phonenumbers` package).

Regex alone flags far too many false positives (dates, invoice numbers, IDs).
`phonenumbers` validates candidates against real numbering-plan rules, so we
lean on it for both detection and pretty-printing.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional
from urllib.parse import unquote

import phonenumbers
from bs4 import BeautifulSoup

from contact_scraper.geo_hints import DEFAULT_REGION_GUESSES, guess_country_from_url

_TEL_HREF_RE = re.compile(r"^tel:", re.IGNORECASE)

# wa.me/<digits> and api.whatsapp.com/send?phone=<digits> encode the number
# in E.164 digits with no leading "+". Very common on small-business sites
# that only put a WhatsApp click-to-chat button on the page, no tel: link
# or plain-text number at all.
_WHATSAPP_RE = re.compile(r"(?:wa\.me/|whatsapp\.com/send\?phone=)(\d[\d\s\-]{5,})", re.IGNORECASE)


def _from_tel_links(soup: BeautifulSoup) -> List[str]:
    numbers = []
    for a in soup.find_all("a", href=_TEL_HREF_RE):
        raw = unquote(a["href"].split(":", 1)[1])
        raw = raw.split("?")[0].strip()
        numbers.append(raw)
    return numbers


def _from_whatsapp_links(soup: BeautifulSoup) -> List[str]:
    numbers = []
    for a in soup.find_all("a", href=True):
        match = _WHATSAPP_RE.search(unquote(a["href"]))
        if match:
            numbers.append("+" + match.group(1))
    return numbers


def _candidate_regions(source_url: Optional[str]) -> List[Optional[str]]:
    regions: List[Optional[str]] = [None]  # None = only match numbers with an explicit "+"
    guess = guess_country_from_url(source_url) if source_url else None
    if guess:
        regions.append(guess)
    for region in DEFAULT_REGION_GUESSES:
        if region not in regions:
            regions.append(region)
    return regions


def _valid_e164(raw: str, regions: Iterable[Optional[str]]) -> Optional[str]:
    for region in regions:
        try:
            parsed = phonenumbers.parse(raw, region)
        except phonenumbers.NumberParseException:
            continue
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
    return None


def extract_phones(text: str, html: Optional[str] = None, source_url: Optional[str] = None) -> List[str]:
    """Return deduplicated, validated phone numbers formatted in international style."""
    regions = _candidate_regions(source_url)
    found: List[str] = []

    if html:
        soup = BeautifulSoup(html, "lxml")
        for raw in _from_tel_links(soup) + _from_whatsapp_links(soup):
            formatted = _valid_e164(raw, regions)
            if formatted and formatted not in found:
                found.append(formatted)

    # Try every candidate region rather than stopping at the first hit: a page
    # can legitimately list both an international "+" number and a second,
    # locally-formatted one that only resolves under the guessed region.
    # A single digit span (e.g. "(601) 234-5678") can parse as *different*,
    # equally "valid" numbers depending on the region tried, so once a span
    # has been claimed by a higher-priority region we skip it for the rest
    # instead of reporting several conflicting readings of the same text.
    claimed_spans: List[tuple] = []
    for region in regions:
        try:
            matcher = phonenumbers.PhoneNumberMatcher(text, region or "ZZ")
        except Exception:
            continue
        for match in matcher:
            if not phonenumbers.is_valid_number(match.number):
                continue
            span = (match.start, match.start + len(match.raw_string))
            if any(span[0] < end and start < span[1] for start, end in claimed_spans):
                continue
            claimed_spans.append(span)
            formatted = phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
            if formatted not in found:
                found.append(formatted)

    return found


def canonicalize(raw: str, source_url: Optional[str] = None) -> Optional[str]:
    """Validate and reformat a phone string from any source (JSON-LD, microdata, tel: link)
    into the same international format `extract_phones` produces, so duplicates from
    different sources collapse into one entry instead of two differently-spaced strings."""
    return _valid_e164(raw, _candidate_regions(source_url))


def guess_region_from_phones(phones: Iterable[str]) -> Optional[str]:
    """Infer a 2-letter region (e.g. "CO") from already-formatted (+CC ...) numbers."""
    for raw in phones:
        try:
            parsed = phonenumbers.parse(raw, None)
        except phonenumbers.NumberParseException:
            continue
        region = phonenumbers.region_code_for_number(parsed)
        if region and region != "ZZ":
            return region
    return None
