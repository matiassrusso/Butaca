from collections import Counter

from backend.app.models import RatedItem
from backend.app.recommender import (
    GENRE_OPTIONS,
    MIN_MATCH_SCORE,
    PICK_OPTIONS,
    TAG_PHRASES,
    _find_reference_title,
    capitalize_sentence,
    recommend,
)


def test_find_reference_title_picks_the_first_loved_title_without_win_counts() -> None:
    # sin señal del juego pairwise, el desempate entre dos "amados" con el
    # mismo rating es el orden de inserción (comportamiento previo, sin
    # cambios) -- ver el siguiente test para el desempate real.
    ratings = [
        RatedItem(title="Movie A", rating=5.0, review="psychological"),
        RatedItem(title="Movie B", rating=5.0, review="psychological"),
    ]
    assert _find_reference_title(ratings, {"psychological"}) == "Movie A"


def test_find_reference_title_breaks_ties_with_pairwise_win_counts() -> None:
    # pedido de Matías (2026-08-03): el juego "¿cuál te gustó más?" solo
    # tiene sentido si de verdad afina cuál de dos "amados" empatados se cita
    # en el why -- acá "Movie B" ganó su ronda pairwise, así que gana el
    # desempate pese a insertarse después.
    ratings = [
        RatedItem(title="Movie A", rating=5.0, review="psychological"),
        RatedItem(title="Movie B", rating=5.0, review="psychological"),
    ]
    win_counts = {"movie b": 1}
    assert _find_reference_title(ratings, {"psychological"}, win_counts) == "Movie B"


def test_recommend_filters_seen_titles_and_prefers_matching_mood() -> None:
    response = recommend(
        ratings=[
            RatedItem(title="Whiplash", rating=4.5, review="psychological and intense"),
            RatedItem(title="Mad Max: Fury Road", rating=1.5, review="too loud"),
        ],
        mood="psychological",
    )

    assert all(item.title != "Mad Max: Fury Road" for item in response.recommendations)
    assert response.recommendations
    assert response.recommendations[0].title in {"Perfect Blue", "Burning"}


def test_recommend_excludes_titles_from_also_seen() -> None:
    custom_catalog = [
        {"title": "Custom Movie", "year": 2021, "kind": "movie", "tags": ["psychological", "dark"]},
    ]

    response = recommend(
        ratings=[],
        mood="",
        catalog=custom_catalog,
        also_seen=frozenset({"Custom Movie"}),
    )

    assert response.recommendations == []


def test_recommend_exclude_seen_false_keeps_already_rated_titles() -> None:
    # /weekly necesita esto: su catálogo es un set fijo ("las mismas 5 para
    # todo el mundo"), así que si el usuario ya puntuó/marcó vista alguna de
    # esas 5, no puede desaparecer en silencio (bug reportado por Matías,
    # 2026-07-31).
    custom_catalog = [
        {"title": "Custom Movie", "year": 2021, "kind": "movie", "tags": ["psychological", "dark"]},
    ]

    response = recommend(
        ratings=[RatedItem(title="Custom Movie", rating=5, review="psychological")],
        mood="",
        catalog=custom_catalog,
        exclude_seen=False,
    )

    assert [item.title for item in response.recommendations] == ["Custom Movie"]


def test_recommend_uses_custom_catalog_when_provided() -> None:
    custom_catalog = [
        {"title": "Custom Movie", "year": 2021, "kind": "movie", "tags": ["psychological", "dark"]},
    ]

    response = recommend(
        ratings=[RatedItem(title="Whiplash", rating=4.5, review="psychological and intense")],
        mood="",
        catalog=custom_catalog,
    )

    assert [item.title for item in response.recommendations] == ["Custom Movie"]


def test_recommend_carries_tmdb_id_when_present_and_none_otherwise() -> None:
    custom_catalog = [
        {
            "title": "Has Tmdb Id",
            "year": 2021,
            "kind": "movie",
            "tags": ["psychological", "dark"],
            "tmdb_id": 999,
        },
        {"title": "Mock Only", "year": 2020, "kind": "movie", "tags": ["psychological", "dark"]},
    ]

    response = recommend(ratings=[], mood="", catalog=custom_catalog, min_score=0)

    by_title = {item.title: item.tmdb_id for item in response.recommendations}
    assert by_title["Has Tmdb Id"] == 999
    assert by_title["Mock Only"] is None


