import io
import zipfile

from fastapi.testclient import TestClient

from backend.app import db, letterboxd_scrape, onboarding_titles
from backend.app.llm_client import LlmError
from backend.app.main import TASTE_TAG_LOOKUP_CAP, _enrich_loved_ratings_with_genre_tags, app
from backend.app.models import RatedItem
from backend.app.tmdb_client import TmdbError

client = TestClient(app)

VALID_RATINGS_CSV = "Name,Rating,Review\nMad Max: Fury Road,1.5,too loud and empty"


def _zip_bytes(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buffer.getvalue()


def _auth_headers(username: str) -> dict[str, str]:
    client.post(
        "/auth/register",
        json={"username": username, "password": "supersecret", "email": f"{username}@example.com"},
    )
    login = client.post("/auth/login", json={"username": username, "password": "supersecret"})
    return {"Authorization": f"Bearer {login.json()['token']}"}


def _post_zip(
    headers: dict[str, str],
    ratings_csv: str = VALID_RATINGS_CSV,
    mood: str = "",
    zip_files: dict[str, str] | None = None,
    **extra_form_fields: str,
):
    return client.post(
        "/recommend/zip",
        headers=headers,
        data={"mood": mood, **extra_form_fields},
        files={
            "file": (
                "export.zip",
                _zip_bytes(zip_files or {"ratings.csv": ratings_csv}),
                "application/zip",
            )
        },
    )


def test_health_accepts_get_and_head() -> None:
    # uptime monitors probe with HEAD by default; GET-only 405s every check
    assert client.get("/health").status_code == 200
    assert client.head("/health").status_code == 200


def test_recommend_zip_rejects_non_zip_filename() -> None:
    headers = _auth_headers("notazip")
    response = client.post(
        "/recommend/zip",
        headers=headers,
        data={"mood": ""},
        files={"file": ("export.csv", b"Name,Rating\nFoo,4.5", "text/csv")},
    )

    assert response.status_code == 400


def test_recommend_zip_rejects_zip_without_ratings_or_reviews() -> None:
    headers = _auth_headers("noratings")
    response = client.post(
        "/recommend/zip",
        headers=headers,
        data={"mood": ""},
        files={
            "file": (
                "export.zip",
                _zip_bytes({"profile.csv": "Date Joined,Username\n2024-01-01,someone\n"}),
                "application/zip",
            )
        },
    )

    assert response.status_code == 400


def test_recommend_zip_rejects_ratings_csv_with_no_valid_rows() -> None:
    headers = _auth_headers("novalid")
    response = _post_zip(headers, ratings_csv="Name,Rating\nUnrated Movie,\n")

    assert response.status_code == 400


def test_recommend_zip_returns_picks_with_ids_for_valid_zip() -> None:
    headers = _auth_headers("validzip")
    response = _post_zip(headers)

    assert response.status_code == 200
    recommendations = response.json()["recommendations"]
    assert recommendations
    assert all(item["id"] is not None for item in recommendations)


def test_recommend_letterboxd_returns_picks_for_valid_username(monkeypatch) -> None:
    monkeypatch.setattr(
        letterboxd_scrape,
        "fetch_letterboxd_diary",
        lambda username: (
            [RatedItem(title="Mad Max: Fury Road", rating=1.5, review="", watched_date="2024-01-01")],
            set(),
        ),
    )
    headers = _auth_headers("lbusername")

    response = client.post(
        "/recommend/letterboxd",
        headers=headers,
        data={"username": "someuser", "mood": ""},
    )

    assert response.status_code == 200
    assert response.json()["recommendations"]


def test_recommend_letterboxd_surfaces_scrape_errors_as_400(monkeypatch) -> None:
    def raise_scrape_error(username: str):
        raise letterboxd_scrape.ScrapeError(f"No encontré un usuario de Letterboxd llamado «{username}».")

    monkeypatch.setattr(letterboxd_scrape, "fetch_letterboxd_diary", raise_scrape_error)
    headers = _auth_headers("lbmissing")

    response = client.post(
        "/recommend/letterboxd",
        headers=headers,
        data={"username": "nosuchuser", "mood": ""},
    )

    assert response.status_code == 400


def test_recommend_letterboxd_rejects_invalid_mode(monkeypatch) -> None:
    headers = _auth_headers("lbbadmode")

    response = client.post(
        "/recommend/letterboxd",
        headers=headers,
        data={"username": "someuser", "mode": "not-a-mode"},
    )

    assert response.status_code == 400


def test_recommend_letterboxd_enriches_taste_from_tmdb_genres_when_reviews_are_empty(
    monkeypatch,
) -> None:
    # username imports never carry review text, so without genre enrichment
    # every pick falls back to the same generic "apuesta distinta" reason
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    monkeypatch.setattr(
        letterboxd_scrape,
        "fetch_letterboxd_diary",
        lambda username: (
            [RatedItem(title="Loved Movie", rating=5, review="", watched_date="2024-01-01")],
            set(),
        ),
    )
    monkeypatch.setattr(
        "backend.app.main.tmdb_client.search_title",
        lambda title: {"tags": ["dark", "psychological"]},
    )
    monkeypatch.setattr(
        "backend.app.main.tmdb_client.fetch_candidates",
        lambda mood: [{"title": "Dark Pick", "year": 2020, "kind": "movie", "tags": ["dark"]}],
    )

    headers = _auth_headers("lbenrich")
    response = client.post(
        "/recommend/letterboxd",
        headers=headers,
        data={"username": "someuser", "mood": ""},
    )

    assert response.status_code == 200
    assert "apuesta distinta" not in response.json()["recommendations"][0]["why"]


def test_enrich_loved_ratings_adds_tmdb_genre_tags_to_loved_titles_only(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    monkeypatch.setattr(
        "backend.app.main.tmdb_client.search_title",
        lambda title: {"tags": ["dark", "psychological"]} if title == "Loved Movie" else None,
    )

    loved = RatedItem(title="Loved Movie", rating=5, review="")
    hated = RatedItem(title="Hated Movie", rating=1, review="")
    ratings = [loved, hated]

    _enrich_loved_ratings_with_genre_tags(ratings)

    assert set(loved.tags) == {"dark", "psychological"}
    assert hated.tags == []


def test_enrich_loved_ratings_noop_when_tmdb_not_configured(monkeypatch) -> None:
    def fail_if_called(title):
        raise AssertionError("should not call TMDb when not configured")

    monkeypatch.setattr("backend.app.main.tmdb_client.search_title", fail_if_called)

    ratings = [RatedItem(title="Loved Movie", rating=5, review="")]
    _enrich_loved_ratings_with_genre_tags(ratings)

    assert ratings[0].tags == []


def test_enrich_loved_ratings_skips_titles_that_fail_to_match(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")

    def raise_error(title):
        raise TmdbError("boom")

    monkeypatch.setattr("backend.app.main.tmdb_client.search_title", raise_error)

    ratings = [RatedItem(title="Loved Movie", rating=5, review="")]
    _enrich_loved_ratings_with_genre_tags(ratings)  # must not raise

    assert ratings[0].tags == []


def test_enrich_loved_ratings_respects_lookup_cap(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    calls: list[str] = []

    def fake_search(title):
        calls.append(title)
        return {"tags": ["dark"]}

    monkeypatch.setattr("backend.app.main.tmdb_client.search_title", fake_search)

    ratings = [
        RatedItem(title=f"Loved {i}", rating=5, review="") for i in range(TASTE_TAG_LOOKUP_CAP + 5)
    ]
    _enrich_loved_ratings_with_genre_tags(ratings)

    assert len(calls) == TASTE_TAG_LOOKUP_CAP


def test_feedback_accepts_own_recommendation() -> None:
    headers = _auth_headers("feedbackok")
    picks = _post_zip(headers).json()["recommendations"]

    response = client.post(
        "/feedback",
        headers=headers,
        json={"recommendation_id": picks[0]["id"], "status": "interested"},
    )

    assert response.status_code == 201


def test_feedback_rejects_recommendation_from_another_user() -> None:
    headers_a = _auth_headers("owner")
    headers_b = _auth_headers("intruder")
    picks = _post_zip(headers_a).json()["recommendations"]

    response = client.post(
        "/feedback",
        headers=headers_b,
        json={"recommendation_id": picks[0]["id"], "status": "interested"},
    )

    assert response.status_code == 404


def test_recommend_zip_falls_back_to_mock_catalog_when_tmdb_fails(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")

    def raise_tmdb_error(mood: str):
        raise TmdbError("boom")

    monkeypatch.setattr("backend.app.main.tmdb_client.fetch_candidates", raise_tmdb_error)

    headers = _auth_headers("tmdbfallback")
    response = _post_zip(headers)

    assert response.status_code == 200
    assert response.json()["recommendations"]


def test_recommend_zip_carries_poster_and_overview_fields(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")

    def fake_fetch_candidates(mood: str):
        return [
            {
                "title": "Custom Movie",
                "year": 2021,
                "kind": "movie",
                "tags": ["psychological", "dark"],
                "poster_path": "https://image.tmdb.org/t/p/w500/poster.jpg",
                "backdrop_path": "https://image.tmdb.org/t/p/w780/backdrop.jpg",
                "overview": "A moody thriller.",
                "vote_average": 7.4,
            }
        ]

    monkeypatch.setattr("backend.app.main.tmdb_client.fetch_candidates", fake_fetch_candidates)

    headers = _auth_headers("posterfields")
    response = _post_zip(
        headers, ratings_csv="Name,Rating,Review\nWhiplash,4.5,psychological and intense"
    )

    assert response.status_code == 200
    item = response.json()["recommendations"][0]
    assert item["poster_path"] == "https://image.tmdb.org/t/p/w500/poster.jpg"
    assert item["backdrop_path"] == "https://image.tmdb.org/t/p/w780/backdrop.jpg"
    assert item["overview"] == "A moody thriller."
    assert item["vote_average"] == 7.4


def test_recommend_zip_uses_llm_refinement_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")

    def fake_refine(ratings, mood, heuristic):
        picked = heuristic.recommendations[0].model_copy(update={"why": "elegido por el agente"})
        return heuristic.model_copy(
            update={"taste_summary": "resumen del agente", "recommendations": [picked]}
        )

    monkeypatch.setattr("backend.app.main.llm_client.refine_recommendations", fake_refine)

    headers = _auth_headers("llmok")
    response = _post_zip(headers)

    assert response.status_code == 200
    body = response.json()
    assert body["taste_summary"] == "resumen del agente"
    assert len(body["recommendations"]) == 1
    assert body["recommendations"][0]["why"] == "elegido por el agente"
    assert body["recommendations"][0]["id"] is not None


def test_recommend_zip_falls_back_to_heuristic_when_llm_fails(monkeypatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")

    def raise_llm_error(ratings, mood, heuristic):
        raise LlmError("boom")

    monkeypatch.setattr("backend.app.main.llm_client.refine_recommendations", raise_llm_error)

    headers = _auth_headers("llmfallback")
    response = _post_zip(headers)

    assert response.status_code == 200
    assert response.json()["recommendations"]


def test_recommend_zip_excludes_previously_recommended_titles() -> None:
    headers = _auth_headers("nuevospicks")

    first = _post_zip(headers).json()["recommendations"]
    second = _post_zip(headers).json()["recommendations"]

    first_titles = {item["title"] for item in first}
    second_titles = {item["title"] for item in second}
    assert first_titles.isdisjoint(second_titles)


def test_recommend_zip_rejects_invalid_mode() -> None:
    headers = _auth_headers("badmode")
    response = _post_zip(headers, mode="bogus")

    assert response.status_code == 400


def test_recommend_zip_rejects_invalid_kind_filter() -> None:
    headers = _auth_headers("badkindfilter")
    response = _post_zip(headers, kind_filter="bogus")

    assert response.status_code == 400


def test_recommend_zip_genres_mode_requires_at_least_one_genre() -> None:
    headers = _auth_headers("nogenres")
    response = _post_zip(headers, mode="genres", genres="")

    assert response.status_code == 400


def test_recommend_zip_genres_mode_filters_by_selected_genres(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")

    def fake_fetch_candidates(mood: str):
        return [
            {"title": "Romance Pick", "year": 2021, "kind": "movie", "tags": ["romantic"]},
            {"title": "Unrelated Pick", "year": 2021, "kind": "movie", "tags": ["quiet"]},
        ]

    monkeypatch.setattr("backend.app.main.tmdb_client.fetch_candidates", fake_fetch_candidates)

    headers = _auth_headers("genremode")
    response = _post_zip(headers, mode="genres", genres="romance")

    assert response.status_code == 200
    titles = {item["title"] for item in response.json()["recommendations"]}
    assert titles == {"Romance Pick"}


def test_recommend_zip_kind_filter_only_returns_series(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")

    def fake_fetch_candidates(mood: str):
        return [
            {"title": "A Movie", "year": 2021, "kind": "movie", "tags": ["dark"]},
            {"title": "A Series", "year": 2021, "kind": "series", "tags": ["dark"]},
        ]

    monkeypatch.setattr("backend.app.main.tmdb_client.fetch_candidates", fake_fetch_candidates)

    headers = _auth_headers("kindfilter")
    response = _post_zip(headers, kind_filter="series")

    assert response.status_code == 200
    titles = {item["title"] for item in response.json()["recommendations"]}
    assert titles == {"A Series"}


def test_recommend_zip_recent_mode_returns_picks(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")

    def fake_fetch_candidates(mood: str):
        return [{"title": "Action Pick", "year": 2021, "kind": "movie", "tags": ["action"]}]

    monkeypatch.setattr("backend.app.main.tmdb_client.fetch_candidates", fake_fetch_candidates)

    diary_csv = (
        "Date,Name,Year,Letterboxd URI,Rating,Rewatch,Tags,Watched Date\n"
        "2024-01-01,Old Boring Movie,2000,https://boxd.it/aaa1,5,No,,2024-01-01\n"
        "2025-06-01,Recent Action Movie,2020,https://boxd.it/aaa2,5,No,,2025-06-01\n"
    )
    ratings_csv = (
        "Name,Rating,Review\n"
        "Old Boring Movie,5,slow and quiet\n"
        "Recent Action Movie,5,action packed\n"
    )
    headers = _auth_headers("recentmode")
    response = _post_zip(
        headers,
        mode="recent",
        zip_files={"ratings.csv": ratings_csv, "diary.csv": diary_csv},
    )

    assert response.status_code == 200
    assert response.json()["recommendations"][0]["title"] == "Action Pick"


def test_movie_details_returns_cast_and_trailer(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    monkeypatch.setattr(
        "backend.app.main.tmdb_client.fetch_credits",
        lambda tmdb_id, kind: [{"name": "Actor", "character": "Role", "profile_path": None}],
    )
    monkeypatch.setattr(
        "backend.app.main.tmdb_client.fetch_trailer_key", lambda tmdb_id, kind: "abc123"
    )
    monkeypatch.setattr(
        "backend.app.main.tmdb_client.fetch_watch_providers",
        lambda tmdb_id, kind: {"link": "u", "flatrate": [{"name": "Netflix", "logo_path": None}], "rent": [], "buy": []},
    )

    headers = _auth_headers("moviedetails")
    response = client.get("/movies/42/details", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["cast"] == [{"name": "Actor", "character": "Role", "profile_path": None}]
    assert body["trailer_key"] == "abc123"
    assert body["providers"]["flatrate"][0]["name"] == "Netflix"


def test_movie_details_survives_watch_providers_failure(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    monkeypatch.setattr(
        "backend.app.main.tmdb_client.fetch_credits",
        lambda tmdb_id, kind: [{"name": "Actor", "character": "Role", "profile_path": None}],
    )
    monkeypatch.setattr("backend.app.main.tmdb_client.fetch_trailer_key", lambda tmdb_id, kind: None)

    def raise_error(tmdb_id, kind):
        raise TmdbError("boom")

    monkeypatch.setattr("backend.app.main.tmdb_client.fetch_watch_providers", raise_error)

    headers = _auth_headers("providerfail")
    response = client.get("/movies/42/details", headers=headers)

    assert response.status_code == 200
    assert response.json()["providers"] is None


def test_movie_details_requires_tmdb_configured() -> None:
    headers = _auth_headers("moviedetailsnokey")
    response = client.get("/movies/42/details", headers=headers)

    assert response.status_code == 503


def test_movie_details_requires_auth() -> None:
    response = client.get("/movies/42/details")

    assert response.status_code == 401


def test_feedback_rejects_invalid_status() -> None:
    headers = _auth_headers("badstatus")
    picks = _post_zip(headers).json()["recommendations"]

    response = client.post(
        "/feedback",
        headers=headers,
        json={"recommendation_id": picks[0]["id"], "status": "bogus"},
    )

    assert response.status_code == 422


def test_history_requires_auth() -> None:
    response = client.get("/history")

    assert response.status_code == 401


def test_history_returns_sessions_for_authenticated_user() -> None:
    headers = _auth_headers("historyuser")
    _post_zip(headers, mood="funny")
    _post_zip(
        headers,
        mood="psychological",
        ratings_csv="Name,Rating,Review\nWhiplash,4.5,psychological and intense",
    )

    response = client.get("/history", headers=headers)

    assert response.status_code == 200
    sessions = response.json()["sessions"]
    assert len(sessions) == 2
    assert sessions[0]["mood"] == "psychological"
    assert sessions[0]["recommendations"]
    assert sessions[0]["taste_summary"]
    assert all(item["id"] is not None for item in sessions[0]["recommendations"])
    assert sessions[1]["mood"] == "funny"


def test_history_excludes_other_users_sessions() -> None:
    owner_headers = _auth_headers("historyowner")
    intruder_headers = _auth_headers("historyintruder")
    _post_zip(owner_headers, mood="funny")

    response = client.get("/history", headers=intruder_headers)

    assert response.status_code == 200
    assert response.json()["sessions"] == []


def test_watched_history_requires_auth() -> None:
    response = client.get("/history/watched")

    assert response.status_code == 401


def test_watched_history_returns_items_from_uploaded_zip() -> None:
    headers = _auth_headers("watcheduser")
    _post_zip(headers, ratings_csv="Name,Rating,Review\nWhiplash,4.5,psychological and intense")

    response = client.get("/history/watched", headers=headers)

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "Whiplash"
    assert items[0]["rating"] == 4.5
    assert items[0]["review"] == "psychological and intense"
    assert items[0]["created_at"]
    assert items[0]["watched_date"] == ""


def test_watched_history_returns_date_from_diary() -> None:
    headers = _auth_headers("watcheddate")
    diary_csv = (
        "Date,Name,Year,Letterboxd URI,Rating,Rewatch,Tags,Watched Date\n"
        "2025-06-01,Whiplash,2014,https://boxd.it/7bQA,4.5,No,,2025-05-28\n"
    )
    _post_zip(
        headers,
        zip_files={
            "ratings.csv": "Name,Rating,Review\nWhiplash,4.5,psychological and intense",
            "diary.csv": diary_csv,
        },
    )

    response = client.get("/history/watched", headers=headers)

    assert response.status_code == 200
    assert response.json()["items"][0]["watched_date"] == "2025-05-28"


def test_watched_history_excludes_other_users_items() -> None:
    owner_headers = _auth_headers("watchedowner")
    intruder_headers = _auth_headers("watchedintruder")
    _post_zip(owner_headers)

    response = client.get("/history/watched", headers=intruder_headers)

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_watched_history_deduplicates_reuploaded_titles() -> None:
    headers = _auth_headers("watcheddedupe")
    _post_zip(headers, ratings_csv="Name,Rating,Review\nWhiplash,4.0,first review")
    _post_zip(headers, ratings_csv="Name,Rating,Review\n whiplash ,2.5,latest review")

    response = client.get("/history/watched", headers=headers)

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "whiplash"
    assert items[0]["rating"] == 2.5
    assert items[0]["review"] == "latest review"


def test_taste_profile_requires_auth() -> None:
    response = client.get("/profile/taste")

    assert response.status_code == 401


def test_taste_profile_requires_tmdb_configured() -> None:
    headers = _auth_headers("profilenotmdb")

    response = client.get("/profile/taste", headers=headers)

    assert response.status_code == 503


def test_taste_profile_returns_genre_and_decade_breakdown(monkeypatch) -> None:
    headers = _auth_headers("profileuser")
    _post_zip(headers, ratings_csv="Name,Rating,Review\nMad Max: Fury Road,5,loved it")

    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    monkeypatch.setattr(
        "backend.app.taste_profile.tmdb_client.search_title",
        lambda title: {
            "tmdb_id": 76341,
            "title": title,
            "year": 2015,
            "kind": "movie",
            "genres": ["Acción"],
        },
    )
    monkeypatch.setattr(
        "backend.app.taste_profile.tmdb_client.fetch_taste_credits",
        lambda tmdb_id, kind: {"director": "George Miller", "actors": ["Tom Hardy"]},
    )

    response = client.get("/profile/taste", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["matched_count"] == 1
    assert body["total_count"] == 1
    assert body["genre_breakdown"] == [{"genre": "Acción", "weight": 5.0}]
    assert body["decade_breakdown"] == [{"decade": 2010, "count": 1}]
    assert body["top_directors"] == [{"name": "George Miller", "count": 1}]
    assert body["top_actors"] == [{"name": "Tom Hardy", "count": 1}]

    # the fallback recompute inside the endpoint should persist too, so a
    # second load hits the cache instead of recomputing again
    stored = db.get_taste_profile(db.get_user_by_username("profileuser")["id"])
    assert stored is not None
    assert stored["genre_breakdown"] == [{"genre": "Acción", "weight": 5.0}]


def test_recommend_zip_persists_taste_profile_for_reuse(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    monkeypatch.setattr(
        "backend.app.taste_profile.tmdb_client.search_title",
        lambda title: {
            "tmdb_id": 76341,
            "title": title,
            "year": 2015,
            "kind": "movie",
            "genres": ["Acción"],
            "tags": [],
        },
    )
    monkeypatch.setattr(
        "backend.app.taste_profile.tmdb_client.fetch_taste_credits",
        lambda tmdb_id, kind: {"director": "George Miller", "actors": ["Tom Hardy"]},
    )
    seen_kind_filters: list[str] = []

    def fake_personalized(profile, mood, kind_filter):
        seen_kind_filters.append(kind_filter)
        return [{"title": "Dark Pick", "year": 2020, "kind": "movie", "tags": ["dark"]}]

    monkeypatch.setattr("backend.app.main.tmdb_client.fetch_personalized_candidates", fake_personalized)

    headers = _auth_headers("persistprofile")
    response = _post_zip(
        headers, ratings_csv="Name,Rating,Review\nMad Max: Fury Road,5,loved it", kind_filter="series"
    )

    assert response.status_code == 200
    assert seen_kind_filters == ["series"]  # forwarded through, not hardcoded to "both"
    stored = db.get_taste_profile(db.get_user_by_username("persistprofile")["id"])
    assert stored is not None
    assert stored["genre_breakdown"] == [{"genre": "Acción", "weight": 5.0}]


def test_recommend_zip_enforces_daily_rate_limit(monkeypatch) -> None:
    monkeypatch.setenv("BUTACA_RECOMMEND_DAILY_LIMIT", "2")
    headers = _auth_headers("ratelimited")

    assert _post_zip(headers).status_code == 200
    assert _post_zip(headers).status_code == 200
    assert _post_zip(headers).status_code == 429


def test_recommend_rate_limit_is_per_user(monkeypatch) -> None:
    monkeypatch.setenv("BUTACA_RECOMMEND_DAILY_LIMIT", "1")
    headers_a = _auth_headers("rluser_a")
    headers_b = _auth_headers("rluser_b")

    assert _post_zip(headers_a).status_code == 200
    assert _post_zip(headers_a).status_code == 429
    # a different user has their own daily counter
    assert _post_zip(headers_b).status_code == 200


def test_admin_stats_404_when_not_configured() -> None:
    assert client.get("/admin/stats").status_code == 404


def test_admin_stats_403_with_wrong_token(monkeypatch) -> None:
    monkeypatch.setenv("BUTACA_ADMIN_TOKEN", "secret")

    assert client.get("/admin/stats", headers={"X-Admin-Token": "wrong"}).status_code == 403


def test_admin_stats_returns_counts(monkeypatch) -> None:
    monkeypatch.setenv("BUTACA_ADMIN_TOKEN", "secret")
    headers = _auth_headers("statsuser")
    picks = _post_zip(headers).json()["recommendations"]
    client.post(
        "/feedback",
        headers=headers,
        json={"recommendation_id": picks[0]["id"], "status": "interested"},
    )

    response = client.get("/admin/stats", headers={"X-Admin-Token": "secret"})

    assert response.status_code == 200
    body = response.json()
    assert body["users"] >= 1
    assert body["sessions"]["total"] >= 1
    assert body["picks_served"] >= 1
    assert body["feedback"]["interested"] >= 1
    assert body["feedback"]["total"] >= 1
    assert "interested" in body["feedback_rate_pct"]


def test_recommend_excludes_not_interested_titles_even_on_pool_exhaustion(monkeypatch) -> None:
    # the whole tiny pool gets recommended on the first call, so the second
    # call's "already recommended" exclusion empties it and triggers the
    # retry — the not_interested title must still stay out even then.
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")

    def fake_fetch_candidates(mood: str):
        return [
            {"title": "Rejected Pick", "year": 2021, "kind": "movie", "tags": ["dark"]},
            {"title": "Kept Pick", "year": 2021, "kind": "movie", "tags": ["dark"]},
        ]

    monkeypatch.setattr("backend.app.main.tmdb_client.fetch_candidates", fake_fetch_candidates)

    headers = _auth_headers("feedbackexclude")
    picks = _post_zip(headers).json()["recommendations"]
    rejected = next(item for item in picks if item["title"] == "Rejected Pick")
    client.post(
        "/feedback",
        headers=headers,
        json={"recommendation_id": rejected["id"], "status": "not_interested"},
    )

    second_titles = {item["title"] for item in _post_zip(headers).json()["recommendations"]}
    assert "Rejected Pick" not in second_titles
    assert "Kept Pick" in second_titles


def test_recommend_zip_refine_false_skips_llm(monkeypatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")

    def boom(ratings, mood, heuristic):
        raise AssertionError("LLM must not run when refine=0")

    monkeypatch.setattr("backend.app.main.llm_client.refine_recommendations", boom)

    headers = _auth_headers("norefine")
    response = _post_zip(headers, refine="0")

    assert response.status_code == 200
    body = response.json()
    assert body["refined"] is False
    assert body["session_id"] is not None


def test_refine_session_applies_llm_and_persists(monkeypatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    headers = _auth_headers("refinesession")
    fast = _post_zip(headers, refine="0").json()
    session_id = fast["session_id"]
    rec_id = fast["recommendations"][0]["id"]

    def fake_refine(ratings, mood, heuristic):
        picks = [heuristic.recommendations[0].model_copy(update={"why": "razón del agente"})]
        return heuristic.model_copy(
            update={"taste_summary": "resumen del agente", "recommendations": picks}
        )

    monkeypatch.setattr("backend.app.main.llm_client.refine_recommendations", fake_refine)

    response = client.post(f"/recommend/sessions/{session_id}/refine", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["refined"] is True
    assert body["taste_summary"] == "resumen del agente"
    assert body["recommendations"][0]["why"] == "razón del agente"

    # persisted: history reflects the rewritten why + summary
    sessions = client.get("/history", headers=headers).json()["sessions"]
    session = next(item for item in sessions if item["id"] == session_id)
    assert session["taste_summary"] == "resumen del agente"
    updated = next(item for item in session["recommendations"] if item["id"] == rec_id)
    assert updated["why"] == "razón del agente"


def test_refine_session_404_for_other_user() -> None:
    owner = _auth_headers("refineowner")
    intruder = _auth_headers("refineintruder")
    fast = _post_zip(owner, refine="0").json()

    response = client.post(f"/recommend/sessions/{fast['session_id']}/refine", headers=intruder)

    assert response.status_code == 404


def test_refine_session_returns_heuristic_when_llm_fails(monkeypatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    headers = _auth_headers("refinefail")
    fast = _post_zip(headers, refine="0").json()

    def raise_llm(ratings, mood, heuristic):
        raise LlmError("boom")

    monkeypatch.setattr("backend.app.main.llm_client.refine_recommendations", raise_llm)

    response = client.post(f"/recommend/sessions/{fast['session_id']}/refine", headers=headers)

    assert response.status_code == 200
    assert response.json()["refined"] is False


def test_recommend_watchlist_mode_400_when_empty() -> None:
    headers = _auth_headers("emptywatchlist")

    response = _post_zip(headers, mode="watchlist")

    assert response.status_code == 400


def test_recommend_watchlist_mode_recommends_from_persisted_watchlist(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")

    def fake_search(title):
        return {
            "tmdb_id": 1,
            "title": title,
            "year": 2021,
            "kind": "movie",
            "genres": [],
            "tags": ["dark"],
            "poster_path": None,
            "backdrop_path": None,
            "overview": "",
            "vote_average": 7.0,
        }

    # search_title is one shared function object — this single patch covers
    # both the watchlist match and the taste-profile build path
    monkeypatch.setattr("backend.app.main.tmdb_client.search_title", fake_search)
    monkeypatch.setattr(
        "backend.app.taste_profile.tmdb_client.fetch_taste_credits",
        lambda tmdb_id, kind: {"director": None, "actors": []},
    )

    headers = _auth_headers("watchlistmode")
    watchlist_csv = (
        "Date,Name,Year,Letterboxd URI\n"
        "2024-01-01,Dune,2021,https://boxd.it/aaa\n"
        "2024-01-02,Sicario,2015,https://boxd.it/bbb\n"
    )
    _post_zip(headers, zip_files={"ratings.csv": VALID_RATINGS_CSV, "watchlist.csv": watchlist_csv})

    # second import carries no watchlist.csv — mode must use the persisted one
    response = _post_zip(headers, mode="watchlist")

    assert response.status_code == 200
    titles = {item["title"] for item in response.json()["recommendations"]}
    assert titles and titles <= {"Dune", "Sicario"}


def test_taste_profile_endpoint_reuses_persisted_profile_without_recomputing(monkeypatch) -> None:
    headers = _auth_headers("cachedprofile")
    user_id = db.get_user_by_username("cachedprofile")["id"]
    db.save_taste_profile(
        user_id,
        {
            "matched_count": 3,
            "total_count": 3,
            "genre_breakdown": [{"genre": "Drama", "weight": 12.0}],
            "decade_breakdown": [{"decade": 2000, "count": 3}],
            "top_directors": [{"name": "Someone", "count": 2}],
            "top_actors": [{"name": "Someone Else", "count": 2}],
        },
    )

    monkeypatch.setenv("TMDB_API_KEY", "fake-key")

    def _boom(title: str) -> dict:
        raise AssertionError("should not recompute when a profile is already persisted")

    monkeypatch.setattr("backend.app.taste_profile.tmdb_client.search_title", _boom)

    response = client.get("/profile/taste", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["genre_breakdown"] == [{"genre": "Drama", "weight": 12.0}]
    assert body["matched_count"] == 3


# ─── Onboarding without Letterboxd ──────────────────────────────────────────

_MANUAL_RATINGS = [
    {"title": t, "rating": 4.5}
    for t in [
        "The Godfather", "Jaws", "Alien", "The Shining", "Blade Runner",
        "Die Hard", "Pulp Fiction", "The Matrix", "Inception", "Parasite",
    ]
]


def test_onboarding_titles_returns_seeds_without_tmdb_key(monkeypatch) -> None:
    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    headers = _auth_headers("onbnokey")

    response = client.get("/onboarding/titles", headers=headers)

    assert response.status_code == 200
    titles = response.json()["titles"]
    assert len(titles) == len(onboarding_titles.ONBOARDING_TITLES)
    # no TMDb key: degrade to title/year only, no posters
    assert all(item["poster_path"] is None for item in titles)
    assert titles[0]["title"] == onboarding_titles.ONBOARDING_TITLES[0]["title"]


def test_onboarding_titles_resolves_posters_with_tmdb(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    seen_years: list[int] = []

    def fake_search(title: str, year: int | None = None) -> dict:
        seen_years.append(year)
        return {"tmdb_id": 42, "poster_path": "https://img/p.jpg"}

    monkeypatch.setattr("backend.app.main.tmdb_client.search_title", fake_search)
    headers = _auth_headers("onbposter")

    response = client.get("/onboarding/titles", headers=headers)

    assert response.status_code == 200
    titles = response.json()["titles"]
    assert all(item["poster_path"] == "https://img/p.jpg" for item in titles)
    assert all(item["tmdb_id"] == 42 for item in titles)
    # cada seed tiene que buscarse con su año curado (regresión Toy Story 5)
    assert sorted(seen_years) == sorted(s["year"] for s in onboarding_titles.ONBOARDING_TITLES)


def test_onboarding_titles_requires_auth() -> None:
    assert client.get("/onboarding/titles").status_code == 401


def test_onboarding_search_returns_matches(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    monkeypatch.setattr(
        "backend.app.main.tmdb_client.search_titles",
        lambda q, limit=8: [
            {"tmdb_id": 1, "title": "Amelie", "year": 2001, "kind": "movie", "poster_path": "p.jpg"}
        ],
    )
    headers = _auth_headers("onbsearch")

    response = client.get("/onboarding/search", params={"q": "amelie"}, headers=headers)

    assert response.status_code == 200
    titles = response.json()["titles"]
    assert len(titles) == 1
    assert titles[0]["title"] == "Amelie"


def test_onboarding_search_returns_empty_for_short_query() -> None:
    headers = _auth_headers("onbsearchshort")

    response = client.get("/onboarding/search", params={"q": "a"}, headers=headers)

    assert response.status_code == 200
    assert response.json()["titles"] == []


def test_onboarding_search_returns_empty_without_tmdb_key(monkeypatch) -> None:
    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    headers = _auth_headers("onbsearchnokey")

    response = client.get("/onboarding/search", params={"q": "godfather"}, headers=headers)

    assert response.status_code == 200
    assert response.json()["titles"] == []


def test_recommend_manual_returns_picks_for_enough_ratings() -> None:
    headers = _auth_headers("manualok")

    response = client.post("/recommend/manual", headers=headers, json={"ratings": _MANUAL_RATINGS})

    assert response.status_code == 200
    recommendations = response.json()["recommendations"]
    assert recommendations
    assert all(item["id"] is not None for item in recommendations)


def test_recommend_manual_rejects_too_few_ratings() -> None:
    headers = _auth_headers("manualfew")

    response = client.post(
        "/recommend/manual", headers=headers, json={"ratings": _MANUAL_RATINGS[:9]}
    )

    assert response.status_code == 400


def test_recommend_manual_rejects_invalid_mode() -> None:
    headers = _auth_headers("manualbadmode")

    response = client.post(
        "/recommend/manual",
        headers=headers,
        json={"ratings": _MANUAL_RATINGS, "mode": "not-a-mode"},
    )

    assert response.status_code == 400


def test_recommend_manual_excludes_rated_titles_from_picks() -> None:
    headers = _auth_headers("manualexcl")

    response = client.post("/recommend/manual", headers=headers, json={"ratings": _MANUAL_RATINGS})

    assert response.status_code == 200
    rated = {item["title"] for item in _MANUAL_RATINGS}
    returned = {item["title"] for item in response.json()["recommendations"]}
    assert not (rated & returned)


def test_profile_summary_requires_auth() -> None:
    assert client.get("/profile/summary").status_code == 401


def test_profile_summary_fresh_user_has_empty_activity() -> None:
    headers = _auth_headers("summaryfresh")

    response = client.get("/profile/summary", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "summaryfresh"
    assert body["email"] == "summaryfresh@example.com"
    assert body["email_verified"] is False
    assert body["member_since"]
    assert body["rated_count"] == 0
    assert body["session_count"] == 0
    assert body["feedback_count"] == 0
    assert body["watchlist_count"] == 0
    assert body["top_title"] is None
    # sin TMDB_API_KEY el lookup del avatar degrada a null, no a error
    assert body["avatar_url"] is None


def test_profile_summary_counts_activity() -> None:
    headers = _auth_headers("summaryactive")
    picks = _post_zip(
        headers,
        ratings_csv="Name,Rating,Review\nWhiplash,4.5,intense\nMad Max: Fury Road,1.5,too loud",
    ).json()["recommendations"]
    client.post(
        "/feedback",
        headers=headers,
        json={"recommendation_id": picks[0]["id"], "status": "interested"},
    )

    response = client.get("/profile/summary", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["rated_count"] == 2
    assert body["session_count"] == 1
    assert body["feedback_count"] == 1
    # top_title = la mejor puntuada, no la última importada
    assert body["top_title"] == "Whiplash"
    assert body["top_rating"] == 4.5
