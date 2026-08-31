from contact_scraper.url_sources import read_urls_from_csv, read_urls_from_file, read_urls_from_txt


def test_txt_ignores_blank_lines_and_comments(tmp_path):
    path = tmp_path / "urls.txt"
    path.write_text("https://a.com\n\n# a comment\nhttps://b.com\n", encoding="utf-8")
    assert read_urls_from_txt(str(path)) == ["https://a.com", "https://b.com"]


def test_csv_with_url_header(tmp_path):
    path = tmp_path / "urls.csv"
    path.write_text("url\nhttps://a.com\nhttps://b.com\n", encoding="utf-8")
    assert read_urls_from_csv(str(path)) == ["https://a.com", "https://b.com"]


def test_csv_with_spanish_header_variant(tmp_path):
    path = tmp_path / "urls.csv"
    path.write_text("Sitio Web\nhttps://a.com\nhttps://b.com\n", encoding="utf-8")
    assert read_urls_from_csv(str(path)) == ["https://a.com", "https://b.com"]


def test_csv_no_header_bare_urls(tmp_path):
    path = tmp_path / "urls.csv"
    path.write_text("https://a.com\nhttps://b.com\n", encoding="utf-8")
    assert read_urls_from_csv(str(path)) == ["https://a.com", "https://b.com"]


def test_csv_url_column_not_first(tmp_path):
    path = tmp_path / "urls.csv"
    path.write_text("Nombre,URL\nClinica A,https://a.com\nClinica B,https://b.com\n", encoding="utf-8")
    assert read_urls_from_csv(str(path)) == ["https://a.com", "https://b.com"]


def test_csv_bare_domains_without_scheme(tmp_path):
    path = tmp_path / "urls.csv"
    path.write_text("a.com\nb.com\n", encoding="utf-8")
    assert read_urls_from_csv(str(path)) == ["a.com", "b.com"]


def test_csv_skips_blank_rows_and_cells(tmp_path):
    path = tmp_path / "urls.csv"
    path.write_text("url\nhttps://a.com\n\nhttps://b.com\n", encoding="utf-8")
    assert read_urls_from_csv(str(path)) == ["https://a.com", "https://b.com"]


def test_empty_csv_returns_empty_list(tmp_path):
    path = tmp_path / "urls.csv"
    path.write_text("", encoding="utf-8")
    assert read_urls_from_csv(str(path)) == []


def test_read_urls_from_file_dispatches_on_extension(tmp_path):
    csv_path = tmp_path / "urls.csv"
    csv_path.write_text("url\nhttps://a.com\n", encoding="utf-8")
    txt_path = tmp_path / "urls.txt"
    txt_path.write_text("https://b.com\n", encoding="utf-8")

    assert read_urls_from_file(str(csv_path)) == ["https://a.com"]
    assert read_urls_from_file(str(txt_path)) == ["https://b.com"]
