"""Utilidades comunes, independientes del nicho: HTTP con rate-limit,
normalización, verificación de webs, dedup, Fit_ICP y exportación CSV.

Este módulo no sabe nada de aceite de oliva ni de ningún nicho concreto.
Los parsers de cada fuente (carpeta sources/ de turno) solo hacen
scraping de su página y devuelven CompanyRow; toda la lógica de
normalización/verificación/dedup/exportación vive aquí. Para un nicho
nuevo (quesos, vino...): nueva carpeta de parsers + este mismo módulo sin
tocar, importado desde el main.py de ese nicho."""
from __future__ import annotations

import csv
import logging
import os
import random
import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, fields
from urllib.parse import urlparse

import requests

USER_AGENT = "AOVE-DirectorioBot/1.0 (+contacto: joelgabriel.ayala@gmail.com)"
# Timeouts distintos a propósito: las páginas de las propias DOP son la fuente
# de verdad (perder una fila cuesta caro) y algunas son pesadas de cargar
# (dopriegodecordoba.es tarda ~7s de forma reproducible), así que llevan más
# margen. La verificación golpea dominios de terceros donde fallar rápido no
# tiene downside.
SCRAPE_TIMEOUT = 10  # segundos, peticiones de scraping a las fuentes (DOP/AEMO/...)
VERIFY_TIMEOUT = 5  # segundos, peticiones de verify_web a webs de empresas

CSV_COLUMNS = [
    "Empresa", "Web", "Verificada WEB", "Nombre", "Apellidos",
    "Teléfono", "Email", "Cargo", "LinkedIn", "Fit_ICP", "Forma_Legal",
    "DOP_Origen", "Revisar_Dedup", "Dirección", "Titular",
]

logger = logging.getLogger("aove_scraper")

CHECKPOINT_PATH = "output/_raw_checkpoint.csv"
_checkpoint_lock = threading.Lock()


def init_checkpoint(path: str = CHECKPOINT_PATH) -> None:
    """Crea (o vacía) el checkpoint con solo la cabecera. Llamar una vez al
    empezar main(), antes de scrapear ninguna fuente."""
    with _checkpoint_lock:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()


def append_raw_row(row: "CompanyRow", path: str = CHECKPOINT_PATH) -> None:
    """Añade una fila cruda al checkpoint en el instante en que se obtiene
    (append + flush + fsync), para no perder trabajo ya scrapeado si el
    proceso muere a mitad de una fuente. Es la copia cruda, sin deduplicar
    ni verificar — el CSV final (aove_empresas.csv) sigue escribiéndose una
    sola vez al terminar, porque el dedup es global entre fuentes y no puede
    decidirse fila a fila. Thread-safe: varios workers pueden llamarla a la
    vez (usado desde scrape_details_concurrently)."""
    with _checkpoint_lock:
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writerow(row.to_csv_dict())
            f.flush()
            os.fsync(f.fileno())


_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT})

_thread_local = threading.local()


def rate_limited_get(url: str, source: str, timeout: int = SCRAPE_TIMEOUT, **kwargs) -> requests.Response:
    """GET con espera de 1-2s desde la última petición a la misma fuente.

    El rate-limit es por hilo (thread-local), no global: cuando varios workers
    de un ThreadPoolExecutor golpean la misma fuente en paralelo, cada uno
    respeta 1-2s entre SUS PROPIAS peticiones consecutivas, pero no se
    bloquean entre sí. Con N workers, la fuente puede recibir hasta N
    peticiones solapadas en vez de una estrictamente cada 1-2s — es la
    concesión explícita para paralelizar sin serializar workers entre ellos."""
    last_by_source = getattr(_thread_local, "last_request_ts", None)
    if last_by_source is None:
        last_by_source = {}
        _thread_local.last_request_ts = last_by_source
    last = last_by_source.get(source)
    if last is not None:
        elapsed = time.monotonic() - last
        wait = random.uniform(1.0, 2.0) - elapsed
        if wait > 0:
            time.sleep(wait)
    resp = _session.get(url, timeout=timeout, **kwargs)
    last_by_source[source] = time.monotonic()
    return resp


