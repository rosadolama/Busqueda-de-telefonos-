"""Fuente: Consejo Regulador DOP Montes de Toledo - 'Empresas certificadas'.

El listado ('CERTIFICADOS EN VIGOR') enlaza a una ficha individual por
empresa (WPBakery) con dirección/teléfono/fax/email/web marcados con
iconos FontAwesome (fa-home, fa-phone, fa-fax, fa-envelope, fa-laptop).
No hay nombre de representante/cargo en ninguna ficha.
"""
from __future__ import annotations

import logging

from bs4 import BeautifulSoup, Tag

from utils_comunes import (
    CompanyRow, EMAIL_RE, normalize_web, rate_limited_get,
    scrape_details_concurrently,
)

SOURCE_NAME = "dop_montes_toledo"
DOP_LABEL = "DOP Montes de Toledo"
LIST_URL = "https://www.domontesdetoledo.com/empresas-certificadas/"
DETAIL_WORKERS = 3


logger = logging.getLogger("aove_scraper")


def scrape() -> list[CompanyRow]:
    rows: list[CompanyRow] = []
    try:
        resp = rate_limited_get(LIST_URL, SOURCE_NAME)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.error("FUENTE FALLIDA: %s | motivo: %s", SOURCE_NAME, exc)
        return rows

    soup = BeautifulSoup(resp.text, "html.parser")
    links = soup.select("div.standard-arrow.list-divider ul li a[href]")
    if not links:
        logger.error("FUENTE FALLIDA: %s | motivo: no se encontró el listado 'CERTIFICADOS EN VIGOR' (¿cambió el HTML?)", SOURCE_NAME)
        return rows

    detail_urls = list(dict.fromkeys(a["href"] for a in links))

    rows.extend(scrape_details_concurrently(detail_urls, _scrape_detail, SOURCE_NAME, max_workers=DETAIL_WORKERS))
    return rows


def _sibling_text_until_break(icon: Tag) -> str:
    parts = []
    node = icon.next_sibling
    while node is not None and getattr(node, "name", None) not in ("br", "i"):
        if isinstance(node, Tag):
            parts.append(node.get_text(strip=True))
        else:
            parts.append(str(node).strip())
        node = node.next_sibling
    return " ".join(p for p in parts if p).strip()


def _sibling_href_until_break(icon: Tag) -> str:
    node = icon.next_sibling
    while node is not None and getattr(node, "name", None) not in ("br",):
        if isinstance(node, Tag):
            if node.name == "i":
                break
            if node.name == "a" and node.get("href"):
                return node["href"]
        node = node.next_sibling
    return ""


def _scrape_detail(url: str) -> CompanyRow | None:
    resp = rate_limited_get(url, SOURCE_NAME)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    h1 = soup.select_one("h1.entry-title")
    empresa = h1.get_text(strip=True) if h1 else ""
    if not empresa:
        return None

    row = CompanyRow(Empresa=empresa, fuente=SOURCE_NAME, DOP_Origen=DOP_LABEL)

    for icon in soup.select("i.fa"):
        classes = icon.get("class", [])
        if "fa-phone" in classes:
            text = _sibling_text_until_break(icon)
            if text and not row.Telefono:
                row.Telefono = text
        elif "fa-envelope" in classes:
            text = _sibling_text_until_break(icon)
            match = EMAIL_RE.search(text)
            if match and not row.Email:
                row.Email = match.group(0)
        elif "fa-laptop" in classes:
            href = _sibling_href_until_break(icon)
            if href and not row.Web:
                row.Web = normalize_web(href)
            elif not row.Web:
                text = _sibling_text_until_break(icon)
                if text:
                    row.Web = normalize_web(text)

    return row
