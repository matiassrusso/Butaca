import builtins
import io
import json
from urllib.error import HTTPError

import pytest

from backend.app import vibes_clustering
from backend.app.llm_client import LlmError


def _quota_error(retry_delay: str | None = "20s") -> HTTPError:
    details = [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry_delay}]
    body = {"error": {"code": 429, "details": details if retry_delay else []}}
    return HTTPError(
        "https://example.test", 429, "Too Many Requests", {},
        io.BytesIO(json.dumps(body).encode("utf-8")),
    )


def _embedding_response(vectors_by_index: list[tuple[int, list[float]]]) -> io.BytesIO:
    payload = {"data": [{"index": i, "embedding": v} for i, v in vectors_by_index]}
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


def test_importing_the_api_does_not_require_the_c_extensions(monkeypatch) -> None:
    """igraph/leidenalg son extensiones en C y main.py importa este módulo al
    arrancar: si estuvieran a nivel módulo, una wheel que no resuelva en el
    server no rompería el job de vibras, no dejaría levantar la API."""
    import importlib
    import sys

    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name in {"igraph", "leidenalg"}:
            raise ImportError(f"sin wheel de {name} en este server")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    monkeypatch.delitem(sys.modules, "backend.app.vibes_clustering", raising=False)

    module = importlib.import_module("backend.app.vibes_clustering")

    assert module.EMBEDDING_MODEL  # importó bien sin las extensiones


def test_leiden_recovers_three_separated_synthetic_groups() -> None:
    vectors = [
        [1, 0.01, 0], [0.99, 0.02, 0], [0, 1, 0.01],
        [0, 0.99, 0.02], [0, 0, 1], [0.01, 0, 0.99],
    ]

    graph = vibes_clustering._build_knn_graph(vectors, k=1)

    assert vibes_clustering._cluster_l1(graph) == [[0, 1], [2, 3], [4, 5]]


def test_seed_titles_interleaves_discover_biases(monkeypatch) -> None:
    def fake_fetch(mood, pages=2):
        identifier = list(vibes_clustering._SEED_MOODS).index(mood)
        return [{"tmdb_id": identifier, "kind": "movie", "title": mood, "year": 2000, "tags": []}]

    monkeypatch.setattr(vibes_clustering.tmdb_client, "fetch_candidates", fake_fetch)
    monkeypatch.setattr(vibes_clustering.tmdb_client, "fetch_top_rated_by_decade", lambda kind, decade, pages=1: [])

    assert [item["tmdb_id"] for item in vibes_clustering._seed_titles(cap=5)] == [0, 1, 2, 3, 4]


def test_seed_titles_folds_in_top_rated_by_decade_pools(monkeypatch) -> None:
    """El sesgo a anime/K-drama sale de que fetch_candidates ordena por
    popularidad (medido en TASKS.md); estas pools ordenan por vote_average
    por década en cambio, y tienen que entrar a la semilla igual que las de
    mood, no quedar sin usar."""

    def fake_fetch(mood, pages=2):
        identifier = list(vibes_clustering._SEED_MOODS).index(mood)
        return [{"tmdb_id": identifier, "kind": "movie", "title": mood, "year": 2000, "tags": []}]

    decade_calls: list[tuple[str, int]] = []

    def fake_decade(kind, decade, pages=1):
        decade_calls.append((kind, decade))
        if (kind, decade) == ("movie", vibes_clustering._SEED_DECADES[0]):
            return [{"tmdb_id": 100, "kind": "movie", "title": "Classic", "year": decade, "tags": []}]
        return []

    monkeypatch.setattr(vibes_clustering.tmdb_client, "fetch_candidates", fake_fetch)
    monkeypatch.setattr(vibes_clustering.tmdb_client, "fetch_top_rated_by_decade", fake_decade)

    seed = vibes_clustering._seed_titles(cap=6)

    assert decade_calls  # las pools de década se consultaron de verdad
    assert 100 in [item["tmdb_id"] for item in seed]