def scrape_details_concurrently(urls, fetch_one, source_name: str, max_workers: int = 3) -> list:
    """Ejecuta fetch_one(url) para cada url con hasta max_workers hilos
    concurrentes (pensado para el patrón 'listado -> ficha individual' de
    Sierra Mágina / Montes de Toledo). Cada hilo mantiene su propio
    rate-limit de 1-2s vía rate_limited_get; los fallos de un item se
    loguean y se descartan sin tumbar el resto."""
    rows = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(fetch_one, url): url for url in urls}
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                row = future.result()
                if row is not None:
                    append_raw_row(row)
                    rows.append(row)
            except Exception as exc:  # noqa: BLE001
                logger.error("FUENTE FALLIDA (ficha): %s | url: %s | motivo: %s", source_name, url, exc)
    return rows


def base_domain(url: str) -> str:
    """Dominio normalizado (sin www., minúsculas) a partir de una URL."""
    if not url:
        return ""
    netloc = urlparse(url if "//" in url else f"//{url}").netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc.split(":")[0]


def normalize_web(url: str) -> str:
    """Fuerza esquema https:// y quita espacios; no inventa dominio si está vacío.
    Si el valor es en realidad una dirección de email (error de la fuente al
    poner un mailto en el campo 'web'), lo rechaza en vez de generar una URL
    inválida tipo https://alguien@gmail.com."""
    if not url:
        return ""
    url = url.strip()
    if not url:
        return ""
    url = re.sub(r"^mailto:", "", url, flags=re.IGNORECASE)
    url = re.sub(r"^https?://", "", url, flags=re.IGNORECASE)
    if EMAIL_RE.fullmatch(url):
        return ""
    return f"https://{url}"


def verify_web(url: str) -> tuple[bool, str]:
    """(checked, detail). checked=True solo si el request HTTP devuelve 200 y el
    dominio final coincide con el solicitado. detail explica el motivo exacto
    (status code, dominio de redirección, o la excepción) para poder debuggear
    sin tener que reintentar a ciegas.

    Sin rate-limit propio a propósito: cada llamada apunta a un dominio de
    empresa distinto e independiente (no es "la misma fuente" repetida como
    el scraping de un DOP), así que es seguro invocarla en paralelo desde un
    ThreadPoolExecutor."""
    if not url:
        return False, "sin URL"
    original_domain = base_domain(url)
    try:
        resp = _session.get(url, timeout=VERIFY_TIMEOUT, allow_redirects=True)
    except requests.RequestException as exc:
        detail = f"{type(exc).__name__}: {exc}"
        logger.info("verify_web fallo para %s: %s", url, detail)
        return False, detail
    final_domain = base_domain(resp.url)
    if resp.status_code != 200:
        return False, f"HTTP {resp.status_code} (url final: {resp.url})"
    if final_domain != original_domain:
        return False, f"redirige a otro dominio: {original_domain} -> {final_domain}"
    return True, f"HTTP 200, dominio {final_domain} confirmado"


VERIFY_WORKERS = 10


