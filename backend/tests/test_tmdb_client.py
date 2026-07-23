import pytest

from backend.app import tmdb_client


@pytest.fixture(autouse=True)
def clear_tmdb_cache() -> None:
    tmdb_client._DISCOVER_CACHE.clear()
    tmdb_client._SEARCH_CACHE.clear()
    tmdb_client._TASTE_CREDITS_CACHE.clear()
    tmdb_client._PERSON_CACHE.clear()
    tmdb_client._PERSONALIZED_CACHE.clear()
    tmdb_client._WATCH_PROVIDERS_CACHE.clear()


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
        "poster_path": None,
        "backdrop_path": None,
        "overview": "",
        "vote_average": None,
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


def test_search_title_with_year_pins_the_release_year(monkeypatch) -> None:
    # regresión: "Toy Story" sin año resolvía al Toy Story 5 en cartelera
    # (results[0] ordena por popularidad) en vez de la película de 1995
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    urls: list[str] = []

    def fake_get_json(url: str) -> dict:
        urls.append(url)
        assert "primary_release_year=1995" in url
        return {
            "results": [
                {"id": 862, "title": "Toy Story", "release_date": "1995-11-22", "genre_ids": [16]}
            ]
        }

    monkeypatch.setattr(tmdb_client, "_get_json", fake_get_json)

    match = tmdb_client.search_title("Toy Story", 1995)

    assert match is not None
    assert match["tmdb_id"] == 862
    assert match["year"] == 1995
    # el año participa de la cache key: la misma búsqueda sin año no debe
    # pisar ni reusar la entrada con año
    tmdb_client.search_title("Toy Story", 1995)
    assert len(urls) == 1


