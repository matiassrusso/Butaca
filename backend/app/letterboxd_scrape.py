"""Import por username de Letterboxd, vía el feed RSS público de cada perfil.

Antes esto scrapeaba `/diary/films/page/N/` con `curl_cffi` para imitar el
fingerprint TLS de Chrome. Eso funcionaba desde una IP residencial pero
**siempre daba 403 en producción**: Cloudflare le sirve un challenge de
JavaScript a las IPs de datacenter (Render), y sin un browser no se puede
resolver. Ver `docs/letterboxd-username-import.md`.

El RSS que Letterboxd publica por perfil no tiene ese problema (sale con
`urllib` pelado), es un canal oficial en vez de scraping, y por entrada trae
más que el HTML del diario: rating, fecha de visto, flag de rewatch
explícito, si el miembro le puso like, y el id de TMDb ya resuelto.

El costo es el alcance: el feed solo expone actividad reciente (~50 entradas)
contra las ~2000 que paginaba el scraper. Para historial completo el camino
sigue siendo el `.zip`.
"""

import logging
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from urllib.error import HTTPError, URLError

from .models import RatedItem

logger = logging.getLogger(__name__)

LETTERBOXD_BASE = "https://letterboxd.com"
REQUEST_TIMEOUT = 15
# Cloudflare corta el User-Agent default de urllib (Python-urllib/3.x) — mismo
# motivo que en mailer.py.
USER_AGENT = "Butaca/1.0"

REWATCH_BONUS = 0.5  # igual que el rewatch del diary.csv del zip
LIKE_RATING = 4.5  # mismo rating sintético que letterboxd_zip.LIKE_RATING

NS = {"letterboxd": "https://letterboxd.com", "tmdb": "https://themoviedb.org"}


class ScrapeError(Exception):
    pass


def _fetch_feed(username: str) -> str:
    url = f"{LETTERBOXD_BASE}/{urllib.parse.quote(username, safe='')}/rss/"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        if exc.code == 404:
            raise ScrapeError(f"No encontré un usuario de Letterboxd llamado «{username}».") from exc
        logger.warning("Letterboxd RSS devolvió %s para %s", exc.code, username)
        raise ScrapeError(f"Letterboxd devolvió un error ({exc.code}).") from exc
    except URLError as exc:
        raise ScrapeError(f"No pude conectarme a Letterboxd: {exc}") from exc


def _text(item: ET.Element, tag: str, ns: str = "letterboxd") -> str | None:
    node = item.find(f"{ns}:{tag}", NS)
    return node.text.strip() if node is not None and node.text else None


def _parse_feed(xml_text: str) -> list[dict]:
    """Devuelve una entrada por item de película del feed. Los items que no son
    de película (listas publicadas) no traen `filmTitle` y se descartan."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ScrapeError("Letterboxd devolvió una respuesta que no pude leer.") from exc

    entries = []
    for item in root.iter("item"):
        title = _text(item, "filmTitle")
        if not title:
            continue

        raw_rating = _text(item, "memberRating")
        try:
            rating = float(raw_rating) if raw_rating else None
        except ValueError:
            rating = None

        raw_tmdb_id = _text(item, "movieId", ns="tmdb")
        try:
            tmdb_id = int(raw_tmdb_id) if raw_tmdb_id else None
        except ValueError:
            tmdb_id = None

        entries.append(
            {
                "title": title,
                "rating": rating,
                "watched_date": _text(item, "watchedDate"),
                "liked": _text(item, "memberLike") == "Yes",
                "tmdb_id": tmdb_id,
            }
        )
    return entries


def fetch_letterboxd_diary(username: str) -> tuple[list[RatedItem], set[str]]:
    """Lee el feed RSS público de un usuario. Devuelve el mismo par
    (ratings, extra_seen) que `letterboxd_zip.parse_letterboxd_zip`, así entra
    al mismo flujo de recommend()."""
    username = username.strip()
    if not username:
        raise ScrapeError("Ingresá un username de Letterboxd.")

    entries = _parse_feed(_fetch_feed(username))

    ratings_by_title: dict[str, RatedItem] = {}
    watched_only: dict[str, str] = {}  # key normalizada -> título, visto sin puntuar

    for entry in entries:
        key = entry["title"].strip().lower()

        if key in ratings_by_title:
            # el mismo título repetido en el feed es un rewatch: señal de gusto
            # más fuerte que una sola vista
            existing = ratings_by_title[key]
            existing.rating = min(5.0, existing.rating + REWATCH_BONUS)
            continue

        rating = entry["rating"]
        source = "import"
        if rating is None and entry["liked"]:
            # un like sin puntuar es señal positiva igual, igual que en el zip
            rating = LIKE_RATING
            source = "like"

        if rating is None:
            watched_only.setdefault(key, entry["title"])
            continue

        watched_only.pop(key, None)
        ratings_by_title[key] = RatedItem(
            title=entry["title"],
            rating=rating,
            review="",
            watched_date=entry["watched_date"],
            tmdb_id=entry["tmdb_id"],
            source=source,
        )

    if not ratings_by_title and not watched_only:
        raise ScrapeError(f"«{username}» no tiene actividad pública reciente para importar.")

    extra_seen = {title.strip().lower() for title in watched_only.values()}
    return list(ratings_by_title.values()), extra_seen
