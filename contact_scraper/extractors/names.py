"""Best-effort extraction of person names -- and their role/"cargo" when one
is available -- from a contact or team page.

There is no reliable general solution for this without full NLP, so a name
is only ever reported when the page gives one of two signals:

1. An explicit marker right before it: an honorific ("Lic." / "Sr." / "Dr.")
   or a label ("Contacto:" / "Atiende:").
2. A short, standalone line (its own line, nothing else on it) immediately
   followed by another short line that looks like a job title -- the
   "Javier Llorente" / "CEO Fundador" team-card pattern. The name alone is
   never enough here; it's the role line right under it that makes this
   worth the (larger, deliberately accepted) false-positive risk of case 1.

Guessing at every Title Case phrase would flood the result with noise (menu
items, headings, "Política de Privacidad", treatment names, etc.), so
neither path fires without one of those signals. An empty result is common
and expected -- most contact pages list a company, not a person.

Optional: if `spacy` and a Spanish model (`es_core_news_sm`) are installed,
`extract_names(..., use_spacy=True)` also runs NER for better recall on
free-flowing "quiénes somos" bios. Neither is a hard dependency.
"""
from __future__ import annotations

import re
from typing import List, Optional

from contact_scraper.models import Person

# A name is matched greedily word-by-word only within a single line ([ \t],
# never \n), otherwise a label on its own line ("Contacto:\nTeléfono: ...")
# would swallow the next line's label as if it were part of the name.
# Lowercase connectors ("del", "de la"...) are allowed between capitalized
# words so compound surnames like "Martínez del Campo" aren't cut short.
_CONNECTOR = r"(?:de(?:[ \t]+la|[ \t]+los|[ \t]+las)?|del)"
# Accepts "Ocampo" (Title Case) and "OCAMPO" (a common all-caps styling for
# team/staff names) but not mixed-case noise like "OcAmPo". Requires 3+
# letters so a capitalized Spanish article at the start of a heading or
# sentence ("El", "La", "Lo") can't itself pass as a name's first word.
_WORD = r"[A-ZÁÉÍÓÚÑ](?:[A-ZÁÉÍÓÚÑ]{2,}|[a-záéíóúñ]{2,})"
_NAME = rf"{_WORD}(?:[ \t]+(?:{_CONNECTOR}[ \t]+)?{_WORD}){{1,3}}"

# A capitalized phrase immediately followed by a legal-entity suffix is a
# company name, not a person, even though it looks identical up to that
# point (e.g. "Contacto: Distribuidora Nacional S.A.S.". The \b anchors the
# check to a real word boundary so a rejected match fails outright instead
# of the preceding greedy word backtracking one letter short to dodge it.
_NOT_A_COMPANY = (
    r"\b(?![ \t]*[,.]?[ \t]*(?:S\.?\s?A\.?\s?S?\.?|S\.?\s?L\.?|S\.?\s?R\.?\s?L\.?|"
    r"Ltda\.?|C\.?\s?A\.?|Inc\.?|LLC|E\.?I\.?R\.?L\.?|SAC|SRL)\b)"
)

_HONORIFIC_RE = re.compile(
    rf"\b(?:Sr|Sra|Srta|Lic|Ing|Dr|Dra|Mtro|Mtra)\.?[ \t]+({_NAME}){_NOT_A_COMPANY}"
)

_LABEL_RE = re.compile(
    r"(?:Contacto|Atenci[oó]n|Atiende|Responsable|Encargad[oa]|Gerente|"
    rf"Propietari[oa]|Representante|Asesor(?:a)?)\s*:\s*({_NAME}){_NOT_A_COMPANY}"
)

# A name with NO honorific/label at all, but alone on its own line -- the
# shape of a name in a team-grid card. On its own this is far too weak a
# signal (any two-word heading would match), so it is only ever accepted
# together with a confirmed role line right after it -- see _regex_names.
_BARE_NAME_LINE_RE = re.compile(rf"^[ \t]*({_NAME}){_NOT_A_COMPANY}[ \t]*$", re.MULTILINE)

# Title-Case phrases that are almost never a person's name on a contact page,
# to filter out matches that slip past the label/honorific context (e.g. a
# label immediately followed by a company or legal boilerplate line instead
# of an actual name).
_STOPWORDS = {
    "todos los derechos", "politica de privacidad", "terminos y condiciones",
    "aviso de privacidad", "atencion al cliente", "servicio al cliente",
    "lunes a viernes", "horario de atencion",
}
_LEGAL_SUFFIX_RE = re.compile(r"\b(s\.?a\.?s?\.?|s\.?l\.?|s\.?r\.?l\.?|ltda\.?|c\.?a\.?|inc\.?|llc)\b\.?$", re.IGNORECASE)


