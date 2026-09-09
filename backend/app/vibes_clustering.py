"""Offline metadata -> NVIDIA embeddings -> Leiden clusters for Butaca vibes."""

# las anotaciones quedan como strings: así `-> igraph.Graph` no obliga a tener
# igraph importado a nivel módulo (ver el comentario de los imports diferidos).
from __future__ import annotations

import json
import logging
import math
import os
import re
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError, URLError

import numpy as np

from . import db, llm_client, tmdb_client

# igraph y leidenalg se importan adentro de las funciones que los usan, no acá:
# son extensiones en C y main.py importa este módulo al arrancar, así que a
# nivel módulo una wheel que no resuelva en el server no rompería el job
# offline de vibras — no dejaría levantar la API entera.

logger = logging.getLogger(__name__)

# NVIDIA NIM y no Gemini: el free tier de Gemini cuenta CADA texto de un
# batchEmbedContents como un request (100/min, 1.000/día), así que la muestra
# no entraba en un día y el job quedaba racionado por tandas. Con la misma key
# que ya usa el resto del proyecto, NIM embebió los 650 títulos en 15,6s.
# Medida la calidad contra el snapshot de Gemini antes de cambiar: empate —
# NVIDIA separa mejor el neo-noir y el suspenso de Hitchcock, Gemini agrupa
# mejor el cine coreano. Lo que decidió el cambio fue poder recomputar cuando
# se quiera, no una mejora de clustering.
EMBEDDING_URL = "https://integrate.api.nvidia.com/v1/embeddings"
EMBEDDING_MODEL = "nvidia/nemotron-3-embed-1b"
EMBED_BATCH_SIZE = 100
EMBED_RETRY_ATTEMPTS = 2
EMBED_RETRY_FALLBACK_SECONDS = 60.0
METADATA_WORKERS = 8
LABEL_DELAY_SECONDS = 2
MAX_LABEL_LENGTH = 40  # el prompt pide 2 a 5 palabras; más que esto no es un nombre
_SEED_MOODS = ("", "action", "funny", "romance", "psychological")
# ataca el sesgo de popularidad de raíz (TASKS.md, 2026-08-02: 13 de 39
# movimientos eran anime o cine coreano porque /discover/tv por popularidad
# está dominado por eso hoy) en vez de compensarlo con más sesiones de mood.
_SEED_DECADES = (1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020)
# Con el mínimo de votos del catálogo, las primeras ocho páginas de discover
# se solapan mucho entre moods y apenas dejaban ~764 títulos tras deduplicar.
# Las décadas aportan calidad y variedad temporal; dar más páginas a series
# crea una muestra propia suficiente para que formen movimientos coherentes.
_SEED_DISCOVER_PAGES = 15
_SEED_MOVIE_DECADE_PAGES = 2
_SEED_SERIES_DECADE_PAGES = 4
OTHER_GENRE_ID = 0
OTHER_GENRE_LABEL = "Otros"
# ponytail: estos pesos son el único ajuste visual del layout; subir el offset
# separa más los movimientos, bajarlo hace todavía más explícita la taxonomía.
GENRE_ANCHOR_WEIGHT = 0.82
EMBEDDING_OFFSET_WEIGHT = 0.18


class VibeError(Exception):
    pass


class QuotaExhausted(VibeError):
    """429 que sobrevivió a los reintentos: es rate limit, no un fallo del
    job. Se distingue de VibeError para poder seguir con una muestra parcial
    en vez de tirar toda la corrida (NIM comparte ~40 req/min con el labeling
    y con los "why" que sirve la app en paralelo)."""