def test_recommend_ranks_by_score_not_catalog_order() -> None:
    # the movie is listed first in the catalog, but the series matches the
    # taste tags fully plus the whole mood — it must rank first despite the
    # small series penalty and its catalog position
    catalog = [
        {"title": "Listed First Movie", "year": 2000, "kind": "movie", "tags": ["psychological"]},
        {
            "title": "Higher Scoring Series",
            "year": 2020,
            "kind": "series",
            "tags": ["psychological", "dark", "mysterious"],
        },
    ]

    response = recommend(
        ratings=[RatedItem(title="Old Movie", rating=5, review="psychological")],
        mood="psychological",
        catalog=catalog,
    )

    assert [item.title for item in response.recommendations] == [
        "Higher Scoring Series",
        "Listed First Movie",
    ]


def test_recommend_discards_matches_below_min_score_instead_of_backfilling() -> None:
    # invariante de Matías (TASKS.md, 2026-08-02): un match débil no es una
    # recomendación real, ni siquiera para completar el cupo — antes se
    # rellenaba con lo que sea para nunca devolver menos de N.
    catalog = [
        {"title": f"Unrelated Movie {i}", "year": 2000 + i, "kind": "movie", "tags": ["quiet"]}
        for i in range(3)
    ]

    response = recommend(
        ratings=[RatedItem(title="Old Movie", rating=5, review="action packed")],
        mood="romance",
        catalog=catalog,
    )

    assert response.recommendations == []


def test_recommend_keeps_matches_at_or_above_min_score() -> None:
    catalog = [{"title": "Strong Match", "year": 2020, "kind": "movie", "tags": ["action"]}]

    response = recommend(
        ratings=[RatedItem(title="Old Movie", rating=5, review="action packed")],
        mood="",
        catalog=catalog,
    )

    assert [item.title for item in response.recommendations] == ["Strong Match"]
    assert response.recommendations[0].match_score >= MIN_MATCH_SCORE


def test_recommend_capitalizes_why() -> None:
    catalog = [{"title": "Some Movie", "year": 2020, "kind": "movie", "tags": ["dark"]}]

    response = recommend(ratings=[], mood="", catalog=catalog, min_score=0)

    assert response.recommendations[0].why[0].isupper()


def test_capitalize_sentence() -> None:
    assert capitalize_sentence("hola mundo.") == "Hola mundo."
    assert capitalize_sentence("") == ""
    assert capitalize_sentence("Ya con mayúscula.") == "Ya con mayúscula."


def test_recommend_kind_filter_excludes_other_kind() -> None:
    catalog = [
        {"title": "A Movie", "year": 2020, "kind": "movie", "tags": ["dark"]},
        {"title": "A Series", "year": 2020, "kind": "series", "tags": ["dark"]},
    ]

    response = recommend(ratings=[], mood="", catalog=catalog, kind_filter="series", min_score=0)

    assert [item.title for item in response.recommendations] == ["A Series"]


def test_recommend_required_any_groups_filters_by_or_logic() -> None:
    catalog = [
        {"title": "Only Action", "year": 2020, "kind": "movie", "tags": ["action"]},
        {"title": "Only Romance", "year": 2020, "kind": "movie", "tags": ["romantic"]},
        {"title": "Neither", "year": 2020, "kind": "movie", "tags": ["quiet"]},
    ]
    groups = (frozenset(GENRE_OPTIONS["action"]), frozenset(GENRE_OPTIONS["romance"]))

    response = recommend(ratings=[], mood="", catalog=catalog, required_any_groups=groups, min_score=0)

    titles = {item.title for item in response.recommendations}
    assert titles == {"Only Action", "Only Romance"}


