from unittest.mock import patch

from contact_scraper import fetcher
from contact_scraper.scraper import scrape

HOME_HTML = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"LocalBusiness","name":"Panaderia Central",
 "telephone":"+57 300 111 2222",
 "address":{"@type":"PostalAddress","streetAddress":"Cra 10 #20-30","addressLocality":"Bogotá","addressCountry":"CO"},
 "openingHoursSpecification":[{"@type":"OpeningHoursSpecification","dayOfWeek":["Monday","Tuesday","Wednesday","Thursday","Friday"],"opens":"08:00","closes":"18:00"}]}
</script>
</head><body>
<nav><a href="/">Inicio</a><a href="/contacto">Contáctenos</a><a href="/equipo">Nuestro Equipo</a></nav>
<footer>Panaderia Central - Bogotá, Colombia</footer>
</body></html>
"""

CONTACT_HTML = """
<html><body>
<h1>Contacto</h1>
<p>Atiende: Sra. Rosa Elena Martínez del Campo</p>
<p>Escríbenos o llámanos al <a href="tel:+573001112222">+57 300 111 2222</a></p>
<p>Horario de atención: Lunes a Viernes de 8:00 a 18:00, Sábados de 9:00 a 13:00.</p>
<p>Nos encontramos en Bogotá, Colombia.</p>
</body></html>
"""

# Real sites (santeclinics.com, clinicaslove.com) list staff only on their
# "about us" page, never on the contact page itself -- this mirrors that.
TEAM_HTML = """
<html><body>
<h1>Nuestro Equipo</h1>
<p>Dr. Andrés Molina</p>
<p>Panadero jefe, 20 años de experiencia.</p>
</body></html>
"""


def _fake_fetch(url, session=None, timeout=15, respect_robots=True):
    if url.rstrip("/") == "https://panaderiacentral.com":
        return fetcher.FetchResult(url=url, status_code=200, html=HOME_HTML)
    if url == "https://panaderiacentral.com/contacto":
        return fetcher.FetchResult(url=url, status_code=200, html=CONTACT_HTML)
    if url == "https://panaderiacentral.com/equipo":
        return fetcher.FetchResult(url=url, status_code=200, html=TEAM_HTML)
    return fetcher.FetchResult(url=url, status_code=404, html=None, error="not found")


def test_full_pipeline_merges_structured_and_text_data():
    with patch("contact_scraper.scraper.fetcher.fetch", side_effect=_fake_fetch):
        info = scrape("https://panaderiacentral.com", delay=0)

    assert info.contact_page_url == "https://panaderiacentral.com/contacto"
    assert info.team_page_url == "https://panaderiacentral.com/equipo"
    assert [(p.name, p.role) for p in info.names] == [
        ("Rosa Elena Martínez del Campo", None),  # next line is a CTA sentence, not a role
        ("Andrés Molina", "Panadero jefe, 20 años de experiencia."),
    ]
    assert info.phones == ["+57 300 1112222"]  # JSON-LD + tel: link + text collapse into one
    assert info.hours == "Lunes, Martes, Miércoles, Jueves, Viernes: 08:00–18:00"
    assert "Lunes a Viernes de 8:00 a 18:00" in info.hours_raw
    assert info.city == "Bogotá"
    assert info.country == "CO"
    assert info.warnings == []


def test_team_page_found_even_when_site_has_no_contact_page():
    # Real case (santeclinics.com): no "Contacto" link or page exists at
    # all, but there IS a real "Sobre Nosotros" link with the team roster.
    # Guessing /contacto, /contact-us, etc. must not burn the whole page
    # budget before the known team link ever gets a turn.
    home_html = """
    <html><body>
    <nav><a href="/">Inicio</a><a href="/sobre-nosotros">Sobre Nosotros</a></nav>
    </body></html>
    """

    def fetch_no_contact_page(url, session=None, timeout=15, respect_robots=True):
        if url.rstrip("/") == "https://clinicasin.example":
            return fetcher.FetchResult(url=url, status_code=200, html=home_html)
        if url == "https://clinicasin.example/sobre-nosotros":
            return fetcher.FetchResult(url=url, status_code=200, html=TEAM_HTML)
        return fetcher.FetchResult(url=url, status_code=404, html=None, error="not found")

    with patch("contact_scraper.scraper.fetcher.fetch", side_effect=fetch_no_contact_page):
        info = scrape("https://clinicasin.example", delay=0)

    assert info.contact_page_url is None
    assert info.team_page_url == "https://clinicasin.example/sobre-nosotros"
    assert [(p.name, p.role) for p in info.names] == [("Andrés Molina", "Panadero jefe, 20 años de experiencia.")]


def test_falls_back_to_www_variant_when_bare_domain_fails():
    # Mirrors a real case (factoriaderesultados.com): the bare domain fails
    # (SSL error, DNS, whatever) but "www." works fine.
    def fetch_only_www(url, session=None, timeout=15, respect_robots=True):
        if url == "https://panaderiacentral.com":
            return fetcher.FetchResult(url=url, status_code=None, html=None, error="ssl error")
        if url == "https://www.panaderiacentral.com":
            return fetcher.FetchResult(url=url, status_code=200, html=HOME_HTML)
        return fetcher.FetchResult(url=url, status_code=404, html=None, error="not found")

    with patch("contact_scraper.scraper.fetcher.fetch", side_effect=fetch_only_www):
        info = scrape("https://panaderiacentral.com", delay=0, max_pages=1)

    assert info.phones == ["+57 300 1112222"]
    assert any("www.panaderiacentral.com" in w for w in info.warnings)


def test_homepage_fetch_failure_is_reported_not_raised():
    def failing_fetch(url, session=None, timeout=15, respect_robots=True):
        return fetcher.FetchResult(url=url, status_code=None, html=None, error="timeout")

    with patch("contact_scraper.scraper.fetcher.fetch", side_effect=failing_fetch):
        info = scrape("https://doesnotresolve.example", delay=0)

    assert info.phones == []
    assert info.names == []
    assert any("no se pudo obtener" in w for w in info.warnings)


def test_normalizes_url_missing_scheme():
    with patch("contact_scraper.scraper.fetcher.fetch", side_effect=_fake_fetch):
        info = scrape("panaderiacentral.com", delay=0)
    assert info.source_url == "https://panaderiacentral.com"


def test_empty_url_raises_value_error():
    import pytest

    with pytest.raises(ValueError):
        scrape("")
    with pytest.raises(ValueError):
        scrape("   ")