def test_resolve_person_id_defaults_to_first_result_sorted_by_popularity(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")

    def fake_get_json(url: str) -> dict:
        assert "search/person" in url
        return {
            "results": [
                {"id": 1, "name": "James Smith", "known_for_department": "Acting", "popularity": 5.0},
                {"id": 2, "name": "James Smith", "known_for_department": "Directing", "popularity": 1.0},
            ]
        }

    monkeypatch.setattr(tmdb_client, "_get_json", fake_get_json)

    assert tmdb_client._resolve_person_id("James Smith") == 1


def test_resolve_person_id_filters_by_expected_department(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    monkeypatch.setattr(
        tmdb_client,
        "_get_json",
        lambda url: {
            "results": [
                {"id": 1, "name": "James Smith", "known_for_department": "Acting", "popularity": 5.0},
                {"id": 2, "name": "James Smith", "known_for_department": "Directing", "popularity": 1.0},
            ]
        },
    )

    assert tmdb_client._resolve_person_id("James Smith", expected_department="Directing") == 2


def test_resolve_person_id_caches_result(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    calls: list[str] = []

    def fake_get_json(url: str) -> dict:
        calls.append(url)
        return {"results": [{"id": 42, "known_for_department": "Directing", "popularity": 1.0}]}

    monkeypatch.setattr(tmdb_client, "_get_json", fake_get_json)

    tmdb_client._resolve_person_id("Some Director")
    tmdb_client._resolve_person_id("some director")  # case-insensitive cache hit

    assert len(calls) == 1


def test_fetch_personalized_candidates_biases_movie_discover_by_profile(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    calls: list[str] = []

    def fake_get_json(url: str) -> dict:
        calls.append(url)
        if "search/person" in url:
            return {"results": [{"id": 525, "known_for_department": "Directing", "popularity": 9.9}]}
        if "discover/movie" in url:
            return {
                "results": [
                    {
                        "id": 1,
                        "title": "Profile Movie",
                        "release_date": "2010-01-01",
                        "genre_ids": [18],
                        "overview": "",
                    }
                ]
            }
        return {"results": []}

    monkeypatch.setattr(tmdb_client, "_get_json", fake_get_json)
    monkeypatch.setattr(
        tmdb_client, "fetch_taste_credits", lambda tmdb_id, kind="movie": {"director": "A Director", "actors": []}
    )

    profile = {
        "genre_breakdown": [{"genre": "Drama", "weight": 10.0}],
        "decade_breakdown": [{"decade": 2010, "count": 3}],
        "top_directors": [{"name": "A Director", "count": 2}],
        "top_actors": [],
    }

    candidates = tmdb_client.fetch_personalized_candidates(profile, mood="", kind_filter="movie")

    movie_call = next(url for url in calls if "discover/movie" in url)
    assert "with_genres=18" in movie_call  # Drama -> 18
    assert "with_people=525" in movie_call
    assert "primary_release_date.gte=2000-01-01" in movie_call
    assert "primary_release_date.lte=2029-12-31" in movie_call

    profile_movie = next(c for c in candidates if c["title"] == "Profile Movie")
    assert profile_movie["_source"] == "profile"
    assert profile_movie["director"] == "A Director"


def test_fetch_personalized_candidates_skips_with_people_for_series(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    calls: list[str] = []

    def fake_get_json(url: str) -> dict:
        calls.append(url)
        if "search/person" in url:
            return {"results": [{"id": 525, "known_for_department": "Acting", "popularity": 9.9}]}
        return {"results": []}

    monkeypatch.setattr(tmdb_client, "_get_json", fake_get_json)

    profile = {
        "genre_breakdown": [{"genre": "Drama", "weight": 10.0}],
        "decade_breakdown": [],
        "top_directors": [],
        "top_actors": [{"name": "Some Actor", "count": 2}],
    }

    tmdb_client.fetch_personalized_candidates(profile, mood="", kind_filter="series")

    tv_call = next(url for url in calls if "discover/tv" in url)
    assert "with_people" not in tv_call


def test_fetch_personalized_candidates_falls_back_to_exploration_only_when_profile_has_no_signal(
    monkeypatch,
) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")

    def fake_get_json(url: str) -> dict:
        if "discover/movie" in url:
            return {
                "results": [
                    {
                        "id": 1,
                        "title": "Explore Movie",
                        "release_date": "2020-01-01",
                        "genre_ids": [28],
                        "overview": "",
                    }
                ]
            }
        return {"results": []}

    monkeypatch.setattr(tmdb_client, "_get_json", fake_get_json)

    profile = {"genre_breakdown": [], "decade_breakdown": [], "top_directors": [], "top_actors": []}
    candidates = tmdb_client.fetch_personalized_candidates(profile, mood="", kind_filter="both")

    assert candidates
    assert all(c["_source"] == "exploration" for c in candidates)


def test_fetch_personalized_candidates_dedupes_profile_and_exploration_overlap(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")

    def fake_get_json(url: str) -> dict:
        if "search/person" in url:
            return {"results": []}
        if "discover/movie" in url:
            return {
                "results": [
                    {
                        "id": 1,
                        "title": "Same Movie",
                        "release_date": "2015-01-01",
                        "genre_ids": [18],
                        "overview": "",
                    }
                ]
            }
        return {"results": []}

    monkeypatch.setattr(tmdb_client, "_get_json", fake_get_json)
    monkeypatch.setattr(
        tmdb_client, "fetch_taste_credits", lambda tmdb_id, kind="movie": {"director": None, "actors": []}
    )

    profile = {
        "genre_breakdown": [{"genre": "Drama", "weight": 5.0}],
        "decade_breakdown": [],
        "top_directors": [],
        "top_actors": [],
    }
    candidates = tmdb_client.fetch_personalized_candidates(profile, mood="", kind_filter="movie")

    titles = [c["title"] for c in candidates]
    assert titles.count("Same Movie") == 1
    assert candidates[0]["_source"] == "profile"  # profile copy wins over the exploration duplicate


def test_fetch_personalized_candidates_caches_profile_discover_page(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    calls: list[str] = []

    def fake_get_json(url: str) -> dict:
        calls.append(url)
        return {"results": []}

    monkeypatch.setattr(tmdb_client, "_get_json", fake_get_json)
    monkeypatch.setattr(tmdb_client, "_now_monotonic", lambda: 100.0)

    profile = {
        "genre_breakdown": [{"genre": "Drama", "weight": 5.0}],
        "decade_breakdown": [],
        "top_directors": [],
        "top_actors": [],
    }

    tmdb_client.fetch_personalized_candidates(profile, mood="", kind_filter="movie")
    calls_after_first = len(calls)
    tmdb_client.fetch_personalized_candidates(profile, mood="", kind_filter="movie")

    # both the profile-biased discover call (this module's own cache) and the
    # exploration slice (fetch_candidates -> its own _DISCOVER_CACHE) hit
    # cache on the second call with the same profile/mood/kind_filter
    assert len(calls) == calls_after_first


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



def test_fetch_watch_providers_maps_region_offers(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    monkeypatch.setenv("BUTACA_WATCH_REGION", "AR")

    def fake_get_json(url: str) -> dict:
        assert "/movie/42/watch/providers" in url
        return {
            "results": {
                "AR": {
                    "link": "https://www.themoviedb.org/movie/42/watch",
                    "flatrate": [
                        {"provider_name": "Netflix", "logo_path": "/nf.jpg", "display_priority": 1},
                        {"provider_name": "Max", "logo_path": "/max.jpg", "display_priority": 0},
                    ],
                    "rent": [{"provider_name": "Apple TV", "logo_path": "/apple.jpg"}],
                },
                "US": {"flatrate": [{"provider_name": "Hulu", "logo_path": "/hulu.jpg"}]},
            }
        }

    monkeypatch.setattr(tmdb_client, "_get_json", fake_get_json)

    providers = tmdb_client.fetch_watch_providers(42, kind="movie")

    assert providers["link"] == "https://www.themoviedb.org/movie/42/watch"
    # sorted by display_priority, so Max (0) comes before Netflix (1)
    assert [p["name"] for p in providers["flatrate"]] == ["Max", "Netflix"]
    assert providers["flatrate"][0]["logo_path"] == "https://image.tmdb.org/t/p/w92/max.jpg"
    assert [p["name"] for p in providers["rent"]] == ["Apple TV"]
    assert providers["buy"] == []


def test_fetch_watch_providers_empty_when_region_absent(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    monkeypatch.setenv("BUTACA_WATCH_REGION", "AR")
    monkeypatch.setattr(
        tmdb_client, "_get_json", lambda url: {"results": {"US": {"flatrate": []}}}
    )

    providers = tmdb_client.fetch_watch_providers(99, kind="movie")

    assert providers == {"link": None, "flatrate": [], "rent": [], "buy": []}
