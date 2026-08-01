import math
from collections import Counter

from .catalog import CATALOG
from .models import RatedItem, Recommendation, RecommendResponse


POSITIVE_HINTS = {
    "slow": ["slow", "quiet", "melancholic", "intimate"],
    "psychological": ["psychological", "mysterious", "dark"],
    "action": ["action", "kinetic", "blockbuster"],
    "romance": ["romantic", "intimate"],
    "funny": ["funny", "light", "sharp"],
    # keys de los tags que vienen de las keywords de TMDb
    # (tmdb_client.KEYWORD_TAG_MAP), acotadas a las que alguien realmente
    # escribiría en una reseña. Sin entrada acá un tag se muestra en la UI pero
    # nunca puede ganar score: este es el único camino por el que un tag del
    # catálogo cobra bonus desde la reseña del usuario.
    "heist": ["heist"],
    "revenge": ["revenge"],
    "road trip": ["road-trip"],
    "coming of age": ["coming-of-age"],
    # ronda 2 (2026-07-30) de KEYWORD_TAG_MAP — "psychological thriller",
    # "character study" y "hold-up robbery" reusan tags ya existentes
    # (psychological/character/heist), así que ya tienen su camino de score
    # sin agregar nada acá.
    "dark comedy": ["dark-comedy"],
    "neo-noir": ["neo-noir"],
    "folk horror": ["folk-horror"],
    "survival": ["survival"],
    "on the run": ["on-the-run"],
    "revisionist western": ["revisionist-western"],
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

# human-readable phrase per internal tag, used to build a "why" that names
# what actually matched instead of a single fixed template sentence — this
# is what makes the reason read as specific to that movie, not boilerplate
TAG_PHRASES: dict[str, str] = {
    "slow": "el ritmo pausado",
    "quiet": "lo silencioso",
    "melancholic": "la melancolía",
    "intimate": "lo íntimo",
    "psychological": "lo psicológico",
    "mysterious": "el misterio",
    "dark": "el tono oscuro",
    "action": "la acción",
    "kinetic": "el ritmo acelerado",
    "blockbuster": "la escala de blockbuster",
    "romantic": "el costado romántico",
    "funny": "el humor",
    "light": "el tono liviano",
    "sharp": "lo filoso",
    "loud": "la intensidad",
    "character": "el foco en los personajes",
    "stylized": "lo visualmente estilizado",
    "dialogue-heavy": "los diálogos extensos",
    "walking": "las caminatas largas",
    "thriller": "el thriller",
    "architectural": "la arquitectura",
    "drama": "el drama",
    "indie": "el espíritu indie",
    "restless": "la inquietud",
    "existential": "lo existencial",
    "sad": "la tristeza",
    "prestige": "la calidad prestige",
    "mystery": "el misterio",
    "messy": "el desorden emocional",
    # tags que salen de las keywords de TMDb (tmdb_client.KEYWORD_TAG_MAP), no
    # de géneros ni del escaneo del overview
    "heist": "el golpe planificado",
    "true-story": "el hecho real detrás",
    "time-travel": "los viajes en el tiempo",
    "coming-of-age": "el coming of age",
    "revenge": "la venganza",
    "single-location": "la acción en un solo lugar",
    "road-trip": "el viaje en ruta",
    "hitman": "el asesino a sueldo",
    "dystopian": "el futuro distópico",
    "found-footage": "el found footage",
    "dark-comedy": "el humor negro",
    "neo-noir": "el neo-noir",
    "folk-horror": "el terror de raíz folk",
    "survival": "la supervivencia",
    "on-the-run": "la fuga constante",
    "revisionist-western": "el western revisionista",
}


def _tag_phrases(tags: set[str]) -> str:
    phrases = [TAG_PHRASES.get(tag, tag) for tag in sorted(tags)]
    if len(phrases) == 1:
        return phrases[0]
    return ", ".join(phrases[:-1]) + " y " + phrases[-1]


def _profile_signals(profile: dict | None) -> tuple[set[str], set[str], int | None]:
    # extracts the director/actor names and heaviest decade from a persisted
    # taste profile (backend/app/taste_profile.py), for scoring candidates
    # that tmdb_client.fetch_personalized_candidates already biased toward —
    # None/empty profile (mock catalog, no TMDb, no signal yet) just yields
    # no bonus anywhere, same as before this existed
    if not profile:
        return set(), set(), None
    directors = {d["name"] for d in profile.get("top_directors", [])}
    actors = {a["name"] for a in profile.get("top_actors", [])}
    decades = profile.get("decade_breakdown", [])
    top_decade = max(decades, key=lambda d: d["count"])["decade"] if decades else None
    return directors, actors, top_decade


def _find_reference_title(ratings: list[RatedItem], matched_tags: set[str]) -> str | None:
    # names the specific title from the user's own history that justifies
    # the match, so the "why" reads as tied to their taste, not a template
    loved = sorted((item for item in ratings if item.rating >= 4), key=lambda i: i.rating, reverse=True)
    for item in loved:
        if positive_tags_from_text(item.review) & matched_tags:
            return item.title
    return None


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
    known_tags = set(TAG_PHRASES) | {
        tag for hint_tags in POSITIVE_HINTS.values() for tag in hint_tags
    }

    for item in ratings:
        review = _normalize(item.review)
        positive_tags.update(positive_tags_from_text(item.review))
        positive_tags.update(
            tag for user_tag in item.tags if (tag := _normalize(user_tag)) in known_tags
        )
        for hint, tags in NEGATIVE_HINTS.items():
            if hint in review:
                negative_tags.update(tags)
        if item.rating <= 2:
            negative_tags.update(["loud"])

    return set(positive_tags), set(negative_tags)


def _pick_with_genre_coverage(
    scored: list[tuple[float, Recommendation, set[str], str]],
    required_any_tags: frozenset[str],
    limit: int = 6,
) -> list[Recommendation]:
    # "quiero seleccionar varios géneros, y que el resultado tenga al menos
    # una película de cada uno" — a plain top-N by score can easily starve
    # out a selected genre entirely, so we force one representative per
    # genre first (best-scoring candidate for that genre), then fill the
    # rest by score.
    chosen: list[tuple[float, Recommendation]] = []
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
            score, rec, tags, _source = match
            chosen.append((score, rec))
            chosen_ids.add(id(rec))
            covered.update(tags & required_any_tags)

    for score, rec, _tags, _source in scored:
        if len(chosen) >= limit:
            break
        if id(rec) in chosen_ids:
            continue
        chosen.append((score, rec))
        chosen_ids.add(id(rec))

    chosen.sort(key=lambda pair: pair[0], reverse=True)
    return [rec for _, rec in chosen]


def _pick_with_exploration(
    scored: list[tuple[float, Recommendation, set[str], str]],
    limit: int = 6,
    exploration_slots: int = 1,
) -> list[Recommendation]:
    # reserves a slot for the best-scoring candidate sourced from the
    # unpersonalized "exploration" query (tmdb_client.fetch_personalized_
    # candidates tags these "_source": "exploration") so a fully personalized
    # pool doesn't collapse the picks into a single narrow taste bubble.
    # Candidates without a "_source" (mock catalog, plain fetch_candidates)
    # default to "profile" and are unaffected — same as plain top-N before.
    exploration = [triple for triple in scored if triple[3] == "exploration"]
    reserved = exploration[:exploration_slots]
    reserved_ids = {id(triple[1]) for triple in reserved}

    picks: list[tuple[float, Recommendation]] = [(triple[0], triple[1]) for triple in reserved]
    for score, rec, _tags, _source in scored:
        if len(picks) >= limit:
            break
        if id(rec) in reserved_ids:
            continue
        picks.append((score, rec))

    picks.sort(key=lambda pair: pair[0], reverse=True)
    return [rec for _, rec in picks]


def recommend(
    ratings: list[RatedItem],
    mood: str,
    catalog: list[dict] = CATALOG,
    also_seen: frozenset[str] = frozenset(),
    kind_filter: str = "both",
    required_any_tags: frozenset[str] | None = None,
    preference_ratings: list[RatedItem] | None = None,
    profile: dict | None = None,
    rejected_tags: Counter | None = None,
    exclude_seen: bool = True,
    limit: int = 6,
) -> RecommendResponse:
    taste_ratings = ratings if preference_ratings is None else preference_ratings
    positive_tags, negative_tags = _collect_preference_tags(taste_ratings)
    # exclude_seen=False para /weekly: ese catálogo es un set fijo ("las
    # mismas 5 para todo el mundo") — si se excluyera lo que el usuario ya
    # puntuó/marcó visto, perdería películas de esa semana en silencio
    # (bug reportado por Matías, 2026-07-31). ratings sigue usándose para
    # puntuar (arriba), solo se lo saca de la exclusión.
    seen_titles = (
        ({_normalize(item.title) for item in ratings} if exclude_seen else set())
        | {_normalize(t) for t in also_seen}
    )
    mood_text = _normalize(mood)
    mood_tags = POSITIVE_HINTS.get(mood_text, [mood_text]) if mood_text else []
    profile_directors, profile_actors, top_decade = _profile_signals(profile)
    # only tags the user rejected 2+ times count: a single "no me interesa"
    # shouldn't blacklist a whole genre off the user's own taste profile — the
    # threshold is the guard against overreacting to one-off dismissals.
    effective_rejected = (
        {tag for tag, count in rejected_tags.items() if count >= 2} if rejected_tags else set()
    )

    scored: list[tuple[float, Recommendation, set[str], str]] = []
    for item in catalog:
        if _normalize(item["title"]) in seen_titles:
            continue
        if kind_filter != "both" and item["kind"] != kind_filter:
            continue

        tags = set(item["tags"])
        if required_any_tags and not (tags & required_any_tags):
            continue

        # director/actor/decade signal from the persisted taste profile —
        # tmdb_client.fetch_personalized_candidates already biased the pool
        # toward these, this scores the actual per-candidate match on top so
        # the "why" can name the specific person/decade behind the pick.
        # item.get(...) is safe against candidates without this data (mock
        # catalog, series, exploration slice): no match, no bonus.
        matched_director = item.get("director") if item.get("director") in profile_directors else None
        matched_actors = set(item.get("actors") or []) & profile_actors
        item_decade = (item["year"] // 10) * 10
        matched_decade = top_decade is not None and item_decade == top_decade

        # evidence points, proportional instead of raw counts: matching 3 of
        # 3 tags is a stronger signal than 3 of 8, and a mood that matches
        # completely beats one that grazes a single hint. 0 = no evidence
        # either way; sign carries direction.
        tag_count = max(len(tags), 1)
        points = 0.0
        points += 30 * len(tags & positive_tags) / tag_count
        points -= 25 * len(tags & negative_tags) / tag_count
        points -= 15 * len(tags & effective_rejected) / tag_count
        if mood_tags:
            points += 20 * len(tags & set(mood_tags)) / len(mood_tags)
        if required_any_tags:
            points += 15 * min(len(tags & required_any_tags), 2) / 2
        if item["kind"] == "series":
            points -= 4
        if matched_director:
            points += 25
        points += 10 * min(len(matched_actors), 2)
        if matched_decade:
            points += 8

        # affinity % via tanh instead of the old additive-then-clamp: 50 is
        # "no evidence", extra evidence has diminishing returns, and the
        # asymptotes at 1/99 mean strong picks keep distinct scores instead
        # of a pile of them pinning at the 99 ceiling (which made ties fall
        # back to catalog order). 40 sets the slope: one solid signal lands
        # in the 70s-80s, a near-perfect stack is needed to graze 99.
        match_score = round(50 + 49 * math.tanh(points / 40))

        # no score floor here on purpose — we always want a full set of picks
        # when the catalog has that many unseen candidates, even if some are
        # weak matches; the displayed match_score already tells the user how weak.
        # reasons name the actual matched tags (and, when possible, the
        # specific title from the user's own history behind the match)
        # instead of a single fixed sentence, so two movies with different
        # matches read as genuinely different picks, not the same template.
        reasons = []
        matched_positive = tags & positive_tags
        matched_mood = tags & set(mood_tags)
        matched_genre = tags & required_any_tags if required_any_tags else set()

        if matched_positive:
            reference = _find_reference_title(taste_ratings, matched_positive)
            # cap how many tags get named: a broad taste profile can match
            # most of a movie's tags at once, and citing all of them reads as
            # a generic tag dump instead of a specific reason
            phrase = _tag_phrases(set(sorted(matched_positive)[:3]))
            if reference:
                reasons.append(f"tira para {phrase}, como lo que valoraste en «{reference}»")
            else:
                reasons.append(f"tira para {phrase}, que es lo que venís premiando")
        if matched_mood:
            reasons.append(f"tiene {_tag_phrases(matched_mood)}, la vibra '{mood_text}' que pediste hoy")
        if matched_genre:
            reasons.append(f"cae dentro de {_tag_phrases(matched_genre)}, el género que elegiste")
        if matched_director:
            reasons.append(f"la dirige {matched_director}, uno de tus directores más repetidos")
        if matched_actors:
            reasons.append(f"tiene a {', '.join(sorted(matched_actors))}, que ya te viene gustando")
        if matched_decade:
            reasons.append(f"es de los {top_decade}s, la década que más consumís")
        if not reasons:
            # bug found while adding director/actor scoring: a candidate with
            # genuinely no tags at all (possible for a hand-authored catalog
            # entry, even though tmdb_client._map_result filters those out of
            # the real TMDb pipeline) made _tag_phrases IndexError on an
            # empty set — falls back to a tag-free sentence instead of crashing.
            candidate_tags = set(item["tags"][:3]) or tags
            if candidate_tags:
                own_phrase = _tag_phrases(candidate_tags)
                reasons.append(f"es una apuesta distinta, con aire a {own_phrase}, para ampliar tu mapa")
            else:
                reasons.append("es una apuesta distinta para ampliar tu mapa")

        scored.append(
            (
                points,
                Recommendation(
                    tmdb_id=item.get("tmdb_id"),
                    title=item["title"],
                    year=item["year"],
                    kind=item["kind"],
                    why=capitalize_sentence(", y ".join(reasons) + "."),
                    match_score=match_score,
                    tags=item["tags"],
                    director=item.get("director"),
                    poster_path=item.get("poster_path"),
                    backdrop_path=item.get("backdrop_path"),
                    overview=item.get("overview", ""),
                    vote_average=item.get("vote_average"),
                ),
                tags,
                item.get("_source", "profile"),
            )
        )

    # sort by the raw float points, not the rounded match_score — rounding
    # to a display percentage creates ties that would fall back to catalog
    # order (movies always listed before series), silently starving series
    # out of the top picks even when they scored just as well.
    scored.sort(key=lambda quad: quad[0], reverse=True)

    if required_any_tags:
        picks = _pick_with_genre_coverage(scored, required_any_tags, limit=limit)
    else:
        picks = _pick_with_exploration(scored, limit=limit)

    return RecommendResponse(
        taste_summary=summarize_taste(taste_ratings, mood),
        recommendations=picks,
    )
