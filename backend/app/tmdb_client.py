import datetime
import json
import logging
import os
import time
import urllib.parse
import urllib.request
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import URLError

from .recommender import PICK_OPTIONS, positive_tags_from_text

logger = logging.getLogger(__name__)

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
DISCOVER_URL = "https://api.themoviedb.org/3/discover/movie"
DISCOVER_TV_URL = "https://api.themoviedb.org/3/discover/tv"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"
REQUEST_TIMEOUT = 5
CACHE_TTL_SECONDS = 5 * 60
CACHE_MAX_ENTRIES = 32

# TMDb's movie genre ids are stable, publicly documented constants, so we
# hardcode the id -> our tag vocabulary mapping instead of fetching and
# caching /genre/movie/list. Coarse on purpose: real nuance comes from the
# overview text scan below, and eventually from the LLM agent.
GENRE_ID_TAG_MAP: dict[int, list[str]] = {
    28: ["action", "kinetic", "blockbuster"],  # Action
    12: ["kinetic", "blockbuster"],  # Adventure
    # "animation" es un tag propio, no solo "stylized": sin el, rechazar una
    # peli animada penalizaba "stylized" -- que comparten Drive, Blade Runner
    # o cualquier Wes Anderson -- y no filtraba NADA de lo animado. Por eso
    # "no me interesa" sobre anime no paraba de traer anime (Matias, 2026-08-07).
    16: ["animation", "stylized"],  # Animation
    35: ["funny", "light"],  # Comedy
    80: ["dark", "psychological"],  # Crime
    99: [],  # Documentary
    18: ["character"],  # Drama
    10751: ["light"],  # Family
    14: ["stylized"],  # Fantasy
    36: ["character"],  # History
    27: ["dark"],  # Horror
    10402: ["light"],  # Music
    9648: ["mysterious", "psychological"],  # Mystery
    10749: ["romantic", "intimate"],  # Romance
    878: ["stylized", "mysterious"],  # Science Fiction
    10770: [],  # TV Movie
    53: ["psychological", "dark"],  # Thriller
    10752: ["dark"],  # War
    37: ["character"],  # Western
}

# Only moods with a clean genre correspondence bias the discover query.
# "slow" has no honest TMDb genre match, so it's left unfiltered and the
# tag-scoring step in recommend() does the work instead.
MOOD_GENRE_ID_MAP: dict[str, int] = {
    "funny": 35,
    "romance": 10749,
    "action": 28,
    "psychological": 53,
}

# TMDb's TV genre ids are a different set than movie genre ids (e.g. no
# standalone Romance/Thriller/Horror). Mapped separately, same coarse
# philosophy as GENRE_ID_TAG_MAP.
TV_GENRE_ID_TAG_MAP: dict[int, list[str]] = {
    10759: ["action", "kinetic", "blockbuster"],  # Action & Adventure
    16: ["animation", "stylized"],  # Animation
    35: ["funny", "light"],  # Comedy
    80: ["dark", "psychological"],  # Crime
    99: [],  # Documentary
    18: ["character"],  # Drama
    10751: ["light"],  # Family
    10762: ["light"],  # Kids
    9648: ["mysterious", "psychological"],  # Mystery
    10763: [],  # News
    10764: [],  # Reality
    10765: ["stylized", "mysterious"],  # Sci-Fi & Fantasy
    10766: ["romantic", "intimate"],  # Soap
    10767: [],  # Talk
    10768: ["dark"],  # War & Politics
    37: ["character"],  # Western
}

# /movie/{id}/keywords (y /tv/) publica tags atómicos y específicos por título
# ("heist", "time loop"), un eje narrativo que los genre_ids de arriba no tienen
# y que el escaneo de overview de positive_tags_from_text no puede inferir.
# El vocabulario de TMDb es enorme y sin curar, así que esto es una allowlist
# deliberada: solo keywords que un usuario reconocería como razón de un pick.
# Match EXACTO sobre el nombre en minúsculas, no substring — los nombres ya
# vienen atomizados, que es justamente la ventaja sobre el escaneo de overview.
#
# Todos estos strings están verificados contra las páginas públicas de TMDb
# (Ocean's Eleven, Oldboy, Little Miss Sunshine, Groundhog Day, Mad Max: Fury
# Road, Blair Witch, Lady Bird, John Wick, Back to the Future, 12 Angry Men,
# The Social Network). Importa: un string equivocado no falla, simplemente
# nunca matchea — quedan varios descartados por eso ("one location", que en
# realidad TMDb llama `huis clos`; "robbery" → es `caper`; "assassin" → es
# `hitman`). Verificar contra un título real antes de sumar entradas nuevas.
# ponytail: tabla semilla. Crecerla es editar este dict + su entrada en
# recommender.TAG_PHRASES; no hay código que cambiar.
KEYWORD_TAG_MAP: dict[str, list[str]] = {
    "heist": ["heist"],
    "caper": ["heist"],
    "based on true story": ["true-story"],
    "biography": ["true-story"],
    "time loop": ["time-travel"],
    "time travel": ["time-travel"],
    "time warp": ["time-travel"],
    "coming of age": ["coming-of-age"],
    "revenge": ["revenge"],
    "road trip": ["road-trip"],
    "road movie": ["road-trip"],
    "hitman": ["hitman"],
    "dystopia": ["dystopian"],
    "post-apocalyptic future": ["dystopian"],
    "dark future": ["dystopian"],
    "found footage": ["found-footage"],
    "pseudo-documentary": ["found-footage"],
    "faux documentary": ["found-footage"],
    # TMDb usa el término teatral francés para "todo pasa en un solo ambiente"
    "huis clos": ["single-location"],
    # ronda 2 (2026-07-30): strings vistos en logs de producción sin mapear.
    # Verificados esta vez contra el buscador público de keywords de TMDb
    # (themoviedb.org/search/keyword?query=...) en vez de un título puntual —
    # confirma que el string exacto existe en el vocabulario de TMDb, mismo
    # criterio de "no adivinar" que el resto de la tabla. "historical" quedó
    # afuera a propósito: existe, pero es tan genérico como el género History
    # y no se lee como una razón específica de un pick.
    "hold-up robbery": ["heist"],  # asalto a mano armada, variante de heist
    "psychological thriller": ["psychological"],
    "character study": ["character"],
    "dark comedy": ["dark-comedy"],
    "neo-noir": ["neo-noir"],
    "folk horror": ["folk-horror"],
    "survival": ["survival"],
    "on the run": ["on-the-run"],
    "revisionist western": ["revisionist-western"],
}

# Only "funny" and "action" have a clean TV genre match; the rest fall back
# to unfiltered discovery + tag scoring, same as MOOD_GENRE_ID_MAP.
MOOD_TV_GENRE_ID_MAP: dict[str, int] = {
    "funny": 35,
    "action": 10759,
}

# Same TMDb genre ids as above, but mapped to their real display name
# instead of our internal tag vocabulary — used by the taste profile, where
# "Drama" reads better to the user than "character".
GENRE_ID_NAME_MAP: dict[int, str] = {
    28: "Acción",
    12: "Aventura",
    16: "Animación",
    35: "Comedia",
    80: "Crimen",
    99: "Documental",
    18: "Drama",
    10751: "Familia",
    14: "Fantasía",
    36: "Historia",
    27: "Terror",
    10402: "Música",
    9648: "Misterio",
    10749: "Romance",
    878: "Ciencia ficción",
    10770: "TV Movie",
    53: "Thriller",
    10752: "Bélica",
    37: "Western",
}

TV_GENRE_ID_NAME_MAP: dict[int, str] = {
    10759: "Acción y aventura",
    16: "Animación",
    35: "Comedia",
    80: "Crimen",
    99: "Documental",
    18: "Drama",
    10751: "Familia",
    10762: "Infantil",
    9648: "Misterio",
    10763: "Noticias",
    10764: "Reality",
    10765: "Ciencia ficción y fantasía",
    10766: "Telenovela",
    10767: "Talk show",
    10768: "Bélica y política",
    37: "Western",
}

# inverse of the maps above (display name -> TMDb id), needed to go from the
# taste profile's genre_breakdown (which stores display names, e.g. "Drama")
# back to a TMDb genre id for the personalized discover query
GENRE_NAME_ID_MAP: dict[str, int] = {name: gid for gid, name in GENRE_ID_NAME_MAP.items()}
TV_GENRE_NAME_ID_MAP: dict[str, int] = {name: gid for gid, name in TV_GENRE_ID_NAME_MAP.items()}

