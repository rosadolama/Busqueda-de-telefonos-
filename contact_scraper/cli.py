"""Command-line interface.

Usage:
    python -m contact_scraper https://example.com
    python -m contact_scraper https://a.com https://b.com --json
    python -m contact_scraper --input urls.txt --output resultados.csv
    python -m contact_scraper --input urls.csv --output resultados.csv
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import List, TextIO

from contact_scraper.models import ContactInfo
from contact_scraper.results_io import write_csv
from contact_scraper.scraper import DEFAULT_DELAY, DEFAULT_MAX_PAGES, DEFAULT_TIMEOUT, scrape
from contact_scraper.url_sources import read_urls_from_file


def _print_human(info: ContactInfo, out: TextIO) -> None:
    print(f"URL:              {info.source_url}", file=out)
    print(f"Página de contacto: {info.contact_page_url or '(no encontrada; se usó la página principal)'}", file=out)
    print(f"Página de equipo: {info.team_page_url or '(no encontrada)'}", file=out)
    print(f"Nombres:          {', '.join(info.names) or '(ninguno encontrado)'}", file=out)
    print(f"Teléfonos:        {', '.join(info.phones) or '(ninguno encontrado)'}", file=out)
    print(f"Horario:          {info.hours or '(no encontrado)'}", file=out)
    print(f"Ciudad probable:  {info.city or '(no determinada)'}", file=out)
    if info.country:
        print(f"País:             {info.country}", file=out)
    if info.address_raw:
        print(f"Dirección (texto): {info.address_raw}", file=out)
    if info.warnings:
        print("Avisos:", file=out)
        for w in info.warnings:
            print(f"  - {w}", file=out)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contact_scraper",
        description="Busca la página de contacto de un sitio y extrae nombres, teléfonos, horario y ciudad.",
    )
    parser.add_argument("urls", nargs="*", help="una o más URLs a analizar")
    parser.add_argument("--input", metavar="FILE", help="archivo .txt (una URL por línea) o .csv con las URLs")
    parser.add_argument("--output", metavar="FILE.csv", help="guarda los resultados en un CSV en vez de imprimirlos")
    parser.add_argument("--json", action="store_true", help="imprime los resultados como JSON")
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES, help="máximo de páginas a visitar por sitio (default: %(default)s)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="timeout por solicitud en segundos (default: %(default)s)")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="pausa entre solicitudes al mismo sitio, en segundos (default: %(default)s)")
    parser.add_argument("--ignore-robots", action="store_true", help="no respetar robots.txt (úsalo solo si tienes autorización del sitio)")
    parser.add_argument("--use-spacy", action="store_true", help="usa spaCy (si está instalado) para mejorar la detección de nombres")
    parser.add_argument("--verbose", action="store_true", help="muestra progreso en stderr")
    return parser


def main(argv: List[str] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    urls = list(args.urls)
    if args.input:
        urls.extend(read_urls_from_file(args.input))

    if not urls:
        parser.error("no se proporcionó ninguna URL (usa un argumento o --input archivo.txt/.csv)")

    results: List[ContactInfo] = []
    for i, url in enumerate(urls):
        if args.verbose:
            print(f"[{i + 1}/{len(urls)}] procesando {url} ...", file=sys.stderr)
        try:
            info = scrape(
                url,
                max_pages=args.max_pages,
                timeout=args.timeout,
                delay=args.delay,
                respect_robots=not args.ignore_robots,
                use_spacy=args.use_spacy,
            )
        except ValueError as exc:
            info = ContactInfo(source_url=url, warnings=[f"URL inválida: {exc}"])
        results.append(info)

    if args.output:
        write_csv(results, args.output)
        if args.verbose:
            print(f"Resultados guardados en {args.output}", file=sys.stderr)
        return 0

    if args.json:
        json.dump([r.to_dict() for r in results], sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 0

    for i, info in enumerate(results):
        if i > 0:
            print("-" * 60)
        _print_human(info, sys.stdout)

    return 0


if __name__ == "__main__":
    sys.exit(main())