def verify_all_webs(rows: "list[CompanyRow]", max_workers: int = VERIFY_WORKERS) -> None:
    """Verifica en paralelo (ThreadPoolExecutor) las webs de una lista de
    filas y les asigna Verificada_WEB/verify_detail in-place. Verifica por
    Web única (no por fila) para no repetir peticiones cuando varias filas
    comparten el mismo dominio.

    Debe correr ANTES de dedup_rows: el guard de conflicto de teléfono en
    dedup_rows necesita saber qué domino está "checked" antes de decidir
    si fusiona o marca Revisar_Dedup."""
    unique_webs = {row.Web for row in rows if row.Web}
    web_results: dict[str, tuple[bool, str]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_web = {executor.submit(verify_web, web): web for web in unique_webs}
        for future in as_completed(future_to_web):
            web_results[future_to_web[future]] = future.result()
    for row in rows:
        if row.Web and row.Web in web_results:
            checked, detail = web_results[row.Web]
            row.Verificada_WEB = "checked" if checked else ""
            row.verify_detail = detail


# Formas legales más específicas primero (S.L.U./S.A.U./S.A.T./S.C.A. antes que
# S.L./S.A.) para que el \b final no se quede matchando solo el prefijo y deje
# colgando el resto ("S.A." dentro de "S.A.T.", etc).
_SUFFIX_RE = re.compile(
    r"\b("
    r"s\.?\s?l\.?\s?u\.?"          # S.L.U.
    r"|s\.?\s?a\.?\s?u\.?"          # S.A.U.
    r"|s\.?\s?a\.?\s?t\.?"          # S.A.T.
    r"|s\.?\s?c\.?\s?a\.?"          # S.C.A.
    r"|s\.?\s?l\.?"                 # S.L.
    r"|s\.?\s?a\.?"                 # S.A.
    r"|soc\.?\s?coop\.?"            # Soc. Coop.
    r"|sdad\.?\s?coop\.?"           # Sdad. Coop.
    r"|s\.?\s?coop\.?(\s?and\.?)?"  # S. Coop. (Andaluza)
    r"|cooperativa"                 # Cooperativa (palabra completa)
    r"|coop\.?"                     # Coop.
    r"|c\.?b\.?"                    # C.B.
    r")\b\.?",
    re.IGNORECASE,
)


def normalize_company_name(name: str) -> str:
    """minúsculas, sin tildes, sin formas societarias, para dedup."""
    if not name:
        return ""
    n = unicodedata.normalize("NFKD", name)
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = n.lower()
    # aplicar dos veces: una fila puede llevar más de un sufijo/forma legal
    # (p.ej. "... Almazara/Envasadora/Comercializadora S.L." o nombres con
    # coma + sigla al final que dejan un segundo hueco tras la primera pasada)
    n = _SUFFIX_RE.sub(" ", n)
    n = _SUFFIX_RE.sub(" ", n)
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


_HONORIFIC_RE = re.compile(r"^(d\.|dn\.|dna\.|dña\.|dª\.|d\s|sr\.|sra\.|srta\.)\s*", re.IGNORECASE)
_PARTICLES = {"de", "del", "la", "las", "los", "y"}


def split_spanish_name(full_name: str) -> tuple[str, str]:
    """Separa 'D. José Manuel Muela Rodríguez' en (Nombre, Apellidos) por heurística,
    sin inventar texto: solo reparte las palabras literales de la fuente."""
    if not full_name:
        return "", ""
    cleaned = _HONORIFIC_RE.sub("", full_name.strip()).strip()
    cleaned = re.sub(r"^d[ñn]?\.?\s+", "", cleaned, flags=re.IGNORECASE)
    words = [w for w in cleaned.split() if w]
    if not words:
        return "", ""
    if len(words) == 1:
        return words[0], ""
    if len(words) == 2:
        return words[0], words[1]

    apellido_tokens: list[str] = []
    content_count = 0
    i = len(words) - 1
    while i >= 0 and content_count < 2:
        w = words[i]
        apellido_tokens.insert(0, w)
        if w.lower() not in _PARTICLES:
            content_count += 1
        i -= 1
    nombre_tokens = words[: i + 1]
    if not nombre_tokens:
        nombre_tokens = [apellido_tokens.pop(0)]
    return " ".join(nombre_tokens), " ".join(apellido_tokens)


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"[+\d][\d\s().\-]{6,}\d")


def normalize_rows(rows: "list[CompanyRow]") -> None:
    """Aplica in-place la normalización de teléfono y la extracción de
    Forma_Legal a cada fila. Pensado para correr sobre las filas crudas,
    antes de verificar/deduplicar."""
    for row in rows:
        row.Telefono = normalize_phone_es(row.Telefono)
        row.Forma_Legal = extract_forma_legal(row.Empresa)


