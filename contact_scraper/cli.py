"""Command-line interface.

Usage:
    python -m contact_scraper https://example.com
    python -m contact_scraper https://a.com https://b.com --json
    python -m contact_scraper --input urls.txt --output resultados.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from typing import List, TextIO

from contact_scraper.models import ContactInfo
from contact_scraper.scraper import DEFAULT_DELAY, DEFAULT_MAX_PAGES, DEFAULT_TIMEOUT, scrape

CSV_FIELDS = [
    "source_url", "contact_page_url", "names", "phones",
    "hours", "city", "country", "address_raw", "warnings",
]


def _read_url_file(path: str) -> List[str]:
    urls = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    return urls


def _print_human(info: ContactInfo, out: TextIO) -> None:
    print(f"URL:              {info.source_url}", file=out)
    print(f"Página de contacto: {info.contact_page_url or '(no encontrada; se usó la página principal)'}", file=out)
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


def _write_csv(results: List[ContactInfo], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for info in results:
            row = info.to_dict()
            writer.writerow(
                {
                    "source_url": row["source_url"],
                    "contact_page_url": row["contact_page_url"] or "",
                    "names": "; ".join(row["names"]),
                    "phones": "; ".join(row["phones"]),
                    "hours": row["hours"] or "",
                    "city": row["city"] or "",
                    "country": row["country"] or "",
                    "address_raw": row["address_raw"] or "",
                    "warnings": " | ".join(row["warnings"]),
                }
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contact_scraper",
        description="Busca la página de contacto de un sitio y extrae nombres, teléfonos, horario y ciudad.",
    )
    parser.add_argument("urls", nargs="*", help="una o más URLs a analizar")
    parser.add_argument("--input", metavar="FILE", help="archivo con una URL por línea")
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
        urls.extend(_read_url_file(args.input))

    if not urls:
        parser.error("no se proporcionó ninguna URL (usa un argumento o --input archivo.txt)")

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
        _write_csv(results, args.output)
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