def test_recommend_required_any_groups_guarantees_coverage_per_option() -> None:
    # 5 strong action matches would normally fill every slot and starve the
    # romance option out entirely — coverage should force at least one in.
    catalog = [
        {"title": f"Action {i}", "year": 2020, "kind": "movie", "tags": ["action", "kinetic"]}
        for i in range(5)
    ] + [{"title": "The Only Romance", "year": 2020, "kind": "movie", "tags": ["romantic"]}]
    groups = (frozenset(GENRE_OPTIONS["action"]), frozenset(GENRE_OPTIONS["romance"]))

    response = recommend(ratings=[], mood="", catalog=catalog, required_any_groups=groups, min_score=0)

    titles = {item.title for item in response.recommendations}
    assert "The Only Romance" in titles
    assert len(response.recommendations) == 6


def test_recommend_single_option_match_clears_min_score() -> None:
    # bug reportado 2026-08-02: con el bonus viejo (15 * tags matcheados),
    # una sola opción de un tag daba match_score=59, un punto abajo del
    # piso — se descartaba siempre. Ahora se cuenta por opción matcheada.
    catalog = [{"title": "Only Horror", "year": 2020, "kind": "movie", "tags": ["dark"]}]
    groups = (frozenset(GENRE_OPTIONS["horror"]),)

    response = recommend(ratings=[], mood="", catalog=catalog, required_any_groups=groups)

    assert [item.title for item in response.recommendations] == ["Only Horror"]
    assert response.recommendations[0].match_score >= MIN_MATCH_SCORE


def test_pick_coverage_is_per_option_in_selection_order() -> None:
    # 4 opciones elegidas, 3 candidatos fuertes cada una: debe salir un pick
    # de cada opción, no que 2 opciones se coman los 6 lugares.
    groups = tuple(frozenset({f"tag{i}"}) for i in range(4))
    catalog = [
        {"title": f"Opt{i}-{j}", "year": 2020, "kind": "movie", "tags": [f"tag{i}"]}
        for i in range(4)
        for j in range(3)
    ]

    response = recommend(ratings=[], mood="", catalog=catalog, required_any_groups=groups, min_score=0)

    titles = {item.title for item in response.recommendations}
    for i in range(4):
        assert any(title.startswith(f"Opt{i}-") for title in titles), f"opción {i} sin representante"


def test_recommend_why_cites_specific_matched_tags_not_a_fixed_template() -> None:
    # two movies matching different tags should read as genuinely different
    # picks, not the same boilerplate sentence
    catalog = [
        {"title": "Dark One", "year": 2020, "kind": "movie", "tags": ["dark", "psychological"]},
        {"title": "Funny One", "year": 2020, "kind": "movie", "tags": ["funny", "light"]},
    ]
    ratings = [
        RatedItem(title="Old Dark Movie", rating=5, review="dark and psychological"),
        RatedItem(title="Old Funny Movie", rating=5, review="funny and light"),
    ]

    response = recommend(ratings=ratings, mood="", catalog=catalog)

    why_by_title = {item.title: item.why for item in response.recommendations}
    assert why_by_title["Dark One"] != why_by_title["Funny One"]
    assert "oscuro" in why_by_title["Dark One"] or "psicológico" in why_by_title["Dark One"]
    assert "humor" in why_by_title["Funny One"]


def test_recommend_why_cites_source_title_from_users_history() -> None:
    catalog = [{"title": "Dark Pick", "year": 2020, "kind": "movie", "tags": ["dark"]}]
    ratings = [RatedItem(title="Perfect Blue", rating=5, review="psychological and dark")]

    response = recommend(ratings=ratings, mood="", catalog=catalog)

    assert "Perfect Blue" in response.recommendations[0].why


def test_recommend_why_mentions_mood_word_when_mood_matches() -> None:
    catalog = [{"title": "Romance Pick", "year": 2020, "kind": "movie", "tags": ["romantic"]}]

    response = recommend(ratings=[], mood="romance", catalog=catalog)

    assert "romance" in response.recommendations[0].why


def test_recommend_why_fallback_varies_by_movies_own_tags() -> None:
    catalog = [
        {"title": "Unrelated A", "year": 2020, "kind": "movie", "tags": ["quiet"]},
        {"title": "Unrelated B", "year": 2020, "kind": "movie", "tags": ["stylized"]},
    ]

    response = recommend(ratings=[], mood="", catalog=catalog, min_score=0)

    why_by_title = {item.title: item.why for item in response.recommendations}
    assert why_by_title["Unrelated A"] != why_by_title["Unrelated B"]


