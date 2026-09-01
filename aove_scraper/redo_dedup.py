"""Rehace verificación + dedup + Fit_ICP sobre el checkpoint crudo ya scrapeado,
sin volver a golpear las fuentes (DOP/AEMO/EVOOLEUM/Flos Olei). Útil tras un
cambio en la lógica de dedup o normalización para medir el impacto sin
re-scrapear.

Orden importante: la verificación de webs va ANTES del dedup, porque el
guard de conflicto de teléfono (dos dominios distintos y verificados no se
fusionan a ciegas) necesita saber qué está "checked" antes de decidir."""
import csv

from utils_comunes import (
    CHECKPOINT_PATH, CompanyRow, apply_fit_icp, dedup_rows, normalize_rows,
    verify_all_webs, write_csv,
)

OUT_PATH = "output/aove_empresas.csv"


def main():
    with open(CHECKPOINT_PATH, encoding="utf-8") as f:
        raw_rows = [CompanyRow.from_csv_dict(d) for d in csv.DictReader(f)]
    print(f"Filas crudas leídas del checkpoint: {len(raw_rows)}")

    normalize_rows(raw_rows)
    verify_all_webs(raw_rows)

    deduped = dedup_rows(raw_rows)
    print(f"Filas tras dedup: {len(deduped)}")
    print(f"Filas fusionadas de más respecto al crudo: {len(raw_rows) - len(deduped)}")

    revisar = [r for r in deduped if r.Revisar_Dedup]
    print(f"Filas marcadas Revisar_Dedup: {len(revisar)}")
    for r in revisar:
        print(f"  {r.Empresa} | {r.Web} | tel {r.Telefono} -> {r.Revisar_Dedup}")

    apply_fit_icp(deduped)

    write_csv(deduped, OUT_PATH)
    print(f"CSV final reescrito en: {OUT_PATH}")


if __name__ == "__main__":
    main()
