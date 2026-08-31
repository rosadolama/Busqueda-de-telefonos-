from contact_scraper.extractors.hours import best_hours_text, extract_hours


def test_simple_day_range_and_time_range():
    text = "Horario de atención: Lunes a Viernes de 8:00 a 18:00, Sábados de 9:00 a 13:00."
    result = extract_hours(text)
    assert "Lunes a Viernes de 8:00 a 18:00" in result
    assert "Sábados de 9:00 a 13:00" in result


def test_abbreviated_days_with_dash_range():
    assert extract_hours("Nuestro horario: Lun-Vie 08:00-17:00") == ["Lun-Vie 08:00-17:00"]


def test_todos_los_dias_variant():
    assert extract_hours("Abrimos todos los días de 9:00 a 18:00.") == ["todos los días de 9:00 a 18:00"]


def test_keyword_without_day_or_time_returns_nothing():
    assert extract_hours("Horario de atención: consulta nuestras redes sociales.") == []


def test_unrelated_text_returns_nothing():
    text = "Somos una empresa fundada en 2015. Contáctenos para más información."
    assert extract_hours(text) == []


def test_best_hours_text_picks_first():
    assert best_hours_text(["A", "B"]) == "A"
    assert best_hours_text([]) is None