def _seed_titles(cap: int = 1500) -> list[dict]:
    """Reuse discover across several genre biases; this is an offline seed, not the catalog."""
    if cap < 1:
        return []
    pages = max(_SEED_DISCOVER_PAGES, math.ceil(cap / (len(_SEED_MOODS) * 40)))
    pools: list[list[dict]] = []
    for mood in _SEED_MOODS:
        items = [
            item for item in tmdb_client.fetch_candidates(mood, pages=pages)
            if item.get("tmdb_id") is not None
        ]
        # fetch_candidates devuelve movies antes que series. Separarlas evita
        # que las series de cada sesgo lleguen recién después de agotar todas
        # sus películas, conservando el balance round-robin entre fuentes.
        pools.extend([[item for item in items if item.get("kind") == kind] for kind in ("movie", "series")])
    for decade in _SEED_DECADES:
        for kind in ("movie", "series"):
            decade_pages = _SEED_MOVIE_DECADE_PAGES if kind == "movie" else _SEED_SERIES_DECADE_PAGES
            pools.append(
                [
                    item
                    for item in tmdb_client.fetch_top_rated_by_decade(kind, decade, pages=decade_pages)
                    if item.get("tmdb_id") is not None
                ]
            )
    seed: list[dict] = []
    seen: set[tuple[int, str]] = set()
    while len(seed) < cap and any(pools):
        for pool in pools:
            while pool:
                item = pool.pop(0)
                key = (item["tmdb_id"], item["kind"])
                if key not in seen:
                    seen.add(key)
                    seed.append(item)
                    break
            if len(seed) == cap:
                break
    return seed


def _metadata_text(item: dict, credits: dict, keywords: list[str]) -> str:
    return "\n".join(
        (
            f"Título: {item['title']}",
            f"Año: {item['year']}",
            f"Formato: {item['kind']}",
            f"Géneros y rasgos: {', '.join(item.get('tags', [])) or 'sin datos'}",
            f"Sinopsis: {item.get('overview') or 'sin sinopsis'}",
            f"Palabras clave: {', '.join(keywords) or 'sin datos'}",
            f"Dirección: {credits.get('director') or 'sin datos'}",
            f"Reparto: {', '.join(credits.get('actors') or []) or 'sin datos'}",
        )
    )


def _metadata_for_item(item: dict) -> dict:
    try:
        credits = tmdb_client.fetch_taste_credits(item["tmdb_id"], item["kind"])
    except tmdb_client.TmdbError:
        credits = {"director": None, "actors": []}
    try:
        keywords = tmdb_client.fetch_keywords(item["tmdb_id"], item["kind"])
    except tmdb_client.TmdbError:
        keywords = []
    return {**item, "credits": credits, "keywords": keywords, "metadata_text": _metadata_text(item, credits, keywords)}


def _retry_delay_seconds(exc: HTTPError) -> float:
    """El 429 puede traer cuánto falta, sea en Retry-After o en el cuerpo."""
    header = exc.headers.get("Retry-After") if exc.headers else None
    if header and header.strip().isdigit():
        return float(header.strip())
    try:
        body = exc.read().decode("utf-8", "replace")
    except OSError:
        return EMBED_RETRY_FALLBACK_SECONDS
    match = re.search(r'"retryDelay":\s*"([\d.]+)s"', body)
    # +1s de margen: el retryDelay que devuelve viene redondeado hacia abajo.
    return float(match.group(1)) + 1 if match else EMBED_RETRY_FALLBACK_SECONDS


