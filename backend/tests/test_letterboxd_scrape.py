import pytest

from backend.app import letterboxd_scrape as ls


def _item(
    title: str,
    *,
    rating: str | None = None,
    watched: str = "2026-01-15",
    rewatch: str = "No",
    like: str = "No",
    tmdb_id: str | None = None,
) -> str:
    rating_tag = f"<letterboxd:memberRating>{rating}</letterboxd:memberRating>" if rating else ""
    tmdb_tag = f"<tmdb:movieId>{tmdb_id}</tmdb:movieId>" if tmdb_id else ""
    return (
        "<item>"
        f"<title>{title}</title>"
        f"<letterboxd:filmTitle>{title}</letterboxd:filmTitle>"
        f"<letterboxd:watchedDate>{watched}</letterboxd:watchedDate>"
        f"<letterboxd:rewatch>{rewatch}</letterboxd:rewatch>"
        f"<letterboxd:memberLike>{like}</letterboxd:memberLike>"
        f"{rating_tag}"
        f"{tmdb_tag}"
        "</item>"
    )


def _feed(*items: str) -> str:
    return (
        "<?xml version='1.0' encoding='utf-8'?>"
        '<rss version="2.0" xmlns:letterboxd="https://letterboxd.com" xmlns:tmdb="https://themoviedb.org">'
        "<channel>" + "".join(items) + "</channel></rss>"
    )


def test_parse_feed_extracts_rating_and_watched_date() -> None:
    entries = ls._parse_feed(_feed(_item("GoodFellas", rating="5.0", watched="2024-09-28")))

    assert entries == [
        {
            "title": "GoodFellas",
            "rating": 5.0,
            "watched_date": "2024-09-28",
            "liked": False,
            "tmdb_id": None,
        }
    ]


def test_parse_feed_extracts_tmdb_id() -> None:
    entries = ls._parse_feed(_feed(_item("GoodFellas", rating="5.0", tmdb_id="769")))

    assert entries[0]["tmdb_id"] == 769


def test_fetch_diary_propagates_tmdb_id_onto_rated_item(monkeypatch) -> None:
    monkeypatch.setattr(
        ls, "_fetch_feed", lambda username: _feed(_item("GoodFellas", rating="5.0", tmdb_id="769"))
    )

    ratings, _ = ls.fetch_letterboxd_diary("someone")

    assert ratings[0].tmdb_id == 769
    assert ratings[0].source == "import"


def test_parse_feed_skips_non_film_items() -> None:
    # Las listas publicadas también salen en el feed, pero sin filmTitle.
    feed = _feed(
        "<item><title>Mi top 10 de 2026</title></item>",
        _item("Heat", rating="4.5"),
    )

    entries = ls._parse_feed(feed)

    assert [e["title"] for e in entries] == ["Heat"]


def test_parse_feed_handles_unrated_entry() -> None:
    entries = ls._parse_feed(_feed(_item("Taxi Driver")))

    assert entries[0]["rating"] is None


def test_fetch_diary_uses_like_as_rating_when_unrated(monkeypatch) -> None:
    monkeypatch.setattr(ls, "_fetch_feed", lambda username: _feed(_item("Weekend", like="Yes")))

    ratings, extra_seen = ls.fetch_letterboxd_diary("someone")

    assert [(r.title, r.rating) for r in ratings] == [("Weekend", ls.LIKE_RATING)]
    assert ratings[0].source == "like"  # synthetic rating, why must not cite it as precise
    assert extra_seen == set()


def test_fetch_diary_sends_unrated_unliked_to_extra_seen(monkeypatch) -> None:
    monkeypatch.setattr(ls, "_fetch_feed", lambda username: _feed(_item("Dune")))

    ratings, extra_seen = ls.fetch_letterboxd_diary("someone")

    assert ratings == []
    assert extra_seen == {"dune"}


def test_fetch_diary_gives_rewatch_bonus_for_repeated_titles(monkeypatch) -> None:
    feed = _feed(_item("Casino", rating="4.0"), _item("Casino", rating="4.0", rewatch="Yes"))
    monkeypatch.setattr(ls, "_fetch_feed", lambda username: feed)

    ratings, _ = ls.fetch_letterboxd_diary("someone")

    assert [(r.title, r.rating) for r in ratings] == [("Casino", 4.0 + ls.REWATCH_BONUS)]


def test_fetch_diary_caps_rewatch_bonus_at_five(monkeypatch) -> None:
    feed = _feed(*[_item("Heat", rating="5.0") for _ in range(4)])
    monkeypatch.setattr(ls, "_fetch_feed", lambda username: feed)

    ratings, _ = ls.fetch_letterboxd_diary("someone")

    assert ratings[0].rating == 5.0


def test_fetch_diary_rejects_empty_username() -> None:
    with pytest.raises(ls.ScrapeError):
        ls.fetch_letterboxd_diary("   ")


def test_fetch_diary_errors_when_feed_has_no_films(monkeypatch) -> None:
    monkeypatch.setattr(ls, "_fetch_feed", lambda username: _feed())

    with pytest.raises(ls.ScrapeError):
        ls.fetch_letterboxd_diary("someone")


def test_fetch_feed_maps_404_to_unknown_user(monkeypatch) -> None:
    def raise_404(*args, **kwargs):
        raise ls.HTTPError("https://letterboxd.com/nadie/rss/", 404, "Not Found", {}, None)

    monkeypatch.setattr(ls.urllib.request, "urlopen", raise_404)

    with pytest.raises(ls.ScrapeError, match="No encontré"):
        ls._fetch_feed("nadie")


def test_fetch_feed_sets_user_agent(monkeypatch) -> None:
    # Sin User-Agent propio Cloudflare corta con 403 — se rompe solo en
    # producción, nunca en los tests mockeados.
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["headers"] = request.headers
        raise ls.URLError("stop here")

    monkeypatch.setattr(ls.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(ls.ScrapeError):
        ls._fetch_feed("someone")

    assert captured["headers"].get("User-agent") == ls.USER_AGENT


def test_parse_feed_wraps_malformed_xml() -> None:
    with pytest.raises(ls.ScrapeError):
        ls._parse_feed("<rss><channel><item>roto")
