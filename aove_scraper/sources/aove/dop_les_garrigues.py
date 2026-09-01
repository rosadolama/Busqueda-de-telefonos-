"""Fuente: DOP les Garrigues - 'Cooperatives/Molins certificats'.

Grid de Elementor: cada cooperativa es un vídeo de YouTube + un h2 con el
nombre, sin enlaces, sin web, sin teléfono, sin email. Se incluye solo con
Empresa (mismo criterio ya acordado para Montes de Toledo/EVOOLEUM cuando
la fuente no publica más datos): no hay nada que inventar aquí.

Selector: h2.elementor-heading-title dentro de .elementor-inner-column,
para no capturar de rebote el h2 del calendario de la agenda (que no está
dentro de una elementor-inner-column ni lleva esa clase de heading).
"""
from __future__ import annotations

import logging

from bs4 import BeautifulSoup

from utils_comunes import CompanyRow, append_raw_row, rate_limited_get

SOURCE_NAME = "dop_les_garrigues"
DOP_LABEL = "DOP Les Garrigues"
URL = "https://olidoplesgarrigues.com/pdo-les-garrigues/cooperativas-molinos-certificados-con-d-o-p-les-garrigues/"

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
    headings = [h2 for h2 in soup.select(".elementor-inner-column h2.elementor-heading-title")]
    if not headings:
        logger.error("FUENTE FALLIDA: %s | motivo: no se encontraron tarjetas de cooperativa (¿cambió el HTML?)", SOURCE_NAME)
        return rows

    for h2 in headings:
        try:
            empresa = h2.get_text(strip=True)
            if not empresa:
                continue
            row = CompanyRow(Empresa=empresa, fuente=SOURCE_NAME, DOP_Origen=DOP_LABEL)
            append_raw_row(row)
            rows.append(row)
        except Exception as exc:  # noqa: BLE001
            logger.error("FUENTE FALLIDA (item): %s | motivo: %s", SOURCE_NAME, exc)
            continue

    return rows
