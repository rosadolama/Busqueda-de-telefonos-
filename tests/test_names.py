from contact_scraper.extractors.names import clean_person_name, extract_names


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


def test_clean_person_name_strips_honorific_and_trailing_emoji():
    # Real case (santeclinics.com): the site's own schema.org Person "name"
    # field contains the raw display string, title and flag emoji included.
    assert clean_person_name("Dr. Ignacio Navarro 🇺🇸 🇪🇸") == "Ignacio Navarro"
    assert clean_person_name("Dra. Alejandra Herrera 🇺🇸 🇪🇸 🇫🇷") == "Alejandra Herrera"


def test_clean_person_name_keeps_single_word_name():
    assert clean_person_name("Roma 🇺🇸 🇪🇸 🇷🇺") == "Roma"


def test_clean_person_name_noop_on_already_clean_name():
    assert clean_person_name("Wanda Medina") == "Wanda Medina"


def test_clean_person_name_still_rejects_company_suffix():
    assert clean_person_name("Distribuidora Nacional S.A.S.") is None


def test_clean_person_name_empty_input():
    assert clean_person_name("") is None


def test_all_caps_name_matched_and_title_cased():
    # Real case (factoriaderesultados.com): team names rendered in all caps.
    assert extract_names("Contacto: ELOY OCAMPO") == ["Eloy Ocampo"]


def test_all_caps_name_without_trigger_is_still_ignored():
    # No honorific/label -> still no guess, same as any other bare name.
    assert extract_names("ELOY OCAMPO\nTrafficker Digital") == []
