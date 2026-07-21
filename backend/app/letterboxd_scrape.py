import html
import logging
import re
import urllib.parse

from curl_cffi import requests as curl_requests
from curl_cffi.requests.exceptions import RequestException

from .models import RatedItem

logger = logging.getLogger(__name__)

# Cloudflare mete su código de bloqueo en el body como "error code: NNNN".
# 1010 = fingerprint del cliente, 1006/1007/1008 = IP baneada, 1015 = rate
# limit. Distinguirlos es la diferencia entre "arreglable en código" y "la IP
# de Render está en la lista negra".
CF_ERROR_RE = re.compile(r"error code:\s*(\d{4})")

LETTERBOXD_BASE = "https://letterboxd.com"
REQUEST_TIMEOUT = 10
REWATCH_BONUS = 0.5  # same bonus as the zip's diary.csv rewatch signal

# ponytail: hard cap on pages fetched per import (100 diary entries/page), so
# a prolific logger can't turn one import into hundreds of sequential
# requests. Bump if real users hit it.
MAX_DIARY_PAGES = 20

# Letterboxd's diary list view is server-rendered (unlike /films/ and
# /films/ratings/, which hydrate ratings client-side via React and can't be
# read without executing JS) — so the diary is the only public page this can
# scrape ratings from. Users who rate films without ever using the diary
# won't have those ratings picked up; documented in
# docs/letterboxd-username-import.md.
ROW_RE = re.compile(r'<tr class="diary-entry-row.*?</tr>', re.S)
TITLE_RE = re.compile(
    # trailing /<n>/ marks the nth diary logging of the same film (rewatches)
    r'<h2 class="primaryname prettify"><a href="[^"]*?/film/([^/"]+)/(?:\d+/)?"[^>]*>(.*?)</a>'
)
DATE_RE = re.compile(r"/diary/films/for/(\d{4})/(\d{2})/(\d{2})/")
RATING_RE = re.compile(r'class="rating rated-(\d{1,2})"')


class ScrapeError(Exception):
    pass


def _fetch_html(url: str) -> str | None:
    # Letterboxd sits behind Cloudflare bot protection that fingerprints the
    # TLS handshake (JA3), not just the User-Agent header — stdlib
    # urllib/requests get a 403 no matter what headers are sent, since
    # Python's ssl module has a recognizably different handshake than a real
    # browser. curl_cffi impersonates a real Chrome TLS fingerprint via
    # libcurl, which is what actually gets through.
    try:
        response = curl_requests.get(url, impersonate="chrome", timeout=REQUEST_TIMEOUT)
    except RequestException as exc:
        raise ScrapeError(f"No pude conectarme a Letterboxd: {exc}") from exc

    if response.status_code == 404:
        return None
    if not response.ok:
        # El motivo real no viene en el status sino en el body de Cloudflare;
        # se loguea del lado del server y no se le muestra al usuario.
        body = response.text or ""
        cf_match = CF_ERROR_RE.search(body)
        snippet = re.sub(r"<[^>]+>|\s+", " ", body).strip()[:200]
        logger.warning(
            "Letterboxd devolvió %s (cf_error=%s, cf_ray=%s, server=%s): %s",
            response.status_code,
            cf_match.group(1) if cf_match else "?",
            response.headers.get("cf-ray", "?"),
            response.headers.get("server", "?"),
            snippet,
        )
        raise ScrapeError(f"Letterboxd devolvió un error ({response.status_code}).")
    return response.text


def _parse_diary_page(page_html: str) -> list[dict]:
    entries = []
    for row in ROW_RE.findall(page_html):
        title_match = TITLE_RE.search(row)
        date_match = DATE_RE.search(row)
        if not title_match or not date_match:
            continue
        slug, raw_title = title_match.groups()
        year, month, day = date_match.groups()
        rating_match = RATING_RE.search(row)
        rating = int(rating_match.group(1)) / 2 if rating_match else None
        entries.append(
            {
                "slug": slug,
                "title": html.unescape(raw_title).strip(),
                "watched_date": f"{year}-{month}-{day}",
                "rating": rating,
            }
        )
    return entries


def fetch_letterboxd_diary(username: str) -> tuple[list[RatedItem], set[str]]:
    """Scrapes a public Letterboxd diary by username. Returns the same
    (ratings, extra_seen) shape as letterboxd_zip.parse_letterboxd_zip so it
    plugs into the same recommend() flow."""
    username = username.strip()
    if not username:
        raise ScrapeError("Ingresá un username de Letterboxd.")

    safe_username = urllib.parse.quote(username, safe="")
    ratings_by_slug: dict[str, RatedItem] = {}
    watched_only: dict[str, str] = {}  # slug -> title, watched but never rated

    for page in range(1, MAX_DIARY_PAGES + 1):
        page_html = _fetch_html(f"{LETTERBOXD_BASE}/{safe_username}/diary/films/page/{page}/")
        if page_html is None:
            if page == 1:
                raise ScrapeError(f"No encontré un usuario de Letterboxd llamado «{username}».")
            break

        entries = _parse_diary_page(page_html)
        if not entries:
            break

        for entry in entries:
            slug = entry["slug"]
            if slug in ratings_by_slug:
                # a repeat diary entry for the same film is a rewatch —
                # stronger taste signal than a single rating
                existing = ratings_by_slug[slug]
                existing.rating = min(5.0, existing.rating + REWATCH_BONUS)
            elif slug in watched_only:
                continue
            elif entry["rating"] is not None:
                ratings_by_slug[slug] = RatedItem(
                    title=entry["title"],
                    rating=entry["rating"],
                    review="",
                    watched_date=entry["watched_date"],
                )
            else:
                watched_only[slug] = entry["title"]

    if not ratings_by_slug and not watched_only:
        raise ScrapeError(f"«{username}» no tiene entradas de diario públicas para importar.")

    extra_seen = {title.strip().lower() for title in watched_only.values()}
    return list(ratings_by_slug.values()), extra_seen
