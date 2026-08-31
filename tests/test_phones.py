from contact_scraper.extractors.phones import canonicalize, extract_phones, guess_region_from_phones


def test_finds_international_number_without_any_hint():
    text = "Escríbenos o llámanos al +57 300 111 2222 con gusto te atendemos."
    assert extract_phones(text) == ["+57 300 1112222"]


def test_finds_tel_link():
    html = '<a href="tel:+525512345678">Llamar</a>'
    assert extract_phones("", html=html) == ["+52 55 1234 5678"]


def test_local_format_uses_domain_country_hint():
    text = "Nuestro fijo es (601) 234-5678 para consultas."
    result = extract_phones(text, source_url="https://miempresa.com.co")
    assert result == ["+57 601 2345678"]


def test_ambiguous_local_span_is_not_reported_twice():
    # "(601) 234-5678" is a *valid* number under both CO and US numbering
    # plans; the higher-priority guessed region should win once, not both.
    text = "Fijo (601) 234-5678 y celular +57 300 123 4567."
    result = extract_phones(text, source_url="https://miempresa.com.co")
    assert result.count("+57 601 2345678") + result.count("+1 601-234-5678") == 1
    assert "+57 300 1234567" in result


def test_no_false_positive_on_plain_numbers():
    text = "Fundada en 1998, con más de 20 sucursales y 4500 empleados."
    assert extract_phones(text) == []


def test_canonicalize_matches_extract_phones_formatting():
    formatted = canonicalize("+57 300 111 2222")
    assert formatted == "+57 300 1112222"
    assert extract_phones("Tel: +57 300 111 2222") == [formatted]


def test_canonicalize_rejects_invalid_number():
    assert canonicalize("123") is None


def test_guess_region_from_phones():
    assert guess_region_from_phones(["+57 300 1112222"]) == "CO"
    assert guess_region_from_phones(["not a phone"]) is None