def normalize_phone_es(raw: str) -> str:
    """Normaliza a +34XXXXXXXXX (9 dígitos, sin espacios). Si no trae prefijo de
    país se asume España. No inventa dígitos: si la longitud no cuadra, deja
    los dígitos tal cual detrás de +34 y registra un aviso."""
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("0034"):
        digits = digits[2:]
    if digits.startswith("34") and len(digits) == 11:
        national = digits[2:]
    elif len(digits) == 9:
        national = digits
    else:
        national = digits[-9:] if len(digits) > 9 else digits
        logger.warning("normalize_phone_es: longitud inesperada en %r -> nacional=%r", raw, national)
    return f"+34{national}"


_FORMA_LEGAL_PATTERNS = [
    (re.compile(r"\bS\.?\s?C\.?\s?A\.?\b", re.IGNORECASE), "S.C.A."),
    (re.compile(r"\bS\.?\s?C\.?\s?L\.?\b", re.IGNORECASE), "S.C.L."),
    (re.compile(r"\bS\.?\s?L\.?\s?U\.?\b", re.IGNORECASE), "S.L.U."),
    (re.compile(r"\bS\.?\s?A\.?\s?U\.?\b", re.IGNORECASE), "S.A.U."),
    (re.compile(r"\bS\.?\s?L\.?\b", re.IGNORECASE), "S.L."),
    (re.compile(r"\bS\.?\s?A\.?\b", re.IGNORECASE), "S.A."),
    (re.compile(r"coop", re.IGNORECASE), "Cooperativa"),
]


def extract_forma_legal(empresa: str) -> str:
    """Forma legal detectada literalmente en el nombre de la empresa, o 'otro'."""
    if not empresa:
        return "otro"
    for pattern, label in _FORMA_LEGAL_PATTERNS:
        if pattern.search(empresa):
            return label
    return "otro"


_FIT_ALTO = ("gerente", "director", "propietario", "administrador")
_FIT_BAJO = ("presidente",)
_FIT_BAJO_FORMA_LEGAL = {"S.C.A.", "Cooperativa", "S.C.L.", "Coop."}


def compute_fit_icp(cargo: str, forma_legal: str = "") -> str:
    """'alto' / 'bajo' / 'revisar' según el cargo. No descarta nada, solo etiqueta.

    Si la forma legal es cooperativa (S.C.A./Cooperativa/S.C.L./Coop.), la
    fila queda en 'bajo' sin importar el cargo: una cooperativa no encaja en
    el ICP aunque su representante sea "Gerente" o "Director", porque la
    decisión de compra no la toma una sola persona con ese cargo."""
    if forma_legal in _FIT_BAJO_FORMA_LEGAL:
        return "bajo"
    if not cargo:
        return "revisar"
    cargo_low = cargo.lower()
    if any(kw in cargo_low for kw in _FIT_ALTO):
        return "alto"
    if any(kw in cargo_low for kw in _FIT_BAJO):
        return "bajo"
    return "revisar"


def apply_fit_icp(rows: "list[CompanyRow]") -> None:
    """Aplica in-place compute_fit_icp a cada fila (Cargo + Forma_Legal).
    Pensado para correr después de dedup_rows, cuando Cargo y Forma_Legal
    de la fila "ganadora" ya están fijados."""
    for row in rows:
        row.Fit_ICP = compute_fit_icp(row.Cargo, row.Forma_Legal)


