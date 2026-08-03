from backend.app import db
from backend.app.db import qmark_to_pyformat


def test_qmark_to_pyformat_translates_all_placeholders():
    sql = "INSERT INTO users (username, password_hash) VALUES (?, ?)"
    assert qmark_to_pyformat(sql) == "INSERT INTO users (username, password_hash) VALUES (%s, %s)"


def test_qmark_to_pyformat_leaves_sql_without_placeholders_unchanged():
    sql = "DELETE FROM sessions WHERE user_id = 1"
    assert qmark_to_pyformat(sql) == sql


def test_vibe_tables_round_trip() -> None:
    db.save_title_embeddings([(7, "movie", [0.1, 0.2]), (7, "series", [0.3, 0.4])], "modelo-a")

    assert db.get_title_embeddings([(7, "movie"), (7, "series")], "modelo-a") == {
        (7, "movie"): [0.1, 0.2],
        (7, "series"): [0.3, 0.4],
    }
    # los vectores de otro modelo no viven en el mismo espacio: el cache de uno
    # nunca puede contestar por el otro (dimensiones distintas = clusters rotos)
    assert db.get_title_embeddings([(7, "movie")], "modelo-b") == {}
    db.save_title_embeddings([(7, "movie", [9.9, 9.9, 9.9])], "modelo-b")
    assert db.get_title_embeddings([(7, "movie")], "modelo-a") == {(7, "movie"): [0.1, 0.2]}

    db.save_vibe_clusters(
        [
            {"level": 1, "cluster_id": 1, "label": "Cine nocturno", "sample_titles": ["A"], "size": 2},
            {"level": 2, "cluster_id": 4, "label": "Atracos tensos", "sample_titles": ["A"], "size": 1},
        ],
        [{"tmdb_id": 7, "kind": "movie", "l1_cluster_id": 1, "l2_cluster_id": 4}],
    )

    assert db.get_title_clusters_by_tmdb_ids([(7, "movie"), (7, "series")]) == {(7, "movie"): 4}
    assert db.get_vibe_clusters(level=2) == [
        {"level": 2, "cluster_id": 4, "label": "Atracos tensos", "sample_titles": ["A"], "size": 1}
    ]


def test_dead_pooled_connections_are_discarded_before_use(monkeypatch) -> None:
    """Neon cierra las conexiones ociosas, pero pool.getconn() las devuelve
    igual: `closed` solo refleja lo que sabe este proceso. Sin el sondeo, la
    primera query real explota con "SSL connection has been closed
    unexpectedly" — que es lo que pasó guardando los clusters tras ~6 min sin
    tocar la base."""
    import psycopg2

    class FakeCursor:
        def __init__(self, alive): self.alive = alive
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, sql, params=()):
            if not self.alive:
                raise psycopg2.OperationalError("SSL connection has been closed unexpectedly")

    class FakeConn:
        def __init__(self, alive): self.alive, self.closed = alive, 0
        def cursor(self, *a, **k): return FakeCursor(self.alive)

    muerta, viva = FakeConn(alive=False), FakeConn(alive=True)
    devueltas, descartadas = [muerta, viva], []

    class FakePool:
        def getconn(self): return devueltas.pop(0)
        def putconn(self, conn, close=False):
            if close:
                descartadas.append(conn)

    assert db._checkout_live_connection(FakePool()) is viva
    assert descartadas == [muerta]


def test_checkout_gives_up_instead_of_looping_forever(monkeypatch) -> None:
    import psycopg2

    class AlwaysDead:
        closed = 0
        def cursor(self, *a, **k):
            raise psycopg2.OperationalError("server closed the connection")

    class FakePool:
        def getconn(self): return AlwaysDead()
        def putconn(self, conn, close=False): pass

    try:
        db._checkout_live_connection(FakePool())
    except psycopg2.Error:
        pass
    else:
        raise AssertionError("tiene que propagar el error, no colgarse reintentando")
