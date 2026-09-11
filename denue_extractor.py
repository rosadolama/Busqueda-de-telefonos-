"""Descarga establecimientos del DENUE (INEGI) por entidad y actividad
económica (SCIAN), paginando en bloques, y los exporta a Excel/CSV.

DENUE ya trae teléfono, correo y sitio web directos de cada establecimiento
(cuando la empresa los reportó), así que sirve como fuente de listas de
prospección por zona/giro para México, en el mismo espíritu que
`aove_scraper/` (nichos europeos) o `dedup_contactos.py` (unificación).
No comparte su pipeline porque el modelo de datos es distinto: DENUE da
establecimientos con ~30 campos crudos del INEGI, no personas de contacto
con cargo, así que se exporta tal cual sin forzar Fit_ICP ni normalización
de teléfono pensada para España (+34).

Requiere un token DENUE (gratuito, uno por usuario): se obtiene en
https://www.inegi.org.mx/app/api/denue/v1/tokenVerify.aspx

Uso:
  export DENUE_TOKEN=tu-token-aqui
  python denue_extractor.py --entidad 09 --sector 43

  # o sin variable de entorno:
  python denue_extractor.py --entidad 09 --sector 43 --token tu-token-aqui

`--entidad` es la clave de entidad INEGI (2 dígitos, p.ej. 09 = CDMX).
`--sector` es el código de actividad SCIAN (2 a 6 dígitos: sector,
subsector, rama o clase — a mayor longitud, más específico).
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import pandas as pd
import requests

URL_TEMPLATE = (
    "https://www.inegi.org.mx/app/api/denue/v1/consulta/BuscarAreaAct/"
    "{entidad}/0/0/0/0/{sector}/0/0/0/0/{ini}/{fin}/0/{token}"
)

REINTENTOS = 3
ESPERA_REINTENTO = 5  # segundos, se duplica en cada reintento


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extractor de listas de empresas del DENUE (INEGI) por entidad y actividad económica.",
    )
    parser.add_argument("--entidad", required=True, help="Clave de entidad INEGI, 2 dígitos (p.ej. 09 = CDMX).")
    parser.add_argument("--sector", required=True, help="Código de actividad SCIAN (2 a 6 dígitos).")
    parser.add_argument("--bloque", type=int, default=100, help="Registros por llamada a la API (default 100; si da error 500/timeout, bajar a 50).")
    parser.add_argument("--max-registros", type=int, default=2000, help="Tope de registros a pedir (default 2000).")
    parser.add_argument("--espera", type=float, default=1.0, help="Pausa en segundos entre bloques (default 1.0).")
    parser.add_argument("--token", default=None, help="Token DENUE. Si no se indica, se lee de la variable de entorno DENUE_TOKEN.")
    parser.add_argument("-o", "--output", default=None, help="Archivo de salida (.xlsx o .csv). Por defecto: denue_<entidad>_sector<sector>.xlsx")
    parser.add_argument("--sin-dedup", action="store_true", help="No agrupar sucursales por razón social; exportar una fila por establecimiento tal cual llega del DENUE.")
    return parser


def deduplicar_por_razon_social(df: pd.DataFrame) -> pd.DataFrame:
    """Agrupa establecimientos por razón social (o Nombre si no hay razón
    social) en una sola fila por empresa, combinando el mejor dato
    disponible de cada columna entre sus sucursales.

    El DENUE reporta campos sin dato como string vacío "", no como NaN.
    agg('first') solo salta NaN, no "" -- si no se normaliza antes, se
    queda con la primera sucursal tal cual (con o sin contacto) en vez de
    combinar el correo de una sucursal con el teléfono de otra. Por eso el
    replace() es el paso que hace el resto del dedup funcionar, no un
    detalle cosmético."""
    df = df.replace("", pd.NA)
    razon_norm = df["Razon_social"].fillna(df["Nombre"]).str.strip().str.upper()
    df = df.assign(razon_norm=razon_norm)
    agg = {c: "first" for c in df.columns if c not in ("razon_norm", "CLEE")}
    agg["CLEE"] = "count"
    df_dedup = (
        df.groupby("razon_norm", as_index=False)
        .agg(agg)
        .rename(columns={"CLEE": "num_sucursales"})
        .drop(columns=["razon_norm"])
    )
    return df_dedup.fillna("")


def _get_con_reintentos(session: requests.Session, url: str) -> requests.Response | None:
    """GET con reintentos ante fallos transitorios (red, 5xx, 429). Devuelve
    None si se agotan los reintentos o el error es claramente definitivo
    (4xx que no sea 429, p.ej. token inválido) para no perder el resto del
    trabajo ya descargado por un solo bloque problemático."""
    espera = ESPERA_REINTENTO
    for intento in range(1, REINTENTOS + 1):
        try:
            resp = session.get(url, timeout=30)
        except requests.RequestException as exc:
            print(f"  intento {intento}/{REINTENTOS}: error de red ({exc})", file=sys.stderr)
        else:
            if resp.status_code == 200:
                return resp
            if resp.status_code == 429 or resp.status_code >= 500:
                print(f"  intento {intento}/{REINTENTOS}: HTTP {resp.status_code}", file=sys.stderr)
            else:
                print(f"  HTTP {resp.status_code} (no se reintenta: probable token inválido o parámetros mal formados)", file=sys.stderr)
                return None
        if intento < REINTENTOS:
            time.sleep(espera)
            espera *= 2
    return None


def extraer(entidad: str, sector: str, token: str, bloque: int, max_registros: int, espera: float) -> list[dict]:
    session = requests.Session()
    registros: list[dict] = []
    for ini in range(1, max_registros, bloque):
        fin = min(ini + bloque - 1, max_registros)
        url = URL_TEMPLATE.format(entidad=entidad, sector=sector, ini=ini, fin=fin, token=token)
        resp = _get_con_reintentos(session, url)
        if resp is None:
            print(f"Bloque {ini}-{fin} falló tras {REINTENTOS} intentos; se detiene con lo ya descargado.", file=sys.stderr)
            break
        try:
            datos = resp.json()
        except ValueError:
            print(f"Bloque {ini}-{fin}: respuesta no es JSON válido (posible error del servicio); se detiene.", file=sys.stderr)
            break
        if not datos:
            break
        registros.extend(datos)
        print(f"{ini}-{fin}: {len(datos)} registros")
        if fin >= max_registros:
            break
        time.sleep(espera)
    return registros


def main():
    args = build_arg_parser().parse_args()
    token = args.token or os.environ.get("DENUE_TOKEN")
    if not token:
        print("Falta el token DENUE. Pásalo con --token o expórtalo como DENUE_TOKEN.", file=sys.stderr)
        print("Se obtiene gratis en: https://www.inegi.org.mx/app/api/denue/v1/tokenVerify.aspx", file=sys.stderr)
        sys.exit(1)

    output = args.output or f"denue_{args.entidad}_sector{args.sector}.xlsx"

    registros = extraer(args.entidad, args.sector, token, args.bloque, args.max_registros, args.espera)
    if not registros:
        print("No se obtuvo ningún registro.", file=sys.stderr)
        sys.exit(1)

    df = pd.DataFrame(registros)
    total_crudo = len(df)
    if not args.sin_dedup:
        df = deduplicar_por_razon_social(df)

    if output.lower().endswith(".csv"):
        df.to_csv(output, index=False)
    else:
        df.to_excel(output, index=False)

    if not args.sin_dedup:
        print(f"\nEstablecimientos crudos: {total_crudo} -> tras agrupar por razón social: {len(df)}")
    print(f"Total filas exportadas: {len(df)} -> {output}")


if __name__ == "__main__":
    main()