@dataclass
class CompanyRow:
    Empresa: str = ""
    Web: str = ""
    Verificada_WEB: str = ""  # "checked" o ""
    Nombre: str = ""
    Apellidos: str = ""
    Telefono: str = ""
    Email: str = ""
    Cargo: str = ""
    LinkedIn: str = ""
    Fit_ICP: str = ""
    Forma_Legal: str = ""
    DOP_Origen: str = ""
    Revisar_Dedup: str = ""  # motivo si el dedup automático NO fusionó por conflicto
    Direccion: str = ""  # domicilio/localidad/provincia, cuando la fuente lo trae (p.ej. registros oficiales)
    Titular: str = ""  # entidad titular del centro, cuando difiere del nombre comercial (Empresa)
    fuente: str = field(default="", compare=False)
    verify_detail: str = field(default="", compare=False)

    def to_csv_dict(self) -> dict:
        return {
            "Empresa": self.Empresa,
            "Web": self.Web,
            "Verificada WEB": self.Verificada_WEB,
            "Nombre": self.Nombre,
            "Apellidos": self.Apellidos,
            "Teléfono": self.Telefono,
            "Email": self.Email,
            "Cargo": self.Cargo,
            "LinkedIn": self.LinkedIn,
            "Fit_ICP": self.Fit_ICP,
            "Forma_Legal": self.Forma_Legal,
            "DOP_Origen": self.DOP_Origen,
            "Revisar_Dedup": self.Revisar_Dedup,
            "Dirección": self.Direccion,
            "Titular": self.Titular,
        }

    @classmethod
    def from_csv_dict(cls, d: dict) -> "CompanyRow":
        """Reconstruye una fila desde una fila de CSV (p.ej. el checkpoint
        crudo), para poder rehacer dedup/verificación sin re-scrapear."""
        return cls(
            Empresa=d.get("Empresa", ""),
            Web=d.get("Web", ""),
            Verificada_WEB=d.get("Verificada WEB", ""),
            Nombre=d.get("Nombre", ""),
            Apellidos=d.get("Apellidos", ""),
            Telefono=d.get("Teléfono", ""),
            Email=d.get("Email", ""),
            Cargo=d.get("Cargo", ""),
            LinkedIn=d.get("LinkedIn", ""),
            Fit_ICP=d.get("Fit_ICP", ""),
            Forma_Legal=d.get("Forma_Legal", ""),
            DOP_Origen=d.get("DOP_Origen", ""),
            Revisar_Dedup=d.get("Revisar_Dedup", ""),
            Direccion=d.get("Dirección", ""),
            Titular=d.get("Titular", ""),
        )


