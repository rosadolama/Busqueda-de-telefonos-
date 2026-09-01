"""Fuente: AEMO (Asociación Española de Municipios del Olivo) - Empresas socias.

Página Odoo (website builder) con tarjetas div.col-md-4.text-center: nombre
comercial (h3), razón social y web como texto plano (sin <a>, sin href).
Directorio muy pequeño (8 empresas socias). Se excluyen los socios que no
son productores de AOVE (correduría de seguros, empresa de pesaje) por
palabras clave en su razón social — AEMO admite como socias a cualquier
empresa "del sector" en sentido amplio, no solo almazaras/envasadoras.
"""
from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from utils_comunes import CompanyRow, append_raw_row, normalize_web, rate_limited_get

SOURCE_NAME = "aemo"
DOP_LABEL = "AEMO"
URL = "https://www.aemo.es/page/empresas-socias"

logger = logging.getLogger("aove_scraper")

_NON_AOVE_KEYWORDS = ("correduría", "correduria", "seguros", "pesaje")
_DOMAIN_RE = re.compile(r"^(https?://)?(www\.)?[\w\-]+\.[a-z]{2,}(/.*)?$", re.IGNORECASE)


def scrape() -> list[CompanyRow]:
    rows: list[CompanyRow] = []
    try:
        resp = rate_limited_get(URL, SOURCE_NAME)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.error("FUENTE FALLIDA: %s | motivo: %s", SOURCE_NAME, exc)
        return rows

    soup = BeautifulSoup(resp.text, "html.parser")
    cards = soup.select("div.col-md-4.text-center")
    if not cards:
        logger.error("FUENTE FALLIDA: %s | motivo: no se encontraron tarjetas de empresa (¿cambió el HTML?)", SOURCE_NAME)
        return rows

    for card in cards:
        try:
            row = _parse_card(card)
            if row is not None:
                append_raw_row(row)
                rows.append(row)
        except Exception as exc:  # noqa: BLE001
            logger.error("FUENTE FALLIDA (item): %s | motivo: %s", SOURCE_NAME, exc)
            continue

    return rows


def _parse_card(card) -> CompanyRow | None:
    # algunas tarjetas (p.ej. COLIVAL, PICUALIA) traen un <h3></h3> vacío
    # antes del real; nos quedamos con el primer h3 que tenga texto.
    empresa = next((h.get_text(strip=True) for h in card.find_all("h3") if h.get_text(strip=True)), "")
    if not empresa:
        return None

    texts = [d.get_text(strip=True) for d in card.find_all("div") if d.get_text(strip=True)]

    razon_social = texts[0] if texts else ""
    if any(kw in razon_social.lower() for kw in _NON_AOVE_KEYWORDS):
        logger.info("%s: excluida '%s' (%s) por no ser productora de AOVE", SOURCE_NAME, empresa, razon_social)
        return None

    web_text = next((t for t in texts if _DOMAIN_RE.match(t) and "@" not in t), "")
    web = normalize_web(web_text) if web_text else ""

    return CompanyRow(Empresa=empresa, Web=web, fuente=SOURCE_NAME, DOP_Origen=DOP_LABEL)
