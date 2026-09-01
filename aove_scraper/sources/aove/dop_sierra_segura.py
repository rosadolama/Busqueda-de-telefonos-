"""Fuente: Consejo Regulador DOP Sierra de Segura - directorio de asociados (Almazaras).

Plugin WordPress 'Directories Pro' (clases drts-*). El listado de la
categoría 'Almazaras' trae nombre + enlace a una ficha individual; la
ficha trae dirección/teléfono/email/web marcados por icono FontAwesome
(fa-map-marker-alt / fa-phone / fa-envelope / fa-globe). Se clasifica por
tipo de icono, no por posición, porque en el listado-resumen se vio un
caso con la web puesta por error en el campo teléfono.
"""
from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup, Tag

from utils_comunes import (
    CompanyRow, EMAIL_RE, normalize_web, rate_limited_get,
    scrape_details_concurrently,
)

SOURCE_NAME = "dop_sierra_segura"
DOP_LABEL = "DOP Sierra de Segura"
LIST_URL = "https://dosierradesegura.com/directory-asociados/categories/almazaras/"
DETAIL_WORKERS = 3

logger = logging.getLogger("aove_scraper")

_DOMAIN_LIKE_RE = re.compile(r"^(https?://)?(www\.)?[\w\-]+\.[a-z]{2,}(/.*)?$", re.IGNORECASE)


def scrape() -> list[CompanyRow]:
    rows: list[CompanyRow] = []
    try:
        resp = rate_limited_get(LIST_URL, SOURCE_NAME)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.error("FUENTE FALLIDA: %s | motivo: %s", SOURCE_NAME, exc)
        return rows

    soup = BeautifulSoup(resp.text, "html.parser")
    items = soup.select(".directory-listing-main")
    if not items:
        logger.error("FUENTE FALLIDA: %s | motivo: no se encontraron fichas de directorio (¿cambió el HTML?)", SOURCE_NAME)
        return rows

    detail_urls = []
    for it in items:
        link = it.select_one(".directory-listing-title a[href]")
        if link:
            detail_urls.append(link["href"])
    detail_urls = list(dict.fromkeys(detail_urls))

    rows.extend(scrape_details_concurrently(detail_urls, _scrape_detail, SOURCE_NAME, max_workers=DETAIL_WORKERS))
    return rows


def _scrape_detail(url: str) -> CompanyRow | None:
    resp = rate_limited_get(url, SOURCE_NAME)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    h1 = soup.select_one("h1")
    empresa = h1.get_text(strip=True) if h1 else ""
    if not empresa:
        return None

    row = CompanyRow(Empresa=empresa, fuente=SOURCE_NAME, DOP_Origen=DOP_LABEL)

    for field in soup.select(".drts-entity-field"):
        icon = field.select_one("i")
        classes = icon.get("class", []) if isinstance(icon, Tag) else []
        value_el = field.select_one(".drts-entity-field-value")
        if not value_el:
            continue
        text = value_el.get_text(" ", strip=True)
        link = value_el.select_one("a[href]")
        href = link["href"] if link else ""

        if "fa-envelope" in classes:
            match = EMAIL_RE.search(text) or EMAIL_RE.search(href)
            if match:
                row.Email = match.group(0)
        elif "fa-globe" in classes:
            web_source = href or text
            if web_source and "@" not in web_source:
                row.Web = normalize_web(web_source)
        elif "fa-phone" in classes:
            # defensa: si en vez de un teléfono aparece una web (visto en el
            # listado-resumen), la mandamos a Web en vez de perderla o
            # guardarla como teléfono inválido
            if _DOMAIN_LIKE_RE.match(text):
                if not row.Web:
                    row.Web = normalize_web(text)
            else:
                row.Telefono = text

    return row