def _embed_batch(texts: list[str], retry: bool = True, timeout: float = 30) -> list[list[float]]:
    """retry=False para el camino en vivo (embeddings.py, adentro de un
    /recommend): esperar el Retry-After de un 429 (hasta EMBED_RETRY_FALLBACK_SECONDS)
    tiene sentido en el job offline, que puede permitirse esperar, pero
    bloquear un request de usuario ese tiempo por un bonus best-effort no
    (reportado por Matías, 2026-08-11: /recommend lento y siempre heurístico
    después de sumar este llamado al flujo en vivo).

    timeout más chico, mismo motivo: medido contra la API real (ver
    embeddings.py y el commit que lo introdujo), una tanda tarda 1-2s. 30s es
    el margen razonable para el job offline, no para un request de usuario que
    se queda colgado ese tiempo si NVIDIA no responde."""
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise VibeError("NVIDIA_API_KEY no configurada.")
    payload = {
        "input": texts,
        "model": EMBEDDING_MODEL,
        "encoding_format": "float",
        # los modelos de retrieval de NIM exigen distinguir consulta de
        # documento; acá siempre estamos indexando metadata de un título.
        "input_type": "passage",
        "truncate": "END",
    }
    request = urllib.request.Request(
        EMBEDDING_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    attempts = EMBED_RETRY_ATTEMPTS if retry else 1
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read())
            break
        # HTTPError es subclase de URLError: va primero para poder distinguir
        # el 429 de rate limit (esperable y recuperable) de un error real.
        except HTTPError as exc:
            if exc.code != 429:
                raise VibeError(f"No pude generar embeddings con NVIDIA: {exc}") from exc
            # pocos reintentos a propósito: si el 429 no cede después de
            # esperar la ventana que pidió el proveedor, insistir con batches
            # de 100 solo empeora las cosas — mejor cortar y clusterizar con
            # lo que haya (medido con Gemini: 9 reintentos, ninguno pasó).
            if attempt == attempts - 1:
                raise QuotaExhausted(f"Rate limit de NVIDIA sostenido: {exc}") from exc
            delay = _retry_delay_seconds(exc)
            logger.info("Embedding rate limit reached, waiting %.0fs before retrying the batch", delay)
            time.sleep(delay)
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise VibeError(f"No pude generar embeddings con NVIDIA: {exc}") from exc
    # ordenar por "index": la API no garantiza que los embeddings vuelvan en
    # el orden en que se mandaron, y acá cada vector tiene que corresponder al
    # título de su misma posición o las asignaciones salen cruzadas.
    entries = sorted(data.get("data", []), key=lambda entry: entry.get("index", 0))
    vectors = [entry.get("embedding") for entry in entries]
    if len(vectors) != len(texts) or any(not vector for vector in vectors):
        raise VibeError("NVIDIA devolvió embeddings incompletos.")
    return vectors


def _build_knn_graph(vectors: list[list[float]], k: int = 15) -> igraph.Graph:
    import igraph

    count = len(vectors)
    graph = igraph.Graph(n=count)
    if count < 2:
        return graph
    matrix = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    normalized = np.divide(matrix, norms, out=np.zeros_like(matrix), where=norms != 0)
    similarity = normalized @ normalized.T
    np.fill_diagonal(similarity, -np.inf)
    neighbors = min(k, count - 1)
    edges: dict[tuple[int, int], float] = {}
    for source, row in enumerate(similarity):
        for target in np.argsort(-row, kind="stable")[:neighbors]:
            weight = float(row[target])
            if weight > 0:
                edge = tuple(sorted((source, int(target))))
                edges[edge] = max(edges.get(edge, 0.0), weight)
    if edges:
        graph.add_edges(list(edges))
        graph.es["weight"] = [edges[edge] for edge in edges]
    return graph


def _compact_clusters(groups: list[list[int]]) -> list[list[int]]:
    return sorted((sorted(group) for group in groups if group), key=lambda group: group[0])


def _partition(graph: igraph.Graph, resolution: float) -> list[list[int]]:
    import leidenalg

    if graph.vcount() == 0:
        return []
    if graph.ecount() == 0:
        return [[vertex] for vertex in range(graph.vcount())]
    partition = leidenalg.find_partition(
        graph,
        leidenalg.RBConfigurationVertexPartition,
        weights="weight",
        resolution_parameter=resolution,
        seed=42,
    )
    return _compact_clusters([list(group) for group in partition])


L2_RESOLUTION = 5.5
MIN_L1_GENRE_SIZE = 8
TV_GENRE_CANONICAL_IDS = {
    10759: 28, 10765: 878, 10768: 10752, 10762: 10751, 10766: 18,
    10764: None, 10763: None, 10767: None,
}


def _cluster_l2(graph: igraph.Graph) -> list[list[int]]:
    return _partition(graph, resolution=L2_RESOLUTION)


