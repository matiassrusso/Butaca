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

_DISCOVER_CACHE: OrderedDict[tuple[str, str, int], tuple[float, list[dict]]] = OrderedDict()


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
            "sort_by": "popularity.desc",
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
