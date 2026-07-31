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


def test_recommend_letterboxd_persists_tmdb_id_from_rss(monkeypatch) -> None:
    # el tmdb:movieId del RSS de username tiene que sobrevivir el round-trip
    # completo: RSS -> RatedItem -> rated_items (DB) -> get_watched_items
    monkeypatch.setattr(
        letterboxd_scrape,
        "fetch_letterboxd_diary",
        lambda username: (
            [
                RatedItem(
                    title="GoodFellas", rating=5, review="", watched_date="2024-01-01", tmdb_id=769
                )
            ],
            set(),
        ),
    )
    headers = _auth_headers("lbtmdbid")

    response = client.post(
        "/recommend/letterboxd", headers=headers, data={"username": "someuser", "mood": ""}
    )

    assert response.status_code == 200
    user_id = db.get_user_by_username("lbtmdbid")["id"]
    watched = db.get_watched_items(user_id)
    goodfellas = next(item for item in watched if item["title"] == "GoodFellas")
    assert goodfellas["tmdb_id"] == 769
    assert goodfellas["source"] == "import"


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


def test_enrich_loved_ratings_uses_tmdb_id_when_present_no_search(monkeypatch) -> None:
    # el tmdb:movieId del RSS de username evita la búsqueda por texto —
    # ahorra el request y el riesgo de matchear un remake homónimo
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")

    def fail_if_called(title):
        raise AssertionError("no debería buscar por texto si ya tiene tmdb_id")

    monkeypatch.setattr("backend.app.main.tmdb_client.search_title", fail_if_called)
    monkeypatch.setattr(
        "backend.app.main.tmdb_client.fetch_title_by_id",
        lambda tmdb_id, kind: {"tags": ["dark", "psychological"]} if tmdb_id == 769 else None,
    )

    ratings = [RatedItem(title="GoodFellas", rating=5, review="", tmdb_id=769)]
    _enrich_loved_ratings_with_genre_tags(ratings)

    assert set(ratings[0].tags) == {"dark", "psychological"}


def test_enrich_loved_ratings_falls_back_to_search_when_id_lookup_misses(monkeypatch) -> None:
    # si el id no resuelve (título borrado de TMDb, id viejo, etc.) cae al
    # camino de siempre en vez de perder la señal
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    monkeypatch.setattr("backend.app.main.tmdb_client.fetch_title_by_id", lambda tmdb_id, kind: None)
    monkeypatch.setattr(
        "backend.app.main.tmdb_client.search_title", lambda title: {"tags": ["dark"]}
    )

    ratings = [RatedItem(title="GoodFellas", rating=5, review="", tmdb_id=999999)]
    _enrich_loved_ratings_with_genre_tags(ratings)

    assert ratings[0].tags == ["dark"]


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


def test_rate_title_persists_to_watched_history() -> None:
    # pedido de Matías (2026-07-31): "Ya la vi" en el modal ahora puede
    # puntuar directo, sin recommendation_id — tiene que andar también para
    # picks de /weekly, que no tienen fila en recommendations_served.
    headers = _auth_headers("ratetitle")

    response = client.post(
        "/profile/rate",
        headers=headers,
        json={"title": "Spider-Man: Brand New Day", "rating": 4.5, "tmdb_id": 969681},
    )

    assert response.status_code == 201
    watched = client.get("/history/watched", headers=headers).json()["items"]
    assert any(
        item["title"] == "Spider-Man: Brand New Day"
        and item["rating"] == 4.5
        and item["source"] == "manual"
        for item in watched
    )


def test_rate_title_rejects_out_of_range_rating() -> None:
    headers = _auth_headers("ratebadrange")

    response = client.post(
        "/profile/rate", headers=headers, json={"title": "X", "rating": 6}
    )

    assert response.status_code == 422


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