def _fallback_label(samples: list[dict]) -> str:
    terms = Counter(
        term.strip().lower()
        for item in samples
        for term in (item.get("keywords") or item.get("tags") or [])
        if term.strip()
    )
    if terms:
        return terms.most_common(1)[0][0].replace("-", " ").title()
    return "Vibra mixta"


def _is_sane_label(label: str) -> bool:
    """Un label del LLM termina siendo una opción clickeable del picker, así
    que tiene que parecerse a un nombre antes de aceptarlo.

    Bajo carga (503 y timeouts de NIM) el modelo degrada y devuelve JSON
    válido con basura adentro; en la corrida contra producción del 2026-08-02
    entró así un movimiento llamado
    'An us:ru} is isan :ureosed: (2:weorted1 (   -11 2itaé:é-122:2 |:}:--'.
    El prompt pide 2 a 5 palabras, y eso es lo que se verifica.
    """
    words = label.split()
    if not label or len(label) > MAX_LABEL_LENGTH or not 1 <= len(words) <= 6:
        return False
    # casi todo tiene que ser letras y espacios: deja pasar "neo-noir",
    # "animación 3d" o "Cine LGBTQ+ de adolescencia", y corta la basura, que
    # viene cargada de dos puntos, llaves, guiones y números sueltos.
    readable = sum(character.isalpha() or character.isspace() for character in label)
    return readable / len(label) >= 0.85


def _label_cluster(sample_titles_metadata: list[dict]) -> str:
    fallback = _fallback_label(sample_titles_metadata)
    if not llm_client.is_configured():
        return fallback
    context = "\n".join(
        f"- {item['title']} ({item['year']}): {', '.join(item.get('keywords') or item.get('tags') or [])}"
        for item in sample_titles_metadata
    )
    prompt = (
        "Dale un nombre corto en español (2 a 5 palabras) al movimiento cinematográfico "
        "que domina en estos títulos. Elegí el género, subgénero, tradición, autor, época o "
        "movimiento que comparta la MAYORÍA: ignorá outliers y nunca nombres un rasgo que aparezca "
        "solo en uno o dos ejemplos. Si hay varias señales, preferí el denominador común más específico "
        "(por ejemplo, mafia antes que drama). No uses nombres de películas ni expliques nada. "
        'Devolvé solo JSON: {"label": "..."}.\n\n' + context
    )
    try:
        label = llm_client._call_nvidia_with_fallback(prompt, os.environ.get("NVIDIA_API_KEY", "")).get("label", "")
    except llm_client.LlmError:
        return fallback
    label = str(label).strip()
    if not _is_sane_label(label):
        logger.warning("Label descartado por no parecer un nombre: %r", label[:120])
        return fallback
    return label


def _sample_cluster(members: list[int], records: list[dict], vectors: list[list[float]]) -> list[dict]:
    matrix = np.asarray([vectors[index] for index in members], dtype=np.float32)
    # Leiden arma el grafo con similitud coseno; elegir los representantes con
    # esa misma geometría evita que la magnitud de un embedding vuelva central
    # a un outlier y termine sesgando el label del LLM.
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    normalized = np.divide(matrix, norms, out=np.zeros_like(matrix), where=norms != 0)
    centroid = normalized.mean(axis=0)
    centroid_norm = np.linalg.norm(centroid)
    if centroid_norm:
        centroid /= centroid_norm
    distances = 1 - normalized @ centroid
    ordered = sorted(range(len(members)), key=lambda index: (float(distances[index]), records[members[index]]["title"]))
    return [records[members[index]] for index in ordered[:6]]


def _svd_2d(matrix: np.ndarray) -> np.ndarray:
    """Proyección a 2D por SVD, centrada y normalizada a [-1, 1].

    Devuelve siempre (n, 2) aunque la matriz tenga menos de 2 filas o rango 1
    (un cluster de 1 o 2 títulos): en esos casos `u` no tiene dos columnas y
    hay que completar con ceros en vez de reventar armando el layout.
    """
    if len(matrix) == 0:
        return np.zeros((0, 2), dtype=np.float32)
    centered = matrix - matrix.mean(axis=0)
    if len(matrix) < 2:
        return np.zeros((len(matrix), 2), dtype=np.float32)
    u, s, _ = np.linalg.svd(centered, full_matrices=False)
    projected = u[:, :2] * s[:2]
    if projected.shape[1] < 2:
        projected = np.pad(projected, ((0, 0), (0, 2 - projected.shape[1])))
    scale = float(np.abs(projected).max())
    return (projected / scale if scale else projected).astype(np.float32)


