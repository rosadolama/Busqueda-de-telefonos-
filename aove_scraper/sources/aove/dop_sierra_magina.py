"""Fuente: Consejo Regulador DOP Sierra Mágina - 'Almazaras / Envasadoras'.

Scraping en 2 pasos: el listado (Divi/portfolio) solo trae nombre + enlace a
una ficha individual por empresa; la ficha trae dirección, teléfono y el
enlace a la web oficial. No hay email de empresa (el único mailto de las
fichas es el contacto del propio Consejo Regulador, así que no se usa) ni
nombre de representante/cargo.
"""
from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from utils_comunes import (
    EMAIL_RE, CompanyRow, normalize_web, rate_limited_get,
    scrape_details_concurrently,
)

SOURCE_NAME = "dop_sierra_magina"
DOP_LABEL = "DOP Sierra Mágina"
LIST_URL = "https://sierramagina.org/almazaras-envasadoras/"
DETAIL_WORKERS = 3

logger = logging.getLogger("aove_scraper")

_PHONE_LINE_RE = re.compile(r"^\+?\d[\d\s.\-]{5,}\d$")


def scrape() -> list[CompanyRow]:
    rows: list[CompanyRow] = []
    try:
        resp = rate_limited_get(LIST_URL, SOURCE_NAME)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.error("FUENTE FALLIDA: %s | motivo: %s", SOURCE_NAME, exc)
        return rows

    soup = BeautifulSoup(resp.text, "html.parser")
    items = soup.select(".et_pb_portfolio_item")
    if not items:
        logger.error("FUENTE FALLIDA: %s | motivo: no se encontraron items de portfolio (¿cambió el HTML?)", SOURCE_NAME)
        return rows

    detail_urls: list[str] = []
    for item in items:
        link = item.find("a", href=True)
        if link:
            detail_urls.append(link["href"])
    detail_urls = list(dict.fromkeys(detail_urls))  # dedup preservando orden

    rows.extend(scrape_details_concurrently(detail_urls, _scrape_detail, SOURCE_NAME, max_workers=DETAIL_WORKERS))
    return rows


def _scrape_detail(url: str) -> CompanyRow | None:
    resp = rate_limited_get(url, SOURCE_NAME)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    h1 = soup.select_one("h1.entry-title")
    empresa = h1.get_text(strip=True) if h1 else ""
    if not empresa:
        return None

    row = CompanyRow(Empresa=empresa, fuente=SOURCE_NAME, DOP_Origen=DOP_LABEL)

    web_link = soup.find("a", string=lambda s: s and "visitar la web" in s.lower())
    if web_link and web_link.get("href"):
        href = web_link["href"]
        bare = re.sub(r"^(mailto:|https?://)", "", href, flags=re.IGNORECASE)
        if EMAIL_RE.fullmatch(bare):
            # la propia ficha puso un email en el botón "web" por error; lo
            # rescatamos como Email en vez de generar una URL inválida
            row.Email = bare
        else:
            row.Web = normalize_web(href)

    info_row = soup.select_one(".et_pb_row_1_tb_body")
    if info_row:
        pieces = [p.strip() for p in info_row.get_text("|", strip=True).split("|") if p.strip()]
        for piece in pieces:
            if _PHONE_LINE_RE.match(piece):
                row.Telefono = piece
                break

    return row