def test_similar_titles_returns_onboarding_title_shape(monkeypatch) -> None:
    # botón "no estoy de acuerdo con el match" (pedido de Matías, 2026-07-31)
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    monkeypatch.setattr(
        "backend.app.main.tmdb_client.fetch_similar_titles",
        lambda tmdb_id, kind: [
            {"tmdb_id": 2, "title": "Similar Movie", "year": 2010, "kind": "movie", "poster_path": None}
        ],
    )

    headers = _auth_headers("similartitles")
    response = client.get("/movies/1/similar", headers=headers)

    assert response.status_code == 200
    assert response.json()["titles"] == [
        {"title": "Similar Movie", "year": 2010, "kind": "movie", "tmdb_id": 2, "poster_path": None, "rating": None}
    ]


def test_similar_titles_requires_tmdb_configured() -> None:
    headers = _auth_headers("similarnokey")
    response = client.get("/movies/1/similar", headers=headers)

    assert response.status_code == 503


def test_similar_titles_requires_auth() -> None:
    response = client.get("/movies/1/similar")

    assert response.status_code == 401


# ─── Buscador global (pedido de Matías, 2026-07-31) ─────────────────────────


def test_titles_search_returns_movies_and_series(monkeypatch) -> None:
    # el buscador de la navbar tiene que cubrir CUALQUIER título, no solo
    # películas como el de onboarding
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    monkeypatch.setattr(
        "backend.app.main.tmdb_client.search_any_titles",
        lambda q: [
            {"tmdb_id": 1, "title": "A Movie", "year": 2020, "kind": "movie", "poster_path": None},
            {"tmdb_id": 2, "title": "A Series", "year": 2019, "kind": "series", "poster_path": None},
        ],
    )
    headers = _auth_headers("titlesearch")

    response = client.get("/titles/search?q=algo", headers=headers)

    assert response.status_code == 200
    assert [t["kind"] for t in response.json()["titles"]] == ["movie", "series"]


def test_titles_search_degrades_to_empty_instead_of_failing(monkeypatch) -> None:
    # un buscador que tira 502 rompe la navbar entera en cada tecla
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")

    def boom(q):
        raise TmdbError("boom")

    monkeypatch.setattr("backend.app.main.tmdb_client.search_any_titles", boom)
    headers = _auth_headers("titlesearchfail")

    response = client.get("/titles/search?q=algo", headers=headers)

    assert response.status_code == 200
    assert response.json()["titles"] == []


def test_titles_search_requires_auth() -> None:
    assert client.get("/titles/search?q=algo").status_code == 401


