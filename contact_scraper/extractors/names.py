"""Best-effort extraction of person names from a contact page.

There is no reliable general solution for this without full NLP: most
business contact pages list a company name, a phone number and an address,
but never a person. This module only reports a name when the page gives an
explicit signal (an honorific like "Lic." / "Sr.", or a label like
"Contacto:" / "Atiende:" right before a capitalized name) rather than
guessing at every Title Case phrase, which would flood the result with
noise (menu items, headings, "Política de Privacidad", etc.). An empty
result is common and expected.

Optional: if `spacy` and a Spanish model (`es_core_news_sm`) are installed,
`extract_names(..., use_spacy=True)` also runs NER for better recall on
free-flowing "quiénes somos" bios. Neither is a hard dependency.
"""
from __future__ import annotations

import re
from typing import List, Optional


# A name is matched greedily word-by-word only within a single line ([ \t],
# never \n), otherwise a label on its own line ("Contacto:\nTeléfono: ...")
# would swallow the next line's label as if it were part of the name.
# Lowercase connectors ("del", "de la"...) are allowed between capitalized
# words so compound surnames like "Martínez del Campo" aren't cut short.
_CONNECTOR = r"(?:de(?:[ \t]+la|[ \t]+los|[ \t]+las)?|del)"
# Accepts "Ocampo" (Title Case) and "OCAMPO" (a common all-caps styling for
# team/staff names) but not mixed-case noise like "OcAmPo".
_WORD = r"[A-ZÁÉÍÓÚÑ](?:[A-ZÁÉÍÓÚÑ]+|[a-záéíóúñ]+)"
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


def _regex_names(text: str) -> List[str]:
    found: List[str] = []
    for pattern in (_HONORIFIC_RE, _LABEL_RE):
        for match in pattern.finditer(text):
            name = _clean(match.group(1))
            if name and name not in found:
                found.append(name)
    return found


_spacy_model = None


def _spacy_names(text: str) -> List[str]:
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
    found: List[str] = []
    for ent in doc.ents:
        if ent.label_ == "PER":
            name = _clean(ent.text)
            if name and len(name.split()) >= 2 and name not in found:
                found.append(name)
    return found


def extract_names(text: str, use_spacy: bool = False) -> List[str]:
    names = _regex_names(text)
    if use_spacy:
        for name in _spacy_names(text):
            if name not in names:
                names.append(name)
    return names
