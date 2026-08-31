"""Shared helpers for guessing a site's country from its URL."""
from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse

# ccTLD -> ISO 3166-1 alpha-2, limited to Spanish/Portuguese-speaking countries
# plus a few common defaults. Used only as a prior to disambiguate phone
# numbers and city names, never as a hard filter.
TLD_TO_COUNTRY = {
    "es": "ES", "mx": "MX", "co": "CO", "ar": "AR", "pe": "PE", "cl": "CL",
    "ec": "EC", "ve": "VE", "gt": "GT", "bo": "BO", "py": "PY", "uy": "UY",
    "cr": "CR", "pa": "PA", "hn": "HN", "sv": "SV", "ni": "NI", "do": "DO",
    "pr": "PR", "cu": "CU", "us": "US", "br": "BR", "pt": "PT",
}

# Reasonable fallback order when a .com/.net/.org domain gives no hint.
DEFAULT_REGION_GUESSES = ["MX", "CO", "ES", "AR", "PE", "CL", "EC", "US"]


def guess_country_from_url(url: str) -> Optional[str]:
    host = urlparse(url).netloc.lower().split(":")[0]
    parts = host.split(".")
    if len(parts) >= 2:
        # Covers both plain ccTLDs (example.co) and second-level ones
        # like example.com.co / example.com.mx.
        tld = parts[-1]
        if tld in TLD_TO_COUNTRY:
            return TLD_TO_COUNTRY[tld]
    return None
