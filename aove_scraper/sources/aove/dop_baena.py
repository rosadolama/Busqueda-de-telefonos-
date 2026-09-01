"""Fuente: Consejo Regulador DOP Baena - 'Nuestras empresas y marcas'.

Página Elementor con tarjetas <a> (logo + nombre en h6) que enlazan
directamente a la web/tienda de cada empresa. No hay teléfono, email ni
representante en esta página: solo Empresa + Web.
"""
from __future__ import annotations

import logging

from bs4 import BeautifulSoup

from utils_comunes import CompanyRow, append_raw_row, normalize_web, rate_limited_get

SOURCE_NAME = "dop_baena"
DOP_LABEL = "DOP Baena"
URL = "https://www.dobaena.com/nuestras-empresas-y-marcas/"

logger = logging.getLogger("aove_scraper")


def scrape() -> list[CompanyRow]:
    rows: list[CompanyRow] = []
    try:
        resp = rate_limited_get(URL, SOURCE_NAME)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.error("FUENTE FALLIDA: %s | motivo: %s", SOURCE_NAME, exc)
        return rows

    soup = BeautifulSoup(resp.text, "html.parser")
    cards = [c for c in soup.select("a.e-con.e-child") if c.select_one("h6.elementor-heading-title")]
    if not cards:
        logger.error("FUENTE FALLIDA: %s | motivo: no se encontraron tarjetas de empresa (¿cambió el HTML?)", SOURCE_NAME)
        return rows

    for card in cards:
        try:
            h6 = card.select_one("h6.elementor-heading-title")
            empresa = h6.get_text(strip=True)
            if not empresa:
                continue
            web = normalize_web(card.get("href", "")) if card.get("href") else ""
            row = CompanyRow(Empresa=empresa, Web=web, fuente=SOURCE_NAME, DOP_Origen=DOP_LABEL)
            append_raw_row(row)
            rows.append(row)
        except Exception as exc:  # noqa: BLE001
            logger.error("FUENTE FALLIDA (item): %s | motivo: %s", SOURCE_NAME, exc)
            continue

    return rows