def write_csv(rows: list[CompanyRow], path: str) -> None:
    """Exporta la lista de filas al CSV final: UTF-8 sin BOM, columnas
    estándar (CSV_COLUMNS)."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_csv_dict())


def dedup_rows(rows: list[CompanyRow]) -> list[CompanyRow]:
    """Dedup por dominio, teléfono normalizado y nombre normalizado, fusionando
    de forma transitiva (union-find): si A comparte dominio con B, y B
    comparte nombre con C, las tres acaban en el mismo grupo aunque A y C no
    compartan ninguna clave entre sí directamente. Este es el caso real que
    motivó el cambio: una fuente sin Web (p.ej. EVOOLEUM) solo puede
    encontrarse con las demás por nombre, no por dominio.

    Dominio siempre fusiona (identificador específico, poco propenso a
    coincidir por azar). El nombre normalizado también fusiona, salvo que
    las dos filas tengan dominios no vacíos y distintos — eso evita
    fusionar dos cooperativas distintas que comparten un nombre genérico
    (p.ej. dos "S.C.A. ... San Isidro" de comarcas distintas, cada una con
    su propia web real).

    El teléfono normalizado NO fusiona a ciegas: es la señal más débil de
    las tres, así que solo fusiona automáticamente si viene corroborado por
    dominio o nombre compartido. Si no hay esa corroboración:
      - dominios distintos y AMBOS verificados -> conflicto real (caso
        "San Isidro" pero con teléfono): no fusiona, marca Revisar_Dedup.
      - dominios distintos SIN verificar ambos -> se fusiona igualmente,
        el teléfono es la mejor señal disponible (un dominio muerto/typo no
        es evidencia fiable de que sean empresas distintas).
      - sin dominio en al menos un lado y nombres distintos -> señal
        demasiado débil para fusionar a ciegas: marca Revisar_Dedup sin
        fusionar (caso real: "JUDISAN, S.L." / "TRESCES – ZARFE, S.L."
        comparten teléfono por un error de copy-paste en la propia ficha
        fuente de Montes de Toledo, pero son dos empresas distintas; ninguna
        de las dos tenía un dominio en conflicto porque JUDISAN no tenía
        ningún dominio).
    Por esto, verify_web debe haberse corrido ANTES de llamar a dedup_rows
    (no después, como en la versión anterior)."""
    n = len(rows)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    domains = [base_domain(r.Web) for r in rows]
    names = [normalize_company_name(r.Empresa) for r in rows]
    phones = [r.Telefono or "" for r in rows]

    by_domain: dict[str, list[int]] = {}
    for i, d in enumerate(domains):
        if d:
            by_domain.setdefault(d, []).append(i)
    for idxs in by_domain.values():
        for j in idxs[1:]:
            union(idxs[0], j)

    verified = [r.Verificada_WEB == "checked" for r in rows]

    by_phone: dict[str, list[int]] = {}
    for i, p in enumerate(phones):
        if p:
            by_phone.setdefault(p, []).append(i)
    for idxs in by_phone.values():
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                i, j = idxs[a], idxs[b]
                same_domain = bool(domains[i]) and domains[i] == domains[j]
                same_name = bool(names[i]) and names[i] == names[j]
                if same_domain or same_name:
                    # corroborado por dominio o nombre -> fusión segura
                    union(i, j)
                    continue
                domain_conflict = bool(domains[i]) and bool(domains[j]) and domains[i] != domains[j]
                if domain_conflict and verified[i] and verified[j]:
                    # dominios distintos y AMBOS verificados -> conflicto real
                    # (caso "San Isidro"): no fusionar, queda para revisión
                    rows[i].Revisar_Dedup = "teléfono compartido, dominios distintos verificados"
                    rows[j].Revisar_Dedup = "teléfono compartido, dominios distintos verificados"
                    continue
                if domain_conflict:
                    # dominios distintos SIN verificar ambos: el teléfono sigue
                    # siendo la mejor señal disponible, se fusiona como antes
                    union(i, j)
                    continue
                # sin dominio corroborante en al menos un lado y nombres
                # distintos -> señal demasiado débil para fusionar a ciegas
                # (caso real "JUDISAN, S.L." / "TRESCES – ZARFE, S.L.": mismo
                # teléfono por un error de copy-paste en la propia fuente,
                # pero son dos empresas distintas)
                rows[i].Revisar_Dedup = "teléfono compartido, sin dominio ni nombre que lo confirme"
                rows[j].Revisar_Dedup = "teléfono compartido, sin dominio ni nombre que lo confirme"

    by_name: dict[str, list[int]] = {}
    for i, nm in enumerate(names):
        if nm:
            by_name.setdefault(nm, []).append(i)
    for idxs in by_name.values():
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                i, j = idxs[a], idxs[b]
                if domains[i] and domains[j] and domains[i] != domains[j]:
                    continue  # dominios distintos y no vacíos -> no es la misma empresa
                union(i, j)

    groups: dict[int, list[CompanyRow]] = {}
    order: list[int] = []
    for i, row in enumerate(rows):
        root = find(i)
        if root not in groups:
            groups[root] = []
            order.append(root)
        groups[root].append(row)

    result = []
    for root in order:
        group = groups[root]
        group.sort(key=lambda r: sum(1 for f in (r.Telefono, r.Email, r.Nombre, r.Web) if f), reverse=True)
        best = group[0]
        for other in group[1:]:
            for attr in ("Nombre", "Apellidos", "Telefono", "Email", "Cargo", "LinkedIn", "Web", "DOP_Origen", "Revisar_Dedup", "Direccion", "Titular"):
                if not getattr(best, attr) and getattr(other, attr):
                    setattr(best, attr, getattr(other, attr))
        result.append(best)
    return result
