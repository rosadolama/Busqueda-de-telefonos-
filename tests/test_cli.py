import csv
import json
from unittest.mock import patch

from contact_scraper.cli import main
from contact_scraper.models import ContactInfo, Person


def _fake_info(url):
    return ContactInfo(
        source_url=url,
        contact_page_url=url.rstrip("/") + "/contacto",
        team_page_url=url.rstrip("/") + "/equipo",
        names=[Person(name="Juan Pérez")],
        phones=["+57 300 1112222"],
        hours="Lunes a Viernes: 08:00-18:00",
        hours_raw=["Lunes a Viernes: 08:00-18:00"],
        city="Bogotá",
        country="CO",
        address_raw="Bogotá, CO",
        warnings=[],
    )


def test_json_output_multiple_urls(capsys):
    with patch("contact_scraper.cli.scrape", side_effect=lambda url, **kw: _fake_info(url)):
        code = main(["https://a.com", "https://b.com", "--json"])
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out) == 2
    assert out[0]["source_url"] == "https://a.com"
    assert out[0]["phones"] == ["+57 300 1112222"]
    assert out[0]["names"] == [{"name": "Juan Pérez", "role": None}]


def test_human_output_single_url(capsys):
    with patch("contact_scraper.cli.scrape", side_effect=lambda url, **kw: _fake_info(url)):
        code = main(["https://a.com"])
    assert code == 0
    out = capsys.readouterr().out
    assert "Juan Pérez" in out
    assert "+57 300 1112222" in out
    assert "Bogotá" in out


def test_csv_output(tmp_path):
    out_file = tmp_path / "resultados.csv"
    with patch("contact_scraper.cli.scrape", side_effect=lambda url, **kw: _fake_info(url)):
        code = main(["https://a.com", "https://b.com", "--output", str(out_file)])
    assert code == 0

    with open(out_file, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 2
    assert rows[0]["names"] == "Juan Pérez"
    assert rows[0]["phones"] == "+57 300 1112222"
    assert rows[0]["city"] == "Bogotá"
    assert rows[0]["team_page_url"] == "https://a.com/equipo"


def test_input_file_is_merged_with_positional_urls(tmp_path):
    url_file = tmp_path / "urls.txt"
    url_file.write_text("# comentario\nhttps://c.com\n\nhttps://d.com\n", encoding="utf-8")

    seen = []

    def fake_scrape(url, **kw):
        seen.append(url)
        return _fake_info(url)

    with patch("contact_scraper.cli.scrape", side_effect=fake_scrape):
        code = main(["https://a.com", "--input", str(url_file), "--json"])
    assert code == 0
    assert seen == ["https://a.com", "https://c.com", "https://d.com"]


def test_no_urls_is_a_usage_error(capsys):
    import pytest

    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code != 0
    assert "usage" in capsys.readouterr().err.lower()
