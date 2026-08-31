# Búsqueda de teléfonos — bot de extracción de contacto

Dada una URL, este bot localiza la página de contacto de un sitio web y extrae:

- **Nombres de personas** (cuando la página los menciona explícitamente)
- **Números de teléfono** (validados y formateados, no cualquier secuencia de dígitos)
- **Horario de atención**
- **Ciudad probable** donde está ubicado el negocio

Prioriza datos estructurados que el propio sitio publica para SEO (schema.org
`LocalBusiness`/`Organization` en JSON-LD o microdatos) porque son la fuente
más confiable, y usa heurísticas de texto en español como respaldo cuando no
existen.

## Instalación

```bash
pip install -r requirements.txt
```

Para desarrollo (incluye `pytest`):

```bash
pip install -r requirements-dev.txt
```

## Uso

### Una sola URL

```bash
python -m contact_scraper https://ejemplo.com
```

```
URL:              https://ejemplo.com
Página de contacto: https://ejemplo.com/contacto
Nombres:          Rosa Elena Martínez del Campo
Teléfonos:        +57 300 1112222
Horario:          Lunes a Viernes: 08:00–18:00
Ciudad probable:  Bogotá
País:             CO
```

Agrega `--json` para obtener el mismo resultado en JSON.

### Varias URLs / modo por lotes

```bash
python -m contact_scraper --input urls.txt --output resultados.csv
```

`urls.txt` lleva una URL por línea (las líneas vacías o que empiezan con `#`
se ignoran). El CSV resultante tiene las columnas: `source_url,
contact_page_url, names, phones, hours, city, country, address_raw,
warnings` (las listas van separadas por `; `).

También puedes combinar URLs directas con `--input`, y usar `--json` en vez
de `--output` para imprimir un arreglo JSON por stdout.

### Opciones útiles

| Opción | Qué hace |
|---|---|
| `--max-pages N` | Máximo de páginas a visitar por sitio (por defecto 3: la principal + hasta 2 páginas de contacto candidatas). |
| `--timeout N` | Timeout por solicitud HTTP, en segundos. |
| `--delay N` | Pausa entre solicitudes al mismo sitio, en segundos (cortesía con el servidor). |
| `--ignore-robots` | Ignora `robots.txt`. Solo si tienes autorización explícita del sitio. |
| `--use-spacy` | Si tienes `spacy` y su modelo en español instalados, los usa para mejorar la detección de nombres. |
| `--verbose` | Muestra progreso en stderr (útil en modo por lotes). |

## Cómo funciona

1. **`fetcher.py`** descarga la página con un User-Agent identificable,
   respeta `robots.txt` por defecto, y limita el tamaño de la respuesta.
2. **`contact_page_finder.py`** busca en la página principal enlaces cuyo
   texto o URL sugieran una página de contacto ("Contáctenos", "Contact us",
   etc.); si no encuentra ninguno, prueba rutas comunes (`/contacto`,
   `/contact-us`, ...).
3. **`structured_data.py`** extrae JSON-LD y microdatos schema.org
   (teléfono, dirección, horario, nombre de empleados/fundadores) cuando el
   sitio los publica.
4. **`extractors/`** cubre lo que los datos estructurados no dan:
   - `phones.py` usa la librería `phonenumbers` (el mismo motor que usa
     Android/Chrome) para validar y formatear números, en vez de un regex
     ingenuo que confundiría fechas o números de factura con teléfonos.
   - `hours.py` busca patrones de día + rango horario en español.
   - `city.py` compara el texto contra un gazetteer de ciudades reales
     (`geonamescache`, sin llamadas de red) y prioriza por coincidencia de
     país y población.
   - `names.py` solo reporta un nombre cuando hay una señal explícita
     ("Lic.", "Sr.", "Contacto:", "Atiende:", etc.), nunca adivina a partir
     de cualquier frase en mayúsculas.
5. **`scraper.py`** combina todo lo anterior con datos estructurados como
   fuente prioritaria.

## Limitaciones (por diseño)

- **Nombres**: la mayoría de páginas de contacto solo listan datos de la
  empresa, no de una persona. Es normal y esperado que `names` quede vacío.
  No se usa NLP pesado por defecto; `--use-spacy` es opcional para mejorar
  el recall si ya tienes `spacy` instalado.
- **Ciudad**: es una inferencia ("ciudad probable"), no un hecho verificado.
  Se prioriza la ciudad que el sitio declara explícitamente
  (`addressLocality`); en texto libre puede haber ambigüedad cuando se
  mencionan varias sucursales.
- **Teléfono**: cuando un número aparece en formato local (sin `+código de
  país`) y el sitio no da pistas de país (dominio `.com` genérico), el país
  se adivina y puede ser incorrecto. Números con `+código` o enlaces `tel:`
  son siempre confiables.
- Sitios que renderizan el contenido con JavaScript (SPA) no se ejecutan;
  solo se procesa el HTML que el servidor entrega directamente.

## Uso responsable

Este bot solo extrae información de contacto que el propio sitio publica
para que el público lo contacte — lo mismo que un visitante podría copiar a
mano. Aun así:

- Respeta `robots.txt` por defecto (usa `--ignore-robots` solo con
  autorización explícita del sitio).
- Limita cuántas páginas visita por sitio y espera entre solicitudes
  (`--delay`) para no sobrecargar servidores ajenos.
- Cumple los términos de uso de cada sitio y la normativa de protección de
  datos aplicable (habeas data, GDPR, etc.) del país donde operes,
  especialmente si vas a usar los datos para contactar personas.
- No está pensado para armar listas de envío masivo no solicitado (spam).

## Pruebas

```bash
pytest
```
