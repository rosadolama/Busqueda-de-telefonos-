from contact_scraper.contact_page_finder import (
    find_contact_links,
    find_team_links,
    guess_common_paths,
    guess_team_common_paths,
)

HOMEPAGE_HTML = """
<html><body>
<nav>
  <a href="/">Inicio</a>
  <a href="/nosotros">Quiénes somos</a>
  <a href="/productos">Productos</a>
  <a href="/contacto">Contáctenos</a>
  <a href="https://facebook.com/miempresa">Contact us on Facebook</a>
</nav>
<footer><a href="/blog">Blog</a></footer>
</body></html>
"""


def test_picks_onsite_contact_link_and_skips_offsite():
    links = find_contact_links("https://miempresa.com", HOMEPAGE_HTML)
    assert links == ["https://miempresa.com/contacto"]


def test_no_candidates_when_nothing_matches():
    html = "<html><body><a href='/productos'>Productos</a></body></html>"
    assert find_contact_links("https://miempresa.com", html) == []


def test_relative_link_resolved_against_base_url():
    html = "<a href='contact-us'>Contact Us</a>"
    links = find_contact_links("https://example.com/en/", html)
    assert links == ["https://example.com/en/contact-us"]


def test_common_paths_are_same_origin():
    paths = guess_common_paths("https://miempresa.com/somewhere/deep")
    assert all(p.startswith("https://miempresa.com/") for p in paths)
    assert "https://miempresa.com/contacto" in paths


def test_picks_onsite_team_link_not_the_contact_one():
    # "Quiénes somos" is where staff names live (santeclinics.com,
    # clinicaslove.com both put their team roster there, never on /contacto).
    links = find_team_links("https://miempresa.com", HOMEPAGE_HTML)
    assert links == ["https://miempresa.com/nosotros"]


def test_team_common_paths_are_same_origin():
    paths = guess_team_common_paths("https://miempresa.com/somewhere/deep")
    assert all(p.startswith("https://miempresa.com/") for p in paths)
    assert "https://miempresa.com/nosotros" in paths
    assert "https://miempresa.com/equipo" in paths