def test_leiden_cluster_ids_are_deterministic_and_empty_groups_are_dropped() -> None:
    vectors = [[1, 0], [0.99, 0.01], [0, 1], [0.01, 0.99]]

    first = vibes_clustering._cluster_l1(vibes_clustering._build_knn_graph(vectors, k=1))
    second = vibes_clustering._cluster_l1(vibes_clustering._build_knn_graph(vectors, k=1))

    assert first == second
    assert vibes_clustering._compact_clusters([[], [3, 2], [], [1]]) == [[1], [2, 3]]


def test_label_cluster_falls_back_to_top_keyword_when_llm_fails(monkeypatch) -> None:
    monkeypatch.setattr(vibes_clustering.llm_client, "is_configured", lambda: True)
    monkeypatch.setattr(
        vibes_clustering.llm_client,
        "_call_nvidia_with_fallback",
        lambda prompt, api_key: (_ for _ in ()).throw(LlmError("caído")),
    )
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")

    assert vibes_clustering._label_cluster([
        {"title": "A", "year": 2000, "keywords": ["heist"], "tags": []},
        {"title": "B", "year": 2001, "keywords": ["heist", "caper"], "tags": []},
    ]) == "Heist"


def test_embed_batch_waits_out_a_rate_limit_and_retries(monkeypatch) -> None:
    """Un 429 en un batch es rate limit, no un fallo: se espera lo que pide
    el proveedor y se reintenta en vez de tirar la corrida."""
    slept: list[float] = []
    attempts = iter([_quota_error("20s"), _embedding_response([(0, [1.0])])])

    def fake_urlopen(request, timeout=None):
        value = next(attempts)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    monkeypatch.setattr(vibes_clustering.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(vibes_clustering.time, "sleep", slept.append)

    assert vibes_clustering._embed_batch(["texto"]) == [[1.0]]
    assert slept == [21.0]  # el retryDelay que vino en el cuerpo, + 1s de margen


def test_embed_batch_reorders_vectors_by_index(monkeypatch) -> None:
    """Cada vector tiene que quedar en la posición del título que lo generó:
    si la API devuelve los embeddings desordenados y se toman tal cual, las
    películas quedan asignadas al cluster de otra sin que nada falle."""
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    monkeypatch.setattr(
        vibes_clustering.urllib.request,
        "urlopen",
        lambda request, timeout=None: _embedding_response([(2, [3.0]), (0, [1.0]), (1, [2.0])]),
    )

    assert vibes_clustering._embed_batch(["a", "b", "c"]) == [[1.0], [2.0], [3.0]]


def test_embed_batch_gives_up_on_a_non_quota_http_error(monkeypatch) -> None:
    def fake_urlopen(request, timeout=None):
        raise HTTPError("https://example.test", 400, "Bad Request", {}, io.BytesIO(b"{}"))

    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    monkeypatch.setattr(vibes_clustering.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(vibes_clustering.time, "sleep", lambda seconds: pytest.fail("no se reintenta un 400"))

    with pytest.raises(vibes_clustering.VibeError):
        vibes_clustering._embed_batch(["texto"])


def test_retry_delay_falls_back_when_the_provider_omits_it() -> None:
    assert vibes_clustering._retry_delay_seconds(_quota_error(None)) == (
        vibes_clustering.EMBED_RETRY_FALLBACK_SECONDS
    )


def test_garbled_llm_labels_fall_back_instead_of_reaching_the_picker(monkeypatch) -> None:
    """Bajo 503/timeouts el modelo devuelve JSON válido con basura adentro, y
    el label termina siendo una opción clickeable. El primer string es el que
    llegó de verdad a producción el 2026-08-02."""
    basura = "An us:ru} is isan :ureosed: (2:weorted1 (      -11 2itaé:é-122:2 |:}:--:--:-2-- "
    monkeypatch.setattr(vibes_clustering.llm_client, "is_configured", lambda: True)
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    monkeypatch.setattr(
        vibes_clustering.llm_client, "_call_nvidia_with_fallback", lambda prompt, api_key: {"label": basura}
    )

    assert vibes_clustering._label_cluster([
        {"title": "A", "year": 2000, "keywords": ["heist"], "tags": []},
    ]) == "Heist"  # cae al heurístico, no al string roto


def test_real_movement_names_are_accepted_as_labels() -> None:
    # los que salieron de las corridas reales tienen que seguir pasando
    for label in (
        "Cine italiano de autor", "neo-noir", "animación 3d", "Charlie Chaplin",
        "Cine LGBTQ+ de adolescencia", "Anime cyberpunk existencial",
    ):
        assert vibes_clustering._is_sane_label(label), label
    for label in ("", "   ", "a" * 60, "1:2:3-4-5 }{ 6:7", "un nombre demasiado largo para ser una etiqueta corta"):
        assert not vibes_clustering._is_sane_label(label), label


def test_recompute_clusters_the_partial_sample_when_the_rate_limit_holds(monkeypatch) -> None:
    """Un rate limit sostenido tiene que dejar clusterizado lo que sí se
    embebió, no tirar la corrida entera (la siguiente completa desde
    title_embeddings, que persiste batch por batch)."""
    seed = [
        {"tmdb_id": identifier, "kind": "movie", "title": str(identifier), "year": 2000, "tags": []}
        for identifier in range(4)
    ]
    saved: dict = {}
    monkeypatch.setattr(vibes_clustering, "EMBED_BATCH_SIZE", 2)
    monkeypatch.setattr(vibes_clustering, "_seed_titles", lambda cap: seed)
    monkeypatch.setattr(
        vibes_clustering,
        "_metadata_for_item",
        lambda item: {**item, "metadata_text": item["title"], "keywords": [], "credits": {}},
    )
    monkeypatch.setattr(vibes_clustering.db, "get_title_embeddings", lambda keys, model: {})
    monkeypatch.setattr(vibes_clustering.db, "save_title_embeddings", lambda entries, model: None)
    monkeypatch.setattr(
        vibes_clustering.db,
        "save_vibe_clusters",
        lambda labels, assignments: saved.update(labels=labels, assignments=assignments),
    )
    monkeypatch.setattr(vibes_clustering, "_label_cluster", lambda samples: "Etiqueta")
    calls = iter([[[1.0, 0.0], [0.99, 0.01]], vibes_clustering.QuotaExhausted("rate limit sostenido")])

    def fake_embed(texts):
        value = next(calls)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(vibes_clustering, "_embed_batch", fake_embed)

    result = vibes_clustering.recompute(seed_cap=4, k=1)

    assert result["quota_exhausted"] is True
    assert result["seeded"] == 2 and result["pending_embeddings"] == 2
    # los 2 embebidos quedan asignados; los 2 sin vector no aparecen en la tabla
    assert sorted(row["tmdb_id"] for row in saved["assignments"]) == [0, 1]


def test_recompute_keeps_completed_embedding_batches_when_a_later_one_fails(monkeypatch) -> None:
    seed = [
        {"tmdb_id": identifier, "kind": "movie", "title": str(identifier), "year": 2000, "tags": []}
        for identifier in range(3)
    ]
    saved: list[list[tuple[int, str, list[float]]]] = []
    monkeypatch.setattr(vibes_clustering, "EMBED_BATCH_SIZE", 2)
    monkeypatch.setattr(vibes_clustering, "_seed_titles", lambda cap: seed)
    monkeypatch.setattr(
        vibes_clustering,
        "_metadata_for_item",
        lambda item: {**item, "metadata_text": item["title"], "keywords": [], "credits": {}},
    )
    monkeypatch.setattr(vibes_clustering.db, "get_title_embeddings", lambda keys, model: {})
    monkeypatch.setattr(vibes_clustering.db, "save_title_embeddings", lambda entries, model: saved.append(entries))
    # VibeError pelado (no QuotaExhausted) = fallo real: corta la corrida.
    calls = iter([[[1.0], [1.0]], vibes_clustering.VibeError("proveedor caído")])

    def fake_embed(texts):
        value = next(calls)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(vibes_clustering, "_embed_batch", fake_embed)

    with pytest.raises(vibes_clustering.VibeError):
        vibes_clustering.recompute(seed_cap=3)

    assert saved == [[(0, "movie", [1.0]), (1, "movie", [1.0])]]
