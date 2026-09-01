"""Fuente: Flos Olei - guía de productores de AOVE.

La página pública (flosolei.com) no trae los datos en el HTML: los carga
por JavaScript desde una API JSON de terceros (bluomelette.net, su
proveedor técnico) que el propio sitio consume públicamente y sin
autenticación — es la misma información que vería un usuario en el
navegador, solo que sin renderizar HTML. 500 empresas mundiales; se filtra
a paese="España".
"""
from __future__ import annotations

import logging

from utils_comunes import CompanyRow, append_raw_row, normalize_web, rate_limited_get

SOURCE_NAME = "flos_olei"
DOP_LABEL = "Flos Olei"
API_URL = "https://www.bluomelette.net/sob/web/api/aziende.php/aziende_guida/2026/es"

logger = logging.getLogger("aove_scraper")


def scrape() -> list[CompanyRow]:
    rows: list[CompanyRow] = []
    try:
        resp = rate_limited_get(API_URL, SOURCE_NAME)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.error("FUENTE FALLIDA: %s | motivo: %s", SOURCE_NAME, exc)
        return rows

    if not isinstance(data, list):
        logger.error("FUENTE FALLIDA: %s | motivo: la API no devolvió una lista (¿cambió el formato?)", SOURCE_NAME)
        return rows

    for entry in data:
        try:
            if entry.get("paese") != "España":
                continue
            empresa = (entry.get("nome") or "").strip()
            if not empresa:
                continue
            web = normalize_web((entry.get("web") or "").strip())
            email = (entry.get("mail") or "").strip()
            telefono = (entry.get("phone") or "").strip()
            row = CompanyRow(
                Empresa=empresa, Web=web, Email=email, Telefono=telefono,
                fuente=SOURCE_NAME, DOP_Origen=DOP_LABEL,
            )
            append_raw_row(row)
            rows.append(row)
        except Exception as exc:  # noqa: BLE001
            logger.error("FUENTE FALLIDA (item): %s | motivo: %s", SOURCE_NAME, exc)
            continue

    return rows
