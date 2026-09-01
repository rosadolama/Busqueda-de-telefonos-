from contact_scraper.extractors.names import clean_person_name, extract_names


def _names(text, **kw):
    return [p.name for p in extract_names(text, **kw)]


def _pairs(text, **kw):
    return [(p.name, p.role) for p in extract_names(text, **kw)]


def test_honorific_prefix():
    text = "Para más información contacte a Lic. María Fernanda Gómez al siguiente número."
    assert _names(text) == ["María Fernanda Gómez"]


def test_label_prefix_stops_at_line_break():
    text = "Contacto: Juan Pérez\nTeléfono: 3001234567"
    assert _pairs(text) == [("Juan Pérez", None)]  # phone number line is not a role


def test_compound_surname_with_connector():
    text = "Atiende: Sra. Rosa Elena Martínez del Campo"
    assert _names(text) == ["Rosa Elena Martínez del Campo"]


def test_company_name_after_label_is_rejected():
    assert _names("Contacto: Distribuidora Nacional S.A.S.") == []
    assert _names("Contacto: Distribuidora Nacional Ltda.") == []
    assert _names("Contacto: ACME Inc.") == []


def test_no_names_in_generic_footer():
    text = "Horario: Lunes a Viernes de 8 a 18.\nCopyright 2024 Todos Los Derechos Reservados."
    assert _names(text) == []


def test_dedup_preserves_first_occurrence_order():
    text = "Gerente: Carlos Andrés Ruiz. También puede escribir a Lic. Carlos Andrés Ruiz directamente."
    assert _pairs(text) == [("Carlos Andrés Ruiz", None)]


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
    assert _names("Contacto: ELOY OCAMPO") == ["Eloy Ocampo"]


# -- "cargo"/role detection --------------------------------------------

def test_role_from_next_line_after_honorific():
    text = "Atiende: Dra. Wanda Medina\nDirectora Médica"
    assert _pairs(text) == [("Wanda Medina", "Directora Médica")]


def test_bare_name_with_role_is_detected_real_case():
    # Real case (clinicaslove.com): no honorific, no label -- just a name
    # card followed by a role line.
    text = "Nosotros\nClínicas love\nJavier Llorente\nCEO Fundador\nMisión"
    assert _pairs(text) == [("Javier Llorente", "CEO Fundador")]


def test_bare_all_caps_name_with_role_is_detected_real_case():
    # Real case (factoriaderesultados.com).
    text = "QUIÉNES SOMOS\nELOY OCAMPO\nTrafficker Digital\nEstrategia de marketing"
    assert _pairs(text) == [("Eloy Ocampo", "Trafficker Digital")]


def test_bare_name_without_a_role_line_is_still_ignored():
    # The pairing with a role is the actual signal; a bare name with
    # nothing after it at all is exactly as weak a signal as before.
    assert _names("ELOY OCAMPO") == []


def test_two_plain_names_with_no_role_between_them_are_rejected():
    text = "Nuestros Clientes\nJuan Perez\nMaria Rodriguez\nCarlos Gomez"
    assert _names(text) == []


def test_section_heading_pair_is_rejected():
    # "About us" pages are full of two-line headings shaped just like a
    # name+role pair ("Nuestra Filosofía" / "El Enfoque de Sante...").
    text = "Nuestra Filosofia\nEl Enfoque de Sante\nCreemos en combinar lo mejor de ambos mundos."
    assert _names(text) == []


def test_bare_company_name_is_rejected_even_with_role_like_line_after():
    text = "Contacto\nDistribuidora Nacional\nAtencion al cliente 24/7"
    assert _names(text) == []


def test_role_rejects_call_to_action_sentence():
    # A name is very often followed by a CTA sentence, not a role.
    text = "Atiende: Sra. Rosa Elena Martínez del Campo\nEscríbenos o llámanos al +57 300 111 2222."
    assert _pairs(text) == [("Rosa Elena Martínez del Campo", None)]


def test_ui_microcopy_is_never_mistaken_for_a_name():
    # Real case (santeclinics.com): each team card is "Name\nVer Perfil".
    # "Ver Perfil" itself must never be treated as a name.
    text = "Dra. Sol Monsalve\nVer Perfil\nRoma\nVer Perfil"
    assert _names(text) == ["Sol Monsalve"]
