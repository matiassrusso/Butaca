"""Resumen anual "Tu año en Butaca".

Agrega lo que YA está en la base (rated_items + recomendaciones servidas) en
los números de una página compartible. Cero tablas nuevas.

Este módulo no toca TMDb a propósito: la resolución de pósters, décadas y
movimientos de vibras vive en main.py (_enrich_wrapped), porque es la parte
que necesita red y tiene que poder fallar sola sin llevarse puesta la página.
"""

import html
import re
from collections import Counter

# 'import' y 'star' son puntajes que el usuario dio de verdad (Letterboxd o el
# selector de estrellas de Butaca). 'manual'/'like'/'game' llevan un rating
# SINTÉTICO — un click, no estrellas puestas. Meterlos en el promedio o en las
# favoritas sería inventarle precisión al usuario; mismo criterio que la
# columna "Dónde" de /history.
PRECISE_SOURCES = frozenset({"import", "star"})

# Debajo de esto no hay "año" que mostrar: mejor un estado vacío honesto que
# una página llena de ceros.
MIN_TITLES_FOR_WRAPPED = 5
MAX_FAVORITES = 8
# cuántos títulos del año se mandan a resolver contra TMDb (pósters + década +
# movimiento). Las favoritas son las primeras MAX_FAVORITES de esta lista.
MAX_TITLES_TO_RESOLVE = 30
MAX_VIBES = 6

_HTML_TAG = re.compile(r"<[^>]+>")


def _plain_review(review: str | None) -> str:
    """Las reseñas de Letterboxd vienen con HTML crudo (`<b style="...">`), y
    React lo escapa: sin esto la reseña se lee con los tags a la vista.
    Verificado contra la base real (la reseña de "Gran Torino" del usuario 31).
    """
    return html.unescape(_HTML_TAG.sub("", review or "")).strip()


def _year_month(item: dict) -> tuple[str, int, bool] | None:
    """(año, mes, ¿es fecha real de visto?) o None si no hay fecha usable.

    `watched_date` viene VACÍO para todo lo que no salió de un import de
    Letterboxd (los ratings a mano, los likes, los del juego no traen fecha),
    así que filtrar el año solo por ahí perdería medio historial en silencio.
    Se cae a `created_at` (cuándo lo registraste), y el flag viaja hasta la UI
    para poder decir QUÉ se está contando en vez de mostrar un número que no
    se puede explicar.
    """
    for value, dated in ((item.get("watched_date"), True), (item.get("created_at"), False)):
        text = (value or "").strip()
        # ambos son "YYYY-MM-DD..." en los dos backends (ver db.py)
        if len(text) >= 7 and text[:4].isdigit() and text[5:7].isdigit():
            month = int(text[5:7])
            if 1 <= month <= 12:
                return text[:4], month, dated
    return None


def _bucket_by_year(watched: list[dict]) -> dict[str, list[tuple[dict, int, bool]]]:
    by_year: dict[str, list[tuple[dict, int, bool]]] = {}
    for item in watched:
        parts = _year_month(item)
        if parts is None:
            continue
        year, month, dated = parts
        by_year.setdefault(year, []).append((item, month, dated))
    return by_year


def _pick_year(requested: int | None, by_year: dict[str, list]) -> int | None:
    """El año pedido gana siempre (aunque esté vacío: el usuario eligió y
    merece ver el estado vacío de ESE año, no que lo mandemos a otro).

    Sin pedido, el default es el año más reciente que tenga suficiente
    historial — y no simplemente el más reciente, porque a principios de año
    (o con dos títulos sueltos de 2026) el default caería siempre en un año
    vacío teniendo diez años de diario atrás.
    """
    if requested is not None:
        return requested
    years = sorted(by_year, reverse=True)
    for year in years:
        if len(by_year[year]) >= MIN_TITLES_FOR_WRAPPED:
            return int(year)
    return int(years[0]) if years else None