def test_recommend_preference_ratings_overrides_taste_signal() -> None:
    catalog = [{"title": "Action Movie", "year": 2020, "kind": "movie", "tags": ["action"]}]
    all_ratings = [RatedItem(title="Old Movie", rating=1, review="boring and quiet")]
    recent_ratings = [RatedItem(title="Recent Movie", rating=5, review="action packed")]

    response = recommend(
        ratings=all_ratings,
        mood="",
        catalog=catalog,
        preference_ratings=recent_ratings,
    )

    assert response.recommendations[0].match_score > 50


def test_recommend_uses_matching_user_tags_as_positive_signal() -> None:
    response = recommend(
        ratings=[RatedItem(title="Tagged Movie", rating=3, tags=[" DARK "])],
        mood="",
        catalog=[{"title": "Dark Pick", "year": 2020, "kind": "movie", "tags": ["dark"]}],
    )

    assert response.recommendations[0].match_score > 50


def test_recommend_uses_keyword_tag_from_review_as_positive_signal() -> None:
    # cierra el loop de los tags que vienen de las keywords de TMDb: sin la
    # entrada en POSITIVE_HINTS el tag se mostraría en la UI pero nunca podría
    # ganar score desde la reseña del usuario.
    response = recommend(
        ratings=[RatedItem(title="Ocean's Eleven", rating=5, review="great heist movie")],
        mood="",
        catalog=[{"title": "Heist Pick", "year": 2020, "kind": "movie", "tags": ["heist"]}],
    )

    assert response.recommendations[0].match_score > 50


def test_recommend_why_names_keyword_tag_in_spanish() -> None:
    # el "why" no puede filtrar el tag crudo en inglés a una frase en español
    response = recommend(
        ratings=[RatedItem(title="Oldboy", rating=5, review="brutal revenge story")],
        mood="",
        catalog=[{"title": "Revenge Pick", "year": 2020, "kind": "movie", "tags": ["revenge"]}],
    )

    assert "la venganza" in response.recommendations[0].why


def test_every_keyword_tag_has_a_spanish_phrase() -> None:
    # guard estructural: evita para siempre el "sumé una entrada al map y me
    # olvidé la frase", que no falla pero mete inglés crudo en prosa española.
    from backend.app.tmdb_client import KEYWORD_TAG_MAP

    for tags in KEYWORD_TAG_MAP.values():
        for tag in tags:
            assert tag in TAG_PHRASES, f"falta la frase en español para el tag {tag!r}"


def test_pick_options_have_phrases_and_unique_keys() -> None:
    # mismo guard que arriba, pero para el picker "a tu elección" — evita
    # sumar una opción nueva a PICK_OPTIONS y olvidarse la frase en español,
    # y una key duplicada que pisaría silenciosamente a la anterior en la
    # vista derivada GENRE_OPTIONS.
    keys = [option["key"] for option in PICK_OPTIONS]
    assert len(keys) == len(set(keys)), "hay keys duplicadas en PICK_OPTIONS"

    for option in PICK_OPTIONS:
        for tag in option["tags"]:
            assert tag in TAG_PHRASES, f"falta la frase en español para el tag {tag!r} ({option['key']})"


def test_recommend_ignores_user_tags_outside_internal_vocabulary() -> None:
    response = recommend(
        ratings=[RatedItem(title="Tagged Movie", rating=3, tags=["personal favorite"])],
        mood="",
        catalog=[{"title": "Dark Pick", "year": 2020, "kind": "movie", "tags": ["dark"]}],
        min_score=0,
    )

    assert response.recommendations[0].match_score == 50


