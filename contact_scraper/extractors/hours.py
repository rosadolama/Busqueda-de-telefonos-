"""Business-hours ("horario de atención") detection from free-flowing text.

Structured data (schema.org openingHours, handled in structured_data.py) is
far more reliable when present; this module is the fallback for the very
common case where a site just writes its hours out in prose, e.g.
"Lunes a Viernes de 8:00 a 18:00".
"""
from __future__ import annotations

import re
from typing import List, Optional

_DAY_WORDS = (
    r"lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bados?|domingos?"
    r"|lun\.?|mar\.?|mi[eé]\.?|jue\.?|vie\.?|s[aá]b\.?|dom\.?"
    r"|todos los d[ií]as|diariamente|d[ií]as h[aá]biles"
)
# "(?!\w)" stops a bare "h" from gluing onto the next word, e.g. the
# "h" in "5 hijos" is not the hour-suffix "h" in "11h" / "20H".
_TIME = r"\d{1,2}(?::\d{2})?\s?(?:h(?:rs?|oras?)?(?!\w)\.?|[ap]\.?\s?m\.?)?"
_RANGE_SEP = r"(?:a|hasta|-|–|—)"
_TIME_RANGE = rf"{_TIME}\s*{_RANGE_SEP}\s*{_TIME}"

# A "hours line": one or more day mentions (optionally joined by commas/"y"/ranges
# like "Lunes a Viernes"), followed somewhere after by a time range.
_HOURS_LINE_RE = re.compile(
    rf"(?:{_DAY_WORDS})"
    rf"(?:\s*(?:,|y|{_RANGE_SEP})\s*(?:{_DAY_WORDS}))*"
    rf"[^.;\n]{{0,25}}?"
    rf"({_TIME_RANGE})",
    re.IGNORECASE,
)

_KEYWORD_RE = re.compile(r"horarios?(?:\s+de\s+atenci[oó]n)?|atendemos|horas?\s+de\s+atenci[oó]n", re.IGNORECASE)
_DAY_ONLY_RE = re.compile(_DAY_WORDS, re.IGNORECASE)
_TIME_ONLY_RE = re.compile(_TIME_RANGE, re.IGNORECASE)


def extract_hours(text: str) -> List[str]:
    """Return raw snippets of text that look like opening-hours statements."""
    text = re.sub(r"[ \t]+", " ", text)
    candidates: List[str] = []

    for match in _HOURS_LINE_RE.finditer(text):
        snippet = re.sub(r"\s+", " ", match.group(0)).strip(" .,;:-–—")
        if snippet and snippet not in candidates:
            candidates.append(snippet)

    if not candidates:
        # Looser pass: grab a window around an explicit "horario" keyword and
        # keep it only if it also contains a day name or a time range.
        for m in _KEYWORD_RE.finditer(text):
            start = max(0, m.start() - 10)
            end = min(len(text), m.end() + 150)
            snippet = re.sub(r"\s+", " ", text[start:end]).strip(" .,;:-–—")
            if _DAY_ONLY_RE.search(snippet) or _TIME_ONLY_RE.search(snippet):
                if snippet not in candidates:
                    candidates.append(snippet)

    return candidates[:5]


def best_hours_text(snippets: List[str]) -> Optional[str]:
    return snippets[0] if snippets else None
