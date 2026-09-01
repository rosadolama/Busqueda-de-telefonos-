"""Fuente: EVOOLEUM TOP100 - ranking de los mejores AOVE del mundo.

Tabla HTML (TablePress) con columnas Score/Brand/Company/Variety/Country.
No hay web, email, teléfono ni representante en esta tabla — es un ranking
de aceites premiados, no un directorio de contacto. Se filtra a las filas
de España; una misma empresa puede aparecer varias veces (una por aceite
premiado), el dedup global las colapsa por nombre.
"""
from __future__ import annotations

import logging

from bs4 import BeautifulSoup

from utils_comunes import CompanyRow, append_raw_row, rate_limited_get

SOURCE_NAME = "evooleum"
DOP_LABEL = "EVOOLEUM Top100"
URL = "https://www.evooleum.com/evooleum-top100/"

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
    table = soup.find("table", class_="tablepress")
    if table is None:
        logger.error("FUENTE FALLIDA: %s | motivo: no se encontró la tabla TOP100 (¿cambió el HTML?)", SOURCE_NAME)
        return rows

    trs = table.find_all("tr")[1:]  # salta la fila de cabecera
    for tr in trs:
        try:
            cells = tr.find_all("td")
            if len(cells) < 5:
                continue
            company = cells[2].get_text(strip=True)
            country = cells[4].get_text(strip=True)
            if not company or "españa" not in country.lower():
                continue
            row = CompanyRow(Empresa=company, fuente=SOURCE_NAME, DOP_Origen=DOP_LABEL)
            append_raw_row(row)
            rows.append(row)
        except Exception as exc:  # noqa: BLE001
            logger.error("FUENTE FALLIDA (item): %s | motivo: %s", SOURCE_NAME, exc)
            continue

    return rows