def _genre_ids(item: dict) -> list[int]:
    name_map = (
        tmdb_client.GENRE_NAME_ID_MAP
        if item.get("kind") == "movie"
        else tmdb_client.TV_GENRE_NAME_ID_MAP
    )
    ids = [name_map[name] for name in item.get("genres", []) if name in name_map]
    if item.get("kind") != "movie":
        ids = [TV_GENRE_CANONICAL_IDS.get(genre_id, genre_id) for genre_id in ids]
        ids = [genre_id for genre_id in ids if genre_id is not None]
    return list(dict.fromkeys(ids)) or [OTHER_GENRE_ID]


def _fold_small_genres(genre_ids_by_title: list[list[int]]) -> list[list[int]]:
    counts = Counter(genre_id for genre_ids in genre_ids_by_title for genre_id in genre_ids)
    small = {
        genre_id for genre_id, count in counts.items()
        if genre_id != OTHER_GENRE_ID and count < MIN_L1_GENRE_SIZE
    }
    return [
        [genre_id for genre_id in genre_ids if genre_id not in small] or [OTHER_GENRE_ID]
        for genre_ids in genre_ids_by_title
    ]


def layout_by_genre_anchors(
    vectors: list[list[float]], genre_ids_by_title: list[list[int]]
) -> list[tuple[float, float]]:
    """Place each title around the mean of its real TMDb genre anchors."""
    if not vectors:
        return []
    matrix = np.asarray(vectors, dtype=np.float32)
    members: dict[int, list[int]] = {}
    for index, genre_ids in enumerate(genre_ids_by_title):
        for genre_id in genre_ids:
            members.setdefault(genre_id, []).append(index)
    genre_ids = sorted(members)
    anchor_layout = _svd_2d(np.stack([matrix[members[genre_id]].mean(axis=0) for genre_id in genre_ids]))
    anchors = {genre_id: anchor_layout[index] for index, genre_id in enumerate(genre_ids)}
    embedding_layout = _svd_2d(matrix)
    positions = []
    for index, title_genres in enumerate(genre_ids_by_title):
        base = np.mean([anchors[genre_id] for genre_id in title_genres if genre_id in anchors], axis=0)
        point = base * GENRE_ANCHOR_WEIGHT + embedding_layout[index] * EMBEDDING_OFFSET_WEIGHT
        positions.append((round(float(point[0]), 4), round(float(point[1]), 4)))
    return positions


