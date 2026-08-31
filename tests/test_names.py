from contact_scraper.extractors.names import extract_names


def test_honorific_prefix():
    text = "Para más información contacte a Lic. María Fernanda Gómez al siguiente número."
    assert extract_names(text) == ["María Fernanda Gómez"]


def test_label_prefix_stops_at_line_break():
    text = "Contacto: Juan Pérez\nTeléfono: 3001234567"
    assert extract_names(text) == ["Juan Pérez"]


def test_compound_surname_with_connector():
    text = "Atiende: Sra. Rosa Elena Martínez del Campo"
    assert extract_names(text) == ["Rosa Elena Martínez del Campo"]


def test_company_name_after_label_is_rejected():
    assert extract_names("Contacto: Distribuidora Nacional S.A.S.") == []
    assert extract_names("Contacto: Distribuidora Nacional Ltda.") == []
    assert extract_names("Contacto: ACME Inc.") == []


def test_no_names_in_generic_footer():
    text = "Horario: Lunes a Viernes de 8 a 18.\nCopyright 2024 Todos Los Derechos Reservados."
    assert extract_names(text) == []


def test_dedup_preserves_first_occurrence_order():
    text = "Gerente: Carlos Andrés Ruiz. También puede escribir a Lic. Carlos Andrés Ruiz directamente."
    assert extract_names(text) == ["Carlos Andrés Ruiz"]