def test_recommend_scores_and_names_director_match_from_profile() -> None:
    catalog = [
        {
            "title": "By Fave Director",
            "year": 2020,
            "kind": "movie",
            "tags": [],
            "director": "Fave Director",
            "actors": [],
        },
        {"title": "Unrelated", "year": 2020, "kind": "movie", "tags": []},
    ]
    profile = {"top_directors": [{"name": "Fave Director", "count": 3}], "top_actors": [], "decade_breakdown": []}

    response = recommend(ratings=[], mood="", catalog=catalog, profile=profile, min_score=0)

    by_title = {item.title: item for item in response.recommendations}
    assert by_title["By Fave Director"].match_score > by_title["Unrelated"].match_score
    assert "Fave Director" in by_title["By Fave Director"].why


def test_recommend_scores_and_names_actor_match_from_profile() -> None:
    catalog = [
        {"title": "With Fave Actor", "year": 2020, "kind": "movie", "tags": [], "actors": ["Fave Actor"]},
        {"title": "Unrelated", "year": 2020, "kind": "movie", "tags": []},
    ]
    profile = {"top_directors": [], "top_actors": [{"name": "Fave Actor", "count": 2}], "decade_breakdown": []}

    response = recommend(ratings=[], mood="", catalog=catalog, profile=profile, min_score=0)

    by_title = {item.title: item for item in response.recommendations}
    assert by_title["With Fave Actor"].match_score > by_title["Unrelated"].match_score
    assert "Fave Actor" in by_title["With Fave Actor"].why


def test_recommend_scores_and_names_decade_match_from_profile() -> None:
    catalog = [
        {"title": "Right Decade", "year": 2015, "kind": "movie", "tags": []},
        {"title": "Wrong Decade", "year": 1985, "kind": "movie", "tags": []},
    ]
    profile = {"top_directors": [], "top_actors": [], "decade_breakdown": [{"decade": 2010, "count": 5}]}

    response = recommend(ratings=[], mood="", catalog=catalog, profile=profile, min_score=0)

    by_title = {item.title: item for item in response.recommendations}
    assert by_title["Right Decade"].match_score > by_title["Wrong Decade"].match_score
    assert "2010s" in by_title["Right Decade"].why


def test_recommend_strong_matches_keep_distinct_scores_instead_of_pinning_at_99() -> None:
    # under the old additive+clamp scoring both of these hit the 99 ceiling
    # and became indistinguishable; tanh keeps them ordered and below 99
    profile = {
        "top_directors": [{"name": "Fave Director", "count": 3}],
        "top_actors": [],
        "decade_breakdown": [],
    }
    catalog = [
        {"title": "Strong", "year": 2020, "kind": "movie", "tags": ["action", "kinetic", "blockbuster"]},
        {
            "title": "Stronger",
            "year": 2020,
            "kind": "movie",
            "tags": ["action", "kinetic", "blockbuster"],
            "director": "Fave Director",
            "actors": [],
        },
    ]
    ratings = [RatedItem(title="Old", rating=5, review="action packed")]

    response = recommend(ratings=ratings, mood="action", catalog=catalog, profile=profile)

    by_title = {item.title: item for item in response.recommendations}
    assert by_title["Stronger"].match_score > by_title["Strong"].match_score
    assert by_title["Stronger"].match_score < 99


def test_recommend_proportional_tag_match_rewards_focused_candidates() -> None:
    # same number of matched tags, but the focused candidate matches all of
    # its tags while the diluted one matches 2 of 6 — focus should win
    catalog = [
        {"title": "Focused", "year": 2020, "kind": "movie", "tags": ["dark", "psychological"]},
        {
            "title": "Diluted",
            "year": 2020,
            "kind": "movie",
            "tags": ["dark", "psychological", "funny", "light", "romantic", "stylized"],
        },
    ]
    ratings = [RatedItem(title="Old", rating=5, review="dark and psychological")]

    response = recommend(ratings=ratings, mood="", catalog=catalog)

    by_title = {item.title: item for item in response.recommendations}
    assert by_title["Focused"].match_score > by_title["Diluted"].match_score


def test_recommend_without_profile_ignores_director_actor_decade_fields() -> None:
    catalog = [
        {"title": "Some Movie", "year": 2020, "kind": "movie", "tags": [], "director": "Anyone", "actors": ["X"]}
    ]

    response = recommend(ratings=[], mood="", catalog=catalog, min_score=0)

    assert response.recommendations[0].match_score == 50


