from contact_scraper.extractors.city import find_address_snippet, guess_city


def test_city_found_via_address_label():
    text = "Estamos ubicados en la Calle 93 #11-27, Bogotá, Colombia. Tel: 3001234567"
    snippet = find_address_snippet(text)
    assert snippet is not None
    result = guess_city(text, preferred_country="CO", address_snippet=snippet)
    assert result["city"] == "Bogotá"
    assert result["countrycode"] == "CO"
    assert result["from_address_line"] is True


def test_city_found_in_plain_text_with_country_hint():
    text = "Visítanos en nuestra tienda de Guadalajara, Jalisco. Horario de 9 a 6."
    result = guess_city(text, preferred_country="MX")
    assert result["city"] == "Guadalajara"


def test_no_country_hint_and_low_population_city_is_not_reported():
    # Generic marketing copy naming a region, not an address, and no strong signal either way.
    text = "Empresa líder en soluciones de software para toda Latinoamérica."
    assert guess_city(text) is None


def test_boilerplate_footer_has_no_city():
    text = "Copyright 2024 Todos los derechos reservados. Política de privacidad."
    assert guess_city(text) is None


def test_first_mentioned_city_wins_when_several_are_equally_plausible():
    text = "Sucursal en Medellín y también en Cali. Escríbenos."
    result = guess_city(text, preferred_country="CO")
    assert result["city"] == "Medellín"
