from fastapi.testclient import TestClient

from backend.app import db, wrapped
from backend.app.main import app

client = TestClient(app)


def _auth_headers(username: str) -> dict[str, str]:
    client.post(
        "/auth/register",
        json={"username": username, "password": "supersecret", "email": f"{username}@example.com"},
    )
    login = client.post("/auth/login", json={"username": username, "password": "supersecret"})
    return {"Authorization": f"Bearer {login.json()['token']}"}


def _item(title, rating=4.0, watched_date="", created_at="2026-03-05 10:00:00", source="import", review=""):
    return {
        "title": title,
        "rating": rating,
        "review": review,
        "watched_date": watched_date,
        "source": source,
        "tmdb_id": None,
        "created_at": created_at,
    }


# ── el bucketing por fecha, que es donde está la trampa ──────────────────


def test_watched_date_wins_over_created_at():
    # un import de Letterboxd trae la fecha real de visto (2015) aunque la fila
    # se haya creado hoy: el año del resumen tiene que ser el de la peli vista
    data = wrapped.summarize([_item("A", watched_date="2015-08-01")], [], None)
    assert data["available_years"] == [{"year": 2015, "count": 1}]
    assert data["dated_count"] == 1


def test_rows_without_watched_date_fall_back_to_created_at():
    # el bug silencioso que evita este test: filtrar solo por watched_date
    # perdería todo lo puntuado a mano (que nunca trae fecha)
    data = wrapped.summarize(
        [_item("A", source="star", created_at="2026-02-01 10:00:00")], [], None
    )
    assert data["year"] == 2026
    assert data["total"] == 1
    assert data["dated_count"] == 0  # se contó por cuándo se registró, y se dice


def test_unusable_dates_are_dropped_not_crashing():
    data = wrapped.summarize(
        [_item("A", watched_date="sin fecha", created_at=""), _item("B", watched_date="2020-13-01", created_at="")],
        [],
        None,
    )
    assert data["available_years"] == []
    assert data["year"] is None
    assert data["total"] == 0


# ── elección de año ──────────────────────────────────────────────────────


def test_default_year_skips_a_thin_current_year():
    # 2026 tiene 2 títulos y 2015 tiene 6: el default no debería mandar al
    # usuario a un año casi vacío teniendo un año real atrás
    items = [_item(f"old{i}", watched_date="2015-05-0%d" % (i + 1)) for i in range(6)]
    items += [_item(f"new{i}", watched_date="2026-01-0%d" % (i + 1)) for i in range(2)]
    data = wrapped.summarize(items, [], None)
    assert data["year"] == 2015
    assert data["enough_data"] is True
    assert data["available_years"] == [{"year": 2026, "count": 2}, {"year": 2015, "count": 6}]


def test_requested_year_wins_even_when_empty():
    data = wrapped.summarize([_item("A", watched_date="2015-05-01")], [], 1999)
    assert data["year"] == 1999
    assert data["total"] == 0
    assert data["enough_data"] is False
    # el año con datos sigue ofreciéndose para poder volver
    assert data["available_years"] == [{"year": 2015, "count": 1}]


def test_no_history_at_all():
    data = wrapped.summarize([], [], None)
    assert data["year"] is None
    assert data["enough_data"] is False
    assert data["favorites"] == []
    assert data["average_rating"] is None


# ── puntajes reales vs sintéticos ────────────────────────────────────────


def test_average_and_favorites_ignore_synthetic_ratings():
    # 'manual'/'like'/'game' son un click, no estrellas: no pueden inflar el
    # promedio ni colarse como "tu favorita del año"
    items = [
        _item("Real", rating=4.0, watched_date="2026-01-01", source="import"),
        _item("Fake", rating=5.0, watched_date="2026-01-02", source="like"),
    ]
    data = wrapped.summarize(items, [], 2026)
    assert data["total"] == 2
    assert data["precise_count"] == 1
    assert data["average_rating"] == 4.0
    assert [f["title"] for f in data["favorites"]] == ["Real"]


