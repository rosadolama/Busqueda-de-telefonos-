"""Best-effort city detection ("posible ciudad") from page text.

Structured data (schema.org addressLocality, handled in structured_data.py)
is authoritative when present -- the site is telling us its own city. This
module is the fallback: it matches words/phrases in the page text against a
gazetteer of real-world cities (geonamescache, offline, no API calls) and
picks the most plausible one using population and a country guess as tie
breakers. It is inherently a guess, never a certainty, which is why the
scraper always calls this field "possible".
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import geonamescache

_ADDRESS_LABEL_RE = re.compile(
    r"(?:direcci[oó]n|ubicaci[oó]n|ubicados?\s+en|nos\s+encontramos\s+en|sucursal(?:es)?\s+en|oficinas?\s+en)"
    r"\s*[:\-]?\s*([^\n]{5,120})",
    re.IGNORECASE,
)

_LATIN_ONLY_RE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ' .-]+$")

# Below this population, a bare match anywhere in the page is too noisy to
# trust; short/common-word city names in particular need a stronger signal
# (an address label, or agreement with the guessed country) to count.
_MIN_POPULATION_BARE_MATCH = 200_000
_MIN_NAME_LEN_BARE_MATCH = 5


@dataclass
class _CityRecord:
    name: str
    countrycode: str
    population: int


_lookup_cache: Optional[Dict[str, List[_CityRecord]]] = None


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def _normalize_key(value: str) -> str:
    return _strip_accents(value).lower().strip()


def _build_lookup() -> Dict[str, List[_CityRecord]]:
    gc = geonamescache.GeonamesCache()
    lookup: Dict[str, List[_CityRecord]] = {}

    def add(name: str, countrycode: str, population: int) -> None:
        if len(name) < 3 or not _LATIN_ONLY_RE.match(name):
            return
        key = _normalize_key(name)
        record = _CityRecord(name=name, countrycode=countrycode, population=population)
        lookup.setdefault(key, []).append(record)

    for city in gc.get_cities().values():
        add(city["name"], city["countrycode"], city["population"])
        for alt in city.get("alternatenames", []):
            add(alt, city["countrycode"], city["population"])

    return lookup


def _lookup() -> Dict[str, List[_CityRecord]]:
    global _lookup_cache
    if _lookup_cache is None:
        _lookup_cache = _build_lookup()
    return _lookup_cache


def _candidate_ngrams(text: str) -> List[Tuple[str, str, int]]:
    """Return (normalized_ngram, original_ngram, start_offset) for 1-3 word windows."""
    word_matches = list(re.finditer(r"[A-Za-zÀ-ÖØ-öø-ÿ]+(?:['.][A-Za-zÀ-ÖØ-öø-ÿ]+)*", text))
    ngrams = []
    for size in (3, 2, 1):
        for i in range(len(word_matches) - size + 1):
            chunk = word_matches[i : i + size]
            words = [m.group(0) for m in chunk]
            # Skip windows that are just lowercase filler words (real city
            # names are written capitalized almost everywhere on the web).
            if not any(w[:1].isupper() for w in words):
                continue
            original = " ".join(words)
            ngrams.append((_normalize_key(original), original, chunk[0].start()))
    return ngrams


def _best_record(records: List[_CityRecord], preferred_country: Optional[str]) -> _CityRecord:
    def score(r: _CityRecord) -> tuple:
        return (1 if preferred_country and r.countrycode == preferred_country else 0, r.population)

    return max(records, key=score)


def find_address_snippet(text: str) -> Optional[str]:
    m = _ADDRESS_LABEL_RE.search(text)
    if m:
        return m.group(1).strip(" .,;:-–—")
    return None


def guess_city(
    text: str,
    preferred_country: Optional[str] = None,
    address_snippet: Optional[str] = None,
) -> Optional[Dict[str, object]]:
    """Return {"city", "countrycode", "population", "evidence"} for the best guess, or None."""
    lookup = _lookup()

    def scan(source: str, in_address: bool) -> List[Tuple[_CityRecord, bool, str, int]]:
        hits = []
        for norm, original, offset in _candidate_ngrams(source):
            records = lookup.get(norm)
            if not records:
                continue
            rec = _best_record(records, preferred_country)
            strong_enough = (
                in_address
                or (preferred_country and rec.countrycode == preferred_country)
                or (rec.population >= _MIN_POPULATION_BARE_MATCH and len(original) >= _MIN_NAME_LEN_BARE_MATCH)
            )
            if strong_enough:
                hits.append((rec, in_address, original, offset))
        return hits

    candidates: List[Tuple[_CityRecord, bool, str, int]] = []
    if address_snippet:
        candidates.extend(scan(address_snippet, in_address=True))
    candidates.extend(scan(text, in_address=False))

    if not candidates:
        return None

    def rank(item: Tuple[_CityRecord, bool, str, int]) -> tuple:
        rec, in_address, _, offset = item
        matches_country = bool(preferred_country and rec.countrycode == preferred_country)
        # Earlier mentions tend to be the primary/HQ address; population only
        # breaks ties once position and country agreement are accounted for.
        return (in_address, matches_country, -offset, rec.population)

    best_rec, in_address, evidence, _offset = max(candidates, key=rank)
    return {
        "city": best_rec.name,
        "countrycode": best_rec.countrycode,
        "population": best_rec.population,
        "evidence": evidence,
        "from_address_line": in_address,
    }
