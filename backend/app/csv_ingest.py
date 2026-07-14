import csv
import io

from .models import RatedItem

TITLE_FIELDS = ("Name", "Title", "Film")
RATING_FIELDS = ("Rating", "Watched Rating", "Letterboxd Rating")
REVIEW_FIELDS = ("Review", "Review Text", "Comments")
DATE_FIELDS = ("Watched Date", "Date")


def _pick(row: dict[str, str], names: tuple[str, ...]) -> str:
    for name in names:
        value = row.get(name, "")
        if value:
            return value.strip()
    return ""


def _parse_rating(value: str) -> float | None:
    raw = value.strip()
    if not raw:
        return None

    try:
        parsed = float(raw)
    except ValueError:
        stars = raw.count("★")
        if not stars and "½" not in raw:
            return None
        parsed = min(5.0, stars + (0.5 if "½" in raw else 0.0))

    if not 0 <= parsed <= 5:
        return None
    return parsed


def parse_ratings_csv(content: str) -> list[RatedItem]:
    stream = io.StringIO(content.lstrip("﻿").strip())
    reader = csv.DictReader(stream)
    if reader.fieldnames:
        reader.fieldnames = [name.strip() if name else name for name in reader.fieldnames]
    ratings: list[RatedItem] = []

    for row in reader:
        title = _pick(row, TITLE_FIELDS)
        rating = _parse_rating(_pick(row, RATING_FIELDS))
        if not title or rating is None:
            continue

        ratings.append(
            RatedItem(
                title=title,
                rating=rating,
                review=_pick(row, REVIEW_FIELDS),
                watched_date=_pick(row, DATE_FIELDS),
            )
        )

    return ratings
