import io
import zipfile

from fastapi.testclient import TestClient

from backend.app.llm_client import LlmError
from backend.app.main import app
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
    client.post("/auth/register", json={"username": username, "password": "supersecret"})
    login = client.post("/auth/login", json={"username": username, "password": "supersecret"})
    return {"Authorization": f"Bearer {login.json()['token']}"}


def _post_zip(headers: dict[str, str], ratings_csv: str = VALID_RATINGS_CSV, mood: str = ""):
    return client.post(
        "/recommend/zip",
        headers=headers,
        data={"mood": mood},
        files={"file": ("export.zip", _zip_bytes({"ratings.csv": ratings_csv}), "application/zip")},
    )


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


def test_recommend_zip_uses_gemini_refinement_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    def fake_refine(ratings, mood, heuristic):
        picked = heuristic.recommendations[0].model_copy(update={"why": "elegido por el agente"})
        return heuristic.model_copy(
            update={"taste_summary": "resumen del agente", "recommendations": [picked]}
        )

    monkeypatch.setattr("backend.app.main.llm_client.refine_recommendations", fake_refine)

    headers = _auth_headers("geminiok")
    response = _post_zip(headers)

    assert response.status_code == 200
    body = response.json()
    assert body["taste_summary"] == "resumen del agente"
    assert len(body["recommendations"]) == 1
    assert body["recommendations"][0]["why"] == "elegido por el agente"
    assert body["recommendations"][0]["id"] is not None


def test_recommend_zip_falls_back_to_heuristic_when_gemini_fails(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    def raise_llm_error(ratings, mood, heuristic):
        raise LlmError("boom")

    monkeypatch.setattr("backend.app.main.llm_client.refine_recommendations", raise_llm_error)

    headers = _auth_headers("geminifallback")
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


def test_movie_details_returns_cast_and_trailer(monkeypatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "fake-key")
    monkeypatch.setattr(
        "backend.app.main.tmdb_client.fetch_credits",
        lambda tmdb_id, kind: [{"name": "Actor", "character": "Role", "profile_path": None}],
    )
    monkeypatch.setattr(
        "backend.app.main.tmdb_client.fetch_trailer_key", lambda tmdb_id, kind: "abc123"
    )

    headers = _auth_headers("moviedetails")
    response = client.get("/movies/42/details", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["cast"] == [{"name": "Actor", "character": "Role", "profile_path": None}]
    assert body["trailer_key"] == "abc123"


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
