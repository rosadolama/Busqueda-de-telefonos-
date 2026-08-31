"""Shared CSV I/O for scrape results, used by both the CLI and the desktop app."""
from __future__ import annotations

import csv
from typing import List

from contact_scraper.models import ContactInfo

CSV_FIELDS = [
    "source_url", "contact_page_url", "team_page_url", "names", "phones",
    "hours", "city", "country", "address_raw", "warnings",
]


def result_to_csv_row(info: ContactInfo) -> dict:
    row = info.to_dict()
    return {
        "source_url": row["source_url"],
        "contact_page_url": row["contact_page_url"] or "",
        "team_page_url": row["team_page_url"] or "",
        "names": "; ".join(row["names"]),
        "phones": "; ".join(row["phones"]),
        "hours": row["hours"] or "",
        "city": row["city"] or "",
        "country": row["country"] or "",
        "address_raw": row["address_raw"] or "",
        "warnings": " | ".join(row["warnings"]),
    }


def write_csv(results: List[ContactInfo], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for info in results:
            writer.writerow(result_to_csv_row(info))
