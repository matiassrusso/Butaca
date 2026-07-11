import pytest

from backend.app import tmdb_client


@pytest.fixture(autouse=True)
def clear_tmdb_cache() -> None:
    tmdb_client._DISCOVER_CACHE.clear()


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

