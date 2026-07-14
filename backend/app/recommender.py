from collections import Counter

from .catalog import CATALOG
from .models import RatedItem, Recommendation, RecommendResponse


POSITIVE_HINTS = {
    "slow": ["slow", "quiet", "melancholic", "intimate"],
    "psychological": ["psychological", "mysterious", "dark"],
    "action": ["action", "kinetic", "blockbuster"],
    "romance": ["romantic", "intimate"],
    "funny": ["funny", "light", "sharp"],
}

NEGATIVE_HINTS = {
    "boring": ["slow", "quiet"],
    "empty": ["slow", "melancholic"],
    "loud": ["loud", "action", "kinetic"],
}

# genre picker for the "por géneros" mode — label lives in the frontend,
# this just maps a stable key to our internal tag vocabulary
GENRE_OPTIONS: dict[str, list[str]] = {
    "action": ["action", "kinetic", "blockbuster"],
    "romance": ["romantic", "intimate"],
    "comedy": ["funny", "light"],
    "horror": ["dark"],
    "drama": ["character", "melancholic"],
    "psychological": ["psychological", "mysterious"],
    "scifi": ["stylized"],
}


def _normalize(text: str) -> str:
    return text.strip().lower()


def capitalize_sentence(text: str) -> str:
    text = text.strip()
    return text[:1].upper() + text[1:] if text else text


def positive_tags_from_text(text: str) -> set[str]:
    normalized = _normalize(text)
    tags: set[str] = set()
    for hint, hint_tags in POSITIVE_HINTS.items():
        if hint in normalized:
            tags.update(hint_tags)
    return tags


def summarize_taste(ratings: list[RatedItem], mood: str) -> str:
    loved = [item for item in ratings if item.rating >= 4]
    disliked = [item for item in ratings if item.rating <= 2.5]

    if not ratings:
        base = "Todavía no tengo historial suficiente, así que arranco con picks bastante amplios."
    elif len(loved) >= len(disliked):
        base = "Tu historial tira más a cine de autor, personajes marcados y algo de riesgo controlado."
    else:
        base = "Tu historial parece castigar lo pretencioso y premiar cosas más directas o efectivas."

    mood_text = _normalize(mood)
    if mood_text:
        return capitalize_sentence(f"{base} Hoy además buscás algo con vibra '{mood_text}'.")
    return capitalize_sentence(base)


def _collect_preference_tags(ratings: list[RatedItem]) -> tuple[set[str], set[str]]:
    positive_tags: Counter[str] = Counter()
    negative_tags: Counter[str] = Counter()

    for item in ratings:
        review = _normalize(item.review)
        positive_tags.update(positive_tags_from_text(item.review))
        if item.rating >= 4.5:
            positive_tags.update(POSITIVE_HINTS["funny"])
        for hint, tags in NEGATIVE_HINTS.items():
            if hint in review:
                negative_tags.update(tags)
        if item.rating >= 4.5:
            positive_tags.update(["character", "intimate"])
        if item.rating <= 2:
            negative_tags.update(["loud"])

    return set(positive_tags), set(negative_tags)


def _pick_with_genre_coverage(
    scored: list[tuple[int, Recommendation, set[str]]],
    required_any_tags: frozenset[str],
    limit: int = 5,
) -> list[Recommendation]:
    # "quiero seleccionar varios géneros, y que el resultado tenga al menos
    # una película de cada uno" — a plain top-N by score can easily starve
    # out a selected genre entirely, so we force one representative per
    # genre first (best-scoring candidate for that genre), then fill the
    # rest by score.
    chosen: list[tuple[int, Recommendation]] = []
    chosen_ids: set[int] = set()
    covered: set[str] = set()

    for tag in required_any_tags:
        if len(chosen) >= limit or tag in covered:
            continue
        match = next(
            (triple for triple in scored if id(triple[1]) not in chosen_ids and tag in triple[2]),
            None,
        )
        if match:
            score, rec, tags = match
            chosen.append((score, rec))
            chosen_ids.add(id(rec))
            covered.update(tags & required_any_tags)

    for score, rec, _ in scored:
        if len(chosen) >= limit:
            break
        if id(rec) in chosen_ids:
            continue
        chosen.append((score, rec))
        chosen_ids.add(id(rec))

    chosen.sort(key=lambda pair: pair[0], reverse=True)
    return [rec for _, rec in chosen]


def recommend(
    ratings: list[RatedItem],
    mood: str,
    catalog: list[dict] = CATALOG,
    also_seen: frozenset[str] = frozenset(),
    kind_filter: str = "both",
    required_any_tags: frozenset[str] | None = None,
    preference_ratings: list[RatedItem] | None = None,
) -> RecommendResponse:
    taste_ratings = ratings if preference_ratings is None else preference_ratings
    positive_tags, negative_tags = _collect_preference_tags(taste_ratings)
    seen_titles = {_normalize(item.title) for item in ratings} | {_normalize(t) for t in also_seen}
    mood_text = _normalize(mood)
    mood_tags = POSITIVE_HINTS.get(mood_text, [mood_text]) if mood_text else []

    scored: list[tuple[int, Recommendation, set[str]]] = []
    for item in catalog:
        if _normalize(item["title"]) in seen_titles:
            continue
        if kind_filter != "both" and item["kind"] != kind_filter:
            continue

        tags = set(item["tags"])
        if required_any_tags and not (tags & required_any_tags):
            continue

        score = 50
        score += 12 * len(tags & positive_tags)
        score -= 10 * len(tags & negative_tags)
        score += 14 * len(tags & set(mood_tags))
        if required_any_tags:
            score += 10 * len(tags & required_any_tags)

        if item["kind"] == "series":
            score -= 8

        # no score floor here on purpose — we always want up to 5 picks when
        # the catalog has that many unseen candidates, even if some are weak
        # matches; the displayed match_score already tells the user how weak.
        reasons = []
        if tags & positive_tags:
            reasons.append("coincide con patrones que venís premiando")
        if tags & set(mood_tags):
            reasons.append("encaja con lo que querés hoy")
        if required_any_tags and (tags & required_any_tags):
            reasons.append("tiene los géneros que elegiste")
        if not reasons:
            reasons.append("tiene pinta de ser un buen riesgo para ampliar tu mapa")

        scored.append(
            (
                score,
                Recommendation(
                    tmdb_id=item.get("tmdb_id"),
                    title=item["title"],
                    year=item["year"],
                    kind=item["kind"],
                    why=capitalize_sentence(", y ".join(reasons) + "."),
                    match_score=max(1, min(score, 99)),
                    tags=item["tags"],
                    poster_path=item.get("poster_path"),
                    backdrop_path=item.get("backdrop_path"),
                    overview=item.get("overview", ""),
                    vote_average=item.get("vote_average"),
                ),
                tags,
            )
        )

    # sort by the raw (uncapped) score, not the clamped match_score — many
    # strong matches hit the same 99 display ceiling, and sorting on the
    # clamped value would make ties fall back to catalog order (movies
    # always listed before series), silently starving series out of the
    # top 5 even when they scored just as well.
    scored.sort(key=lambda triple: triple[0], reverse=True)

    if required_any_tags:
        picks = _pick_with_genre_coverage(scored, required_any_tags)
    else:
        picks = [recommendation for _, recommendation, _ in scored[:5]]

    return RecommendResponse(
        taste_summary=summarize_taste(taste_ratings, mood),
        recommendations=picks,
    )
