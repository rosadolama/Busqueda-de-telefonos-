"""Headless GUI tests (need a real Tk display -- run under xvfb-run on Linux).

Skipped automatically if tkinter isn't installed or no display is available,
so `pytest` still runs cleanly on a machine without either.
"""
import time
from unittest.mock import patch

import pytest

tk = pytest.importorskip("tkinter")

from contact_scraper.models import ContactInfo  # noqa: E402
from contact_scraper.results_io import write_csv  # noqa: E402

try:
    _probe = tk.Tk()
    _probe.destroy()
    _HAS_DISPLAY = True
except tk.TclError:
    _HAS_DISPLAY = False

pytestmark = pytest.mark.skipif(not _HAS_DISPLAY, reason="no Tk display available")


def _pump_until(root, condition, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        root.update()
        if condition():
            return True
        time.sleep(0.05)
    return False


def test_gui_batch_populates_table_and_exports_csv(tmp_path):
    from contact_scraper.gui import App

    def fake_scrape(url, **kwargs):
        return ContactInfo(source_url=url, phones=["+57 300 1112222"], city="Bogotá", warnings=[])

    root = tk.Tk()
    try:
        app = App(root)
        csv_path = tmp_path / "urls.csv"
        csv_path.write_text("url\nhttps://a.com\nhttps://b.com\n", encoding="utf-8")
        app.csv_path = str(csv_path)
        app.start_button.config(state="normal")

        with patch("contact_scraper.gui.scrape", side_effect=fake_scrape):
            app._start()
            assert _pump_until(root, lambda: len(app.results) >= 2)

        assert len(app.tree.get_children()) == 2
        assert str(app.save_button["state"]) == "normal"
        assert app.results[0].source_url == "https://a.com"
        assert app.results[0].phones == ["+57 300 1112222"]

        out_csv = tmp_path / "out.csv"
        write_csv(app.results, str(out_csv))
        content = out_csv.read_text(encoding="utf-8")
        assert "https://a.com" in content
        assert "Bogotá" in content
    finally:
        root.destroy()


def test_gui_one_bad_url_does_not_stop_the_batch(tmp_path):
    from contact_scraper.gui import App

    def flaky_scrape(url, **kwargs):
        if "bad" in url:
            raise RuntimeError("boom - simulated crash")
        return ContactInfo(source_url=url, phones=["+1 555 0100"], warnings=[])

    root = tk.Tk()
    try:
        app = App(root)
        csv_path = tmp_path / "urls.csv"
        csv_path.write_text("url\nhttps://good1.com\nhttps://bad.com\nhttps://good2.com\n", encoding="utf-8")
        app.csv_path = str(csv_path)
        app.start_button.config(state="normal")

        with patch("contact_scraper.gui.scrape", side_effect=flaky_scrape):
            app._start()
            assert _pump_until(root, lambda: len(app.results) >= 3)

        assert len(app.results) == 3
        bad = app.results[1]
        assert bad.source_url == "https://bad.com"
        assert any("Error inesperado" in w for w in bad.warnings)
        assert app.results[2].phones == ["+1 555 0100"]
    finally:
        root.destroy()


def test_gui_stop_halts_before_remaining_urls(tmp_path):
    from contact_scraper.gui import App

    def slow_scrape(url, **kwargs):
        time.sleep(0.2)
        return ContactInfo(source_url=url, warnings=[])

    root = tk.Tk()
    try:
        app = App(root)
        csv_path = tmp_path / "urls.csv"
        csv_path.write_text("url\n" + "\n".join(f"https://site{i}.com" for i in range(10)) + "\n", encoding="utf-8")
        app.csv_path = str(csv_path)
        app.start_button.config(state="normal")

        with patch("contact_scraper.gui.scrape", side_effect=slow_scrape):
            app._start()
            assert _pump_until(root, lambda: len(app.results) >= 1)
            app._stop()
            assert _pump_until(root, lambda: str(app.start_button["state"]) == "normal")

        assert len(app.results) < 10
    finally:
        root.destroy()