SEARCH_URL = "https://api.themoviedb.org/3/search/movie"
SEARCH_TV_URL = "https://api.themoviedb.org/3/search/tv"
# a title's matched genres/year/credits don't change, so these are cached
# much longer than discover pages
TITLE_CACHE_TTL_SECONDS = 24 * 60 * 60
TITLE_CACHE_MAX_ENTRIES = 500

_DISCOVER_CACHE: OrderedDict[tuple[str, str, int], tuple[float, list[dict]]] = OrderedDict()
_SEARCH_CACHE: OrderedDict[str, tuple[float, dict | None]] = OrderedDict()
_TASTE_CREDITS_CACHE: OrderedDict[tuple[str, int], tuple[float, dict]] = OrderedDict()
_PERSON_CACHE: OrderedDict[str, tuple[float, int | None]] = OrderedDict()
_PERSONALIZED_CACHE: OrderedDict[tuple, tuple[float, list[dict]]] = OrderedDict()
_WATCH_PROVIDERS_CACHE: OrderedDict[tuple[str, int, str], tuple[float, dict]] = OrderedDict()
_KEYWORDS_CACHE: OrderedDict[tuple[str, int], tuple[float, list[str]]] = OrderedDict()
_TITLE_BY_ID_CACHE: OrderedDict[tuple[str, int], tuple[float, dict | None]] = OrderedDict()
# picker "a tu elección" (recommender.PICK_OPTIONS) — id de una keyword de
# búsqueda no cambia, mismo TTL que _PERSON_CACHE; páginas de /discover por
# opción, mismo TTL que _DISCOVER_CACHE (compartida entre selecciones)
_KEYWORD_ID_CACHE: OrderedDict[str, tuple[float, int | None]] = OrderedDict()
_OPTION_CACHE: OrderedDict[tuple[str, str, int], tuple[float, list[dict]]] = OrderedDict()
# single entry, not keyed — there's only one "the catalog" to count
_CATALOG_STATS_CACHE_TTL_SECONDS = 24 * 60 * 60
_catalog_stats_cache: tuple[float, dict] | None = None

# ponytail: matches a single discover page's worth of movie candidates; raise
# if latency allows enriching more per personalized recommend request.
CREDITS_ENRICH_CAP = 30

# El pool personalizado pedía UNA página (20 títulos) y siempre la misma, así
# que "Nuevos picks" volvía a mirar los mismos 20 de siempre y, con la
# exclusión de ya-recomendados, se quedaba sin nada para ofrecer (reportado por
# Matías, 2026-08-07: "¿en serio hay solo 4 películas en todo el mundo?" —
# medido contra TMDb, un perfil de género típico devuelve ~7.500 títulos en
# ~376 páginas). Mismo bug que ya se había arreglado para el swipe de /rate el
# 2026-08-03, que nunca se llevó acá.
# Piso de votos del pool de recomendación. Estaba en 200 y ese era el motivo
# real de "son pésimas recomendaciones" (Matías, 2026-08-07): con
# sort_by=vote_average.desc, un piso bajo premia lo nicho-pero-adorado — una
# peli con 200 votos y 8.5 le gana a un clásico con 20.000 y 8.4. Medido sobre
# 60 títulos de un perfil drama/thriller/acción:
#
#   piso 200  -> 26% animadas, 48% no-inglesas (cabeza: Attack on Titan, Demon Slayer)
#   piso 3000 -> 10% animadas, 25% no-inglesas (cabeza: The Dark Knight, Parasite)
#
# O sea que un cuarto del pool era anime sin importar el gusto del usuario, y
# ninguna penalización por tags podía compensar semejante inundación. 3000 baja
# el sesgo a la mitad sin volverlo puro Hollywood (Parasite sobrevive) y deja
# 1.128 títulos / 57 páginas, de sobra para la ventana de PERSONALIZED_PAGE_WINDOW.
MIN_VOTE_COUNT = 3000

# El picker ("a tu elección") mantiene el piso viejo A PROPÓSITO: ahí el usuario
# pidió algo angosto explícitamente, y filtrar por popularidad justo entonces
# vacía las opciones. Medido con el piso alto: "b movie" (vibra Schlock) queda
# en 0 títulos, "folk horror" en 5, "gothic horror" en 6. Cuando alguien pide
# schlock, hay que darle schlock — el sesgo del pool por defecto es un problema
# distinto, porque ahí no eligió nada.
MIN_VOTE_COUNT_PICKER = 200

PERSONALIZED_PAGES = 3  # páginas por consulta de discover: 20 títulos cada una
# Las páginas arrancan en un offset que avanza a medida que el usuario consume
# picks, y da la vuelta al llegar al tope. Acotado (y no "seguir avanzando para
# siempre") porque sort_by=vote_average.desc hace que la página 300 sea
# relleno, y porque un offset más allá del total_pages real devolvería vacío.
PERSONALIZED_PAGE_WINDOW = 10


class TmdbError(Exception):
    pass


def _load_env_file() -> None:
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_env_file()


def is_configured() -> bool:
    return bool(os.environ.get("TMDB_API_KEY"))


def _get_json(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT) as response:
            return json.loads(response.read())
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise TmdbError(f"No pude consultar TMDb: {exc}") from exc


def _image_url(path: str | None, size: str) -> str | None:
    if not path:
        return None
    return f"{TMDB_IMAGE_BASE}/{size}{path}"


def _map_result(
    raw: dict,
    kind: str = "movie",
    genre_tag_map: dict[int, list[str]] = GENRE_ID_TAG_MAP,
    require_tags: bool = True,
) -> dict | None:
    title_field = "title" if kind == "movie" else "name"
    date_field = "release_date" if kind == "movie" else "first_air_date"
    title = (raw.get(title_field) or "").strip()
    date_value = raw.get(date_field) or ""
    if not title or len(date_value) < 4:
        return None

    try:
        year = int(date_value[:4])
    except ValueError:
        return None

    overview = raw.get("overview") or ""
    tags: set[str] = set()
    for genre_id in raw.get("genre_ids", []):
        tags.update(genre_tag_map.get(genre_id, []))
    tags.update(positive_tags_from_text(overview))

    if require_tags and not tags:
        return None

    return {
        "tmdb_id": raw.get("id"),
        "title": title,
        "year": year,
        "kind": kind,
        "tags": sorted(tags),
        "poster_path": _image_url(raw.get("poster_path"), "w500"),
        "backdrop_path": _image_url(raw.get("backdrop_path"), "w780"),
        "overview": overview,
        "vote_average": raw.get("vote_average"),
    }


def _now_monotonic() -> float:
    return time.monotonic()


def _clone_items(items: list[dict]) -> list[dict]:
    return [item.copy() for item in items]


def _get_cached_discover_page(cache_key: tuple[str, str, int]) -> list[dict] | None:
    cached = _DISCOVER_CACHE.get(cache_key)
    if cached is None:
        return None

    expires_at, items = cached
    if expires_at <= _now_monotonic():
        # .pop(..., None) not del: build_taste_profile fetches candidates
        # concurrently now, so another thread may have already evicted this
        # same expired key between the .get() above and here.
        _DISCOVER_CACHE.pop(cache_key, None)
        return None

    _DISCOVER_CACHE.move_to_end(cache_key)
    return _clone_items(items)


def _store_cached_discover_page(cache_key: tuple[str, str, int], items: list[dict]) -> None:
    _DISCOVER_CACHE[cache_key] = (_now_monotonic() + CACHE_TTL_SECONDS, _clone_items(items))
    _DISCOVER_CACHE.move_to_end(cache_key)
    while len(_DISCOVER_CACHE) > CACHE_MAX_ENTRIES:
        _DISCOVER_CACHE.popitem(last=False)


def _fetch_from_discover(
    url: str,
    kind: str,
    genre_tag_map: dict[int, list[str]],
    mood_genre_map: dict[str, int],
    mood: str,
    api_key: str,
    pages: int,
) -> list[dict]:
    normalized_mood = mood.strip().lower()
    genre_id = mood_genre_map.get(normalized_mood)

    candidates: list[dict] = []
    for page in range(1, pages + 1):
        cache_key = (kind, normalized_mood, page)
        cached_page = _get_cached_discover_page(cache_key)
        if cached_page is not None:
            candidates.extend(cached_page)
            continue

        params = {
            "api_key": api_key,
            "language": "en-US",
            # vote_average, not popularity: popularity.desc ranks what's
            # trending right now (new releases, current buzz), which skews
            # every recommendation toward recent titles regardless of taste.
            # vote_count.gte keeps this from surfacing obscure titles with a
            # handful of 10/10 votes.
            "sort_by": "vote_average.desc",
            "vote_count.gte": MIN_VOTE_COUNT,
            "include_adult": "false",
            "page": page,
        }
        if genre_id:
            params["with_genres"] = genre_id

        page_url = f"{url}?{urllib.parse.urlencode(params)}"
        data = _get_json(page_url)

        mapped_page: list[dict] = []
        for raw in data.get("results", []):
            mapped = _map_result(raw, kind, genre_tag_map)
            if mapped:
                mapped_page.append(mapped)

        _store_cached_discover_page(cache_key, mapped_page)
        candidates.extend(mapped_page)

    return candidates