def _clean(name: str) -> Optional[str]:
    name = name.strip()
    if name.isupper():  # "ELOY OCAMPO" -> "Eloy Ocampo", for consistent output
        name = name.title()
    if name.lower() in _STOPWORDS:
        return None
    if _LEGAL_SUFFIX_RE.search(name):
        return None
    return name


_LEADING_HONORIFIC_RE = re.compile(r"^(?:Sr|Sra|Srta|Lic|Ing|Dr|Dra|Mtro|Mtra)\.?\s+", re.IGNORECASE)
# Runs from the first letter through any mix of letters/spaces/apostrophes/
# hyphens/periods, i.e. everything a name can plausibly contain -- anything
# after that (emoji, flag icons, a trailing job title glued on) is dropped.
_NAME_RUN_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'.\- ]*")


def clean_person_name(raw: str) -> Optional[str]:
    """Tidy up a name that came from a site's own (not always careful)
    structured data, e.g. schema.org Person "name": "Dr. Ignacio Navarro
    🇺🇸 🇪🇸" -> "Ignacio Navarro". Regex-extracted names never need this --
    they're built strictly from name-shaped characters to begin with."""
    if not raw:
        return None
    value = _LEADING_HONORIFIC_RE.sub("", raw.strip())
    match = _NAME_RUN_RE.match(value)
    value = match.group(0).strip() if match else value.strip()
    return _clean(value) if value else None


# Generic link/button microcopy that sits right under a name in a team-grid
# card but is not a role -- must be rejected explicitly, since on its own it
# is short and title-shaped exactly like a real "cargo" would be.
_ROLE_BLOCKLIST = {
    "ver perfil", "ver mas", "ver más", "leer mas", "leer más", "leer bio",
    "video", "compartir", "conocelo", "conócelo", "conocela", "conócela",
    "conoce mas", "conoce más", "saber mas", "saber más", "mas informacion",
    "más información", "+ info", "info",
    # icon-font accessibility labels ("Envelope" for a mail icon, etc.),
    # common across many site templates regardless of niche.
    "envelope", "facebook", "instagram", "linkedin", "twitter", "whatsapp",
    "youtube", "tiktok", "pinterest",
    # Some sites keep a hidden English copy of nav/UI strings in the same
    # DOM (translation plugins, hreflang alternates); real case
    # (santeclinics.com): "Book", "Treatments", "Previous slide" etc.
    "book", "treatments", "previous slide", "next slide", "legal notice",
    "read more", "learn more", "see more", "share", "menu", "close",
}
_ROLE_SHAPE_RE = re.compile(r"^[A-Za-zÁÉÍÓÚÑáéíóúñÀ-ÖØ-öø-ÿ0-9 ,.\-&/]{3,60}$")

# Words that show up in job titles/roles but essentially never inside a
# person's own name. Used two ways: a "name" candidate containing one of
# these is actually a role line that happens to be name-shaped (e.g. "CEO
# Fundador", both of which independently pass as capitalized _WORD-shaped
# tokens); and a role candidate containing one is trusted as a role even if
# it also happens to match the bare-name shape (e.g. "Atención al Paciente").
_ROLE_WORDS = {
    "ceo", "cto", "cfo", "coo", "vp", "fundador", "fundadora", "director",
    "directora", "gerente", "gerenta", "coordinador", "coordinadora",
    "encargado", "encargada", "responsable", "digital", "marketing",
    "trafficker", "atencion", "atención", "cliente", "clientes", "paciente",
    "pacientes", "especialista", "asesor", "asesora", "consultor",
    "consultora", "comercial", "ventas", "recepcion", "recepción",
    "administrador", "administradora", "socio", "socia",
}

# Company-ish nouns that, alone, aren't a legal-entity suffix (so
# _NOT_A_COMPANY doesn't catch them) but still mark a line as a business
# name rather than a person -- e.g. "Distribuidora Nacional" with no "S.A.S."
# attached at all.
_COMPANY_WORDS = {
    "distribuidora", "distribuidor", "comercializadora", "constructora",
    "inversiones", "corporacion", "corporación", "compania", "compañía",
    "industrias", "importadora", "exportadora", "franquicia", "franquicias",
}

# "About us" pages are full of section headings shaped exactly like a
# two-word name ("Nuestra Filosofía", "Nuestra Historia", "El Enfoque de
# Sante") -- common nouns/pronouns that never form part of an actual name.
_HEADING_WORDS = {
    "nuestra", "nuestro", "nuestros", "nuestras", "filosofia", "filosofía",
    "historia", "vision", "visión", "mision", "misión", "enfoque", "valores",
    "equipo", "somos", "nosotros",
}

