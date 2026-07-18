from backend.app.csv_ingest import parse_ratings_csv


def test_parse_ratings_csv_supports_decimal_and_star_formats() -> None:
    content = """Name,Rating,Review
Perfect Blue,4.5,psychological and dark
Before Sunrise,★★★★½,"romantic, warm"
No Rating,,
"""

    ratings, discarded = parse_ratings_csv(content)

    assert [item.title for item in ratings] == ["Perfect Blue", "Before Sunrise"]
    assert [item.rating for item in ratings] == [4.5, 4.5]
    assert ratings[1].review == "romantic, warm"
    assert discarded == 1  # "No Rating" row


def test_parse_ratings_csv_skips_out_of_range_ratings_instead_of_crashing() -> None:
    content = """Name,Rating,Review
Too High,8,broken export
Too Low,-1,broken export
Perfect Blue,4.5,psychological and dark
"""

    ratings, discarded = parse_ratings_csv(content)

    assert [item.title for item in ratings] == ["Perfect Blue"]
    assert discarded == 2


def test_parse_ratings_csv_handles_bom_and_padded_headers() -> None:
    content = "﻿ Name , Rating ,Review\nPerfect Blue,4.5,psychological and dark\n"

    ratings, discarded = parse_ratings_csv(content)

    assert [item.title for item in ratings] == ["Perfect Blue"]
    assert discarded == 0
