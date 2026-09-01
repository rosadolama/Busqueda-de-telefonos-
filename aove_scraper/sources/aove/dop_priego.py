"""Fuente: Consejo Regulador DOP Priego de Córdoba - página 'Empresas AOVE'.

La página lista almazaras/envasadoras/comercializadoras amparadas con nombre,
representante, teléfono, email y web en tarjetas HTML (WordPress + JetEngine).
No hay paginación: todo va en una sola página.
"""
from __future__ import annotations

import logging

from bs4 import BeautifulSoup

from utils_comunes import (
    CompanyRow, EMAIL_RE, PHONE_RE, append_raw_row, normalize_web,
    rate_limited_get, split_spanish_name,
)

SOURCE_NAME = "dop_priego_cordoba"
DOP_LABEL = "DOP Priego de Córdoba"
URL = "https://www.dopriegodecordoba.es/empresas-aove/"

logger = logging.getLogger("aove_scraper")


def scrape() -> list[CompanyRow]:
    rows: list[CompanyRow] = []
    try:
        resp = rate_limited_get(URL, SOURCE_NAME)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - loguear y no tumbar el script
        logger.error("FUENTE FALLIDA: %s | motivo: %s", SOURCE_NAME, exc)
        return rows

    soup = BeautifulSoup(resp.text, "html.parser")
    items = soup.select(".jet-listing-grid__item")
    if not items:
        logger.error("FUENTE FALLIDA: %s | motivo: no se encontraron tarjetas de empresa (¿cambió el HTML?)", SOURCE_NAME)
        return rows

    for item in items:
        try:
            row = _parse_item(item)
            if row is not None:
                append_raw_row(row)
                rows.append(row)
        except Exception as exc:  # noqa: BLE001
            logger.error("FUENTE FALLIDA (item): %s | motivo: %s", SOURCE_NAME, exc)
            continue

    return rows


def _parse_item(item) -> CompanyRow | None:
    heading = item.select_one("h4.elementor-heading-title")
    empresa = heading.get_text(strip=True) if heading else ""
    if not empresa:
        return None

    web = ""
    img_link = item.select_one(".elementor-image a[href]")
    if img_link and img_link.get("href"):
        href = img_link["href"]
        if "@" not in href:  # descarta mailto/enlaces mal formados
            web = normalize_web(href)

    row = CompanyRow(Empresa=empresa, Web=web, fuente=SOURCE_NAME, DOP_Origen=DOP_LABEL)

    for box in item.select(".elementor-icon-box-wrapper"):
        title_el = box.select_one(".elementor-icon-box-title")
        desc_el = box.select_one(".elementor-icon-box-description")
        title = title_el.get_text(strip=True) if title_el else ""
        desc = box.get_text(" ", strip=True)  # texto completo por si el email/tel va en el desc

        combined = f"{title} {desc_el.get_text(strip=True) if desc_el else ''}"

        email_match = EMAIL_RE.search(combined)
        if email_match and not row.Email:
            row.Email = email_match.group(0)
            continue

        if title.lower().startswith("tel") and not row.Telefono:
            phone_match = PHONE_RE.search(title)
            if phone_match:
                row.Telefono = phone_match.group(0).strip()
            continue

        if title.lower().startswith("nº de empresa") or "empresa certificada" in title.lower():
            continue  # metadato de certificación, no forma parte del schema

        if title.lower().startswith("www.") or title.lower().startswith("http"):
            if not row.Web:
                row.Web = normalize_web(title)
            continue

        # Cualquier otro icon-box con título+descripción se interpreta como Cargo + persona
        if title and desc_el and not row.Cargo:
            person_desc = desc_el.get_text(strip=True)
            nombre, apellidos = split_spanish_name(person_desc)
            row.Cargo = title
            row.Nombre = nombre
            row.Apellidos = apellidos

    return row
