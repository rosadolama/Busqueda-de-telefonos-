import csv

from contact_scraper.models import ContactInfo, Person
from contact_scraper.results_io import result_to_csv_row, write_csv


def _sample_info() -> ContactInfo:
    return ContactInfo(
        source_url="https://a.com",
        contact_page_url="https://a.com/contacto",
        team_page_url="https://a.com/equipo",
        names=[Person(name="Juan Pérez", role="Gerente"), Person(name="María Gómez")],
        phones=["+57 300 1112222"],
        hours="Lunes a Viernes: 08:00-18:00",
        hours_raw=["Lunes a Viernes: 08:00-18:00"],
        city="Bogotá",
        country="CO",
        address_raw="Bogotá, CO",
        warnings=["no se encontró un horario de atención"],
    )


def test_result_to_csv_row_joins_lists():
    row = result_to_csv_row(_sample_info())
    assert row["names"] == "Juan Pérez (Gerente); María Gómez"
    assert row["phones"] == "+57 300 1112222"
    assert row["warnings"] == "no se encontró un horario de atención"
    assert row["city"] == "Bogotá"


def test_result_to_csv_row_none_fields_become_empty_string():
    info = ContactInfo(source_url="https://b.com")
    row = result_to_csv_row(info)
    assert row["contact_page_url"] == ""
    assert row["team_page_url"] == ""
    assert row["hours"] == ""
    assert row["city"] == ""
    assert row["names"] == ""


def test_write_csv_round_trips(tmp_path):
    out = tmp_path / "out.csv"
    write_csv([_sample_info()], str(out))

    with open(out, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    assert len(rows) == 1
    assert rows[0]["source_url"] == "https://a.com"
    assert rows[0]["names"] == "Juan Pérez (Gerente); María Gómez"
    assert rows[0]["team_page_url"] == "https://a.com/equipo"