def fetch_candidates(mood: str, pages: int = 2) -> list[dict]:
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        raise TmdbError("TMDB_API_KEY no configurada.")

    movies = _fetch_from_discover(
        DISCOVER_URL, "movie", GENRE_ID_TAG_MAP, MOOD_GENRE_ID_MAP, mood, api_key, pages
    )
    series = _fetch_from_discover(
        DISCOVER_TV_URL, "series", TV_GENRE_ID_TAG_MAP, MOOD_TV_GENRE_ID_MAP, mood, api_key, pages
    )
    return movies + series


def _resolve_keyword_id(name: str) -> int | None:
    """Resuelve un string de keyword (recommender.PICK_OPTIONS) a su id
    numérico de TMDb, para el filtro with_keywords de /discover. Match
    exacto sobre el nombre en minúsculas -- /search/keyword devuelve
    variantes parecidas (p.ej. "hip hop" trae "hip-hop", "hip hop culture",
    etc.), así que tomar resultados[0] a ciegas matchearía la keyword
    equivocada. Un miss no rompe nada, solo esa keyword no aporta candidatos
    (mismo criterio que _enrich_with_keyword_tags). Cacheado 24h como
    _resolve_person_id: el id de una keyword no cambia."""
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        raise TmdbError("TMDB_API_KEY no configurada.")

    cache_key = name.strip().lower()
    cached = _KEYWORD_ID_CACHE.get(cache_key)
    if cached is not None:
        expires_at, result = cached
        if expires_at > _now_monotonic():
            _KEYWORD_ID_CACHE.move_to_end(cache_key)
            return result
        _KEYWORD_ID_CACHE.pop(cache_key, None)

    params = {"api_key": api_key, "query": name, "language": "en-US"}
    data = _get_json(f"https://api.themoviedb.org/3/search/keyword?{urllib.parse.urlencode(params)}")
    keyword_id = next(
        (r["id"] for r in data.get("results", []) if (r.get("name") or "").strip().lower() == cache_key),
        None,
    )

    _KEYWORD_ID_CACHE[cache_key] = (_now_monotonic() + TITLE_CACHE_TTL_SECONDS, keyword_id)
    _KEYWORD_ID_CACHE.move_to_end(cache_key)
    while len(_KEYWORD_ID_CACHE) > TITLE_CACHE_MAX_ENTRIES:
        _KEYWORD_ID_CACHE.popitem(last=False)
    return keyword_id


def _get_cached_option_page(cache_key: tuple[str, str, int]) -> list[dict] | None:
    cached = _OPTION_CACHE.get(cache_key)
    if cached is None:
        return None
    expires_at, items = cached
    if expires_at <= _now_monotonic():
        _OPTION_CACHE.pop(cache_key, None)
        return None
    _OPTION_CACHE.move_to_end(cache_key)
    return _clone_items(items)


def _store_cached_option_page(cache_key: tuple[str, str, int], items: list[dict]) -> None:
    _OPTION_CACHE[cache_key] = (_now_monotonic() + CACHE_TTL_SECONDS, _clone_items(items))
    _OPTION_CACHE.move_to_end(cache_key)
    while len(_OPTION_CACHE) > CACHE_MAX_ENTRIES:
        _OPTION_CACHE.popitem(last=False)


def _fetch_option_for_kind(option: dict, kind: str, pages: int, api_key: str) -> list[dict]:
    """Un request a /discover por opción y por kind -- nunca combinar
    géneros/keywords de opciones DISTINTAS en un mismo request: TMDb hace
    AND entre with_genres y with_keywords, así que juntar dos opciones en
    un solo llamado significaría "opción A Y opción B", no la semántica OR
    que promete recommender.required_any_groups."""
    genre_ids = option["movie_genres"] if kind == "movie" else option["tv_genres"]
    keyword_ids = [
        kid for name in option["keywords"] if (kid := _resolve_keyword_id(name)) is not None
    ]
    if not genre_ids and not keyword_ids:
        # esta opción no tiene query para este kind (ej. "Terror" no tiene
        # género de TV equivalente) -- no aporta nada, no es un error
        return []

    url = DISCOVER_URL if kind == "movie" else DISCOVER_TV_URL
    genre_tag_map = GENRE_ID_TAG_MAP if kind == "movie" else TV_GENRE_ID_TAG_MAP

    results: list[dict] = []
    for page in range(1, pages + 1):
        cache_key = (kind, option["key"], page)
        cached_page = _get_cached_option_page(cache_key)
        if cached_page is not None:
            results.extend(cached_page)
            continue

        params = {
            "api_key": api_key,
            "language": "en-US",
            "sort_by": "vote_average.desc",
            "vote_count.gte": MIN_VOTE_COUNT_PICKER,
            "include_adult": "false",
            "page": page,
        }
        if genre_ids:
            params["with_genres"] = "|".join(str(gid) for gid in genre_ids)
        if keyword_ids:
            params["with_keywords"] = "|".join(str(kid) for kid in keyword_ids)

        data = _get_json(f"{url}?{urllib.parse.urlencode(params)}")
        mapped_page: list[dict] = []
        for raw in data.get("results", []):
            # require_tags=False: sabemos que este candidato matchea la
            # opción porque TMDb lo filtró por nosotros (with_genres/
            # with_keywords), no depende de que _map_result haya inferido
            # algún tag desde genre_ids/overview -- géneros como
            # "documental" mapean a [] en GENRE_ID_TAG_MAP y perderían casi
            # todo si dependieran de eso.
            mapped = _map_result(raw, kind, genre_tag_map, require_tags=False)
            if mapped is None:
                continue
            # estampar el tag de la opción encima de lo que haya inferido
            # _map_result -- este es el paso que reemplaza al post-filtro
            mapped["tags"] = sorted(set(mapped["tags"]) | set(option["tags"]))
            mapped_page.append(mapped)

        _store_cached_option_page(cache_key, mapped_page)
        results.extend(mapped_page)

    return results


