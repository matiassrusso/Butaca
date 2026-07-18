import csv
import io
import zipfile

from .csv_ingest import parse_ratings_csv
from .models import RatedItem

# Letterboxd's own export column names are fixed, unlike a hand-pasted CSV,
# so we read these files directly instead of guessing column variants.
RATINGS_FILES = ("reviews.csv", "ratings.csv")  # reviews.csv has review text, prefer it
LIKES_FILE = "likes/films.csv"
DIARY_FILE = "diary.csv"
WATCHED_FILE = "watched.csv"
PROFILE_FILE = "profile.csv"

LIKE_RATING = 4.5  # synthetic rating for liked-but-unrated titles
FAVORITE_RATING = 5.0  # synthetic rating for explicit "Favorite Films"
REWATCH_BONUS = 0.5


class ZipParseError(Exception):
    pass


def _normalize(title: str) -> str:
    return title.strip().lower()


def _read_csv(zf: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    if name not in zf.namelist():
        return []
    content = zf.read(name).decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(content)))


def _parse_tags(row: dict[str, str]) -> list[str]:
    return [tag.strip() for tag in row.get("Tags", "").split(",") if tag.strip()]


def parse_letterboxd_zip(data: bytes) -> tuple[list[RatedItem], set[str], int]:
    """Returns (ratings, extra_seen, discarded_rows) — discarded_rows counts
    rows from the base ratings/reviews CSV that had no usable title+rating,
    so the caller can tell the user their import wasn't 100% complete."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ZipParseError("Ese archivo no es un .zip válido.") from exc

    base_rows = None
    for name in RATINGS_FILES:
        if name in zf.namelist():
            base_rows = zf.read(name).decode("utf-8-sig")
            break
    if base_rows is None:
        raise ZipParseError(
            "No encontré ratings.csv ni reviews.csv en el zip — ¿es un export de Letterboxd?"
        )

    try:
        parsed_ratings, discarded_count = parse_ratings_csv(base_rows)
        ratings_by_title: dict[str, RatedItem] = {
            _normalize(item.title): item for item in parsed_ratings
        }

        for row in _read_csv(zf, "reviews.csv"):
            existing = ratings_by_title.get(_normalize(row.get("Name", "")))
            if existing:
                existing.tags = _parse_tags(row)

        diary_rows = _read_csv(zf, DIARY_FILE)
        for row in diary_rows:
            key = _normalize(row.get("Name", ""))
            existing = ratings_by_title.get(key)
            if existing is None:
                continue
            if row.get("Rewatch") == "Yes":
                existing.rating = min(5.0, existing.rating + REWATCH_BONUS)
            # diary.csv's "Watched Date" is the actual date the user saw the
            # film, more accurate than ratings.csv's "Date" (date rated)
            watched_date = row.get("Watched Date", "").strip()
            if watched_date:
                existing.watched_date = watched_date
            diary_tags = _parse_tags(row)
            if diary_tags:
                # Diary is the per-watch record, so its tags override review-level tags.
                existing.tags = diary_tags

        likes_rows = _read_csv(zf, LIKES_FILE)
        for row in likes_rows:
            title = row.get("Name", "").strip()
            key = _normalize(title)
            if title and key not in ratings_by_title:
                ratings_by_title[key] = RatedItem(title=title, rating=LIKE_RATING, review="")

        watched_rows = _read_csv(zf, WATCHED_FILE)
        extra_seen = {_normalize(row.get("Name", "")) for row in watched_rows if row.get("Name")}

        profile_rows = _read_csv(zf, PROFILE_FILE)
        if profile_rows:
            favorite_uris = [
                uri.strip()
                for uri in profile_rows[0].get("Favorite Films", "").split(",")
                if uri.strip()
            ]
            if favorite_uris:
                uri_to_title = {
                    row["Letterboxd URI"]: row["Name"]
                    for row in watched_rows
                    if row.get("Letterboxd URI") and row.get("Name")
                }
                for uri in favorite_uris:
                    title = uri_to_title.get(uri)
                    key = _normalize(title) if title else None
                    if title and (
                        key not in ratings_by_title
                        or ratings_by_title[key].rating < FAVORITE_RATING
                    ):
                        ratings_by_title[key] = RatedItem(
                            title=title, rating=FAVORITE_RATING, review=""
                        )
    except csv.Error as exc:
        raise ZipParseError("Uno de los CSV del zip vino mal formado.") from exc

    return list(ratings_by_title.values()), extra_seen, discarded_count
