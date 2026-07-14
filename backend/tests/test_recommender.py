from backend.app.models import RatedItem
from backend.app.recommender import GENRE_OPTIONS, capitalize_sentence, recommend


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

    response = recommend(ratings=[], mood="", catalog=custom_catalog)

    by_title = {item.title: item.tmdb_id for item in response.recommendations}
    assert by_title["Has Tmdb Id"] == 999
    assert by_title["Mock Only"] is None


def test_recommend_breaks_match_score_ties_by_raw_score_not_catalog_order() -> None:
    # both items clamp to the same displayed match_score (99), but the
    # series scores higher before clamping — it should rank first even
    # though it's listed second in the catalog and gets the series penalty.
    catalog = [
        {
            "title": "Capped Movie",
            "year": 2000,
            "kind": "movie",
            "tags": ["psychological", "dark", "mysterious"],
        },
        {
            "title": "Higher Raw Series",
            "year": 2020,
            "kind": "series",
            "tags": ["psychological", "dark", "mysterious", "character", "intimate", "funny"],
        },
    ]

    response = recommend(
        ratings=[RatedItem(title="Old Movie", rating=5, review="psychological")],
        mood="psychological",
        catalog=catalog,
    )

    assert [item.title for item in response.recommendations] == [
        "Higher Raw Series",
        "Capped Movie",
    ]
    assert response.recommendations[0].match_score == 99
    assert response.recommendations[1].match_score == 99


def test_recommend_backfills_weak_matches_instead_of_returning_too_few() -> None:
    # none of these share a single tag with the user's taste or mood, so
    # under the old "score < 40: continue" cutoff every one of them would
    # get dropped and the response would come back empty
    catalog = [
        {"title": f"Unrelated Movie {i}", "year": 2000 + i, "kind": "movie", "tags": ["quiet"]}
        for i in range(3)
    ]

    response = recommend(
        ratings=[RatedItem(title="Old Movie", rating=5, review="action packed")],
        mood="romance",
        catalog=catalog,
    )

    assert len(response.recommendations) == 3


def test_recommend_capitalizes_why() -> None:
    catalog = [{"title": "Some Movie", "year": 2020, "kind": "movie", "tags": ["dark"]}]

    response = recommend(ratings=[], mood="", catalog=catalog)

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

    response = recommend(ratings=[], mood="", catalog=catalog, kind_filter="series")

    assert [item.title for item in response.recommendations] == ["A Series"]


def test_recommend_required_any_tags_filters_by_or_logic() -> None:
    catalog = [
        {"title": "Only Action", "year": 2020, "kind": "movie", "tags": ["action"]},
        {"title": "Only Romance", "year": 2020, "kind": "movie", "tags": ["romantic"]},
        {"title": "Neither", "year": 2020, "kind": "movie", "tags": ["quiet"]},
    ]
    required = frozenset(GENRE_OPTIONS["action"]) | frozenset(GENRE_OPTIONS["romance"])

    response = recommend(ratings=[], mood="", catalog=catalog, required_any_tags=required)

    titles = {item.title for item in response.recommendations}
    assert titles == {"Only Action", "Only Romance"}


def test_recommend_required_any_tags_guarantees_genre_coverage() -> None:
    # 5 strong action matches would normally fill every slot and starve the
    # romance genre out entirely — coverage should force at least one in.
    catalog = [
        {"title": f"Action {i}", "year": 2020, "kind": "movie", "tags": ["action", "kinetic"]}
        for i in range(5)
    ] + [{"title": "The Only Romance", "year": 2020, "kind": "movie", "tags": ["romantic"]}]
    required = frozenset(GENRE_OPTIONS["action"]) | frozenset(GENRE_OPTIONS["romance"])

    response = recommend(ratings=[], mood="", catalog=catalog, required_any_tags=required)

    titles = {item.title for item in response.recommendations}
    assert "The Only Romance" in titles
    assert len(response.recommendations) == 5


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