def fetch_candidates_for_options(keys: list[str], kind_filter: str = "both", pages: int = 1) -> list[dict]:
    """El picker "a tu elección" (recommender.PICK_OPTIONS) maneja su propio
    fetch en vez de post-filtrar el pool de perfil/mood que main.py trae por
    otra razón -- con opciones angostas (una keyword puntual) ese pool nunca
    traía señal suficiente para que el post-filtro encontrara algo (bug
    reportado 2026-08-02). Un request por opción elegida y por kind,
    paralelizado; deduplicado por (kind, título)."""
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        raise TmdbError("TMDB_API_KEY no configurada.")

    options_by_key = {o["key"]: o for o in PICK_OPTIONS}
    kinds = ["movie", "series"] if kind_filter == "both" else [kind_filter]
    jobs = [
        (option, kind)
        for key in keys
        if (option := options_by_key.get(key)) is not None
        for kind in kinds
    ]
    if not jobs:
        return []

    def _run(job: tuple[dict, str]) -> list[dict]:
        option, kind = job
        return _fetch_option_for_kind(option, kind, pages, api_key)

    with ThreadPoolExecutor(max_workers=4) as pool:
        pages_per_job = pool.map(_run, jobs)

    combined: list[dict] = [item for page_items in pages_per_job for item in page_items]

    seen: set[tuple[str, str]] = set()
    deduped: list[dict] = []
    for item in combined:
        key = (item["kind"], item["title"].strip().lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    return deduped


WEEKLY_TRENDING_URL = "https://api.themoviedb.org/3/trending/movie/week"
WEEKLY_PICKS_COUNT = 5
# tope de páginas para completar las 5 — cada página trae 20 resultados y
# _map_result descarta los sin tags, así que la página 1 sola a veces no
# alcanza para 5 (bug reportado por Matías, 2026-07-31: solo 3 de 5)
WEEKLY_TRENDING_MAX_PAGES = 3
# de las 5 semanales, cuántas se reservan para variedad de épocas en vez de
# trending puro — sin esto las 5 daban siempre estrenos del año actual,
# porque /trending/movie/week sesga a lo nuevo por diseño (reportado por
# Matías, 2026-07-31: "las 5 dieron todas de 2026")
WEEKLY_CLASSIC_SLOTS = 2
# rota una década por semana ISO en vez de siempre la misma — sigue siendo
# 100% TMDb real (discover ordenado por vote_average), no una lista armada
# a mano; año de inicio de cada década que /discover filtra con
# primary_release_date
WEEKLY_CLASSIC_DECADES = [1970, 1980, 1990, 2000, 2010]
# cacheado por semana ISO (no por TTL fijo): "recomendaciones semanales,
# iguales para todos" (pedido de Matías) — todos los usuarios que pidan
# /weekly en la misma semana tienen que ver EXACTAMENTE el mismo set de
# películas, así que la clave de cache es la semana, no un timestamp.
_WEEKLY_TRENDING_CACHE: dict[str, list[dict]] = {}


def _iso_week_key() -> str:
    year, week, _ = datetime.datetime.now(datetime.timezone.utc).isocalendar()
    return f"{year}-W{week:02d}"


def _iso_week_number() -> int:
    _, week, _ = datetime.datetime.now(datetime.timezone.utc).isocalendar()
    return week


def _fetch_trending_movies(api_key: str, seen_ids: set[int], count: int) -> list[dict]:
    picks: list[dict] = []
    if count <= 0:
        return picks
    for page in range(1, WEEKLY_TRENDING_MAX_PAGES + 1):
        params = {"api_key": api_key, "language": "en-US", "page": page}
        data = _get_json(f"{WEEKLY_TRENDING_URL}?{urllib.parse.urlencode(params)}")
        for raw in data.get("results", []):
            result = _map_result(raw, "movie", GENRE_ID_TAG_MAP)
            if result is None or result["tmdb_id"] in seen_ids:
                continue
            seen_ids.add(result["tmdb_id"])
            picks.append(result)
            if len(picks) >= count:
                break
        if len(picks) >= count:
            break
    return picks


def _fetch_weekly_classics(api_key: str, seen_ids: set[int], count: int) -> list[dict]:
    """Lo mejor puntuado (vote_average, vote_count.gte para filtrar ruido)
    de una década que rota cada semana ISO — variedad de épocas sin
    curación a mano, ver WEEKLY_CLASSIC_SLOTS."""
    if count <= 0:
        return []
    decade = WEEKLY_CLASSIC_DECADES[_iso_week_number() % len(WEEKLY_CLASSIC_DECADES)]
    params = {
        "api_key": api_key,
        "language": "en-US",
        "sort_by": "vote_average.desc",
        "vote_count.gte": 1000,
        "primary_release_date.gte": f"{decade}-01-01",
        "primary_release_date.lte": f"{decade + 9}-12-31",
    }
    data = _get_json(f"{DISCOVER_URL}?{urllib.parse.urlencode(params)}")
    picks: list[dict] = []
    for raw in data.get("results", []):
        result = _map_result(raw, "movie", GENRE_ID_TAG_MAP)
        if result is None or result["tmdb_id"] in seen_ids:
            continue
        seen_ids.add(result["tmdb_id"])
        picks.append(result)
        if len(picks) >= count:
            break
    return picks


def fetch_top_rated_by_decade(kind: str, decade: int, pages: int = 1) -> list[dict]:
    """Lo mejor puntuado (vote_average.desc) de una década/formato dado —
    mismo patrón que _fetch_weekly_classics, generalizado a movies+series y
    cualquier década. Usado por vibes_clustering para mezclar en la semilla
    de la Fase 4: el discover ordenado por popularidad que usa fetch_candidates
    está hoy dominado por anime/K-drama en /tv (medido 2026-08-02: 13 de 39
    movimientos eran justamente eso), y esto ataca el sesgo de raíz en vez de
    compensarlo con más géneros."""
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        raise TmdbError("TMDB_API_KEY no configurada.")

    url = DISCOVER_URL if kind == "movie" else DISCOVER_TV_URL
    genre_tag_map = GENRE_ID_TAG_MAP if kind == "movie" else TV_GENRE_ID_TAG_MAP
    date_field = "primary_release_date" if kind == "movie" else "first_air_date"

    items: list[dict] = []
    for page in range(1, pages + 1):
        params = {
            "api_key": api_key,
            "language": "en-US",
            "sort_by": "vote_average.desc",
            "vote_count.gte": MIN_VOTE_COUNT,
            "page": page,
            f"{date_field}.gte": f"{decade}-01-01",
            f"{date_field}.lte": f"{decade + 9}-12-31",
        }
        data = _get_json(f"{url}?{urllib.parse.urlencode(params)}")
        for raw in data.get("results", []):
            result = _map_result(raw, kind, genre_tag_map)
            if result is not None:
                items.append(result)
    return items


def fetch_weekly_trending() -> list[dict]:
    """5 películas semanales: 3 de tendencia real de TMDb
    (/trending/movie/week) + 2 de variedad de épocas (WEEKLY_CLASSIC_SLOTS,
    ver _fetch_weekly_classics) — mismo shape que fetch_candidates (via
    _map_result), mismas para todos los usuarios durante toda la semana
    ISO actual. No hay curación editorial a mano en ningún lado: ambas
    fuentes son consultas reales a TMDb, no una lista armada a mano."""
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        raise TmdbError("TMDB_API_KEY no configurada.")

    cache_key = _iso_week_key()
    cached = _WEEKLY_TRENDING_CACHE.get(cache_key)
    if cached is not None:
        return _clone_items(cached)

    seen_ids: set[int] = set()
    mapped = _fetch_trending_movies(api_key, seen_ids, WEEKLY_PICKS_COUNT - WEEKLY_CLASSIC_SLOTS)

    try:
        mapped += _fetch_weekly_classics(api_key, seen_ids, WEEKLY_CLASSIC_SLOTS)
    except TmdbError:
        pass  # variedad de épocas es best-effort — si falla, se rellena abajo con más trending

    if len(mapped) < WEEKLY_PICKS_COUNT:
        mapped += _fetch_trending_movies(api_key, seen_ids, WEEKLY_PICKS_COUNT - len(mapped))

    mapped = mapped[:WEEKLY_PICKS_COUNT]

    # sin esto, todos los candidatos comparten el mismo vocabulario chico de
    # ~12 tags de género — con un perfil de gusto diverso, positive_tags
    # termina cubriéndolos todos y cualquier candidato matchea "completo",
    # dando el mismo match_score a los 5 (reportado por Matías, 2026-07-31:
    # "todas dan 81%"). Mismo enriquecimiento que ya reciben los candidatos
    # de /recommend (fetch_personalized_candidates) — acá nunca se aplicaba.
    for item in mapped:
        _enrich_with_keyword_tags(item, "movie")

    # una sola semana vigente a la vez — no hace falta un LRU con TTL, la
    # semana vieja simplemente no se vuelve a pedir nunca más
    _WEEKLY_TRENDING_CACHE.clear()
    _WEEKLY_TRENDING_CACHE[cache_key] = mapped
    return _clone_items(mapped)


def fetch_catalog_stats() -> dict:
    """Real counts from the same TMDb pool recommendations are drawn from
    (vote_count.gte MIN_VOTE_COUNT, matching _fetch_from_discover), not the raw TMDb
    total which is inflated by obscure/duplicate entries. Cached a day —
    this backs a footer decoration, not something that needs to be live."""
    global _catalog_stats_cache
    if _catalog_stats_cache is not None:
        expires_at, cached = _catalog_stats_cache
        if expires_at > _now_monotonic():
            return cached

    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        raise TmdbError("TMDB_API_KEY no configurada.")

    def _total_results(url: str) -> int:
        params = {"api_key": api_key, "vote_count.gte": MIN_VOTE_COUNT, "include_adult": "false"}
        data = _get_json(f"{url}?{urllib.parse.urlencode(params)}")
        return int(data.get("total_results", 0))

    stats = {
        "movies": _total_results(DISCOVER_URL),
        "series": _total_results(DISCOVER_TV_URL),
        "genres": len(set(GENRE_ID_TAG_MAP) | set(TV_GENRE_ID_TAG_MAP)),
    }
    _catalog_stats_cache = (_now_monotonic() + _CATALOG_STATS_CACHE_TTL_SECONDS, stats)
    return stats


def _tmdb_endpoint_kind(kind: str) -> str:
    return "movie" if kind == "movie" else "tv"


def fetch_credits(tmdb_id: int, kind: str = "movie", limit: int = 10) -> list[dict]:
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        raise TmdbError("TMDB_API_KEY no configurada.")

    endpoint = _tmdb_endpoint_kind(kind)
    url = f"https://api.themoviedb.org/3/{endpoint}/{tmdb_id}/credits?api_key={api_key}"
    data = _get_json(url)

    cast = sorted(data.get("cast", []), key=lambda member: member.get("order", 999))
    return [
        {
            "name": member["name"],
            "character": member.get("character", ""),
            "profile_path": _image_url(member.get("profile_path"), "w185"),
        }
        for member in cast
        if member.get("name")
    ][:limit]


def fetch_trailer_key(tmdb_id: int, kind: str = "movie") -> str | None:
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        raise TmdbError("TMDB_API_KEY no configurada.")

    endpoint = _tmdb_endpoint_kind(kind)
    url = f"https://api.themoviedb.org/3/{endpoint}/{tmdb_id}/videos?api_key={api_key}"
    data = _get_json(url)

    trailers = [
        video
        for video in data.get("results", [])
        if video.get("site") == "YouTube" and video.get("type") == "Trailer" and video.get("key")
    ]
    if not trailers:
        return None
    trailers.sort(key=lambda video: not video.get("official", False))
    return trailers[0]["key"]


def _watch_region() -> str:
    return os.environ.get("BUTACA_WATCH_REGION", "AR").strip().upper() or "AR"


def fetch_watch_providers(tmdb_id: int, kind: str = "movie") -> dict:
    """Streaming/rent/buy availability for one title in the configured region
    (default AR), from TMDb's /watch/providers (data sourced from JustWatch —
    attribution is required and rendered in the frontend). Cached a day, same
    OrderedDict TTL+LRU idiom as the other caches in this module."""
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        raise TmdbError("TMDB_API_KEY no configurada.")

    region = _watch_region()
    cache_key = (kind, tmdb_id, region)
    cached = _WATCH_PROVIDERS_CACHE.get(cache_key)
    if cached is not None:
        expires_at, result = cached
        if expires_at > _now_monotonic():
            _WATCH_PROVIDERS_CACHE.move_to_end(cache_key)
            return result
        # .pop(..., None) not del: the detail modal can open concurrently, so
        # another request may have already evicted this expired key.
        _WATCH_PROVIDERS_CACHE.pop(cache_key, None)

    endpoint = _tmdb_endpoint_kind(kind)
    url = f"https://api.themoviedb.org/3/{endpoint}/{tmdb_id}/watch/providers?api_key={api_key}"
    data = _get_json(url)
    region_data = (data.get("results") or {}).get(region) or {}

    def _providers(offer_type: str) -> list[dict]:
        return [
            {"name": p["provider_name"], "logo_path": _image_url(p.get("logo_path"), "w92")}
            for p in sorted(
                region_data.get(offer_type, []), key=lambda p: p.get("display_priority", 999)
            )
            if p.get("provider_name")
        ]

    result = {
        "link": region_data.get("link"),
        "flatrate": _providers("flatrate"),
        "rent": _providers("rent"),
        "buy": _providers("buy"),
    }
    _WATCH_PROVIDERS_CACHE[cache_key] = (
        _now_monotonic() + TITLE_CACHE_TTL_SECONDS,
        result,
    )
    _WATCH_PROVIDERS_CACHE.move_to_end(cache_key)
    while len(_WATCH_PROVIDERS_CACHE) > TITLE_CACHE_MAX_ENTRIES:
        _WATCH_PROVIDERS_CACHE.popitem(last=False)
    return result


def _search_one(
    url: str,
    kind: str,
    genre_name_map: dict[int, str],
    genre_tag_map: dict[int, list[str]],
    title: str,
    api_key: str,
    year: int | None = None,
) -> dict | None:
    params = {"api_key": api_key, "query": title, "language": "en-US", "include_adult": "false"}
    # sin año, results[0] es "el más popular que matchea el texto" — para
    # títulos de franquicia eso puede ser otra película (ej. "Toy Story"
    # devolvía Toy Story 5 por hype de estreno en vez de la de 1995)
    if year is not None:
        params["primary_release_year" if kind == "movie" else "first_air_date_year"] = str(year)
    data = _get_json(f"{url}?{urllib.parse.urlencode(params)}")
    results = data.get("results", [])
    if not results:
        return None

    raw = results[0]
    title_field = "title" if kind == "movie" else "name"
    date_field = "release_date" if kind == "movie" else "first_air_date"
    date_value = raw.get(date_field) or ""
    if len(date_value) < 4:
        return None
    try:
        year = int(date_value[:4])
    except ValueError:
        return None

    genre_ids = raw.get("genre_ids", [])
    genres = sorted({genre_name_map[gid] for gid in genre_ids if gid in genre_name_map})
    tags = sorted({tag for gid in genre_ids for tag in genre_tag_map.get(gid, [])})
    # poster/overview/vote were added so a title matched from a Letterboxd
    # watchlist can be shown as a real pick (recommender.py reads these);
    # existing callers just ignore the extra keys.
    return {
        "tmdb_id": raw.get("id"),
        "title": (raw.get(title_field) or "").strip(),
        "year": year,
        "kind": kind,
        "genres": genres,
        "tags": tags,
        "poster_path": _image_url(raw.get("poster_path"), "w500"),
        "backdrop_path": _image_url(raw.get("backdrop_path"), "w780"),
        "overview": raw.get("overview") or "",
        "vote_average": raw.get("vote_average"),
    }


def search_title(title: str, year: int | None = None) -> dict | None:
    """Best-effort match of a free-text (e.g. Letterboxd) title against TMDb:
    tries movie search first, then TV. Cached for a day since a title's
    genres/year don't change. Pass `year` when known to pin the exact film
    (franchise names resolve to the currently-hyped entry otherwise)."""
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        raise TmdbError("TMDB_API_KEY no configurada.")

    if not title.strip():
        return None
    cache_key = f"{title.strip().lower()}|{year}" if year is not None else title.strip().lower()

    cached = _SEARCH_CACHE.get(cache_key)
    if cached is not None:
        expires_at, result = cached
        if expires_at > _now_monotonic():
            _SEARCH_CACHE.move_to_end(cache_key)
            return result.copy() if result else None
        # .pop(..., None) not del: this runs concurrently across threads
        # (build_taste_profile matches titles in parallel), so another
        # thread may have already evicted this same expired key.
        _SEARCH_CACHE.pop(cache_key, None)

    result = _search_one(SEARCH_URL, "movie", GENRE_ID_NAME_MAP, GENRE_ID_TAG_MAP, title, api_key, year)
    if result is None:
        result = _search_one(SEARCH_TV_URL, "series", TV_GENRE_ID_NAME_MAP, TV_GENRE_ID_TAG_MAP, title, api_key, year)

    _SEARCH_CACHE[cache_key] = (_now_monotonic() + TITLE_CACHE_TTL_SECONDS, result)
    _SEARCH_CACHE.move_to_end(cache_key)
    while len(_SEARCH_CACHE) > TITLE_CACHE_MAX_ENTRIES:
        _SEARCH_CACHE.popitem(last=False)

    return result.copy() if result else None


def search_titles(query: str, limit: int = 8) -> list[dict]:
    """Several movie matches for a free-text query, for the onboarding search
    box (rate a film you've seen that isn't in the curated seed list). Minimal
    shape — title/year/tmdb_id/poster — since the manual recommend flow
    re-resolves genres/tags per title later anyway. Movies only; the seed list
    is movies too."""
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        raise TmdbError("TMDB_API_KEY no configurada.")

    query = query.strip()
    if not query:
        return []

    params = {"api_key": api_key, "query": query, "language": "en-US", "include_adult": "false"}
    data = _get_json(f"{SEARCH_URL}?{urllib.parse.urlencode(params)}")

    out: list[dict] = []
    for raw in data.get("results", []):
        title = (raw.get("title") or "").strip()
        date_value = raw.get("release_date") or ""
        if not title or len(date_value) < 4:
            continue
        try:
            year = int(date_value[:4])
        except ValueError:
            continue
        out.append(
            {
                "tmdb_id": raw.get("id"),
                "title": title,
                "year": year,
                "kind": "movie",
                "poster_path": _image_url(raw.get("poster_path"), "w500"),
            }
        )
        if len(out) >= limit:
            break
    return out


MULTI_SEARCH_URL = "https://api.themoviedb.org/3/search/multi"


def search_any_titles(query: str, limit: int = 8) -> list[dict]:
    """Películas Y series para el buscador de la navbar (pedido de Matías,
    2026-07-31: "que el usuario pueda buscar CUALQUIER película o serie").

    search_titles() de arriba es movies-only a propósito — la lista semilla del
    onboarding también lo es. Acá hace falta el otro alcance, así que va contra
    /search/multi y se filtran las personas, que ese endpoint también devuelve."""
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        raise TmdbError("TMDB_API_KEY no configurada.")

    query = query.strip()
    if not query:
        return []

    params = {"api_key": api_key, "query": query, "language": "en-US", "include_adult": "false"}
    data = _get_json(f"{MULTI_SEARCH_URL}?{urllib.parse.urlencode(params)}")

    out: list[dict] = []
    for raw in data.get("results", []):
        media_type = raw.get("media_type")
        if media_type not in ("movie", "tv"):
            continue  # /search/multi mezcla personas
        kind = "movie" if media_type == "movie" else "series"
        title = (raw.get("title") if media_type == "movie" else raw.get("name")) or ""
        title = title.strip()
        date_value = (
            raw.get("release_date") if media_type == "movie" else raw.get("first_air_date")
        ) or ""
        if not title or len(date_value) < 4:
            continue
        try:
            year = int(date_value[:4])
        except ValueError:
            continue
        out.append(
            {
                "tmdb_id": raw.get("id"),
                "title": title,
                "year": year,
                "kind": kind,
                "poster_path": _image_url(raw.get("poster_path"), "w500"),
            }
        )
        if len(out) >= limit:
            break
    return out


POPULAR_URL = {"movie": "https://api.themoviedb.org/3/movie/popular", "series": "https://api.themoviedb.org/3/tv/popular"}


def fetch_popular_titles(kind: str, page: int) -> list[dict]:
    """Los más populares de TMDb ahora mismo (no vote_average como el resto
    del módulo) -- para "puntuar más" (pedido de Matías, 2026-08-03): la
    idea es justamente que el usuario reconozca algo popular que vio y
    quizás se olvidó de anotar, no descubrir algo de nicho. TMDb "popular"
    incluye estrenos futuros con mucho hype (bug real reportado 2026-08-03:
    salió "Avengers: Doomsday", 2026, sin haberse estrenado todavía) -- se
    descartan los que su fecha de estreno/emisión sea posterior a hoy, algo
    imposible de haber visto."""
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        raise TmdbError("TMDB_API_KEY no configurada.")
    genre_tag_map = GENRE_ID_TAG_MAP if kind == "movie" else TV_GENRE_ID_TAG_MAP
    date_field = "release_date" if kind == "movie" else "first_air_date"
    today = datetime.date.today().isoformat()
    params = {"api_key": api_key, "language": "en-US", "page": page}
    data = _get_json(f"{POPULAR_URL[kind]}?{urllib.parse.urlencode(params)}")
    return [
        result
        for raw in data.get("results", [])
        if (raw.get(date_field) or "") <= today
        and (result := _map_result(raw, kind, genre_tag_map)) is not None
    ]


def fetch_title_by_id(tmdb_id: int, kind: str = "movie") -> dict | None:
    """Resuelve un título directo por su TMDb id, sin buscar por texto — para
    cuando ya lo tenemos (el `tmdb:movieId` que trae el feed RSS de username
    de Letterboxd, ver RatedItem.tmdb_id). Mismo shape de retorno que
    search_title/_search_one (tmdb_id/title/year/kind/genres/tags/...),
    mismo cache de 24h — evita una búsqueda por texto que puede matchear mal
    (ej. un remake con el mismo nombre) y ahorra el request de búsqueda
    entero."""
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        raise TmdbError("TMDB_API_KEY no configurada.")

    cache_key = (kind, tmdb_id)
    cached = _TITLE_BY_ID_CACHE.get(cache_key)
    if cached is not None:
        expires_at, result = cached
        if expires_at > _now_monotonic():
            _TITLE_BY_ID_CACHE.move_to_end(cache_key)
            return result.copy() if result else None
        _TITLE_BY_ID_CACHE.pop(cache_key, None)

    genre_name_map = GENRE_ID_NAME_MAP if kind == "movie" else TV_GENRE_ID_NAME_MAP
    genre_tag_map = GENRE_ID_TAG_MAP if kind == "movie" else TV_GENRE_ID_TAG_MAP
    endpoint = _tmdb_endpoint_kind(kind)
    result: dict | None
    try:
        raw = _get_json(f"https://api.themoviedb.org/3/{endpoint}/{tmdb_id}?api_key={api_key}&language=en-US")
    except TmdbError:
        result = None
    else:
        title_field = "title" if kind == "movie" else "name"
        date_field = "release_date" if kind == "movie" else "first_air_date"
        date_value = raw.get(date_field) or ""
        try:
            year = int(date_value[:4])
        except ValueError:
            year = None
        if not raw.get(title_field) or year is None:
            result = None
        else:
            # /movie/{id} y /tv/{id} devuelven "genres" como objetos
            # {id, name}, no "genre_ids" (lista de ints) como el resto de
            # los endpoints usados en este módulo
            genre_ids = [g["id"] for g in raw.get("genres", [])]
            genres = sorted({genre_name_map[gid] for gid in genre_ids if gid in genre_name_map})
            tags = sorted({tag for gid in genre_ids for tag in genre_tag_map.get(gid, [])})
            result = {
                "tmdb_id": raw.get("id"),
                "title": raw[title_field].strip(),
                "year": year,
                "kind": kind,
                "genres": genres,
                "tags": tags,
                "poster_path": _image_url(raw.get("poster_path"), "w500"),
                "backdrop_path": _image_url(raw.get("backdrop_path"), "w780"),
                "overview": raw.get("overview") or "",
                "vote_average": raw.get("vote_average"),
            }

    _TITLE_BY_ID_CACHE[cache_key] = (_now_monotonic() + TITLE_CACHE_TTL_SECONDS, result)
    _TITLE_BY_ID_CACHE.move_to_end(cache_key)
    while len(_TITLE_BY_ID_CACHE) > TITLE_CACHE_MAX_ENTRIES:
        _TITLE_BY_ID_CACHE.popitem(last=False)
    return result.copy() if result else None


# Pool, no cuántos se muestran: el flujo de votación descarta los que el
# usuario no vio, así que hacen falta bastantes más que los 6 votos que pide
# para tener margen (pedido de Matías, 2026-07-31).
SIMILAR_TITLES_LIMIT = 20


def fetch_similar_titles(tmdb_id: int, kind: str = "movie") -> list[dict]:
    """Botón "no estoy de acuerdo con el match": si un título llega sin
    evidencia real en el perfil (ej. ama a Spider-Man pero nunca puntuó nada
    de esa saga), le ofrece títulos parecidos para votar y llenar ese hueco.

    Pega contra /recommendations y NO contra /similar: /similar matchea por
    keywords y géneros y devuelve cualquier cosa — para "The Gentlemen" traía
    "Stuart Little" y "Around the World in 80 Days" (reportado por Matías con
    captura, 2026-07-31), y votar eso no dice nada sobre su gusto.
    /recommendations sale del comportamiento real de los usuarios de TMDb y
    es bastante mejor. Cae a /similar solo si /recommendations viene vacío,
    que pasa con títulos muy nuevos o de nicho.

    Mismo shape que fetch_candidates (vía _map_result), mismo criterio: sin
    tags mapeables, se descarta."""
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        raise TmdbError("TMDB_API_KEY no configurada.")

    genre_tag_map = GENRE_ID_TAG_MAP if kind == "movie" else TV_GENRE_ID_TAG_MAP
    endpoint = _tmdb_endpoint_kind(kind)

    def _fetch(path: str) -> list[dict]:
        data = _get_json(
            f"https://api.themoviedb.org/3/{endpoint}/{tmdb_id}/{path}"
            f"?api_key={api_key}&language=en-US"
        )
        return [
            result
            for raw in data.get("results", [])
            if (result := _map_result(raw, kind, genre_tag_map)) is not None
        ]

    mapped = _fetch("recommendations")
    if not mapped:
        mapped = _fetch("similar")
    return mapped[:SIMILAR_TITLES_LIMIT]


def fetch_taste_credits(tmdb_id: int, kind: str = "movie") -> dict:
    """Director + top-3 billed cast for one title, for the taste profile
    aggregation. Kept separate from fetch_credits (used by the detail modal)
    so that function's tested shape doesn't have to change."""
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        raise TmdbError("TMDB_API_KEY no configurada.")

    cache_key = (kind, tmdb_id)
    cached = _TASTE_CREDITS_CACHE.get(cache_key)
    if cached is not None:
        expires_at, result = cached
        if expires_at > _now_monotonic():
            _TASTE_CREDITS_CACHE.move_to_end(cache_key)
            return result
        # .pop(..., None) not del: build_taste_profile fetches credits
        # concurrently now, another thread may have evicted this key already.
        _TASTE_CREDITS_CACHE.pop(cache_key, None)

    endpoint = _tmdb_endpoint_kind(kind)
    url = f"https://api.themoviedb.org/3/{endpoint}/{tmdb_id}/credits?api_key={api_key}"
    data = _get_json(url)

    director = next(
        (
            member["name"]
            for member in data.get("crew", [])
            if member.get("job") == "Director" and member.get("name")
        ),
        None,
    )
    cast = sorted(data.get("cast", []), key=lambda member: member.get("order", 999))
    actors = [member["name"] for member in cast if member.get("name")][:3]

    result = {"director": director, "actors": actors}
    _TASTE_CREDITS_CACHE[cache_key] = (_now_monotonic() + TITLE_CACHE_TTL_SECONDS, result)
    _TASTE_CREDITS_CACHE.move_to_end(cache_key)
    while len(_TASTE_CREDITS_CACHE) > TITLE_CACHE_MAX_ENTRIES:
        _TASTE_CREDITS_CACHE.popitem(last=False)
    return result


def fetch_keywords(tmdb_id: int, kind: str = "movie") -> list[str]:
    """Los keywords freeform de TMDb para un título ("heist", "time loop"), que
    KEYWORD_TAG_MAP traduce a nuestro vocabulario interno.

    Devuelve los nombres CRUDOS, no los tags ya mapeados: así el cache guarda
    data de TMDb y editar KEYWORD_TAG_MAP toma efecto sin invalidarlo. Cacheado
    un día, mismo idioma OrderedDict TTL+LRU que el resto de este módulo."""
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        raise TmdbError("TMDB_API_KEY no configurada.")

    cache_key = (kind, tmdb_id)
    cached = _KEYWORDS_CACHE.get(cache_key)
    if cached is not None:
        expires_at, names = cached
        if expires_at > _now_monotonic():
            _KEYWORDS_CACHE.move_to_end(cache_key)
            # copia, no el objeto cacheado: el bug que esta feature tiene que
            # evitar es justamente aliasing de listas entre requests
            return list(names)
        # .pop(..., None) en vez de del: misma race de eviction concurrente que
        # el resto de los caches de este módulo.
        _KEYWORDS_CACHE.pop(cache_key, None)

    endpoint = _tmdb_endpoint_kind(kind)
    url = f"https://api.themoviedb.org/3/{endpoint}/{tmdb_id}/keywords?api_key={api_key}"
    data = _get_json(url)

    # /movie/{id}/keywords devuelve el array bajo "keywords", /tv/{id}/keywords
    # bajo "results" — mismo path, distinto nombre de campo. Se leen los dos en
    # vez de ramificar por kind.
    raw = data.get("keywords") or data.get("results") or []
    names = [name.strip() for entry in raw if (name := entry.get("name"))]

    _KEYWORDS_CACHE[cache_key] = (_now_monotonic() + TITLE_CACHE_TTL_SECONDS, names)
    _KEYWORDS_CACHE.move_to_end(cache_key)
    while len(_KEYWORDS_CACHE) > TITLE_CACHE_MAX_ENTRIES:
        _KEYWORDS_CACHE.popitem(last=False)
    return list(names)


def _tags_from_keywords(keywords: list[str]) -> set[str]:
    tags: set[str] = set()
    for keyword in keywords:
        tags.update(KEYWORD_TAG_MAP.get(keyword.strip().lower(), ()))
    return tags


def _enrich_with_keyword_tags(item: dict, kind: str) -> None:
    """Suma a los tags de un candidato los que salen de sus keywords de TMDb.

    Asigna una lista NUEVA en vez de mutar item["tags"]: los dicts que reparte
    _get_cached_personalized vienen de _clone_items, que es una copia shallow —
    item["tags"] sigue siendo el mismo objeto lista que vive adentro de
    _PERSONALIZED_CACHE, así que un .append()/.extend() acá acumularía tags en
    cada request servido desde esa entrada mientras viva (5 min)."""
    try:
        keywords = fetch_keywords(item["tmdb_id"], kind=kind)
    except TmdbError as exc:
        # a diferencia de credits, esto se loguea: sin el log un fallo sistémico
        # del endpoint (o una key sin permisos) es indistinguible de "el título
        # no tiene keywords mapeados", y la feature muere en silencio.
        logger.warning("Keywords de %s (%s) fallaron: %s", item.get("tmdb_id"), kind, exc)
        return
    # Tope de 2 tags por título, y no es cosmético: el scoring de recommend()
    # divide el término de match positivo por len(tags), así que un tag que el
    # perfil del usuario no matchea DILUYE el score del candidato (y solo los
    # primeros CREDITS_ENRICH_CAP se enriquecen, así que sería asimétrico
    # contra el resto del pool). 2 lo acota a algo comparable al spread de tags
    # de género que ya existe, y coincide con los 2 que muestra la card.
    extra = set(sorted(_tags_from_keywords(keywords))[:2])
    if extra:
        item["tags"] = sorted(set(item["tags"]) | extra)
    # log del hit rate: KEYWORD_TAG_MAP es una allowlist chica contra el
    # vocabulario enorme de TMDb, así que "0 tags nuevos" es el caso normal y no
    # se distingue de un bug sin ver los keywords crudos que llegaron.
    logger.info(
        "Keywords %s (%s): %d crudos -> %s",
        item.get("title"),
        kind,
        len(keywords),
        sorted(extra) or "sin match",
    )


def enrich_with_keyword_tags(item: dict, kind: str = "movie") -> None:
    """Igual que el enriquecimiento que reciben los candidatos de /recommend y
    /weekly, expuesto para un título suelto (el del buscador). Sin esto ese
    título se puntúa con menos señal que el resto y su match_score no es
    comparable con el de las otras pantallas."""
    _enrich_with_keyword_tags(item, kind)


def _resolve_person_id(name: str, expected_department: str | None = None) -> int | None:
    """Resolves a free-text name (a top director/actor from the taste
    profile) to a TMDb person_id, for use in a with_people discover filter.
    TMDb already returns /search/person results sorted by popularity
    descending, so results[0] is a reasonable default; filtering by
    known_for_department first (confirmed via docs/(C) research-tmdb-
    discover-personalization.md) cheaply avoids the rare case where an
    unrelated, more-popular homonym outranks the actual match. Cached 24h
    like search_title, since a person's id never changes."""
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        raise TmdbError("TMDB_API_KEY no configurada.")

    cache_key = f"{name.strip().lower()}::{expected_department or ''}"
    cached = _PERSON_CACHE.get(cache_key)
    if cached is not None:
        expires_at, result = cached
        if expires_at > _now_monotonic():
            _PERSON_CACHE.move_to_end(cache_key)
            return result
        # .pop(..., None) not del: same concurrent-eviction race as the
        # other caches in this module now that callers run in a thread pool.
        _PERSON_CACHE.pop(cache_key, None)

    params = {"api_key": api_key, "query": name, "language": "en-US", "include_adult": "false"}
    data = _get_json(f"https://api.themoviedb.org/3/search/person?{urllib.parse.urlencode(params)}")
    results = data.get("results", [])
    if expected_department:
        results = [r for r in results if r.get("known_for_department") == expected_department] or results
    person_id = results[0]["id"] if results else None

    _PERSON_CACHE[cache_key] = (_now_monotonic() + TITLE_CACHE_TTL_SECONDS, person_id)
    _PERSON_CACHE.move_to_end(cache_key)
    while len(_PERSON_CACHE) > TITLE_CACHE_MAX_ENTRIES:
        _PERSON_CACHE.popitem(last=False)
    return person_id


def _get_cached_personalized(cache_key: tuple) -> list[dict] | None:
    cached = _PERSONALIZED_CACHE.get(cache_key)
    if cached is None:
        return None
    expires_at, items = cached
    if expires_at <= _now_monotonic():
        # .pop(..., None) not del: same concurrent-eviction race as the
        # other caches in this module now that callers run in a thread pool.
        _PERSONALIZED_CACHE.pop(cache_key, None)
        return None
    _PERSONALIZED_CACHE.move_to_end(cache_key)
    return _clone_items(items)


def _store_cached_personalized(cache_key: tuple, items: list[dict]) -> None:
    _PERSONALIZED_CACHE[cache_key] = (_now_monotonic() + CACHE_TTL_SECONDS, _clone_items(items))
    _PERSONALIZED_CACHE.move_to_end(cache_key)
    while len(_PERSONALIZED_CACHE) > CACHE_MAX_ENTRIES:
        _PERSONALIZED_CACHE.popitem(last=False)


def _fetch_personalized_discover(
    url: str,
    kind: str,
    genre_tag_map: dict[int, list[str]],
    genre_ids: list[int],
    person_ids: list[int],
    decade: int | None,
    api_key: str,
    start_page: int = 1,
    pages: int = PERSONALIZED_PAGES,
) -> list[dict]:
    # confirmed empirically (docs/(C) research-tmdb-discover-personalization.md):
    # pipe within a param is OR (any of these genres/people), different
    # with_*/date params combine with AND — so genre OR + people OR + a soft
    # decade window all narrow together in a single request, no need to
    # split into one request per filter.
    cache_key = (
        kind, tuple(sorted(genre_ids)), tuple(sorted(person_ids)), decade, start_page, pages,
    )
    cached = _get_cached_personalized(cache_key)
    if cached is not None:
        return cached

    params = {
        "api_key": api_key,
        "language": "en-US",
        "sort_by": "vote_average.desc",
        "vote_count.gte": MIN_VOTE_COUNT,
        "include_adult": "false",
    }
    if genre_ids:
        params["with_genres"] = "|".join(str(gid) for gid in genre_ids)
    if person_ids:
        params["with_people"] = "|".join(str(pid) for pid in person_ids)
    if decade is not None:
        date_field = "primary_release_date" if kind == "movie" else "first_air_date"
        # soft bias, not a hard filter: the favorite decade plus one on
        # either side, so this doesn't narrow the pool down to almost nothing
        params[f"{date_field}.gte"] = f"{decade - 10}-01-01"
        params[f"{date_field}.lte"] = f"{decade + 19}-12-31"

    mapped: list[dict] = []
    for page in range(start_page, start_page + pages):
        data = _get_json(f"{url}?{urllib.parse.urlencode({**params, 'page': page})}")
        mapped.extend(
            result
            for raw in data.get("results", [])
            if (result := _map_result(raw, kind, genre_tag_map)) is not None
        )
    for item in mapped:
        item["_source"] = "profile"

    _store_cached_personalized(cache_key, mapped)
    return mapped


def fetch_personalized_candidates(
    profile: dict, mood: str, kind_filter: str = "both", start_page: int = 1
) -> list[dict]:
    """Builds the candidate pool from the user's persisted taste profile
    (top genres, directors/actors, favorite decade) instead of TMDb's global
    top-rated list, so two users with different tastes see different pools.
    Movie candidates get enriched with director/cast (for recommender.py's
    scoring) since with_people only works on /discover/movie (confirmed in
    the research doc — /discover/tv silently ignores it). Movies AND series
    also get TMDb-keyword tags folded into "tags" (KEYWORD_TAG_MAP): that
    endpoint does work on /tv, so it's the only per-item signal series get.
    Always mixes in a small unpersonalized "exploration" slice (reusing
    fetch_candidates as-is) so the pool doesn't fully collapse into the user's
    existing taste bubble; recommender.py reserves a pick slot for it via the
    "_source" tag. That slice also gets keyword tags now (same cap as
    profile/series), otherwise it never had a shot at matching on equal
    footing in recommend()'s scoring."""
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        raise TmdbError("TMDB_API_KEY no configurada.")

    genre_names = [g["genre"] for g in profile.get("genre_breakdown", [])[:3]]
    decade_breakdown = profile.get("decade_breakdown", [])
    top_decade = max(decade_breakdown, key=lambda d: d["count"])["decade"] if decade_breakdown else None

    person_candidates = [(d["name"], "Directing") for d in profile.get("top_directors", [])[:3]]
    person_candidates += [(a["name"], "Acting") for a in profile.get("top_actors", [])[:3]]
    person_ids: list[int] = []
    for name, department in person_candidates:
        try:
            person_id = _resolve_person_id(name, department)
        except TmdbError:
            continue
        if person_id is not None:
            person_ids.append(person_id)

    has_profile_signal = bool(genre_names) or bool(person_ids) or top_decade is not None

    candidates: list[dict] = []

    if has_profile_signal and kind_filter in ("movie", "both"):
        movie_genre_ids = [GENRE_NAME_ID_MAP[name] for name in genre_names if name in GENRE_NAME_ID_MAP]
        # pasadas de precisión: angostas a propósito (la de acá abajo pide
        # género Y persona en la misma película), así que se quedan en una
        # página — medido, la query combinada tiene 2-3 páginas EN TOTAL, pedir
        # la 7 devuelve vacío.
        movie_pools = [
            _fetch_personalized_discover(
                DISCOVER_URL, "movie", GENRE_ID_TAG_MAP, movie_genre_ids, person_ids,
                top_decade, api_key, pages=1,
            )
        ]
        if movie_genre_ids and person_ids:
            # pasada solo-por-género, que es la que tiene margen de verdad:
            # medido contra TMDb, género+década da ~7.500 títulos en ~376
            # páginas, mientras que las dos pasadas angostas de arriba se
            # agotan en la primera. Sin esto, un perfil con directores/actores
            # conocidos NUNCA veía una consulta ancha — el pool entero salía de
            # queries con with_people, y de ahí "solo 4 películas en todo el
            # mundo" (Matías, 2026-08-07). Es la única que pagina en profundidad.
            movie_pools.append(
                _fetch_personalized_discover(
                    DISCOVER_URL, "movie", GENRE_ID_TAG_MAP, movie_genre_ids, [],
                    top_decade, api_key, start_page,
                )
            )
        if person_ids:
            # with_genres and with_people combine with AND (confirmed in
            # docs/(C) research-tmdb-discover-personalization.md and again
            # here empirically): the pool above requires the profile's top
            # genre AND a favorite person on the same movie, so a director's
            # films outside that genre never show up — verified live against
            # a Christopher Nolan profile, where The Dark Knight/Inception/
            # Memento (not tagged "Drama") were missing from that first call
            # and only appeared once with_genres was dropped here. Without
            # them in the pool, recommend()'s director/actor bonus (the only
            # way past the ~86% ceiling with 4/4 tags + decade) almost never
            # fires. This second, people-only pass finds movies that
            # genuinely are by/with the favorite person regardless of genre.
            movie_pools.append(
                _fetch_personalized_discover(
                    DISCOVER_URL, "movie", GENRE_ID_TAG_MAP, [], person_ids,
                    top_decade, api_key, pages=1,
                )
            )
        for movies in movie_pools:
            for item in movies[:CREDITS_ENRICH_CAP]:
                # credits y keywords son enriquecimientos independientes: que falle
                # uno no tiene que saltear el otro para el mismo item (esto era un
                # `continue` antes de que existieran los keywords).
                try:
                    credits = fetch_taste_credits(item["tmdb_id"], kind="movie")
                except TmdbError:
                    pass
                else:
                    item["director"] = credits["director"]
                    item["actors"] = credits["actors"]
                _enrich_with_keyword_tags(item, "movie")
            candidates.extend(movies)

    if has_profile_signal and kind_filter in ("series", "both"):
        # with_people isn't supported on /discover/tv (confirmed empirically
        # — the param is silently ignored), so series only get genre/decade bias
        tv_genre_ids = [TV_GENRE_NAME_ID_MAP[name] for name in genre_names if name in TV_GENRE_NAME_ID_MAP]
        series = _fetch_personalized_discover(
            DISCOVER_TV_URL, "series", TV_GENRE_ID_TAG_MAP, tv_genre_ids, [],
            top_decade, api_key, start_page,
        )
        # los keywords, a diferencia de with_people, SÍ funcionan en /tv — así
        # que este es el primer enriquecimiento por item que reciben las series
        for item in series[:CREDITS_ENRICH_CAP]:
            _enrich_with_keyword_tags(item, "series")
        candidates.extend(series)

    exploration = fetch_candidates(mood, pages=1)
    for item in exploration:
        item["_source"] = "exploration"
    # antes solo profile/series recibían keyword tags, así que la exploration
    # nunca competía en igualdad de condiciones en el scoring de recommend().
    # fetch_candidates devuelve "movies + series" (movies siempre primero), así
    # que cortar por CREDITS_ENRICH_CAP sobre la lista combinada dejaba a las
    # series de exploration sin enriquecer siempre que hubiera >= cap movies
    # (el caso normal) — se aplica el cap por separado, igual que profile/series.
    exploration_movies = [item for item in exploration if item["kind"] == "movie"]
    exploration_series = [item for item in exploration if item["kind"] == "series"]
    for item in exploration_movies[:CREDITS_ENRICH_CAP]:
        _enrich_with_keyword_tags(item, "movie")
    for item in exploration_series[:CREDITS_ENRICH_CAP]:
        _enrich_with_keyword_tags(item, "series")
    candidates.extend(exploration)

    seen: set[tuple[str, str]] = set()
    deduped: list[dict] = []
    for item in candidates:
        key = (item["kind"], item["title"].strip().lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    return deduped
