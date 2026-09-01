"""Fuente: Gobierno de Aragón - Registro de Entidades, Centros y Servicios
Sociales, dataset abierto "residencias-mayores" (portal CKAN opendata.aragon.es).

No es scraping de HTML: es un CSV de datos abiertos descargable directamente
en una sola petición (robots.txt de opendata.aragon.es permite explícitamente
esta ruta de descarga; Disallow solo afecta a /ckan/api/, listados con
querystring y páginas de historial/rating).

Se probó primero La Rioja (paginasamarillas.es y larioja.org), pero ambas
fuentes bloquean cualquier petición automatizada (Incapsula / Cloudflare
managed challenge) antes de servir ningún contenido, así que se descartaron.

El dataset no trae web de la empresa (no existe esa columna en el CSV
origen), así que Web queda siempre vacío para esta fuente: no se inventa.
CEN.NOMBRE (nombre del centro) se usa como Empresa; ENT.NOMBRE (entidad
titular, puede ser un ayuntamiento, empresa o particular distinto del
nombre del centro) se guarda aparte en Titular.
"""
from __future__ import annotations

import csv
import io
import logging

from utils_comunes import CompanyRow, append_raw_row, rate_limited_get

SOURCE_NAME = "registro_aragon"
LABEL = "Registro Aragón (residencias mayores)"
URL = (
    "https://opendata.aragon.es/ckan/dataset/a51da258-20e9-460a-ac58-318e2ce7bdbc"
    "/resource/21c5ea29-755f-4f51-9a02-d082e59cede7/download/residencias-mayores.csv"
)

logger = logging.getLogger("aove_scraper")


def scrape() -> list[CompanyRow]:
    rows: list[CompanyRow] = []
    try:
        resp = rate_limited_get(URL, SOURCE_NAME)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.error("FUENTE FALLIDA: %s | motivo: %s", SOURCE_NAME, exc)
        return rows

    reader = csv.DictReader(io.StringIO(resp.text), delimiter=";")
    for record in reader:
        try:
            empresa = (record.get("CEN.NOMBRE") or "").strip()
            if not empresa:
                continue
            titular = (record.get("ENT.NOMBRE") or "").strip()
            domicilio = (record.get("DOMICILIO") or "").strip()
            localidad = (record.get("LOCALIDAD") or "").strip()
            provincia = (record.get("PROVINCIA") or "").strip()
            direccion = ", ".join(p for p in (domicilio, localidad, provincia) if p)
            telefono = (record.get("TELEFONO") or "").strip()

            row = CompanyRow(
                Empresa=empresa,
                Titular=titular,
                Direccion=direccion,
                Telefono=telefono,
                fuente=SOURCE_NAME,
                DOP_Origen=LABEL,
            )
            append_raw_row(row)
            rows.append(row)
        except Exception as exc:  # noqa: BLE001
            logger.error("FUENTE FALLIDA (item): %s | motivo: %s", SOURCE_NAME, exc)
            continue

    return rows
