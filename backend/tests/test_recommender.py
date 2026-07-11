from backend.app.models import RatedItem
from backend.app.recommender import recommend


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
