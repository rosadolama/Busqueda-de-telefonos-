"""Data structures shared across the scraper."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ContactInfo:
    """Result of scraping a single site for contact details."""

    source_url: str
    contact_page_url: Optional[str] = None
    names: List[str] = field(default_factory=list)
    phones: List[str] = field(default_factory=list)
    hours: Optional[str] = None
    hours_raw: List[str] = field(default_factory=list)
    city: Optional[str] = None
    country: Optional[str] = None
    address_raw: Optional[str] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "source_url": self.source_url,
            "contact_page_url": self.contact_page_url,
            "names": self.names,
            "phones": self.phones,
            "hours": self.hours,
            "hours_raw": self.hours_raw,
            "city": self.city,
            "country": self.country,
            "address_raw": self.address_raw,
            "warnings": self.warnings,
        }
