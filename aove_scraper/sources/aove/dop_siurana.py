"""Fuente: Consell Regulador DOP Siurana - pàgina 'Entitats'.

Estructura pròpia del lloc (classes dops-*): el llistat agrupa entitats
per població, cada una amb enllaç a una fitxa individual. La fitxa té un
bloc específic '.sec-main-block-moli' (el molí, no la botiga/agrobotiga)
amb adreça/telèfon/email/web amb classes semàntiques clares.
"""
from __future__ import annotations

import logging

from bs4 import BeautifulSoup

from utils_comunes import CompanyRow, normalize_web, rate_limited_get, scrape_details_concurrently

SOURCE_NAME = "dop_siurana"
DOP_LABEL = "DOP Siurana"
LIST_URL = "https://dopsiurana.com/entitats/"
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
    poblacions = soup.select(".dops-el-poblacio")
    if not poblacions:
        logger.error("FUENTE FALLIDA: %s | motivo: no se encontró el listado de entitats (¿cambió el HTML?)", SOURCE_NAME)
        return rows

    detail_urls = []
    for poblacio in poblacions:
        for link in poblacio.select(".dops-el-entitat a[href]"):
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

    moli = soup.select_one(".sec-main-block-moli")
    if moli:
        tel = moli.select_one(".sec-main-tel")
        if tel:
            row.Telefono = tel.get_text(" ", strip=True)
        mail = moli.select_one(".sec-main-mail")
        if mail:
            row.Email = mail.get_text(" ", strip=True)
        web = moli.select_one(".sec-main-web a[href]")
        if web:
            row.Web = normalize_web(web["href"])

    return row