def test_title_verdict_scores_and_explains_a_searched_title(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    monkeypatch.setattr(
        "backend.app.main.tmdb_client.fetch_title_by_id",
        lambda tmdb_id, kind: {
            "tmdb_id": tmdb_id,
            "title": "Searched Movie",
            "year": 2020,
            "kind": "movie",
            "tags": ["dark", "psychological"],
            "poster_path": None,
            "backdrop_path": None,
            "overview": "algo",
            "vote_average": 8.0,
        },
    )
    monkeypatch.setattr("backend.app.main.tmdb_client.enrich_with_keyword_tags", lambda item, kind: None)
    monkeypatch.setattr(
        "backend.app.main._rebuild_ratings",
        lambda user_id: [RatedItem(title="Loved", rating=4.5, tags=["dark", "psychological"])],
    )
    headers = _auth_headers("verdictok")

    response = client.get("/titles/42/verdict", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Searched Movie"
    assert body["match_score"] > 50  # hay evidencia real, no el piso de "sin datos"
    assert body["why"]


def test_title_verdict_says_you_already_saw_it(monkeypatch) -> None:
    # mismo trato que en /weekly: si ya la puntuaste, el veredicto lo dice
    # derecho en vez de mandarle al LLM el título como candidato y como
    # historial a la vez
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    monkeypatch.setattr(
        "backend.app.main.tmdb_client.fetch_title_by_id",
        lambda tmdb_id, kind: {
            "tmdb_id": tmdb_id,
            "title": "Seen Movie",
            "year": 2020,
            "kind": "movie",
            "tags": ["dark"],
            "poster_path": None,
            "backdrop_path": None,
            "overview": "",
            "vote_average": 7.0,
        },
    )
    monkeypatch.setattr("backend.app.main.tmdb_client.enrich_with_keyword_tags", lambda item, kind: None)
    monkeypatch.setattr(
        "backend.app.main._rebuild_ratings",
        lambda user_id: [RatedItem(title="Seen Movie", rating=4.5, tags=["dark"])],
    )
    headers = _auth_headers("verdictseen")

    response = client.get("/titles/42/verdict", headers=headers)

    assert response.status_code == 200
    assert response.json()["why"] == "Ya la viste — te encantó."


def test_title_verdict_404s_for_an_unknown_tmdb_id(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    monkeypatch.setattr("backend.app.main.tmdb_client.fetch_title_by_id", lambda tmdb_id, kind: None)
    headers = _auth_headers("verdict404")

    assert client.get("/titles/999999/verdict", headers=headers).status_code == 404


def test_title_verdict_rejects_an_invalid_kind(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    headers = _auth_headers("verdictbadkind")

    assert client.get("/titles/1/verdict?kind=person", headers=headers).status_code == 400


def test_title_verdict_requires_auth() -> None:
    assert client.get("/titles/1/verdict").status_code == 401


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
    assert items[0]["source"] == "import"


def test_watched_history_distinguishes_import_from_manual_source() -> None:
    # pedido de Matías (2026-07-31): la bitácora necesita saber si un rating
    # vino de Letterboxd (estrellas reales) o de un botón de Butaca (rating
    # sintético) para no mostrar ambos como si fueran el mismo tipo de dato
    headers = _auth_headers("watchedsource")
    _post_zip(headers, ratings_csv="Name,Rating,Review\nWhiplash,4.5,great")
    client.post(
        "/profile/rate", headers=headers, json={"title": "Manual Movie", "rating": 3.5}
    )

    items = client.get("/history/watched", headers=headers).json()["items"]

    by_title = {item["title"]: item["source"] for item in items}
    assert by_title["Whiplash"] == "import"
    assert by_title["Manual Movie"] == "manual"


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


def test_onboarding_titles_merges_previously_rated_titles(monkeypatch) -> None:
    # feedback: el banner "Usar mi perfil" era todo o nada (no dejaba sumar
    # títulos ni cambiar ratings); ahora la grilla de onboarding precarga lo
    # que el usuario ya puntuó antes, de cualquier fuente, y sigue editable.
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    monkeypatch.setattr(
        "backend.app.main.tmdb_client.search_title",
        lambda title, year=None: {
            "tmdb_id": 999,
            "year": 2015,
            "kind": "movie",
            "poster_path": "https://img/extra.jpg",
            "tags": [],
        },
    )
    headers = _auth_headers("onbmerge")
    client.post(
        "/recommend/manual",
        headers=headers,
        json={"ratings": _MANUAL_RATINGS + [{"title": "Nunca Sabrás Que Vi Esto", "rating": 4.0}]},
    )

    response = client.get("/onboarding/titles", headers=headers)

    assert response.status_code == 200
    titles = {item["title"]: item for item in response.json()["titles"]}

    # seed que el usuario también puntuó: aparece con su rating
    assert titles["The Godfather"]["rating"] == 4.5
    # título puntuado que NO está en la lista semilla: también aparece,
    # resuelto contra TMDb best-effort (sin año curado)
    extra = titles["Nunca Sabrás Que Vi Esto"]
    assert extra["rating"] == 4.0
    assert extra["tmdb_id"] == 999
    assert extra["poster_path"] == "https://img/extra.jpg"
    # seed que el usuario NO puntuó: sin rating
    unrated_seed_titles = {s["title"] for s in onboarding_titles.ONBOARDING_TITLES} - {
        r["title"] for r in _MANUAL_RATINGS
    }
    assert titles[next(iter(unrated_seed_titles))]["rating"] is None


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


def test_recommend_manual_excludes_titles_rated_in_a_different_session() -> None:
    # bug reportado por Matias (2026-07-30): puntuar "Before Sunrise" en una
    # sesion (ej. "Sin cuenta") y despues generar recomendaciones desde OTRA
    # sesion/fuente (ej. Letterboxd, acá simulado con un 2do /recommend/manual
    # con ratings distintos) la recomendaba de vuelta -- la exclusion de
    # "ya vistas" solo miraba lo puntuado EN ESE request puntual, nunca el
    # historial completo persistido (db.get_watched_items).
    headers = _auth_headers("manualcross")

    first_session = [{"title": "Before Sunrise", "rating": 4.5}] + [
        {"title": t, "rating": 4.5}
        for t in [
            "The Godfather", "Jaws", "Alien", "The Shining", "Blade Runner",
            "Die Hard", "Pulp Fiction", "The Matrix", "Inception",
        ]
    ]
    first = client.post("/recommend/manual", headers=headers, json={"ratings": first_session})
    assert first.status_code == 200

    second_session = [
        {"title": t, "rating": 4.5}
        for t in [
            "Parasite", "Whiplash", "Get Out", "La La Land", "Joker",
            "Oppenheimer", "Interstellar", "Django Unchained", "Titanic", "Gladiator",
        ]
    ]
    second = client.post("/recommend/manual", headers=headers, json={"ratings": second_session})

    assert second.status_code == 200
    titles = {item["title"] for item in second.json()["recommendations"]}
    assert "Before Sunrise" not in titles


def test_recommend_manual_persists_source_as_manual() -> None:
    # el "source" es lo que despues usa llm_client para NO citar un puntaje
    # numerico preciso ("4.5/5") en el why de algo que fue un click de boton,
    # no un rating real que el usuario haya dado
    headers = _auth_headers("manualsource")
    client.post("/recommend/manual", headers=headers, json={"ratings": _MANUAL_RATINGS})

    user_id = db.get_user_by_username("manualsource")["id"]
    watched = db.get_watched_items(user_id)

    assert watched
    assert all(item["source"] == "manual" for item in watched)


def test_recommend_profile_reuses_saved_ratings_without_duplicating() -> None:
    headers = _auth_headers("profileshortcut")
    client.post("/recommend/manual", headers=headers, json={"ratings": _MANUAL_RATINGS})
    user_id = db.get_user_by_username("profileshortcut")["id"]
    watched_before = len(db.get_watched_items(user_id))

    response = client.post("/recommend/profile", headers=headers, json={})

    assert response.status_code == 200
    assert response.json()["recommendations"]
    # persist=False: regenerating from the saved profile must not re-insert
    # the same rated_items rows
    assert len(db.get_watched_items(user_id)) == watched_before


def test_recommend_profile_requires_existing_profile() -> None:
    headers = _auth_headers("profilenoprofile")

    response = client.post("/recommend/profile", headers=headers, json={})

    assert response.status_code == 400


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


# ─── Recomendaciones de la semana (pedido de Matías, 2026-07-30) ────────────

_WEEKLY_TRENDING = [
    {
        "tmdb_id": i,
        "title": f"Weekly Movie {i}",
        "year": 2020,
        "kind": "movie",
        "tags": ["dark", "psychological"],
        "poster_path": None,
        "backdrop_path": None,
        "overview": "",
        "vote_average": 7.5,
    }
    for i in range(5)
]


def test_weekly_requires_tmdb_configured(monkeypatch) -> None:
    monkeypatch.delenv("TMDB_API_KEY", raising=False)

    assert client.get("/weekly").status_code == 503


def test_weekly_works_without_auth_no_personalization(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    monkeypatch.setattr(
        "backend.app.main.tmdb_client.fetch_weekly_trending", lambda: _WEEKLY_TRENDING
    )

    response = client.get("/weekly")

    assert response.status_code == 200
    recs = response.json()["recommendations"]
    assert len(recs) == 5
    assert {r["title"] for r in recs} == {m["title"] for m in _WEEKLY_TRENDING}
    # sin historial no hay evidencia — match_score neutro (50, "sin evidencia")
    assert all(r["match_score"] == 50 for r in recs)


def test_weekly_same_five_movies_for_every_user_this_week(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    monkeypatch.setattr(
        "backend.app.main.tmdb_client.fetch_weekly_trending", lambda: _WEEKLY_TRENDING
    )
    headers_a = _auth_headers("weeklyusera")
    headers_b = _auth_headers("weeklyuserb")

    titles_a = {r["title"] for r in client.get("/weekly", headers=headers_a).json()["recommendations"]}
    titles_b = {r["title"] for r in client.get("/weekly", headers=headers_b).json()["recommendations"]}
    titles_anon = {r["title"] for r in client.get("/weekly").json()["recommendations"]}

    assert titles_a == titles_b == titles_anon == {m["title"] for m in _WEEKLY_TRENDING}


def test_weekly_scores_against_the_users_real_taste(monkeypatch) -> None:
    # /recommend/manual no carga review (solo title+rating) y las tags de
    # _enrich_loved_ratings_with_genre_tags nunca se persisten (rated_items no
    # tiene columna tags) — así que el signal de un usuario real solo
    # sobrevive entre requests vía review text o el profile de directores/
    # actores/década. Para aislar lo que este test quiere probar (que /weekly
    # efectivamente pasa el historial del usuario a recommend() y puntúa con
    # eso) se mockea _rebuild_ratings directo con tags ya puestas, en vez de
    # depender de esa cadena completa de persistencia.
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    monkeypatch.setattr(
        "backend.app.main.tmdb_client.fetch_weekly_trending", lambda: _WEEKLY_TRENDING
    )
    monkeypatch.setattr(
        "backend.app.main._rebuild_ratings",
        lambda user_id: [
            RatedItem(title="Loved Movie", rating=4.5, tags=["dark", "psychological"])
        ],
    )
    headers = _auth_headers("weeklytaste")

    response = client.get("/weekly", headers=headers)

    assert response.status_code == 200
    recs = response.json()["recommendations"]
    assert all(r["match_score"] > 50 for r in recs)


def test_weekly_differentiates_identical_match_scores_by_vote_average(monkeypatch) -> None:
    # bug reportado por Matías (2026-07-31): 4 de las 5 semanales daban
    # exactamente el mismo match_score (81%) — confirmado contra logs de
    # producción que KEYWORD_TAG_MAP no diferenciaba esos títulos. Con el
    # mismo tag-match para todos (mismo vote_average de _WEEKLY_TRENDING no
    # sirve acá), se arma un catálogo a mano con vote_average distinto por
    # título para probar el desempate.
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    catalog = [
        {**item, "vote_average": 8.5 if i == 0 else 6.5} for i, item in enumerate(_WEEKLY_TRENDING)
    ]
    monkeypatch.setattr("backend.app.main.tmdb_client.fetch_weekly_trending", lambda: catalog)
    monkeypatch.setattr(
        "backend.app.main._rebuild_ratings",
        lambda user_id: [
            RatedItem(title="Loved Movie", rating=4.5, tags=["dark", "psychological"])
        ],
    )
    headers = _auth_headers("weeklydifferentiate")

    response = client.get("/weekly", headers=headers)

    assert response.status_code == 200
    recs = response.json()["recommendations"]
    scores = {r["tmdb_id"]: r["match_score"] for r in recs}
    # todos tenían el mismo tag-match (mismo score de recommend()) pero
    # distinto vote_average -> el desempate los separa
    assert scores[0] > scores[1]


def test_weekly_never_nudges_a_score_below_the_no_evidence_floor(monkeypatch) -> None:
    # match_score=50 es "sin evidencia" a propósito (isUnknownMatch en el
    # frontend) — el desempate por vote_average no debe tocarlo, si no un
    # 50% real (sin evidencia) se mostraría como si tuviera evidencia
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    monkeypatch.setattr(
        "backend.app.main.tmdb_client.fetch_weekly_trending", lambda: _WEEKLY_TRENDING
    )

    response = client.get("/weekly")  # sin sesión -> sin evidencia, match_score=50

    assert response.status_code == 200
    assert all(r["match_score"] == 50 for r in response.json()["recommendations"])


def test_weekly_enriches_loved_ratings_with_tmdb_tags_before_scoring(monkeypatch) -> None:
    # bug reportado por Matías (2026-07-31): un título amado sin reseña (like
    # o favorito de Letterboxd, botón manual) llega de la DB sin tags
    # (rated_items no tiene columna tags) y /weekly nunca llamaba a
    # _enrich_loved_ratings_with_genre_tags como sí hace /recommend — así que
    # match_score quedaba en el piso de 50 aunque el LLM sí supiera que lo
    # había amado. Esto prueba que /weekly ahora pasa por el mismo
    # enriquecimiento antes de puntuar.
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    monkeypatch.setattr(
        "backend.app.main.tmdb_client.fetch_weekly_trending", lambda: _WEEKLY_TRENDING
    )
    monkeypatch.setattr(
        "backend.app.main._rebuild_ratings",
        lambda user_id: [RatedItem(title="Loved Movie", rating=4.5, review="", source="like")],
    )
    monkeypatch.setattr(
        "backend.app.main.tmdb_client.search_title",
        lambda title: {"tags": ["dark", "psychological"]} if title == "Loved Movie" else None,
    )
    headers = _auth_headers("weeklyenrich")

    response = client.get("/weekly", headers=headers)

    assert response.status_code == 200
    assert all(r["match_score"] > 50 for r in response.json()["recommendations"])


def test_weekly_keeps_all_five_even_when_user_already_rated_one(monkeypatch) -> None:
    # bug reportado por Matías (2026-07-31): recommend() excluye del catálogo
    # cualquier título que ya esté en el historial del usuario — correcto
    # para /recommend, pero /weekly promete "las mismas 5 para todo el
    # mundo" y perdía en silencio cualquiera de las 5 que el usuario ya
    # hubiera puntuado o marcado como vista.
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    monkeypatch.setattr(
        "backend.app.main.tmdb_client.fetch_weekly_trending", lambda: _WEEKLY_TRENDING
    )
    monkeypatch.setattr(
        "backend.app.main._rebuild_ratings",
        lambda user_id: [RatedItem(title="Weekly Movie 0", rating=4.5, review="")],
    )
    headers = _auth_headers("weeklyalreadyseen")

    response = client.get("/weekly", headers=headers)

    assert response.status_code == 200
    recs = response.json()["recommendations"]
    assert {r["title"] for r in recs} == {m["title"] for m in _WEEKLY_TRENDING}


def test_weekly_uses_llm_prediction_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    monkeypatch.setattr(
        "backend.app.main.tmdb_client.fetch_weekly_trending", lambda: _WEEKLY_TRENDING
    )
    monkeypatch.setattr(
        "backend.app.main.llm_client.predict_fit",
        lambda user_id, ratings, heuristic: heuristic.model_copy(
            update={
                "recommendations": [
                    r.model_copy(update={"why": "predicción del LLM"}) for r in heuristic.recommendations
                ]
            }
        ),
    )
    headers = _auth_headers("weeklyllm")
    client.post("/recommend/manual", headers=headers, json={"ratings": _MANUAL_RATINGS})

    response = client.get("/weekly", headers=headers)

    assert response.status_code == 200
    assert all(r["why"] == "predicción del LLM" for r in response.json()["recommendations"])


def test_weekly_falls_back_to_heuristic_when_llm_fails(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    monkeypatch.setattr(
        "backend.app.main.tmdb_client.fetch_weekly_trending", lambda: _WEEKLY_TRENDING
    )

    def boom(user_id, ratings, heuristic):
        raise LlmError("boom")

    monkeypatch.setattr("backend.app.main.llm_client.predict_fit", boom)
    headers = _auth_headers("weeklyllmfail")
    client.post("/recommend/manual", headers=headers, json={"ratings": _MANUAL_RATINGS})

    response = client.get("/weekly", headers=headers)

    assert response.status_code == 200
    assert len(response.json()["recommendations"]) == 5