# A name is very often followed, in ordinary contact-page prose, by a whole
# NEW SENTENCE rather than a role ("Atiende: Sra. X" / "Escríbenos o
# llámanos al..."). Job titles are noun phrases; a line built around one of
# these call-to-action imperatives is a sentence, not a "cargo".
_CTA_VERB_WORDS = {
    "escribenos", "escríbenos", "escribinos", "llamanos", "llámanos",
    "contactanos", "contáctanos", "visitanos", "visítanos", "siguenos",
    "síguenos", "suscribete", "suscríbete", "registrate", "regístrate",
    "solicita", "agenda", "reserva", "compra", "compre", "descubre",
    "explora", "comparte", "consulta", "escribe", "llama", "contacta",
}


def _line_words(line: str) -> List[str]:
    return re.findall(r"[a-záéíóúñ]+", line.lower())


def _contains_any(line: str, words: set) -> bool:
    return any(w in words for w in _line_words(line))


def _line_after(text: str, pos: int) -> Optional[str]:
    """The next full line after `pos`, skipping whatever remains of the
    current line (e.g. trailing emoji after a matched name)."""
    newline_idx = text.find("\n", pos)
    if newline_idx == -1:
        return None
    next_newline_idx = text.find("\n", newline_idx + 1)
    end = next_newline_idx if next_newline_idx != -1 else len(text)
    line = text[newline_idx + 1 : end].strip()
    return line or None


def _looks_like_role(line: Optional[str]) -> bool:
    if not line:
        return False
    if line.lower() in _ROLE_BLOCKLIST:
        return False
    if not _ROLE_SHAPE_RE.match(line):
        return False
    if "@" in line or "http" in line.lower():
        return False
    if _contains_any(line, _CTA_VERB_WORDS):
        return False  # a call-to-action sentence, not a job title
    if re.search(r"\d{3,}", line):  # phone numbers, addresses, etc.
        return False
    if _HONORIFIC_RE.search(line) or _LABEL_RE.search(line):
        return False  # someone else's card, not this person's role
    if _BARE_NAME_LINE_RE.match(line) and not _contains_any(line, _ROLE_WORDS):
        return False  # looks like another plain name, not a role
    return True


def _regex_names(text: str) -> List[Person]:
    found: List[Person] = []
    seen_names = set()

    def add(name: Optional[str], role: Optional[str]) -> None:
        if name and name not in seen_names:
            seen_names.add(name)
            found.append(Person(name=name, role=role))

    for pattern in (_HONORIFIC_RE, _LABEL_RE):
        for match in pattern.finditer(text):
            name = _clean(match.group(1))
            role = _line_after(text, match.end(1))
            add(name, role if _looks_like_role(role) else None)

    # Bare name, no honorific/label: only trustworthy together with a role
    # line right after it -- that pairing is the actual signal, not the
    # name shape alone.
    for match in _BARE_NAME_LINE_RE.finditer(text):
        name = _clean(match.group(1))
        if not name or name in seen_names:
            continue
        if name.lower() in _ROLE_BLOCKLIST:
            continue  # UI microcopy ("Ver Perfil"), not a person
        if _contains_any(name, _ROLE_WORDS) or _contains_any(name, _COMPANY_WORDS) or _contains_any(name, _HEADING_WORDS):
            continue  # e.g. "CEO Fundador", "Distribuidora Nacional", "Nuestra Filosofía" -- not a person
        role = _line_after(text, match.end())
        if _looks_like_role(role):
            add(name, role)

    return found


_spacy_model = None


def _spacy_names(text: str) -> List[Person]:
    global _spacy_model
    if _spacy_model is None:
        try:
            import spacy

            _spacy_model = spacy.load("es_core_news_sm")
        except Exception:
            _spacy_model = False  # remember the failure, don't retry every call

    if not _spacy_model:
        return []

    doc = _spacy_model(text[:20000])  # cap input size; contact pages don't need more
    found: List[Person] = []
    seen = set()
    for ent in doc.ents:
        if ent.label_ == "PER":
            name = _clean(ent.text)
            if name and len(name.split()) >= 2 and name not in seen:
                seen.add(name)
                found.append(Person(name=name))
    return found


def extract_names(text: str, use_spacy: bool = False) -> List[Person]:
    people = _regex_names(text)
    if use_spacy:
        seen = {p.name for p in people}
        for person in _spacy_names(text):
            if person.name not in seen:
                seen.add(person.name)
                people.append(person)
    return people
