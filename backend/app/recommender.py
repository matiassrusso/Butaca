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


def _normalize(text: str) -> str:
    return text.strip().lower()


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
        return f"{base} Hoy además buscás algo con vibra '{mood_text}'."
    return base


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


def recommend(
    ratings: list[RatedItem],
    mood: str,
    catalog: list[dict] = CATALOG,
    also_seen: frozenset[str] = frozenset(),
) -> RecommendResponse:
    positive_tags, negative_tags = _collect_preference_tags(ratings)
    seen_titles = {_normalize(item.title) for item in ratings} | {_normalize(t) for t in also_seen}
    mood_text = _normalize(mood)
    mood_tags = POSITIVE_HINTS.get(mood_text, [mood_text]) if mood_text else []

    scored: list[tuple[int, Recommendation]] = []
    for item in catalog:
        if _normalize(item["title"]) in seen_titles:
            continue

        tags = set(item["tags"])
        score = 50
        score += 12 * len(tags & positive_tags)
        score -= 10 * len(tags & negative_tags)
        score += 14 * len(tags & set(mood_tags))

        if item["kind"] == "series":
            score -= 8

        if score < 40:
            continue

        reasons = []
        if tags & positive_tags:
            reasons.append("coincide con patrones que venís premiando")
        if tags & set(mood_tags):
            reasons.append("encaja con lo que querés hoy")
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
                    why=", y ".join(reasons) + ".",
                    match_score=max(1, min(score, 99)),
                    tags=item["tags"],
                    poster_path=item.get("poster_path"),
                    backdrop_path=item.get("backdrop_path"),
                    overview=item.get("overview", ""),
                    vote_average=item.get("vote_average"),
                ),
            )
        )

    # sort by the raw (uncapped) score, not the clamped match_score — many
    # strong matches hit the same 99 display ceiling, and sorting on the
    # clamped value would make ties fall back to catalog order (movies
    # always listed before series), silently starving series out of the
    # top 5 even when they scored just as well.
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return RecommendResponse(
        taste_summary=summarize_taste(ratings, mood),
        recommendations=[recommendation for _, recommendation in scored[:5]],
    )
