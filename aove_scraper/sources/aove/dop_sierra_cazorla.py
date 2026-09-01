"""Fuente: Consejo Regulador DOP Sierra de Cazorla - página 'Almazaras'.

Página Avada (tema WordPress) con "Fusion Flip Box": el frente de la
tarjeta trae el nombre de la empresa, el dorso trae población + web +
teléfono en un único <p> separado por <br>. No hay email ni representante.
Una sola página, sin paginación ni fichas individuales.
"""
from __future__ import annotations

import logging

from bs4 import BeautifulSoup

from utils_comunes import CompanyRow, append_raw_row, normalize_web, rate_limited_get

SOURCE_NAME = "dop_sierra_cazorla"
DOP_LABEL = "DOP Sierra de Cazorla"
URL = "https://www.desierracazorla.es/almazaras/"

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
    boxes = soup.select(".fusion-flip-box")
    if not boxes:
        logger.error("FUENTE FALLIDA: %s | motivo: no se encontraron tarjetas 'fusion-flip-box' (¿cambió el HTML?)", SOURCE_NAME)
        return rows

    for box in boxes:
        try:
            row = _parse_box(box)
            if row is not None:
                append_raw_row(row)
                rows.append(row)
        except Exception as exc:  # noqa: BLE001
            logger.error("FUENTE FALLIDA (item): %s | motivo: %s", SOURCE_NAME, exc)
            continue

    return rows


def _parse_box(box) -> CompanyRow | None:
    front = box.select_one(".flip-box-front-inner")
    empresa = front.get_text(" ", strip=True) if front else ""
    if not empresa:
        return None

    row = CompanyRow(Empresa=empresa, fuente=SOURCE_NAME, DOP_Origen=DOP_LABEL)

    back_p = box.select_one(".flip-box-back-inner p")
    if back_p:
        # el <p> del dorso trae: población | web | teléfono, separados por <br>
        parts = [p.strip() for p in back_p.get_text("|", strip=True).split("|") if p.strip()]
        if len(parts) >= 3:
            _, web_text, phone_text = parts[0], parts[1], parts[2]
            row.Web = normalize_web(web_text)
            row.Telefono = phone_text
        elif len(parts) == 2:
            # solo web o solo teléfono, sin certeza de cuál falta; nos
            # quedamos con lo que se pueda identificar sin adivinar
            for p in parts:
                if any(c.isdigit() for c in p) and sum(c.isdigit() for c in p) >= 6:
                    row.Telefono = p
                else:
                    row.Web = normalize_web(p)

    return row
