from backend.app import taste_profile, tmdb_client


def test_build_taste_profile_aggregates_genres_decades_and_people(monkeypatch) -> None:
    matches = {
        "mad max": {
            "tmdb_id": 1,
            "title": "Mad Max: Fury Road",
            "year": 2015,
            "kind": "movie",
            "genres": ["Acción", "Ciencia ficción"],
        },
        "her": {
            "tmdb_id": 2,
            "title": "Her",
            "year": 2013,
            "kind": "movie",
            "genres": ["Drama", "Ciencia ficción"],
        },
        "no match": None,
    }
    credits = {
        1: {"director": "George Miller", "actors": ["Tom Hardy", "Charlize Theron"]},
        2: {"director": "Spike Jonze", "actors": ["Joaquin Phoenix"]},
    }

    monkeypatch.setattr(tmdb_client, "search_title", lambda title: matches[title.lower()])
    monkeypatch.setattr(
        tmdb_client, "fetch_taste_credits", lambda tmdb_id, kind: credits[tmdb_id]
    )

    watched = [
        {"title": "Mad Max", "rating": 5.0, "review": "", "created_at": "x"},
        {"title": "Her", "rating": 4.0, "review": "", "created_at": "x"},
        {"title": "No Match", "rating": 3.0, "review": "", "created_at": "x"},
    ]

    profile = taste_profile.build_taste_profile(watched)

    assert profile["total_count"] == 3
    assert profile["matched_count"] == 2
    assert profile["genre_breakdown"] == [
        {"genre": "Ciencia ficción", "weight": 9.0},
        {"genre": "Acción", "weight": 5.0},
        {"genre": "Drama", "weight": 4.0},
    ]
    assert profile["decade_breakdown"] == [
        {"decade": 2010, "count": 2},
    ]
    assert {"name": "George Miller", "count": 1} in profile["top_directors"]
    assert {"name": "Spike Jonze", "count": 1} in profile["top_directors"]
    assert {"name": "Tom Hardy", "count": 1} in profile["top_actors"]


def test_build_taste_profile_skips_titles_that_error_on_search(monkeypatch) -> None:
    def raise_error(title: str):
        raise tmdb_client.TmdbError("boom")

    monkeypatch.setattr(tmdb_client, "search_title", raise_error)

    profile = taste_profile.build_taste_profile(
        [{"title": "Anything", "rating": 5.0, "review": "", "created_at": "x"}]
    )

    assert profile["matched_count"] == 0
    assert profile["genre_breakdown"] == []


def test_match_title_uses_tmdb_id_when_present_no_search(monkeypatch) -> None:
    # el tmdb:movieId del RSS de username evita la búsqueda por texto —
    # ahorra el request y el riesgo de matchear un remake homónimo
    def fail_if_called(title):
        raise AssertionError("no debería buscar por texto si ya tiene tmdb_id")

    monkeypatch.setattr(tmdb_client, "search_title", fail_if_called)
    monkeypatch.setattr(
        tmdb_client,
        "fetch_title_by_id",
        lambda tmdb_id, kind: {"tmdb_id": 769, "genres": ["Drama"], "year": 1990}
        if tmdb_id == 769
        else None,
    )

    item, match = taste_profile._match_title({"title": "GoodFellas", "tmdb_id": 769})

    assert match == {"tmdb_id": 769, "genres": ["Drama"], "year": 1990}


def test_match_title_falls_back_to_search_when_id_lookup_misses(monkeypatch) -> None:
    monkeypatch.setattr(tmdb_client, "fetch_title_by_id", lambda tmdb_id, kind: None)
    monkeypatch.setattr(
        tmdb_client, "search_title", lambda title: {"tmdb_id": 1, "genres": ["Drama"], "year": 1990}
    )

    item, match = taste_profile._match_title({"title": "GoodFellas", "tmdb_id": 999999})

    assert match == {"tmdb_id": 1, "genres": ["Drama"], "year": 1990}


def test_build_taste_profile_handles_empty_history() -> None:
    profile = taste_profile.build_taste_profile([])

    assert profile == {
        "matched_count": 0,
        "total_count": 0,
        "genre_breakdown": [],
        "decade_breakdown": [],
        "top_directors": [],
        "top_actors": [],
    }


def test_build_taste_profile_caps_credits_lookups_below_match_cap(monkeypatch) -> None:
    monkeypatch.setattr(taste_profile, "MAX_TITLES_TO_MATCH", 10)
    monkeypatch.setattr(taste_profile, "MAX_TITLES_FOR_CREDITS", 2)

    def fake_search(title: str) -> dict:
        return {
            "tmdb_id": int(title.split()[-1]),
            "title": title,
            "year": 2000,
            "kind": "movie",
            "genres": [],
        }

    credit_calls: list[int] = []

    def fake_credits(tmdb_id: int, kind: str) -> dict:
        credit_calls.append(tmdb_id)
        return {"director": f"Director {tmdb_id}", "actors": []}

    monkeypatch.setattr(tmdb_client, "search_title", fake_search)
    monkeypatch.setattr(tmdb_client, "fetch_taste_credits", fake_credits)

    watched = [
        {"title": f"Movie {i}", "rating": float(i), "review": "", "created_at": "x"}
        for i in range(5)
    ]

    profile = taste_profile.build_taste_profile(watched)

    assert profile["matched_count"] == 5
    assert len(credit_calls) == 2