def recompute(seed_cap: int = 1500, k: int = 15) -> dict:
    seed = _seed_titles(seed_cap)
    if not seed:
        return {"seeded": 0, "new_embeddings": 0, "clustered": 0, "l1_clusters": 0, "l2_clusters": 0, "genres": 0}

    with ThreadPoolExecutor(max_workers=METADATA_WORKERS) as pool:
        records = list(pool.map(_metadata_for_item, seed))
    keys = [(item["tmdb_id"], item["kind"]) for item in records]
    cached = db.get_title_embeddings(keys, EMBEDDING_MODEL)
    missing = [item for item in records if (item["tmdb_id"], item["kind"]) not in cached]
    generated: dict[tuple[int, str], list[float]] = {}
    # el free tier de Gemini tiene DOS cuotas (100 requests/minuto y 1.000 por
    # día, y cada texto de un batch cuenta como un request): una muestra de
    # ~1.000 títulos no entra entera en un solo día. Quedarse sin cuota no es
    # un error del job — se clusteriza con lo que haya embebido y la corrida
    # siguiente completa el resto desde title_embeddings, que ya persiste
    # batch por batch. Un fallo real (key mala, Gemini caído) sí corta.
    exhausted = False
    for start in range(0, len(missing), EMBED_BATCH_SIZE):
        batch = missing[start:start + EMBED_BATCH_SIZE]
        try:
            vectors = _embed_batch([item["metadata_text"] for item in batch])
        except QuotaExhausted as exc:
            logger.warning("Gemini quota exhausted after %d embeddings: %s", len(generated), exc)
            exhausted = True
            break
        entries = [(item["tmdb_id"], item["kind"], vector) for item, vector in zip(batch, vectors)]
        db.save_title_embeddings(entries, EMBEDDING_MODEL)
        generated.update({(tmdb_id, kind): vector for tmdb_id, kind, vector in entries})

    # records/keys/vectors tienen que quedar alineados por índice: los grupos
    # de Leiden vienen como posiciones dentro de esta lista.
    embedded = [
        (item, cached.get(key) or generated.get(key))
        for item, key in zip(records, keys)
        if (cached.get(key) or generated.get(key)) is not None
    ]
    if not embedded:
        raise VibeError("No hay ningún embedding disponible para clusterizar.")
    records = [item for item, _ in embedded]
    vectors = [vector for _, vector in embedded]

    genre_ids_by_title = _fold_small_genres([_genre_ids(record) for record in records])
    l1_ids = [genre_ids[0] for genre_ids in genre_ids_by_title]
    positions = layout_by_genre_anchors(vectors, genre_ids_by_title)
    genre_names_by_id = {OTHER_GENRE_ID: OTHER_GENRE_LABEL}
    for record, genre_ids in zip(records, genre_ids_by_title):
        genre_names_by_id.update({
            genre_id: tmdb_client.GENRE_ID_NAME_MAP[genre_id]
            for genre_id in genre_ids if genre_id in tmdb_client.GENRE_ID_NAME_MAP
        })
    graph = _build_knn_graph(vectors, k=k)
    l2_groups = _cluster_l2(graph)
    l2_ids = [0] * len(records)
    for cluster_id, members in enumerate(l2_groups, start=1):
        for index in members:
            l2_ids[index] = cluster_id
    assignments = [
        {
            "tmdb_id": record["tmdb_id"], "kind": record["kind"],
            "l1_cluster_id": l1_ids[index], "l2_cluster_id": l2_ids[index],
            "title": record["title"], "year": record["year"],
            "poster_path": record.get("poster_path"), "x": positions[index][0], "y": positions[index][1],
        }
        for index, record in enumerate(records)
    ]
    clusters = [(2, cluster_id, members) for cluster_id, members in enumerate(l2_groups, start=1)]
    genre_counts = Counter(genre_id for genre_ids in genre_ids_by_title for genre_id in genre_ids)
    labels = [
        {"level": 1, "cluster_id": genre_id, "label": label, "sample_titles": [], "size": genre_counts[genre_id]}
        for genre_id, label in sorted(genre_names_by_id.items())
        if genre_counts[genre_id]
    ]
    seen_labels: set[tuple[int, int]] = set()
    for level, cluster_id, members in clusters:
        identity = (level, cluster_id)
        if identity in seen_labels:
            continue
        seen_labels.add(identity)
        samples = _sample_cluster(members, records, vectors)
        if labels and llm_client.is_configured():
            time.sleep(LABEL_DELAY_SECONDS)
        labels.append(
            {
                "level": level,
                "cluster_id": cluster_id,
                "label": _label_cluster(samples),
                "sample_titles": [item["title"] for item in samples],
                "size": len(members),
            }
        )
    db.save_vibe_clusters(labels, assignments)
    return {
        "seeded": len(records),
        "new_embeddings": len(generated),
        "clustered": len(records),
        # cuántos títulos de la muestra quedaron sin clusterizar por cuota:
        # sin esto, una corrida a medias se lee igual que una completa.
        "pending_embeddings": len(seed) - len(records),
        "quota_exhausted": exhausted,
        "l1_clusters": len(labels) - len(l2_groups),
        "l2_clusters": len(l2_groups),
        "genres": len(labels) - len(l2_groups),
    }
