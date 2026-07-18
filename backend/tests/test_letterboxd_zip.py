import io
import zipfile

import pytest

from backend.app import letterboxd_zip


def _build_zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buffer.getvalue()


RATINGS_CSV = (
    "Date,Name,Year,Letterboxd URI,Rating\n"
    "2024-09-28,GoodFellas,1990,https://boxd.it/29FA,5\n"
    "2024-09-28,Taxi Driver,1976,https://boxd.it/2b8y,4\n"
)


def test_parse_letterboxd_zip_requires_a_real_zip() -> None:
    with pytest.raises(letterboxd_zip.ZipParseError):
        letterboxd_zip.parse_letterboxd_zip(b"not a zip")


def test_parse_letterboxd_zip_rejects_malformed_csv_field() -> None:
    oversized_field = "a" * 200_000
    data = _build_zip({"ratings.csv": f"Name,Rating\n{oversized_field},4.5\n"})

    with pytest.raises(letterboxd_zip.ZipParseError):
        letterboxd_zip.parse_letterboxd_zip(data)


def test_parse_letterboxd_zip_requires_ratings_or_reviews_file() -> None:
    data = _build_zip({"profile.csv": "Date,Username\n2024-01-01,someone\n"})

    with pytest.raises(letterboxd_zip.ZipParseError):
        letterboxd_zip.parse_letterboxd_zip(data)


def test_parse_letterboxd_zip_prefers_reviews_csv_over_ratings_csv() -> None:
    reviews_csv = (
        "Date,Name,Year,Letterboxd URI,Rating,Review\n"
        "2024-09-28,GoodFellas,1990,https://boxd.it/29FA,5,psychological and dark\n"
    )
    data = _build_zip({"ratings.csv": RATINGS_CSV, "reviews.csv": reviews_csv})

    ratings, _, _ = letterboxd_zip.parse_letterboxd_zip(data)

    assert len(ratings) == 1
    assert ratings[0].review == "psychological and dark"


def test_parse_letterboxd_zip_boosts_rewatches() -> None:
    diary_csv = (
        "Date,Name,Year,Letterboxd URI,Rating,Rewatch,Tags,Watched Date\n"
        "2025-10-24,GoodFellas,1990,https://boxd.it/29FA,4,Yes,,2025-10-23\n"
    )
    data = _build_zip({"ratings.csv": RATINGS_CSV, "diary.csv": diary_csv})

    ratings, _, _ = letterboxd_zip.parse_letterboxd_zip(data)

    goodfellas = next(r for r in ratings if r.title == "GoodFellas")
    assert goodfellas.rating == 5.0  # already 5, clamped, not 5.5


def test_parse_letterboxd_zip_reads_tags_from_diary_and_reviews() -> None:
    reviews_csv = (
        "Date,Name,Year,Letterboxd URI,Rating,Review,Tags\n"
        "2024-09-28,GoodFellas,1990,https://boxd.it/29FA,5,great,action\n"
        "2024-09-28,Taxi Driver,1976,https://boxd.it/2b8y,4,great,\" funny , , dark \"\n"
    )
    diary_csv = (
        "Date,Name,Year,Letterboxd URI,Rating,Rewatch,Tags,Watched Date\n"
        "2024-09-28,GoodFellas,1990,https://boxd.it/29FA,5,No,\" psychological , dark \",2024-09-28\n"
    )

    ratings, _, _ = letterboxd_zip.parse_letterboxd_zip(
        _build_zip({"reviews.csv": reviews_csv, "diary.csv": diary_csv})
    )

    tags_by_title = {item.title: item.tags for item in ratings}
    assert tags_by_title["GoodFellas"] == ["psychological", "dark"]
    assert tags_by_title["Taxi Driver"] == ["funny", "dark"]


def test_parse_letterboxd_zip_defaults_to_empty_tags_without_column() -> None:
    empty_tags_reviews = (
        "Date,Name,Year,Letterboxd URI,Rating,Review,Tags\n"
        "2024-09-28,GoodFellas,1990,https://boxd.it/29FA,5,great,\n"
    )
    ratings, _, _ = letterboxd_zip.parse_letterboxd_zip(_build_zip({"ratings.csv": RATINGS_CSV}))
    reviews, _, _ = letterboxd_zip.parse_letterboxd_zip(
        _build_zip({"reviews.csv": empty_tags_reviews})
    )

    assert all(item.tags == [] for item in ratings)
    assert reviews[0].tags == []


def test_parse_letterboxd_zip_adds_liked_titles_not_already_rated() -> None:
    likes_csv = (
        "Date,Name,Year,Letterboxd URI\n"
        "2024-09-28,Whiplash,2014,https://boxd.it/7bQA\n"
        "2024-09-28,GoodFellas,1990,https://boxd.it/29FA\n"  # already rated, should not duplicate/override
    )
    data = _build_zip({"ratings.csv": RATINGS_CSV, "likes/films.csv": likes_csv})

    ratings, _, _ = letterboxd_zip.parse_letterboxd_zip(data)

    titles = {r.title: r.rating for r in ratings}
    assert titles["Whiplash"] == 4.5
    assert titles["GoodFellas"] == 5.0  # untouched by the like


def test_parse_letterboxd_zip_resolves_favorite_films_via_watched_csv() -> None:
    watched_csv = (
        "Date,Name,Year,Letterboxd URI\n"
        "2024-09-28,12 Angry Men,1957,https://boxd.it/2auI\n"
    )
    profile_csv = "Date Joined,Username,Favorite Films\n2024-09-28,someone,https://boxd.it/2auI\n"
    data = _build_zip(
        {"ratings.csv": RATINGS_CSV, "watched.csv": watched_csv, "profile.csv": profile_csv}
    )

    ratings, _, _ = letterboxd_zip.parse_letterboxd_zip(data)

    favorite = next(r for r in ratings if r.title == "12 Angry Men")
    assert favorite.rating == 5.0


def test_parse_letterboxd_zip_returns_watched_titles_as_extra_seen() -> None:
    watched_csv = (
        "Date,Name,Year,Letterboxd URI\n"
        "2024-09-28,GoodFellas,1990,https://boxd.it/29FA\n"
        "2024-09-28,Unrated Movie,2020,https://boxd.it/xyz1\n"
    )
    data = _build_zip({"ratings.csv": RATINGS_CSV, "watched.csv": watched_csv})

    _, extra_seen, _ = letterboxd_zip.parse_letterboxd_zip(data)

    assert "unrated movie" in extra_seen


def test_parse_letterboxd_zip_reports_discarded_rows_from_base_csv() -> None:
    ratings_with_gaps = (
        "Date,Name,Year,Letterboxd URI,Rating\n"
        "2024-09-28,GoodFellas,1990,https://boxd.it/29FA,5\n"
        "2024-09-28,,1976,https://boxd.it/2b8y,4\n"  # no title
        "2024-09-28,No Rating,1999,https://boxd.it/xyz1,\n"  # no rating
    )
    data = _build_zip({"ratings.csv": ratings_with_gaps})

    ratings, _, discarded = letterboxd_zip.parse_letterboxd_zip(data)

    assert len(ratings) == 1
    assert discarded == 2
