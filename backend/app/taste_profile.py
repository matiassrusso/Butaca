"""Aggregates a user's watched-titles history into a visual taste profile
(genre weights, decade counts, favorite directors/actors) by matching each
title against TMDb.
"""

from concurrent.futures import ThreadPoolExecutor

from . import tmdb_client

# ponytail: matching + credits are one TMDb request each, and a real
# Letterboxd export can run into the hundreds of titles — cap both stages so
# a profile load stays fast. Raise these if a slower-but-fuller profile is
# worth the wait.
MAX_TITLES_TO_MATCH = 150
MAX_TITLES_FOR_CREDITS = 50
TOP_GENRES = 8
TOP_DECADES = 10
TOP_PEOPLE = 8

# these are blocking network calls, not CPU work, so a thread pool gets real
# concurrency despite the GIL — this is what turns ~150 sequential TMDb
# round trips (each ~200-400ms, tens of seconds total) into a few seconds.
# TMDb's rate limit is ~50 req/s, well above this worker count.
MATCH_WORKERS = 10


def _match_title(item: dict) -> tuple[dict, dict | None]:
    try:
        # el tmdb_id ya resuelto (RSS de username, ver RatedItem.tmdb_id)
        # evita una búsqueda por texto — más rápido y sin riesgo de
        # matchear un remake homónimo
        tmdb_id = item.get("tmdb_id")
        if tmdb_id is not None:
            match = tmdb_client.fetch_title_by_id(tmdb_id, "movie")
            if match:
                return item, match
        return item, tmdb_client.search_title(item["title"])
    except tmdb_client.TmdbError:
        return item, None


def _fetch_credits(pair: tuple[dict, dict]) -> tuple[dict, dict | None]:
    item, match = pair
    try:
        return item, tmdb_client.fetch_taste_credits(match["tmdb_id"], kind=match["kind"])
    except tmdb_client.TmdbError:
        return item, None


def build_taste_profile(watched_items: list[dict]) -> dict:
    total_count = len(watched_items)
    # highest-rated first: within the cap, prioritize the titles that most
    # define this user's taste, not just the most recently imported ones
    ranked = sorted(watched_items, key=lambda item: item["rating"], reverse=True)
    candidates = ranked[:MAX_TITLES_TO_MATCH]

    with ThreadPoolExecutor(max_workers=MATCH_WORKERS) as pool:
        matched = pool.map(_match_title, candidates)
    matches: list[tuple[dict, dict]] = [(item, match) for item, match in matched if match]

    genre_weight: dict[str, float] = {}
    decade_count: dict[int, int] = {}
    for item, match in matches:
        for genre in match["genres"]:
            genre_weight[genre] = genre_weight.get(genre, 0.0) + item["rating"]
        decade = (match["year"] // 10) * 10
        decade_count[decade] = decade_count.get(decade, 0) + 1

    director_count: dict[str, int] = {}
    actor_count: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=MATCH_WORKERS) as pool:
        credited = pool.map(_fetch_credits, matches[:MAX_TITLES_FOR_CREDITS])
    for _item, credits in credited:
        if credits is None:
            continue
        if credits["director"]:
            director_count[credits["director"]] = director_count.get(credits["director"], 0) + 1
        for actor in credits["actors"]:
            actor_count[actor] = actor_count.get(actor, 0) + 1

    return {
        "matched_count": len(matches),
        "total_count": total_count,
        "genre_breakdown": [
            {"genre": genre, "weight": weight}
            for genre, weight in sorted(
                genre_weight.items(), key=lambda kv: kv[1], reverse=True
            )[:TOP_GENRES]
        ],
        "decade_breakdown": [
            {"decade": decade, "count": count}
            for decade, count in sorted(decade_count.items())[-TOP_DECADES:]
        ],
        "top_directors": [
            {"name": name, "count": count}
            for name, count in sorted(
                director_count.items(), key=lambda kv: kv[1], reverse=True
            )[:TOP_PEOPLE]
        ],
        "top_actors": [
            {"name": name, "count": count}
            for name, count in sorted(
                actor_count.items(), key=lambda kv: kv[1], reverse=True
            )[:TOP_PEOPLE]
        ],
    }
