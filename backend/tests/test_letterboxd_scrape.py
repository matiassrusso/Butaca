import pytest

from backend.app import letterboxd_scrape as ls


def _diary_row(slug: str, title: str, date: str, rating: int | None = None, viewing_index: int | None = None) -> str:
    href_suffix = f"{viewing_index}/" if viewing_index else ""
    rating_span = f'<span class="rating rated-{rating}"> stars </span>' if rating else '<span class="rating "> </span>'
    year, month, day = date.split("-")
    return (
        '<tr class="diary-entry-row">'
        f'<a class="daydate" href="/user/diary/films/for/{year}/{month}/{day}/">{day}</a>'
        f'<h2 class="primaryname prettify"><a href="/user/film/{slug}/{href_suffix}">{title}</a></h2>'
        f"{rating_span}"
        "</tr>"
    )


def _diary_page(*rows: str) -> str:
    return "<table>" + "".join(rows) + "</table>"


def test_parse_diary_page_extracts_rating_and_date() -> None:
    page = _diary_page(_diary_row("goodfellas", "GoodFellas", "2024-09-28", rating=10))

    entries = ls._parse_diary_page(page)

    assert entries == [
        {"slug": "goodfellas", "title": "GoodFellas", "watched_date": "2024-09-28", "rating": 5.0}
    ]


def test_parse_diary_page_handles_unrated_entry() -> None:
    page = _diary_page(_diary_row("taxi-driver", "Taxi Driver", "2024-09-28"))

    entries = ls._parse_diary_page(page)

    assert entries[0]["rating"] is None


def test_parse_diary_page_handles_rewatch_url_suffix() -> None:
    page = _diary_page(_diary_row("passages", "Passages", "2024-01-01", viewing_index=2))

    entries = ls._parse_diary_page(page)

    assert entries[0]["slug"] == "passages"


def test_fetch_letterboxd_diary_requires_username(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ls.ScrapeError):
        ls.fetch_letterboxd_diary("  ")


def test_fetch_letterboxd_diary_raises_for_unknown_username(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ls, "_fetch_html", lambda url: None)

    with pytest.raises(ls.ScrapeError):
        ls.fetch_letterboxd_diary("nosuchuser")


def test_fetch_letterboxd_diary_raises_when_diary_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ls, "_fetch_html", lambda url: _diary_page())

    with pytest.raises(ls.ScrapeError):
        ls.fetch_letterboxd_diary("newuser")


def test_fetch_letterboxd_diary_splits_rated_and_unrated_into_ratings_and_extra_seen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page1 = _diary_page(
        _diary_row("goodfellas", "GoodFellas", "2024-09-28", rating=10),
        _diary_row("passages", "Passages", "2024-01-01"),
    )

    def fake_fetch(url: str) -> str | None:
        return page1 if "page/1/" in url else None

    monkeypatch.setattr(ls, "_fetch_html", fake_fetch)

    ratings, extra_seen = ls.fetch_letterboxd_diary("someuser")

    assert [item.title for item in ratings] == ["GoodFellas"]
    assert ratings[0].rating == 5.0
    assert ratings[0].watched_date == "2024-09-28"
    assert extra_seen == {"passages"}


def test_fetch_letterboxd_diary_applies_rewatch_bonus_on_repeat_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page1 = _diary_page(
        _diary_row("goodfellas", "GoodFellas", "2024-09-28", rating=8, viewing_index=2),
        _diary_row("goodfellas", "GoodFellas", "2020-01-01", rating=8),
    )

    def fake_fetch(url: str) -> str | None:
        return page1 if "page/1/" in url else None

    monkeypatch.setattr(ls, "_fetch_html", fake_fetch)

    ratings, _ = ls.fetch_letterboxd_diary("someuser")

    assert len(ratings) == 1
    assert ratings[0].rating == 4.5  # 4.0 base + 0.5 rewatch bonus
    assert ratings[0].watched_date == "2024-09-28"  # first (most recent) occurrence wins


def test_fetch_letterboxd_diary_caps_rewatch_bonus_at_five(monkeypatch: pytest.MonkeyPatch) -> None:
    page1 = _diary_page(
        *[_diary_row("goodfellas", "GoodFellas", "2024-01-01", rating=10, viewing_index=i) for i in range(1, 6)]
    )

    monkeypatch.setattr(ls, "_fetch_html", lambda url: page1 if "page/1/" in url else None)

    ratings, _ = ls.fetch_letterboxd_diary("someuser")

    assert ratings[0].rating == 5.0


def test_fetch_letterboxd_diary_paginates_until_empty_page(monkeypatch: pytest.MonkeyPatch) -> None:
    page1 = _diary_page(_diary_row("film-a", "Film A", "2024-02-01", rating=10))
    page2 = _diary_page(_diary_row("film-b", "Film B", "2024-01-01", rating=8))
    calls = []

    def fake_fetch(url: str) -> str | None:
        calls.append(url)
        if "page/1/" in url:
            return page1
        if "page/2/" in url:
            return page2
        return _diary_page()

    monkeypatch.setattr(ls, "_fetch_html", fake_fetch)

    ratings, _ = ls.fetch_letterboxd_diary("someuser")

    assert {item.title for item in ratings} == {"Film A", "Film B"}
    assert len(calls) == 3  # stops at the first empty page


def test_fetch_letterboxd_diary_stops_at_max_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    full_page = _diary_page(_diary_row("film-a", "Film A", "2024-02-01", rating=10))
    calls = []

    def fake_fetch(url: str) -> str | None:
        calls.append(url)
        return full_page

    monkeypatch.setattr(ls, "_fetch_html", fake_fetch)
    monkeypatch.setattr(ls, "MAX_DIARY_PAGES", 3)

    ls.fetch_letterboxd_diary("someuser")

    assert len(calls) == 3


def test_fetch_html_wraps_network_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    from curl_cffi.requests.exceptions import ConnectionError as CurlConnectionError

    def raise_connection_error(url, impersonate, timeout):
        raise CurlConnectionError("boom")

    monkeypatch.setattr(ls.curl_requests, "get", raise_connection_error)

    with pytest.raises(ls.ScrapeError):
        ls._fetch_html("https://letterboxd.com/someuser/diary/films/page/1/")


def test_fetch_html_wraps_non_404_error_statuses(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        status_code = 500
        ok = False
        text = ""
        headers: dict[str, str] = {}

    monkeypatch.setattr(ls.curl_requests, "get", lambda url, impersonate, timeout: FakeResponse())

    with pytest.raises(ls.ScrapeError):
        ls._fetch_html("https://letterboxd.com/someuser/diary/films/page/1/")


def test_fetch_html_logs_cloudflare_error_code(monkeypatch, caplog) -> None:
    # Distinguir 1010 (fingerprint, arreglable) de 1006/1015 (IP baneada) es lo
    # único que dice si el bloqueo se puede resolver en código.
    class BlockedResponse:
        status_code = 403
        ok = False
        text = "<html>Access denied | error code: 1006</html>"
        headers = {"cf-ray": "abc123-EZE"}

    monkeypatch.setattr(ls.curl_requests, "get", lambda url, impersonate, timeout: BlockedResponse())

    with caplog.at_level("WARNING"):
        with pytest.raises(ls.ScrapeError):
            ls._fetch_html("https://letterboxd.com/someuser/diary/films/page/1/")

    assert "cf_error=1006" in caplog.text
    assert "abc123-EZE" in caplog.text
