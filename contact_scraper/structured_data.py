"""Extract schema.org contact info that sites embed for SEO (JSON-LD + microdata).

When present, this is far more reliable than scraping visible text, since the
site itself is asserting "this is our phone number / city / hours".
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

_BUSINESS_TYPES = {
    "localbusiness", "organization", "corporation", "store", "restaurant",
    "professionalservice", "medicalbusiness", "attorney", "dentist",
    "generalcontractor", "homeandconstructionbusiness", "realestateagent",
}
_PERSON_TYPE = "person"

_DAY_MAP = {
    "mo": "Lunes", "monday": "Lunes",
    "tu": "Martes", "tuesday": "Martes",
    "we": "Miércoles", "wednesday": "Miércoles",
    "th": "Jueves", "thursday": "Jueves",
    "fr": "Viernes", "friday": "Viernes",
    "sa": "Sábado", "saturday": "Sábado",
    "su": "Domingo", "sunday": "Domingo",
}


def _type_names(node: Dict[str, Any]) -> List[str]:
    t = node.get("@type", "")
    if isinstance(t, list):
        return [str(x).lower() for x in t]
    return [str(t).lower()]


def _iter_nodes(data: Any):
    """Yield every dict node in a JSON-LD document, unwrapping @graph and lists."""
    if isinstance(data, list):
        for item in data:
            yield from _iter_nodes(item)
    elif isinstance(data, dict):
        yield data
        if "@graph" in data:
            yield from _iter_nodes(data["@graph"])


def extract_json_ld(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    nodes: List[Dict[str, Any]] = []
    for tag in soup.find_all("script", type=lambda t: t and "ld+json" in t.lower()):
        raw = tag.string or tag.get_text()
        if not raw or not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        nodes.extend(_iter_nodes(data))
    return nodes


def _country_str(value: Any) -> Optional[str]:
    """schema.org allows addressCountry to be a plain string (ISO code or
    full name) or a nested Country object with its own "name"."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and isinstance(value.get("name"), str):
        return value["name"]
    return None


def _address_to_parts(addr: Any) -> Dict[str, Optional[str]]:
    if isinstance(addr, str):
        return {"locality": None, "region": None, "country": None, "raw": addr}
    if isinstance(addr, dict):
        country = _country_str(addr.get("addressCountry"))
        return {
            "locality": addr.get("addressLocality"),
            "region": addr.get("addressRegion"),
            "country": country,
            "raw": ", ".join(
                str(v) for v in [
                    addr.get("streetAddress"), addr.get("addressLocality"),
                    addr.get("addressRegion"), addr.get("postalCode"), country,
                ] if v
            ) or None,
        }
    return {"locality": None, "region": None, "country": None, "raw": None}


def _opening_hours_spec_to_text(spec: Any) -> List[str]:
    results = []
    items = spec if isinstance(spec, list) else [spec]
    for item in items:
        if isinstance(item, str):
            results.append(_openinghours_string_to_text(item))
        elif isinstance(item, dict):
            days = item.get("dayOfWeek", [])
            days = days if isinstance(days, list) else [days]
            day_names = []
            for d in days:
                key = str(d).rsplit("/", 1)[-1].lower()
                day_names.append(_DAY_MAP.get(key, str(d)))
            opens = item.get("opens", "")
            closes = item.get("closes", "")
            if day_names and opens and closes:
                results.append(f"{', '.join(day_names)}: {opens}–{closes}")
    return [r for r in results if r]


_OH_RE = re.compile(
    r"\b(Mo|Tu|We|Th|Fr|Sa|Su)(?:-(Mo|Tu|We|Th|Fr|Sa|Su))?\s+(\d{1,2}:\d{2})-(\d{1,2}:\d{2})",
    re.IGNORECASE,
)


def _openinghours_string_to_text(value: str) -> str:
    """Convert compact schema.org strings like 'Mo-Fr 09:00-18:00' to Spanish."""
    m = _OH_RE.search(value)
    if not m:
        return value
    start, end, opens, closes = m.groups()
    start_name = _DAY_MAP.get(start.lower(), start)
    if end:
        end_name = _DAY_MAP.get(end.lower(), end)
        return f"{start_name} a {end_name}: {opens}–{closes}"
    return f"{start_name}: {opens}–{closes}"


def _person_name(node: Dict[str, Any]) -> Optional[str]:
    if _PERSON_TYPE in _type_names(node):
        name = node.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def summarize_structured_data(nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Pull phones/address/hours/names out of parsed JSON-LD nodes."""
    phones: List[str] = []
    names: List[str] = []
    hours: List[str] = []
    address: Dict[str, Optional[str]] = {"locality": None, "region": None, "country": None, "raw": None}

    for node in nodes:
        types = _type_names(node)

        tel = node.get("telephone")
        if isinstance(tel, str) and tel.strip():
            phones.append(tel.strip())

        if any(t in _BUSINESS_TYPES for t in types):
            if "address" in node and not address["raw"]:
                address = _address_to_parts(node["address"])

            oh = node.get("openingHoursSpecification")
            if oh:
                hours.extend(_opening_hours_spec_to_text(oh))
            oh_simple = node.get("openingHours")
            if oh_simple:
                items = oh_simple if isinstance(oh_simple, list) else [oh_simple]
                for item in items:
                    if isinstance(item, str):
                        hours.append(_openinghours_string_to_text(item))

            for key in ("employee", "founder", "founders", "employees"):
                val = node.get(key)
                if not val:
                    continue
                for person in (val if isinstance(val, list) else [val]):
                    if isinstance(person, dict):
                        name = _person_name(person) or (person.get("name") if isinstance(person.get("name"), str) else None)
                        if name:
                            names.append(name)

            cp = node.get("contactPoint")
            if cp:
                for point in (cp if isinstance(cp, list) else [cp]):
                    if isinstance(point, dict):
                        cp_tel = point.get("telephone")
                        if isinstance(cp_tel, str) and cp_tel.strip():
                            phones.append(cp_tel.strip())
                        cp_name = point.get("name")
                        if isinstance(cp_name, str) and cp_name.strip():
                            names.append(cp_name.strip())

        direct_name = _person_name(node)
        if direct_name:
            names.append(direct_name)

    return {
        "phones": list(dict.fromkeys(phones)),
        "names": list(dict.fromkeys(names)),
        "hours": list(dict.fromkeys(hours)),
        "address": address,
    }


def extract_microdata(soup: BeautifulSoup) -> Dict[str, Any]:
    """Fallback for sites using schema.org microdata (itemprop=...) instead of JSON-LD."""
    def first_text(prop: str) -> Optional[str]:
        el = soup.find(attrs={"itemprop": prop})
        if not el:
            return None
        if el.name == "meta":
            return el.get("content")
        return el.get_text(strip=True) or None

    locality = first_text("addressLocality")
    region = first_text("addressRegion")
    country = first_text("addressCountry")
    telephone = first_text("telephone")

    address_raw = None
    if any([locality, region, country]):
        address_raw = ", ".join(v for v in [locality, region, country] if v)

    return {
        "phones": [telephone] if telephone else [],
        "address": {"locality": locality, "region": region, "country": country, "raw": address_raw},
    }


def extract_meta_geo(soup: BeautifulSoup) -> Optional[str]:
    """<meta name="geo.placename" content="Bogotá"> style hints."""
    tag = soup.find("meta", attrs={"name": re.compile("^geo.placename$", re.IGNORECASE)})
    if tag and tag.get("content"):
        return tag["content"].strip()
    return None
