import pytest

from backend.app import tmdb_client


@pytest.fixture(autouse=True)
def clear_tmdb_cache() -> None:
    tmdb_client._DISCOVER_CACHE.clear()
    tmdb_client._SEARCH_CACHE.clear()
    tmdb_client._TASTE_CREDITS_CACHE.clear()


def test_fetch_candidates_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("TMDB_API_KEY", raising=False)

    with pytest.raises(tmdb_client.TmdbError):
        tmdb_client.fetch_candidates("funny")


def test_fetch_candidates_maps_genres_and_overview_to_tags(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    calls: list[str] = []

    def fake_get_json(url: str) -> dict:
        calls.append(url)
        return {
            "results": [
                {
                    "title": "Fake Thriller",
                    "release_date": "2020-05-01",
                    "genre_ids": [53],  # Thriller -> psychological, dark
                    "overview": "A slow and quiet character study.",
                    "poster_path": "/poster123.jpg",
                    "backdrop_path": "/backdrop456.jpg",
                    "vote_average": 8.1,
                },
                {
                    "title": "No Year",
                    "release_date": "",
                    "genre_ids": [28],
                    "overview": "",
                },
                {
                    "title": "No Tags At All",
                    "release_date": "2019-01-01",
                    "genre_ids": [99],  # Documentary -> no mapped tags
                    "overview": "",
                },
            ]
        }

    monkeypatch.setattr(tmdb_client, "_get_json", fake_get_json)

    candidates = tmdb_client.fetch_candidates("funny", pages=1)

    # movie-shaped fixture also gets sent through the TV discover call, but
    # it has no "name"/"first_air_date" so it maps to nothing there.
    assert len(candidates) == 1
    item = candidates[0]
    assert item["title"] == "Fake Thriller"
    assert item["year"] == 2020
    assert item["kind"] == "movie"
    assert {"psychological", "dark", "slow", "quiet", "melancholic", "intimate"} <= set(
        item["tags"]
    )
    assert item["poster_path"] == "https://image.tmdb.org/t/p/w500/poster123.jpg"
    assert item["backdrop_path"] == "https://image.tmdb.org/t/p/w780/backdrop456.jpg"
    assert item["vote_average"] == 8.1
    assert len(calls) == 2
    assert "discover/movie" in calls[0] and "with_genres=35" in calls[0]  # "funny" -> Comedy
    assert "discover/tv" in calls[1] and "with_genres=35" in calls[1]


def test_fetch_candidates_includes_series_from_tv_discover(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")

    def fake_get_json(url: str) -> dict:
        if "discover/tv" in url:
            return {
                "results": [
                    {
                        "name": "Fake Prestige Drama",
                        "first_air_date": "2021-03-01",
                        "genre_ids": [18],  # Drama -> character
                        "overview": "",
                        "poster_path": "/tvposter.jpg",
                        "vote_average": 8.5,
                    }
                ]
            }
        return {"results": []}

    monkeypatch.setattr(tmdb_client, "_get_json", fake_get_json)

    candidates = tmdb_client.fetch_candidates("funny", pages=1)

    assert len(candidates) == 1
    item = candidates[0]
    assert item["title"] == "Fake Prestige Drama"
    assert item["year"] == 2021
    assert item["kind"] == "series"
    assert item["tags"] == ["character"]
    assert item["poster_path"] == "https://image.tmdb.org/t/p/w500/tvposter.jpg"


def test_fetch_candidates_reuses_cached_pages_until_ttl_expires(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    calls: list[str] = []

    def fake_get_json(url: str) -> dict:
        calls.append(url)
        if "discover/tv" in url:
            return {
                "results": [
                    {
                        "name": "Cached Show",
                        "first_air_date": "2021-03-01",
                        "genre_ids": [18],
                        "overview": "",
                    }
                ]
            }
        return {
            "results": [
                {
                    "title": "Cached Movie",
                    "release_date": "2020-05-01",
                    "genre_ids": [53],
                    "overview": "dark and slow",
                }
            ]
        }

    monkeypatch.setattr(tmdb_client, "_get_json", fake_get_json)
    monkeypatch.setattr(tmdb_client, "_now_monotonic", lambda: 100.0)

    first = tmdb_client.fetch_candidates("funny", pages=1)
    second = tmdb_client.fetch_candidates("funny", pages=1)

    assert first == second
    assert len(calls) == 2


def test_fetch_candidates_refreshes_after_ttl(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    calls: list[str] = []
    times = iter([100.0, 100.0, 401.0, 401.0, 401.0, 401.0])

    def fake_now() -> float:
        return next(times)

    def fake_get_json(url: str) -> dict:
        calls.append(url)
        if "discover/tv" in url:
            return {
                "results": [
                    {
                        "name": f"Show {len(calls)}",
                        "first_air_date": "2021-03-01",
                        "genre_ids": [18],
                        "overview": "",
                    }
                ]
            }
        return {
            "results": [
                {
                    "title": f"Movie {len(calls)}",
                    "release_date": "2020-05-01",
                    "genre_ids": [53],
                    "overview": "dark and slow",
                }
            ]
        }

    monkeypatch.setattr(tmdb_client, "_now_monotonic", fake_now)
    monkeypatch.setattr(tmdb_client, "_get_json", fake_get_json)
    monkeypatch.setattr(tmdb_client, "CACHE_TTL_SECONDS", 300)

    first = tmdb_client.fetch_candidates("funny", pages=1)
    second = tmdb_client.fetch_candidates("funny", pages=1)

    assert len(calls) == 4
    assert first != second


def test_map_result_reads_tv_fields_when_kind_is_series() -> None:
    mapped = tmdb_client._map_result(
        {
            "name": "Fake Show",
            "first_air_date": "2019-01-01",
            "genre_ids": [10765],  # Sci-Fi & Fantasy
            "overview": "",
        },
        kind="series",
        genre_tag_map=tmdb_client.TV_GENRE_ID_TAG_MAP,
    )

    assert mapped is not None
    assert mapped["kind"] == "series"
    assert mapped["year"] == 2019
    assert {"stylized", "mysterious"} <= set(mapped["tags"])


def test_map_result_handles_missing_images() -> None:
    mapped = tmdb_client._map_result(
        {
            "title": "No Poster",
            "release_date": "2018-01-01",
            "genre_ids": [53],
            "overview": "",
        }
    )

    assert mapped is not None
    assert mapped["poster_path"] is None
    assert mapped["backdrop_path"] is None


def test_map_result_captures_tmdb_id() -> None:
    mapped = tmdb_client._map_result(
        {
            "id": 12345,
            "title": "Has Id",
            "release_date": "2018-01-01",
            "genre_ids": [53],
            "overview": "",
        }
    )

    assert mapped is not None
    assert mapped["tmdb_id"] == 12345


def test_get_json_wraps_network_errors(monkeypatch) -> None:
    def raise_url_error(*args, **kwargs):
        raise tmdb_client.URLError("boom")

    monkeypatch.setattr(tmdb_client.urllib.request, "urlopen", raise_url_error)

    with pytest.raises(tmdb_client.TmdbError):
        tmdb_client._get_json("https://api.themoviedb.org/3/discover/movie")


def test_fetch_credits_sorts_by_order_and_limits(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")

    def fake_get_json(url: str) -> dict:
        assert "/movie/42/credits" in url
        return {
            "cast": [
                {"name": "Second", "character": "B", "order": 1, "profile_path": "/b.jpg"},
                {"name": "First", "character": "A", "order": 0, "profile_path": None},
                {"name": "", "character": "no name", "order": 2},
            ]
        }

    monkeypatch.setattr(tmdb_client, "_get_json", fake_get_json)

    cast = tmdb_client.fetch_credits(42, kind="movie", limit=2)

    assert [c["name"] for c in cast] == ["First", "Second"]
    assert cast[1]["profile_path"] == "https://image.tmdb.org/t/p/w185/b.jpg"


def test_fetch_trailer_key_prefers_official_youtube_trailer(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")

    def fake_get_json(url: str) -> dict:
        assert "/tv/7/videos" in url
        return {
            "results": [
                {"site": "YouTube", "type": "Trailer", "key": "unofficial", "official": False},
                {"site": "YouTube", "type": "Trailer", "key": "official", "official": True},
                {"site": "Vimeo", "type": "Trailer", "key": "ignored"},
            ]
        }

    monkeypatch.setattr(tmdb_client, "_get_json", fake_get_json)

    assert tmdb_client.fetch_trailer_key(7, kind="series") == "official"


def test_fetch_trailer_key_returns_none_when_no_trailer(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    monkeypatch.setattr(tmdb_client, "_get_json", lambda url: {"results": []})

    assert tmdb_client.fetch_trailer_key(1) is None


def test_search_title_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("TMDB_API_KEY", raising=False)

    with pytest.raises(tmdb_client.TmdbError):
        tmdb_client.search_title("Anything")


def test_search_title_matches_movie_first(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")

    def fake_get_json(url: str) -> dict:
        assert "search/movie" in url
        return {
            "results": [
                {
                    "id": 99,
                    "title": "Fake Drama",
                    "release_date": "2015-06-01",
                    "genre_ids": [18, 53],
                }
            ]
        }

    monkeypatch.setattr(tmdb_client, "_get_json", fake_get_json)

    match = tmdb_client.search_title("fake drama")

    assert match == {
        "tmdb_id": 99,
        "title": "Fake Drama",
        "year": 2015,
        "kind": "movie",
        "genres": ["Drama", "Thriller"],
        "tags": ["character", "dark", "psychological"],
    }


def test_search_title_falls_back_to_tv_when_no_movie_match(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")

    def fake_get_json(url: str) -> dict:
        if "search/movie" in url:
            return {"results": []}
        assert "search/tv" in url
        return {
            "results": [
                {"id": 7, "name": "Fake Show", "first_air_date": "2010-01-01", "genre_ids": [35]}
            ]
        }

    monkeypatch.setattr(tmdb_client, "_get_json", fake_get_json)

    match = tmdb_client.search_title("fake show")

    assert match is not None
    assert match["kind"] == "series"
    assert match["genres"] == ["Comedia"]


def test_search_title_caches_result(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    calls: list[str] = []

    def fake_get_json(url: str) -> dict:
        calls.append(url)
        return {"results": [{"id": 1, "title": "X", "release_date": "2000-01-01", "genre_ids": []}]}

    monkeypatch.setattr(tmdb_client, "_get_json", fake_get_json)

    tmdb_client.search_title("X")
    tmdb_client.search_title("x")  # case-insensitive cache hit

    assert len(calls) == 1


def test_fetch_taste_credits_extracts_director_and_top_cast(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")

    def fake_get_json(url: str) -> dict:
        assert "/movie/42/credits" in url
        return {
            "crew": [
                {"job": "Producer", "name": "Someone Else"},
                {"job": "Director", "name": "The Director"},
            ],
            "cast": [
                {"name": "Third", "order": 2},
                {"name": "First", "order": 0},
                {"name": "Second", "order": 1},
                {"name": "Fourth", "order": 3},
            ],
        }

    monkeypatch.setattr(tmdb_client, "_get_json", fake_get_json)

    credits = tmdb_client.fetch_taste_credits(42, kind="movie")

    assert credits == {"director": "The Director", "actors": ["First", "Second", "Third"]}