def test_recommend_reserves_one_exploration_slot_even_when_outscored_by_profile_picks() -> None:
    catalog = [
        {"title": f"Profile {i}", "year": 2020, "kind": "movie", "tags": ["action"], "_source": "profile"}
        for i in range(5)
    ] + [{"title": "Exploration Pick", "year": 2020, "kind": "movie", "tags": [], "_source": "exploration"}]
    ratings = [RatedItem(title="Old", rating=5, review="action packed")]

    response = recommend(ratings=ratings, mood="", catalog=catalog, min_score=0)

    titles = {item.title for item in response.recommendations}
    assert "Exploration Pick" in titles
    assert len(response.recommendations) == 6


def test_recommend_penalizes_tags_rejected_twice() -> None:
    catalog = [
        {"title": "Dark Pick", "year": 2020, "kind": "movie", "tags": ["dark"]},
        {"title": "Light Pick", "year": 2020, "kind": "movie", "tags": ["light"]},
    ]

    response = recommend(ratings=[], mood="", catalog=catalog, rejected_tags=Counter({"dark": 2}), min_score=0)

    by_title = {item.title: item for item in response.recommendations}
    assert by_title["Light Pick"].match_score > by_title["Dark Pick"].match_score


def test_recommend_ignores_tag_rejected_only_once() -> None:
    # a single "no me interesa" shouldn't blacklist a whole tag — needs 2+
    catalog = [
        {"title": "Dark Pick", "year": 2020, "kind": "movie", "tags": ["dark"]},
        {"title": "Light Pick", "year": 2020, "kind": "movie", "tags": ["light"]},
    ]

    response = recommend(ratings=[], mood="", catalog=catalog, rejected_tags=Counter({"dark": 1}), min_score=0)

    by_title = {item.title: item for item in response.recommendations}
    assert by_title["Dark Pick"].match_score == by_title["Light Pick"].match_score == 50


def test_recommend_untagged_catalog_items_default_to_profile_source() -> None:
    # items without an explicit "_source" (mock catalog, plain fetch_candidates)
    # must not accidentally get treated as reserved "exploration" slots
    catalog = [
        {"title": f"Movie {i}", "year": 2020, "kind": "movie", "tags": ["action"]} for i in range(5)
    ]
    ratings = [RatedItem(title="Old", rating=5, review="action packed")]

    response = recommend(ratings=ratings, mood="", catalog=catalog)

    assert len(response.recommendations) == 5


def test_series_only_pool_is_not_penalised_below_the_match_floor() -> None:
    # la penalización de series existe para que no desplacen películas; en un
    # pool sin películas se aplica a todas por igual, así que no ordena nada y
    # solo empuja la tanda entera abajo de MIN_MATCH_SCORE. Medido con datos
    # reales el 2026-08-02: un movimiento 100% series daba 57 en los seis
    # candidatos y devolvía cero picks, con perfil afín y no afín por igual.
    catalog = [
        {"title": f"Serie {i}", "year": 2020, "kind": "series", "tags": ["light", "stylized", "vibe-l2:44"]}
        for i in range(6)
    ]

    response = recommend(
        ratings=[],
        mood="",
        catalog=catalog,
        required_any_groups=(frozenset({"vibe-l2:44"}),),
    )

    assert len(response.recommendations) == 6
    assert all(item.match_score >= MIN_MATCH_SCORE for item in response.recommendations)


def test_series_still_lose_the_tiebreak_against_movies_in_a_mixed_pool() -> None:
    # el fix de arriba no puede desactivar la penalización donde sí importa
    catalog = [
        {"title": "Serie", "year": 2020, "kind": "series", "tags": ["dark"]},
        {"title": "Peli", "year": 2020, "kind": "movie", "tags": ["dark"]},
    ]
    ratings = [RatedItem(title="Vieja", rating=5, review="dark and moody")]

    response = recommend(ratings=ratings, mood="", catalog=catalog, min_score=0)

    by_title = {item.title: item.match_score for item in response.recommendations}
    assert by_title["Peli"] > by_title["Serie"]
