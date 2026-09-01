"""Orquestador de directorios de empresas por nicho.

Cada nicho vive en su propia carpeta bajo sources/<nicho>/, con un parser
por fuente (cada uno expone scrape() -> list[CompanyRow] y un SOURCE_NAME).
Este script descubre esos parsers dinámicamente, los ejecuta, y pasa el
resultado combinado a utils_comunes.py para normalizar, verificar,
deduplicar, puntuar y exportar.

Para un nicho nuevo (quesos, vino...): crear sources/<nicho>/ con sus
parsers siguiendo el mismo patrón que sources/aove/, y correr
`python main.py --nicho <nicho>`. No hace falta tocar este archivo ni
utils_comunes.py.
"""
import argparse
import importlib
import logging
import pkgutil
import sys
import time
from pathlib import Path

from utils_comunes import (
    CHECKPOINT_PATH, CompanyRow, VERIFY_WORKERS, apply_fit_icp, dedup_rows,
    init_checkpoint, normalize_rows, verify_all_webs, write_csv,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("scraper")

SOURCES_DIR = Path(__file__).parent / "sources"


def _available_nichos() -> list[str]:
    if not SOURCES_DIR.is_dir():
        return []
    return sorted(
        p.name for p in SOURCES_DIR.iterdir()
        if p.is_dir() and not p.name.startswith("__") and (p / "__init__.py").exists()
    )


def discover_parsers(nicho: str) -> list:
    """Importa dinámicamente todos los módulos de sources/<nicho>/ que
    expongan scrape() y SOURCE_NAME (el contrato mínimo de un parser).
    Módulos sin ese contrato (helpers, __init__) se ignoran en silencio."""
    niche_dir = SOURCES_DIR / nicho
    if not niche_dir.is_dir():
        disponibles = _available_nichos()
        listado = ", ".join(disponibles) if disponibles else "(ninguno encontrado en sources/)"
        print(f"Nicho '{nicho}' no encontrado en sources/. Nichos disponibles: {listado}", file=sys.stderr)
        sys.exit(1)

    package_name = f"sources.{nicho}"
    modules = []
    for module_info in sorted(pkgutil.iter_modules([str(niche_dir)]), key=lambda m: m.name):
        if module_info.ispkg:
            continue
        module = importlib.import_module(f"{package_name}.{module_info.name}")
        if hasattr(module, "scrape") and hasattr(module, "SOURCE_NAME"):
            modules.append(module)

    if not modules:
        print(f"Nicho '{nicho}' existe en sources/ pero no tiene ningún parser válido (sin scrape()/SOURCE_NAME).", file=sys.stderr)
        sys.exit(1)

    return modules


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Scraper de directorios de empresas, organizado por nicho (uno por carpeta en sources/).",
        epilog=(
            "Ejemplos:\n"
            "  python main.py --nicho aove\n"
            "  python main.py --nicho quesos\n"
            "\n"
            "Para un nicho nuevo: crear sources/<nicho>/ con parsers que expongan\n"
            "scrape() -> list[CompanyRow] y SOURCE_NAME, siguiendo el patrón de\n"
            "sources/aove/. No hace falta tocar main.py ni utils_comunes.py."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--nicho",
        required=True,
        help="Carpeta en sources/ a scrapear (p.ej. 'aove'). Nichos disponibles: "
        + (", ".join(_available_nichos()) or "(ninguno)"),
    )
    return parser


def main():
    args = build_arg_parser().parse_args()
    nicho = args.nicho
    out_path = f"output/{nicho}_empresas.csv"

    modules = discover_parsers(nicho)
    print(f"Nicho: {nicho} | fuentes encontradas: {len(modules)} ({', '.join(m.SOURCE_NAME for m in modules)})")

    init_checkpoint()
    print(f"Checkpoint crudo (append en vivo): {CHECKPOINT_PATH}")

    all_rows: list[CompanyRow] = []
    per_source_counts: dict[str, int] = {}
    scrape_timings: dict[str, float] = {}

    t_scrape_start = time.perf_counter()
    for module in modules:
        t0 = time.perf_counter()
        try:
            rows = module.scrape()
        except Exception as exc:  # noqa: BLE001 - ninguna fuente debe tumbar el script
            logger.error("FUENTE FALLIDA: %s | motivo: %s", module.SOURCE_NAME, exc)
            rows = []
        elapsed = time.perf_counter() - t0
        scrape_timings[module.SOURCE_NAME] = elapsed
        per_source_counts[module.SOURCE_NAME] = len(rows)
        print(f"{module.SOURCE_NAME}: {len(rows)} filas crudas ({elapsed:.1f}s)")
        all_rows.extend(rows)
    t_scrape_total = time.perf_counter() - t_scrape_start

    normalize_rows(all_rows)

    # Verificación ANTES del dedup: el guard de conflicto de teléfono en
    # dedup_rows necesita saber qué domino está "checked" antes de decidir.
    t_verify_start = time.perf_counter()
    verify_all_webs(all_rows)
    t_verify_total = time.perf_counter() - t_verify_start

    deduped = dedup_rows(all_rows)
    apply_fit_icp(deduped)

    write_csv(deduped, out_path)

    _print_summary(per_source_counts, all_rows, deduped, scrape_timings, t_scrape_total, t_verify_total, out_path)


def _print_summary(per_source_counts, raw_rows, deduped, scrape_timings, t_scrape_total, t_verify_total, out_path):
    total_raw = len(raw_rows)
    total_dedup = len(deduped)
    verified = sum(1 for r in deduped if r.Verificada_WEB == "checked")
    with_contact = sum(1 for r in deduped if r.Telefono or r.Email)
    fit_alto = sum(1 for r in deduped if r.Fit_ICP == "alto")
    fit_bajo = sum(1 for r in deduped if r.Fit_ICP == "bajo")
    fit_revisar = sum(1 for r in deduped if r.Fit_ICP == "revisar")

    print("\n=== TIEMPOS ===")
    for source, elapsed in scrape_timings.items():
        print(f"  scraping {source}: {elapsed:.1f}s")
    print(f"  scraping TOTAL: {t_scrape_total:.1f}s")
    print(f"  verificación de webs ({VERIFY_WORKERS} workers): {t_verify_total:.1f}s")
    print(f"  TOTAL script: {t_scrape_total + t_verify_total:.1f}s")

    print("\n=== RESUMEN ===")
    print("Filas por fuente (crudas):")
    for source, count in per_source_counts.items():
        print(f"  {source}: {count}")
    print(f"Total filas crudas: {total_raw}")
    print(f"Filas tras dedup: {total_dedup}")
    if total_dedup:
        print(f"Webs verificadas (checked): {verified}/{total_dedup} ({verified/total_dedup:.0%})")
        print(f"Filas con al menos un contacto (tel o email): {with_contact}/{total_dedup} ({with_contact/total_dedup:.0%})")
        print(f"Fit_ICP -> alto: {fit_alto} ({fit_alto/total_dedup:.0%}) | bajo: {fit_bajo} | revisar: {fit_revisar}")

    no_checked = [r for r in deduped if r.Verificada_WEB != "checked" and r.Web]
    if no_checked:
        print(f"\n--- Debug: {len(no_checked)} filas con web pero sin 'checked' ---")
        for row in no_checked:
            print(f"  {row.Empresa} | {row.Web} -> {row.verify_detail}")

    revisar = [r for r in deduped if r.Revisar_Dedup]
    if revisar:
        print(f"\n--- Revisar_Dedup: {len(revisar)} filas con conflicto de fusión sin resolver automáticamente ---")
        for row in revisar:
            print(f"  {row.Empresa} | {row.Web} | tel {row.Telefono} -> {row.Revisar_Dedup}")

    print(f"\nCSV combinado (deduplicado y verificado) escrito en: {out_path}")
    print(f"Checkpoint crudo (cada fila, en el instante en que se scrapeó): {CHECKPOINT_PATH}")


if __name__ == "__main__":
    main()