def _favorites(rows: list[tuple[dict, int, bool]]) -> list[dict]:
    """Lo mejor puntuado del año. Solo puntajes reales: una favorita elegida
    por un rating sintético no es una favorita."""
    precise = [item for item, _month, _dated in rows if item.get("source") in PRECISE_SOURCES]
    ranked = sorted(
        precise,
        # desempate por reseña escrita: si dos tienen 5 estrellas, la que te
        # hizo escribir algo dice más de tu año
        key=lambda item: (item.get("rating", 0), bool((item.get("review") or "").strip())),
        reverse=True,
    )
    return [
        {
            "title": item["title"],
            "rating": item["rating"],
            "source": item.get("source", "import"),
            "review": _plain_review(item.get("review")),
        }
        for item in ranked[:MAX_TITLES_TO_RESOLVE]
    ]


def summarize(
    watched: list[dict], sessions: list[dict], year: int | None = None
) -> dict:
    """`watched` sale de db.get_watched_items (ya viene deduplicado por título
    con prioridad de fuente) y `sessions` de db.get_recommendation_history."""
    by_year = _bucket_by_year(watched)
    available_years = [
        {"year": int(key), "count": len(rows)}
        for key, rows in sorted(by_year.items(), reverse=True)
    ]
    selected = _pick_year(year, by_year)
    rows = by_year.get(str(selected), []) if selected is not None else []

    precise_ratings = [
        item["rating"] for item, _m, _d in rows if item.get("source") in PRECISE_SOURCES
    ]
    month_counts = Counter(month for _item, month, _dated in rows)
    ranked_titles = _favorites(rows)

    # ── lo que Butaca te sirvió ese año ──────────────────────────────────
    # created_at de la sesión, no de cada pick: son del mismo momento y la
    # fila servida no expone su propio created_at (ver get_recommendation_history).
    picks_by_month: dict[str, list[int]] = {}
    tag_counts: Counter[str] = Counter()
    served_cluster_ids: Counter[int] = Counter()
    picks_count = 0
    for session in sessions:
        stamp = (session.get("created_at") or "").strip()
        if len(stamp) < 7 or stamp[:4] != str(selected):
            continue
        month_key = stamp[:7]
        for pick in session.get("recommendations", []):
            picks_count += 1
            picks_by_month.setdefault(month_key, []).append(pick.get("match_score", 0))
            for tag in pick.get("tags", []):
                if tag.startswith("vibe-l2:"):
                    try:
                        served_cluster_ids[int(tag.split(":", 1)[1])] += 1
                    except ValueError:
                        continue
                else:
                    tag_counts[tag] += 1

    match_curve = [
        {
            "month": month_key,
            "avg_match": round(sum(scores) / len(scores)),
            "count": len(scores),
        }
        for month_key, scores in sorted(picks_by_month.items())
    ]

    return {
        "year": selected,
        "available_years": available_years,
        "enough_data": len(rows) >= MIN_TITLES_FOR_WRAPPED,
        "total": len(rows),
        "precise_count": len(precise_ratings),
        "dated_count": sum(1 for _item, _month, dated in rows if dated),
        "review_count": sum(
            1 for item, _m, _d in rows if (item.get("review") or "").strip()
        ),
        "average_rating": (
            round(sum(precise_ratings) / len(precise_ratings), 2)
            if precise_ratings
            else None
        ),
        "by_month": [
            {"month": month, "count": month_counts.get(month, 0)}
            for month in range(1, 13)
        ],
        "top_month": (month_counts.most_common(1)[0][0] if month_counts else None),
        "favorites": ranked_titles[:MAX_FAVORITES],
        "picks_count": picks_count,
        "match_curve": match_curve,
        "vibes": [
            {"label": tag, "count": count} for tag, count in tag_counts.most_common(MAX_VIBES)
        ],
        # se llenan en main.py con TMDb + los clusters de la Fase 4
        "decades": [],
        "movements": [],
        # interno: main.py lo consume y lo saca antes de responder
        "_resolve_titles": [row["title"] for row in ranked_titles],
        "_served_cluster_ids": dict(served_cluster_ids),
    }
