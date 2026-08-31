"""Reading the list of URLs to scrape, from a plain text file or a CSV.

Used by both the CLI (--input) and the desktop app (CSV upload button).
"""
from __future__ import annotations

import csv
import os
from typing import List, Optional

_URL_HEADER_NAMES = {
    "url", "urls", "website", "web", "sitio", "sitio web", "pagina",
    "página", "dominio", "link", "enlace",
}


def _looks_like_url(value: str) -> bool:
    value = value.strip().lower()
    if not value:
        return False
    return value.startswith(("http://", "https://")) or ("." in value and " " not in value)


def read_urls_from_txt(path: str) -> List[str]:
    """One URL per line; blank lines and lines starting with # are ignored."""
    urls = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    return urls


def read_urls_from_csv(path: str) -> List[str]:
    """Accepts a CSV with a header like "url"/"website"/"sitio web" (in any
    column position), or -- with no recognizable header -- just takes the
    first column of every row."""
    with open(path, "r", newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))

    if not rows:
        return []

    header = [cell.strip().lower() for cell in rows[0]]
    url_col: Optional[int] = None
    for i, cell in enumerate(header):
        if cell in _URL_HEADER_NAMES:
            url_col = i
            break

    if url_col is not None:
        data_rows = rows[1:]
    else:
        url_col = 0
        # No recognizable header name: if the very first cell doesn't even
        # look like a URL, assume it's a header we just don't recognize and
        # skip it, rather than trying to "scrape" a column title.
        data_rows = rows[1:] if rows[0] and not _looks_like_url(rows[0][0]) else rows

    urls = []
    for row in data_rows:
        if len(row) > url_col:
            value = row[url_col].strip()
            if value:
                urls.append(value)
    return urls


def read_urls_from_file(path: str) -> List[str]:
    """Dispatch on file extension: .csv -> read_urls_from_csv, else plain text."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        return read_urls_from_csv(path)
    return read_urls_from_txt(path)
