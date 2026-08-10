"""Parecido semántico entre lo que el usuario amó y el pool de candidatos.

Los embeddings ya existían en el proyecto (vibes_clustering) pero alimentaban
SOLO el picker de movimientos: el scoring de recommender.recommend() no los
tocaba. Acá se convierten en una señal más del motor, al lado de director,
actor y década.
"""

from __future__ import annotations

import logging

import numpy as np

from . import db, vibes_clustering

logger = logging.getLogger(__name__)

# Clave de modelo propia y no la de vibes_clustering: la plantilla de acá es
# más corta (sin keywords ni credits, que son 2 requests extra de TMDb por
# título — impagable adentro de un /recommend). Dos plantillas distintas dan
# vectores que no son comparables entre sí, así que no pueden compartir cache.
MODEL = f"{vibes_clustering.EMBEDDING_MODEL}:lite"

# Topes de textos NUEVOS por request. Medido contra la API real de NVIDIA:
# 20 textos 1,2s / 60 textos 1,5s / 120 textos 2,1s — o sea que el costo es casi
# todo de ida y vuelta, no de tamaño. Lo que ya está embebido sale de la DB y no
# cuesta nada, así que un título se paga una sola vez en toda la vida del sitio.
MAX_NEW_CANDIDATES = 120
MAX_LOVED = 40

# Centrado en la media DEL POOL, escala FIJA. Medido sobre un mismo pool de 159
# candidatos de discover con cuatro perfiles muy distintos (thriller de autor
# con 10 amadas y con 30, comedia romántica, anime): el desvío casi no se movió
# (0,084 / 0,086 / 0,085 / 0,080) pero la media se corrió de 0,46 a 0,56 según
# el perfil. O sea: el desvío es una constante del modelo, la media no.
#
# Restar la media del pool saca ese corrimiento, que es una propiedad del par
# usuario-pool y no dice nada de un título puntual. Dividir por una constante y
# NO por el desvío del pool es lo que mantiene el número comparable entre
# tandas (mismo motivo por el que el match_score que se muestra es el del motor
# y no el del LLM, que repuntúa en cada llamada) — y de paso hace lo correcto
# con un pool angosto: si todos los candidatos están igual de cerca del gusto,
# los embeddings no inventan un ranking.
SIMILARITY_SPREAD = 0.08
AFFINITY_CLIP = 2.0


def _lite_text(item: dict) -> str:
    """Las mismas 5 primeras líneas de vibes_clustering._metadata_text, sin las
    dos que necesitan requests extra de TMDb.

    Tiene que ser IDÉNTICA de los dos lados (títulos amados y candidatos): la
    similitud entre un vector de esta plantilla y uno de otra no significa nada.
    """
    return "\n".join(
        (
            f"Título: {item['title']}",
            f"Año: {item['year']}",
            f"Formato: {item['kind']}",
            f"Géneros y rasgos: {', '.join(item.get('tags') or []) or 'sin datos'}",
            f"Sinopsis: {item.get('overview') or 'sin sinopsis'}",
        )
    )


def _key(item: dict) -> tuple[int | None, str]:
    return (item.get("tmdb_id"), item.get("kind", "movie"))


def _vectors_for(items: list[dict], max_new: int) -> dict[tuple[int, str], list[float]]:
    """Lee de la DB lo que ya está y embebe lo que falta, hasta `max_new`."""
    wanted: dict[tuple[int, str], dict] = {}
    for item in items:
        key = _key(item)
        # sin tmdb_id no hay clave estable con la que cachear (el catálogo mock
        # de los tests y el modo sin TMDb caen enteros acá)
        if key[0] is not None and key not in wanted:
            wanted[key] = item
    if not wanted:
        return {}
    vectors = db.get_title_embeddings(list(wanted), MODEL)
    missing = [item for key, item in wanted.items() if key not in vectors][:max_new]
    for start in range(0, len(missing), vibes_clustering.EMBED_BATCH_SIZE):
        batch = missing[start:start + vibes_clustering.EMBED_BATCH_SIZE]
        generated = vibes_clustering._embed_batch([_lite_text(item) for item in batch])
        db.save_title_embeddings(
            [(_key(item)[0], _key(item)[1], vector) for item, vector in zip(batch, generated)],
            MODEL,
        )
        vectors.update({_key(item): vector for item, vector in zip(batch, generated)})
    return vectors


def _unit(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=-1, keepdims=True)
    return matrix / np.where(norms == 0, 1, norms)


def affinity_by_key(loved: list[dict], candidates: list[dict]) -> dict[tuple[int, str], float]:
    """Qué tan cerca del centro del gusto del usuario cae cada candidato.

    `loved` son matches de TMDb de títulos que el usuario puntuó alto;
    `candidates`, el pool que se va a puntuar. El valor ya viene normalizado
    (ver SIMILARITY_SPREAD) y recortado, listo para que recommend() lo
    multiplique por su peso. Un candidato sin vector simplemente no aparece en
    el dict: cero bonus, el mismo criterio de "no match, no bonus" que ya usan
    director, actor y década.
    """
    if not loved or not candidates:
        return {}
    loved_vectors = _vectors_for(loved[:MAX_LOVED], MAX_LOVED)
    if not loved_vectors:
        return {}
    candidate_vectors = _vectors_for(candidates, MAX_NEW_CANDIDATES)
    if not candidate_vectors:
        return {}
    # normalizar ANTES de promediar: si no, un vector con norma más grande pesa
    # más en el centroide solo por ser más largo, que no es una preferencia
    centroid = _unit(_unit(np.asarray(list(loved_vectors.values()), dtype=np.float32)).mean(axis=0))
    keys = list(candidate_vectors)
    matrix = _unit(np.asarray([candidate_vectors[key] for key in keys], dtype=np.float32))
    similarity = matrix @ centroid
    centered = (similarity - similarity.mean()) / SIMILARITY_SPREAD
    return {
        key: float(np.clip(value, -AFFINITY_CLIP, AFFINITY_CLIP))
        for key, value in zip(keys, centered)
    }
