import pytest

from backend.app import db, embeddings, vibes_clustering


def _item(tmdb_id: int, title: str, **extra) -> dict:
    return {
        "tmdb_id": tmdb_id,
        "title": title,
        "year": 2000,
        "kind": "movie",
        "tags": ["dark"],
        "overview": "algo pasa",
        **extra,
    }


def _no_network(monkeypatch) -> list[list[str]]:
    """Registra los textos que se hubieran mandado a NVIDIA, sin llamarla."""
    calls: list[list[str]] = []

    def fake(texts, retry=True):
        calls.append(texts)
        # un vector distinto por texto, determinístico: sirve para chequear
        # qué se persistió sin depender del modelo real
        return [[float(len(text)), float(index), 1.0] for index, text in enumerate(texts)]

    monkeypatch.setattr(vibes_clustering, "_embed_batch", fake)
    return calls


def test_lite_text_only_uses_fields_a_candidate_already_carries() -> None:
    """La plantilla no puede pedir keywords ni credits: son 2 requests extra de
    TMDb por título y esto corre adentro de un /recommend."""
    text = embeddings._lite_text(_item(1, "Zodiac"))

    assert "Zodiac" in text and "algo pasa" in text
    assert "Palabras clave" not in text and "Dirección" not in text


def test_lite_text_is_identical_for_a_loved_match_and_a_candidate() -> None:
    """Si los dos lados no usan la MISMA plantilla, la similitud no significa
    nada. Un match de search_title trae claves de más (genres, vote_average);
    el texto tiene que salir igual igual."""
    candidate = _item(9, "Prisoners")
    loved_match = {**candidate, "genres": ["Thriller"], "vote_average": 8.1}

    assert embeddings._lite_text(loved_match) == embeddings._lite_text(candidate)


def test_affinity_ranks_the_candidate_closest_to_the_taste_centroid(monkeypatch) -> None:
    monkeypatch.setattr(vibes_clustering, "_embed_batch", lambda texts: [])
    db.save_title_embeddings(
        [
            (1, "movie", [1.0, 0.0, 0.0]),  # amada
            (10, "movie", [1.0, 0.0, 0.0]),  # calcada a la amada
            (11, "movie", [0.0, 1.0, 0.0]),  # ortogonal
            (12, "movie", [-1.0, 0.0, 0.0]),  # opuesta
        ],
        embeddings.MODEL,
    )
    candidates = [_item(10, "Igual"), _item(11, "Distinta"), _item(12, "Opuesta")]

    affinity = embeddings.affinity_by_key([_item(1, "Amada")], candidates)

    assert affinity[(10, "movie")] > affinity[(11, "movie")] > affinity[(12, "movie")]
    # recortado a ±AFFINITY_CLIP: sin el clip, coseno 1 contra -1 sobre un
    # SIMILARITY_SPREAD de 0,08 daría un número absurdo (±12) que se comería
    # todo el resto del scoring
    assert affinity[(10, "movie")] == pytest.approx(embeddings.AFFINITY_CLIP)
    assert affinity[(12, "movie")] == pytest.approx(-embeddings.AFFINITY_CLIP)


def test_affinity_is_centered_so_a_uniformly_distant_pool_gets_no_ranking() -> None:
    """El pool entero igual de lejos del gusto no es información: los
    embeddings no tienen que inventar un ganador."""
    db.save_title_embeddings(
        [(1, "movie", [1.0, 0.0]), (10, "movie", [0.0, 1.0]), (11, "movie", [0.0, -1.0])],
        embeddings.MODEL,
    )

    affinity = embeddings.affinity_by_key(
        [_item(1, "Amada")], [_item(10, "A"), _item(11, "B")]
    )

    assert affinity[(10, "movie")] == pytest.approx(0.0)
    assert affinity[(11, "movie")] == pytest.approx(0.0)


def test_affinity_embeds_only_what_is_missing_and_persists_it(monkeypatch) -> None:
    calls = _no_network(monkeypatch)
    db.save_title_embeddings([(1, "movie", [1.0, 0.0, 0.0])], embeddings.MODEL)

    embeddings.affinity_by_key([_item(1, "Amada")], [_item(10, "Nueva"), _item(11, "Otra")])

    # una sola llamada, y solo por los dos candidatos: la amada ya estaba
    assert len(calls) == 1 and len(calls[0]) == 2
    # la segunda vez sale entera de la DB
    embeddings.affinity_by_key([_item(1, "Amada")], [_item(10, "Nueva"), _item(11, "Otra")])
    assert len(calls) == 1


def test_lite_vectors_never_land_in_the_clustering_cache(monkeypatch) -> None:
    """Plantillas distintas, espacios distintos: si compartieran clave de
    modelo, el clustering de vibras leería vectores que no son suyos."""
    _no_network(monkeypatch)

    embeddings.affinity_by_key([_item(1, "Amada")], [_item(10, "Nueva")])

    assert embeddings.MODEL != vibes_clustering.EMBEDDING_MODEL
    assert db.get_title_embeddings([(10, "movie")], vibes_clustering.EMBEDDING_MODEL) == {}
    assert db.get_title_embeddings([(10, "movie")], embeddings.MODEL)


def test_affinity_skips_candidates_without_a_tmdb_id(monkeypatch) -> None:
    """El catálogo mock (y cualquier modo sin TMDb) no trae tmdb_id: sin clave
    estable no hay cache posible, así que ni se intenta."""
    calls = _no_network(monkeypatch)
    db.save_title_embeddings([(1, "movie", [1.0, 0.0, 0.0])], embeddings.MODEL)
    mock_catalog = [{"title": "Columbus", "year": 2017, "kind": "movie", "tags": ["quiet"]}]

    assert embeddings.affinity_by_key([_item(1, "Amada")], mock_catalog) == {}
    assert calls == []


def test_affinity_embeds_live_without_retrying_on_rate_limit(monkeypatch) -> None:
    """El camino en vivo (adentro de un /recommend) tiene que pedir retry=False:
    dormir el Retry-After de un 429 acá bloquea el request de un usuario por un
    bonus best-effort (reportado por Matías, 2026-08-11: /recommend lento y
    siempre heurístico después de sumar embeddings al flujo en vivo)."""
    seen_retry: list[bool] = []

    def fake(texts, retry=True):
        seen_retry.append(retry)
        return [[1.0, 0.0, 0.0] for _ in texts]

    monkeypatch.setattr(vibes_clustering, "_embed_batch", fake)

    embeddings.affinity_by_key([_item(1, "Amada")], [_item(10, "Nueva")])

    assert seen_retry == [False, False]  # amada y candidatos, ninguno reintenta


def test_affinity_is_empty_without_loved_titles(monkeypatch) -> None:
    calls = _no_network(monkeypatch)

    assert embeddings.affinity_by_key([], [_item(10, "Nueva")]) == {}
    assert calls == []


def test_affinity_caps_how_many_new_titles_one_request_embeds(monkeypatch) -> None:
    """Tope explícito: /recommend ya es lento y cada texto nuevo es tiempo de
    NVIDIA. Los que quedan afuera suman 0, que es 'igual que el promedio'."""
    calls = _no_network(monkeypatch)
    db.save_title_embeddings([(1, "movie", [1.0, 0.0, 0.0])], embeddings.MODEL)
    monkeypatch.setattr(embeddings, "MAX_NEW_CANDIDATES", 3)

    affinity = embeddings.affinity_by_key(
        [_item(1, "Amada")], [_item(100 + i, f"Peli {i}") for i in range(10)]
    )

    assert sum(len(texts) for texts in calls) == 3
    assert len(affinity) == 3
