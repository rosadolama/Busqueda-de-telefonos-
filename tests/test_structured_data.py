from bs4 import BeautifulSoup

from contact_scraper.structured_data import (
    extract_json_ld,
    extract_meta_geo,
    extract_microdata,
    summarize_structured_data,
)

JSON_LD_HTML = """
<html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "LocalBusiness",
  "name": "Panaderia Central",
  "telephone": "+57 300 111 2222",
  "address": {
    "@type": "PostalAddress",
    "streetAddress": "Cra 10 #20-30",
    "addressLocality": "Bogotá",
    "addressCountry": "CO"
  },
  "openingHoursSpecification": [
    {"@type": "OpeningHoursSpecification", "dayOfWeek": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"], "opens": "08:00", "closes": "18:00"}
  ],
  "employee": {"@type": "Person", "name": "Rosa Martínez"}
}
</script>
</head><body></body></html>
"""

MICRODATA_HTML = """
<div itemscope itemtype="https://schema.org/LocalBusiness">
  <span itemprop="telephone">+52 55 1234 5678</span>
  <span itemprop="addressLocality">Ciudad de México</span>
  <span itemprop="addressCountry">MX</span>
</div>
"""


def test_extract_and_summarize_json_ld():
    soup = BeautifulSoup(JSON_LD_HTML, "lxml")
    nodes = extract_json_ld(soup)
    assert len(nodes) == 1

    summary = summarize_structured_data(nodes)
    assert summary["phones"] == ["+57 300 111 2222"]
    assert summary["names"] == ["Rosa Martínez"]
    assert summary["address"]["locality"] == "Bogotá"
    assert summary["address"]["country"] == "CO"
    assert summary["hours"] == ["Lunes, Martes, Miércoles, Jueves, Viernes: 08:00–18:00"]


def test_address_country_as_nested_object_not_raw_string():
    # schema.org allows addressCountry to be a full Country object instead
    # of a plain ISO code string; the "raw" address must not leak Python's
    # dict repr, and "country" should fall back to the object's name.
    html = """
    <script type="application/ld+json">
    {"@type": "LocalBusiness", "telephone": "+51 1 234 5678",
     "address": {"@type": "PostalAddress", "addressLocality": "Lima",
                 "addressCountry": {"@type": "Country", "name": "Perú"}}}
    </script>
    """
    soup = BeautifulSoup(html, "lxml")
    summary = summarize_structured_data(extract_json_ld(soup))
    assert summary["address"]["country"] == "Perú"
    assert "{" not in summary["address"]["raw"]
    assert "Perú" in summary["address"]["raw"]


def test_malformed_json_ld_is_ignored_not_fatal():
    html = '<script type="application/ld+json">{not valid json</script>'
    soup = BeautifulSoup(html, "lxml")
    assert extract_json_ld(soup) == []


def test_microdata_fallback():
    soup = BeautifulSoup(MICRODATA_HTML, "lxml")
    result = extract_microdata(soup)
    assert result["phones"] == ["+52 55 1234 5678"]
    assert result["address"]["locality"] == "Ciudad de México"
    assert result["address"]["country"] == "MX"


def test_meta_geo_placename():
    soup = BeautifulSoup('<meta name="geo.placename" content="Lima">', "lxml")
    assert extract_meta_geo(soup) == "Lima"


def test_meta_geo_absent():
    soup = BeautifulSoup("<html></html>", "lxml")
    assert extract_meta_geo(soup) is None
