import json
import os
import time
import urllib.parse
import urllib.request
from collections import OrderedDict
from pathlib import Path
from urllib.error import URLError

from .recommender import positive_tags_from_text

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
    16: ["stylized"],  # Animation
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
    16: ["stylized"],  # Animation
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

SEARCH_URL = "https://api.themoviedb.org/3/search/movie"
SEARCH_TV_URL = "https://api.themoviedb.org/3/search/tv"
# a title's matched genres/year/credits don't change, so these are cached
# much longer than discover pages
TITLE_CACHE_TTL_SECONDS = 24 * 60 * 60
TITLE_CACHE_MAX_ENTRIES = 500

_DISCOVER_CACHE: OrderedDict[tuple[str, str, int], tuple[float, list[dict]]] = OrderedDict()
_SEARCH_CACHE: OrderedDict[str, tuple[float, dict | None]] = OrderedDict()
_TASTE_CREDITS_CACHE: OrderedDict[tuple[str, int], tuple[float, dict]] = OrderedDict()


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
    raw: dict, kind: str = "movie", genre_tag_map: dict[int, list[str]] = GENRE_ID_TAG_MAP
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

    if not tags:
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
        del _DISCOVER_CACHE[cache_key]
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
            "vote_count.gte": 200,
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


def _search_one(
    url: str,
    kind: str,
    genre_name_map: dict[int, str],
    genre_tag_map: dict[int, list[str]],
    title: str,
    api_key: str,
) -> dict | None:
    params = {"api_key": api_key, "query": title, "language": "en-US", "include_adult": "false"}
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
    return {
        "tmdb_id": raw.get("id"),
        "title": (raw.get(title_field) or "").strip(),
        "year": year,
        "kind": kind,
        "genres": genres,
        "tags": tags,
    }


def search_title(title: str) -> dict | None:
    """Best-effort match of a free-text (e.g. Letterboxd) title against TMDb:
    tries movie search first, then TV. Cached for a day since a title's
    genres/year don't change."""
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        raise TmdbError("TMDB_API_KEY no configurada.")

    cache_key = title.strip().lower()
    if not cache_key:
        return None

    cached = _SEARCH_CACHE.get(cache_key)
    if cached is not None:
        expires_at, result = cached
        if expires_at > _now_monotonic():
            _SEARCH_CACHE.move_to_end(cache_key)
            return result.copy() if result else None
        del _SEARCH_CACHE[cache_key]

    result = _search_one(SEARCH_URL, "movie", GENRE_ID_NAME_MAP, GENRE_ID_TAG_MAP, title, api_key)
    if result is None:
        result = _search_one(SEARCH_TV_URL, "series", TV_GENRE_ID_NAME_MAP, TV_GENRE_ID_TAG_MAP, title, api_key)

    _SEARCH_CACHE[cache_key] = (_now_monotonic() + TITLE_CACHE_TTL_SECONDS, result)
    _SEARCH_CACHE.move_to_end(cache_key)
    while len(_SEARCH_CACHE) > TITLE_CACHE_MAX_ENTRIES:
        _SEARCH_CACHE.popitem(last=False)

    return result.copy() if result else None


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
        del _TASTE_CREDITS_CACHE[cache_key]

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