def test_review_breaks_ties_between_equal_ratings():
    items = [
        _item("Sin reseña", rating=5.0, watched_date="2026-01-01"),
        _item("Con reseña", rating=5.0, watched_date="2026-01-02", review="una obra maestra"),
    ]
    data = wrapped.summarize(items, [], 2026)
    assert data["favorites"][0]["title"] == "Con reseña"
    assert data["review_count"] == 1


# ── meses y picks ────────────────────────────────────────────────────────


def test_months_and_top_month():
    items = [_item("A", watched_date="2026-03-01"), _item("B", watched_date="2026-03-09"), _item("C", watched_date="2026-07-01")]
    data = wrapped.summarize(items, [], 2026)
    assert len(data["by_month"]) == 12
    assert data["top_month"] == 3
    assert data["by_month"][2] == {"month": 3, "count": 2}


def test_match_curve_and_vibes_from_served_picks():
    sessions = [
        {
            "created_at": "2026-02-10 12:00:00",
            "recommendations": [
                {"match_score": 70, "tags": ["dark", "vibe-l2:3"]},
                {"match_score": 80, "tags": ["dark"]},
            ],
        },
        {
            "created_at": "2026-05-10 12:00:00",
            "recommendations": [{"match_score": 90, "tags": ["funny"]}],
        },
        # otro año: no entra
        {"created_at": "2025-05-10 12:00:00", "recommendations": [{"match_score": 10, "tags": ["x"]}]},
    ]
    data = wrapped.summarize([_item("A", watched_date="2026-01-01")], sessions, 2026)
    assert data["picks_count"] == 3
    assert data["match_curve"] == [
        {"month": "2026-02", "avg_match": 75, "count": 2},
        {"month": "2026-05", "avg_match": 90, "count": 1},
    ]
    assert data["vibes"][0] == {"label": "dark", "count": 2}
    # los vibe-l2 no son vibras de texto, van al canal de movimientos
    assert all(v["label"] != "vibe-l2:3" for v in data["vibes"])
    assert data["_served_cluster_ids"] == {3: 1}


# ── el endpoint ──────────────────────────────────────────────────────────


def test_endpoint_requires_auth():
    assert client.get("/wrapped").status_code == 401


def test_endpoint_returns_the_users_year():
    headers = _auth_headers("wrappeduser")
    user_id = db.get_user_by_username("wrappeduser")["id"]
    db.save_rated_items(
        user_id,
        [(f"Peli {i}", 4.5, "", "2024-06-0%d" % (i + 1), "import", None) for i in range(6)],
    )

    body = client.get("/wrapped", headers=headers).json()
    assert body["year"] == 2024
    assert body["total"] == 6
    assert body["enough_data"] is True
    # sin TMDb configurado (ver conftest) la página sigue saliendo, sin pósters
    assert body["favorites"][0]["poster_path"] is None
    assert body["decades"] == []
    assert body["movements"] == []
    assert "_resolve_titles" not in body


def test_endpoint_empty_state_for_a_fresh_user():
    headers = _auth_headers("emptyuser")
    body = client.get("/wrapped", headers=headers).json()
    assert body["year"] is None
    assert body["enough_data"] is False
    assert body["available_years"] == []


def test_endpoint_honours_the_year_param():
    headers = _auth_headers("yearuser")
    user_id = db.get_user_by_username("yearuser")["id"]
    db.save_rated_items(
        user_id,
        [("Vieja", 5.0, "", "2016-01-01", "import", None), ("Nueva", 4.0, "", "2024-01-01", "import", None)],
    )
    body = client.get("/wrapped?year=2016", headers=headers).json()
    assert body["year"] == 2016
    assert [f["title"] for f in body["favorites"]] == ["Vieja"]
    assert [y["year"] for y in body["available_years"]] == [2024, 2016]


def test_letterboxd_review_html_is_stripped():
    # las reseñas del export vienen con HTML crudo y React lo escapa: sin
    # limpiarlo, la tarjeta muestra los tags a la vista (visto en la base real)
    data = wrapped.summarize(
        [
            _item(
                "Gran Torino",
                rating=5.0,
                watched_date="2026-01-01",
                review='<b style="font-style: italic;">perd&oacute;n</b> y venganza',
            )
        ],
        [],
        2026,
    )
    assert data["favorites"][0]["review"] == "perdón y venganza"
