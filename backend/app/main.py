import hmac
import logging
import os
import sqlite3
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, File, Form, HTTPException, Header, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import auth, catalog, db, letterboxd_scrape, letterboxd_zip, llm_client, mailer, taste_profile, tmdb_client
from .models import (
    AuthResponse,
    CatalogStatsResponse,
    FeedbackRequest,
    MovieDetails,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RatedItem,
    RecommendationHistoryResponse,
    PasswordResetStartResponse,
    Recommendation,
    RecommendRequest,
    RecommendResponse,
    RegisterRequest,
    TasteProfileResponse,
    UserCredentials,
    WatchedHistoryResponse,
)
from .recommender import GENRE_OPTIONS, recommend

MAX_ZIP_SIZE = 20 * 1024 * 1024  # 20MB — real Letterboxd exports run in the tens of KB
VALID_MODES = {"profile", "recent", "genres", "watchlist"}
VALID_KIND_FILTERS = {"movie", "series", "both"}
RECENT_WINDOW = 10  # how many of the user's most-recently-watched titles count as "lo último que vi"
DEFAULT_RECOMMEND_DAILY_LIMIT = 20  # per user; protects TMDb/NIM quotas. 0 = off.
WATCHLIST_MATCH_CAP = 60  # how many watchlist titles to resolve against TMDb per request

# ponytail: uvicorn only wires handlers for its own "uvicorn.*" loggers, not
# root — without this, logger.warning() calls below fall back to Python's
# bare "handler of last resort" (WARNING+ only, no timestamp/level/module),
# so nothing below WARNING ever reaches Render's log viewer at all.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)
# ponytail: recommend() only reads taste signal from review text and
# explicit Letterboxd Tags — titles with neither (any username-scraped
# import, or a zip rating with no review) contribute nothing, so the "why"
# collapses to the same generic fallback for everyone. Filling in each loved
# title's real TMDb genre closes that gap; capped since this runs
# synchronously in the request path (raise if latency allows more).
TASTE_TAG_LOOKUP_CAP = 30


def _debug_mode() -> bool:
    return os.environ.get("BUTACA_DEBUG", "").strip().lower() in {"1", "true", "yes"}


def _recommend_daily_limit() -> int:
    raw = os.environ.get("BUTACA_RECOMMEND_DAILY_LIMIT", "").strip()
    if not raw:
        return DEFAULT_RECOMMEND_DAILY_LIMIT
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_RECOMMEND_DAILY_LIMIT


def _refine_enabled(value: str) -> bool:
    # default on: only an explicit falsy value turns the LLM refine off (the
    # frontend passes "0" for the fast first render, then calls the refine
    # endpoint separately).
    return value.strip().lower() not in {"0", "false", "no"}


def _rebuild_ratings(user_id: int) -> list[RatedItem]:
    return [
        RatedItem(
            title=item["title"],
            rating=item["rating"],
            review=item.get("review", ""),
            watched_date=item.get("watched_date", ""),
        )
        for item in db.get_watched_items(user_id)
    ]


def _enforce_recommend_rate_limit(user_id: int) -> None:
    limit = _recommend_daily_limit()
    if limit <= 0:
        return
    today_start = datetime.now(timezone.utc).strftime("%Y-%m-%d 00:00:00")
    if db.count_sessions_since(user_id, today_start) >= limit:
        raise HTTPException(
            status_code=429,
            detail="Llegaste al límite de recomendaciones de hoy. Probá de nuevo mañana.",
        )


_DEFAULT_ALLOWED_ORIGINS = [
    "https://butaca.xyz",
    "https://www.butaca.xyz",
    "https://pelipick.vercel.app",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]
_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("BUTACA_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
] or _DEFAULT_ALLOWED_ORIGINS

app = FastAPI(title="Butaca API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # ponytail: an exception FastAPI itself doesn't catch (i.e. not an
    # HTTPException) escapes past CORSMiddleware before it can attach
    # Access-Control-* headers, so the browser reports "Failed to fetch"
    # instead of the real 500 — hiding the actual bug behind a network-error
    # message. Catching it here keeps it inside the CORS layer.
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Error interno del servidor."})


@app.api_route("/health", methods=["GET", "HEAD"])
def health() -> dict[str, str]:
    # HEAD too: uptime monitors (UptimeRobot et al.) probe with HEAD by
    # default, and GET-only would 405 every check — a false "down" alert on
    # a backend that's actually fine.
    return {"status": "ok"}


@app.get("/catalog/stats", response_model=CatalogStatsResponse)
def catalog_stats() -> CatalogStatsResponse:
    if not tmdb_client.is_configured():
        raise HTTPException(status_code=503, detail="Catálogo de TMDb no configurado.")
    try:
        stats = tmdb_client.fetch_catalog_stats()
    except tmdb_client.TmdbError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return CatalogStatsResponse(**stats)


@app.get("/admin/stats")
def admin_stats(x_admin_token: str | None = Header(default=None)) -> dict:
    # gated by a shared secret in BUTACA_ADMIN_TOKEN. When that env isn't
    # set (any environment that hasn't opted in) the endpoint 404s as if it
    # didn't exist, so it's never reachable in prod without deliberate setup.
    expected = os.environ.get("BUTACA_ADMIN_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=404, detail="No encontrado.")
    if not x_admin_token or not hmac.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=403, detail="Token de administrador inválido.")
    return db.get_admin_stats()


@app.post("/auth/register", response_model=AuthResponse, status_code=201)
def register(payload: RegisterRequest) -> AuthResponse:
    if db.get_user_by_username(payload.username) is not None:
        raise HTTPException(status_code=409, detail="Ese usuario ya existe.")

    password_hash, password_salt = auth.hash_password(payload.password)
    user_id = db.create_user(payload.username, password_hash, password_salt, payload.email)
    token = auth.create_token()
    db.create_session(token, user_id)
    return AuthResponse(token=token, username=payload.username)


@app.post("/auth/login", response_model=AuthResponse)
def login(payload: UserCredentials) -> AuthResponse:
    now = auth.now_ts()
    attempt = db.get_login_attempt(payload.username)
    if attempt is not None and attempt["locked_until"] > now:
        wait_seconds = attempt["locked_until"] - now
        raise HTTPException(
            status_code=429,
            detail=f"Demasiados intentos fallidos. Probá de nuevo en {wait_seconds}s.",
        )

    user = db.get_user_by_username(payload.username)
    if user is None or not auth.verify_password(
        payload.password, user["password_hash"], user["password_salt"]
    ):
        failed_attempts = (attempt["failed_attempts"] if attempt is not None else 0) + 1
        lock_seconds = auth.login_lock_seconds(failed_attempts)
        db.save_login_attempt(payload.username, failed_attempts, now + lock_seconds)
        if lock_seconds:
            raise HTTPException(
                status_code=429,
                detail=f"Demasiados intentos fallidos. Probá de nuevo en {lock_seconds}s.",
            )
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")

    db.clear_login_attempts(payload.username)
    token = auth.create_token()
    db.create_session(token, user["id"])
    return AuthResponse(token=token, username=user["username"])


@app.post("/auth/forgot-password", response_model=PasswordResetStartResponse)
def forgot_password(payload: PasswordResetRequest) -> PasswordResetStartResponse:
    user = db.get_user_by_username(payload.username)
    if user is None:
        return PasswordResetStartResponse(status="ok", reset_token=None)

    token, token_hash = auth.create_password_reset_token()
    expires_at = auth.now_ts() + auth.RESET_TOKEN_TTL_SECONDS
    db.save_password_reset_token(user["id"], token_hash, expires_at)

    if not mailer.is_configured():
        logger.warning("Password reset email skipped: RESEND_API_KEY no está configurada.")
    elif not user["email"]:
        logger.warning("Password reset email skipped: el usuario no tiene email cargado.")
    else:
        try:
            mailer.send_password_reset_email(user["email"], token)
            logger.info("Password reset email sent.")
        except mailer.MailError as exc:
            logger.warning("Password reset email failed to send: %s", exc)

    exposed_token = token if _debug_mode() else None
    return PasswordResetStartResponse(status="ok", reset_token=exposed_token)


@app.post("/auth/reset-password", status_code=204)
def reset_password(payload: PasswordResetConfirmRequest) -> None:
    token_record = db.get_password_reset_token(auth.hash_token(payload.token))
    if token_record is None or token_record["expires_at"] < auth.now_ts():
        raise HTTPException(status_code=400, detail="Token de recuperación inválido o expirado.")

    password_hash, password_salt = auth.hash_password(payload.password)
    db.update_user_password(token_record["user_id"], password_hash, password_salt)
    db.delete_password_reset_tokens_for_user(token_record["user_id"])
    db.delete_sessions_for_user(token_record["user_id"])
    db.clear_login_attempts(token_record["username"])


@app.get("/auth/me")
def me(user: sqlite3.Row = Depends(auth.get_current_user)) -> dict[str, str]:
    return {"username": user["username"]}


@app.post("/auth/logout", status_code=204)
def logout(authorization: str | None = Header(default=None)) -> None:
    if authorization and authorization.startswith("Bearer "):
        db.delete_session(authorization.removeprefix("Bearer ").strip())


@app.post("/recommend", response_model=RecommendResponse)
def recommend_titles(payload: RecommendRequest) -> RecommendResponse:
    return recommend(payload.ratings, payload.mood)


@app.get("/history", response_model=RecommendationHistoryResponse)
def recommendation_history(
    user: sqlite3.Row = Depends(auth.get_current_user),
) -> RecommendationHistoryResponse:
    return RecommendationHistoryResponse(sessions=db.get_recommendation_history(user["id"]))


@app.get("/history/watched", response_model=WatchedHistoryResponse)
def watched_history(
    user: sqlite3.Row = Depends(auth.get_current_user),
) -> WatchedHistoryResponse:
    return WatchedHistoryResponse(items=db.get_watched_items(user["id"]))


@app.get("/profile/taste", response_model=TasteProfileResponse)
def taste_profile_endpoint(
    user: sqlite3.Row = Depends(auth.get_current_user),
) -> TasteProfileResponse:
    if not tmdb_client.is_configured():
        raise HTTPException(status_code=503, detail="Catálogo de TMDb no configurado.")

    # ponytail: reuse the profile persisted by the last /recommend/zip or
    # /recommend/letterboxd call (see _finish_recommend) instead of redoing
    # ~200 TMDb requests on every page load. Only recompute here if none
    # exists yet — pre-feature users, or someone hitting this before their
    # first import — and persist that recompute so future calls hit cache.
    persisted = db.get_taste_profile(user["id"])
    if persisted is not None:
        return TasteProfileResponse(**persisted)

    watched = db.get_watched_items(user["id"])
    profile = taste_profile.build_taste_profile(watched)
    db.save_taste_profile(user["id"], profile)
    return TasteProfileResponse(**profile)


def _validate_recommend_params(mode: str, kind_filter: str) -> None:
    if mode not in VALID_MODES:
        raise HTTPException(status_code=400, detail="Modo de recomendación inválido.")
    if kind_filter not in VALID_KIND_FILTERS:
        raise HTTPException(status_code=400, detail="Filtro de tipo inválido.")


def _enrich_loved_ratings_with_genre_tags(ratings: list[RatedItem]) -> None:
    """Mutates loved titles (rating >= 4) in place, adding their real TMDb
    genre tags on top of whatever tags they already have. Only loved titles
    qualify, since _collect_preference_tags treats any tag on a RatedItem as
    positive signal regardless of rating — tagging a hated movie this way
    would flip its genre into a false positive."""
    if not tmdb_client.is_configured():
        return
    loved = sorted((r for r in ratings if r.rating >= 4), key=lambda r: r.rating, reverse=True)
    loved = loved[:TASTE_TAG_LOOKUP_CAP]
    if not loved:
        return

    def _match(item: RatedItem) -> tuple[RatedItem, dict | None]:
        try:
            return item, tmdb_client.search_title(item.title)
        except tmdb_client.TmdbError:
            return item, None

    # blocking network calls, not CPU work — a thread pool gets real
    # concurrency here despite the GIL (see taste_profile.MATCH_WORKERS)
    with ThreadPoolExecutor(max_workers=taste_profile.MATCH_WORKERS) as pool:
        results = pool.map(_match, loved)
    for item, match in results:
        if match:
            item.tags = list(item.tags) + match["tags"]


def _watchlist_candidates(titles: list[str]) -> list[dict]:
    """Resolve the user's Letterboxd watchlist titles to TMDb candidates so
    recommend() can rank them by taste, instead of pulling fresh discover
    results. Parallel like _enrich_loved_ratings_with_genre_tags — these are
    blocking network calls, not CPU work."""
    if not tmdb_client.is_configured() or not titles:
        return []

    def _match(title: str) -> dict | None:
        try:
            return tmdb_client.search_title(title)
        except tmdb_client.TmdbError:
            return None

    with ThreadPoolExecutor(max_workers=taste_profile.MATCH_WORKERS) as pool:
        results = pool.map(_match, titles[:WATCHLIST_MATCH_CAP])
    return [match for match in results if match]


def _finish_recommend(
    ratings: list[RatedItem],
    extra_seen: set[str],
    mood: str,
    mode: str,
    kind_filter: str,
    genres: str,
    user: sqlite3.Row,
    discarded_rows: int = 0,
    refine: bool = True,
) -> RecommendResponse:
    """Shared tail of both /recommend/zip and /recommend/letterboxd: once a
    source has produced (ratings, extra_seen), the rest of the flow —
    candidates, exclusion, scoring, LLM refine, persistence — is identical.
    refine=False skips the (slow) LLM step and returns the heuristic picks
    immediately; the frontend then calls /recommend/sessions/{id}/refine to
    swap in the LLM-written reasons without blocking the first render."""
    _enforce_recommend_rate_limit(user["id"])

    if not ratings:
        raise HTTPException(
            status_code=400,
            detail="No encontré ratings ni reviews usables para armar recomendaciones.",
        )

    _enrich_loved_ratings_with_genre_tags(ratings)

    # save ratings before computing the taste profile (moved up from the end
    # of this function) so the profile reflects this import and can bias
    # *this* request's own candidates below, not just future ones — see
    # docs/(C) plan-de-trabajo.md §4 for why this used to run too late.
    db.save_rated_items(
        user["id"],
        [(item.title, item.rating, item.review, item.watched_date) for item in ratings],
    )

    # Guarded broadly: this is a personalization/caching side effect, not the
    # point of the request — a TMDb hiccup (or a mocked search_title missing
    # fields it expects, see TASKS.md) should degrade to the unpersonalized
    # pool below, not fail an otherwise-servable recommend call.
    profile: dict | None = None
    if tmdb_client.is_configured():
        try:
            watched = db.get_watched_items(user["id"])
            profile = taste_profile.build_taste_profile(watched)
            db.save_taste_profile(user["id"], profile)
        except Exception:
            logger.warning("Taste profile computation failed, falling back to unpersonalized candidates", exc_info=True)
            profile = None

    if mode == "watchlist":
        # recommend FROM the user's Letterboxd watchlist instead of discover.
        # The list is persisted per import; username imports don't carry one,
        # so this leans on a previously imported zip.
        watchlist = db.get_watchlist_items(user["id"])
        if not watchlist:
            raise HTTPException(
                status_code=400,
                detail="Tu watchlist está vacía. Importá el zip de Letterboxd (el import por username no la trae).",
            )
        candidates = _watchlist_candidates(watchlist)
        if not candidates:
            raise HTTPException(
                status_code=400,
                detail="No pude matchear tu watchlist contra el catálogo de TMDb.",
            )
    else:
        candidates = catalog.CATALOG
        if tmdb_client.is_configured():
            try:
                if profile and profile.get("genre_breakdown"):
                    candidates = tmdb_client.fetch_personalized_candidates(profile, mood, kind_filter)
                else:
                    candidates = tmdb_client.fetch_candidates(mood)
            except tmdb_client.TmdbError as exc:
                logger.warning("TMDb candidates fetch failed, falling back to mock catalog: %s", exc)
                candidates = catalog.CATALOG

    # explicit feedback is a hard exclusion, unlike "already recommended"
    # (relaxed on retry below): a title the user marked seen or not_interested
    # must never resurface, so fold it into extra_seen up front. The tags of
    # not_interested picks feed a scoring penalty in recommend().
    feedback = db.get_feedback_signals(user["id"])
    extra_seen = set(extra_seen) | set(feedback["seen_titles"]) | {
        item["title"] for item in feedback["not_interested"]
    }
    rejected_tags: Counter[str] = Counter()
    for item in feedback["not_interested"]:
        rejected_tags.update(item["tags"])

    # exclude titles already recommended to this user before, so hitting
    # "nuevos picks" and regenerating with the same source+mood surfaces
    # different movies instead of the same deterministic top 5
    already_recommended = db.get_recently_recommended_titles(user["id"])
    also_seen = frozenset(extra_seen) | frozenset(already_recommended)

    # "según lo último que vi" narrows the taste signal to the user's most
    # recently watched titles instead of their whole history — exclusion
    # (also_seen/ratings above) still covers everything they've ever watched
    preference_ratings = None
    if mode == "recent":
        preference_ratings = sorted(
            ratings, key=lambda item: item.watched_date, reverse=True
        )[:RECENT_WINDOW]

    selected_genres = [key.strip() for key in genres.split(",") if key.strip()]
    required_any_tags = frozenset(
        tag for key in selected_genres for tag in GENRE_OPTIONS.get(key, [])
    )
    if mode == "genres" and not required_any_tags:
        raise HTTPException(
            status_code=400, detail="Elegí al menos un género para este modo."
        )

    response = recommend(
        ratings,
        mood,
        catalog=candidates,
        also_seen=also_seen,
        kind_filter=kind_filter,
        required_any_tags=required_any_tags or None,
        preference_ratings=preference_ratings,
        profile=profile,
        rejected_tags=rejected_tags or None,
    )

    # the "don't repeat what I already recommended" exclusion can exhaust a
    # small candidate pool (narrow genre filter, small personalized pool,
    # or just enough "nuevos picks" clicks in one session) — resurfacing an
    # older pick beats failing the request outright once there's genuinely
    # nothing new left to show.
    if not response.recommendations and already_recommended:
        logger.info("Candidate pool exhausted by already-recommended exclusion, retrying without it")
        response = recommend(
            ratings,
            mood,
            catalog=candidates,
            also_seen=frozenset(extra_seen),
            kind_filter=kind_filter,
            required_any_tags=required_any_tags or None,
            preference_ratings=preference_ratings,
            profile=profile,
            rejected_tags=rejected_tags or None,
        )

    refined = False
    if refine and llm_client.is_configured():
        try:
            response = llm_client.refine_recommendations(ratings, mood, response)
            refined = True
        except llm_client.LlmError as exc:
            logger.warning("LLM refine failed, falling back to heuristic why: %s", exc)

    session_id = db.create_recommendation_session(user["id"], mood, response.taste_summary)
    inserted_ids = db.save_recommendations(
        session_id,
        user["id"],
        mood,
        [item.model_dump() for item in response.recommendations],
    )
    for item, new_id in zip(response.recommendations, inserted_ids):
        item.id = new_id

    response.discarded_rows = discarded_rows
    response.session_id = session_id
    response.refined = refined
    logger.info(
        "recommend done user=%s mode=%s kind=%s personalized=%s llm=%s refined=%s picks=%d discarded_rows=%d",
        user["id"],
        mode,
        kind_filter,
        bool(profile),
        llm_client.is_configured(),
        refined,
        len(response.recommendations),
        discarded_rows,
    )
    return response


@app.post("/recommend/zip", response_model=RecommendResponse)
async def recommend_titles_from_zip(
    mood: str = Form(""),
    mode: str = Form("profile"),
    kind_filter: str = Form("both"),
    genres: str = Form(""),
    refine: str = Form("1"),
    file: UploadFile = File(...),
    user: sqlite3.Row = Depends(auth.get_current_user),
) -> RecommendResponse:
    _validate_recommend_params(mode, kind_filter)

    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Subí el .zip que exporta Letterboxd.")

    data = await file.read()
    if len(data) > MAX_ZIP_SIZE:
        raise HTTPException(status_code=400, detail="Ese zip es demasiado grande.")

    try:
        ratings, extra_seen, discarded_rows = letterboxd_zip.parse_letterboxd_zip(data)
    except letterboxd_zip.ZipParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # persist this import's watchlist so "watchlist" mode (this request or a
    # later one) has it. Only overwrite when non-empty, so an export missing
    # the file — or an emptied list — doesn't silently wipe a good one.
    watchlist_titles = letterboxd_zip.parse_watchlist_titles(data)
    if watchlist_titles:
        db.save_watchlist_items(user["id"], watchlist_titles)

    return _finish_recommend(
        ratings, extra_seen, mood, mode, kind_filter, genres, user, discarded_rows,
        refine=_refine_enabled(refine),
    )


@app.post("/recommend/letterboxd", response_model=RecommendResponse)
def recommend_titles_from_letterboxd(
    username: str = Form(...),
    mood: str = Form(""),
    mode: str = Form("profile"),
    kind_filter: str = Form("both"),
    genres: str = Form(""),
    refine: str = Form("1"),
    user: sqlite3.Row = Depends(auth.get_current_user),
) -> RecommendResponse:
    _validate_recommend_params(mode, kind_filter)

    try:
        ratings, extra_seen = letterboxd_scrape.fetch_letterboxd_diary(username)
    except letterboxd_scrape.ScrapeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _finish_recommend(
        ratings, extra_seen, mood, mode, kind_filter, genres, user, refine=_refine_enabled(refine)
    )


@app.post("/recommend/sessions/{session_id}/refine", response_model=RecommendResponse)
def refine_session(
    session_id: int, user: sqlite3.Row = Depends(auth.get_current_user)
) -> RecommendResponse:
    """Second half of progressive rendering: re-run the LLM refine over a
    session's already-served heuristic picks and persist the rewritten
    reasons. Returns refined=False (200, not an error) when the LLM isn't
    configured or fails, so the frontend just keeps the heuristic text."""
    session = db.get_recommendation_session(session_id, user["id"])
    if session is None:
        raise HTTPException(status_code=404, detail="Sesión no encontrada.")

    rec_rows = db.get_session_recommendations(session_id, user["id"])
    recommendations = [Recommendation(**row) for row in rec_rows]
    heuristic = RecommendResponse(
        taste_summary=session["taste_summary"],
        recommendations=recommendations,
        session_id=session_id,
    )

    if not llm_client.is_configured() or not recommendations:
        return heuristic

    try:
        refined = llm_client.refine_recommendations(
            _rebuild_ratings(user["id"]), session["mood"], heuristic
        )
    except llm_client.LlmError as exc:
        logger.warning("Session refine failed, returning heuristic: %s", exc)
        return heuristic

    db.update_session_refinement(
        session_id,
        refined.taste_summary,
        [(rec.id, rec.why) for rec in refined.recommendations if rec.id is not None],
    )
    refined.session_id = session_id
    refined.refined = True
    return refined


@app.get("/movies/{tmdb_id}/details", response_model=MovieDetails)
def movie_details(
    tmdb_id: int, kind: str = "movie", user: sqlite3.Row = Depends(auth.get_current_user)
) -> MovieDetails:
    if not tmdb_client.is_configured():
        raise HTTPException(status_code=503, detail="Catálogo de TMDb no configurado.")

    try:
        cast = tmdb_client.fetch_credits(tmdb_id, kind=kind)
        trailer_key = tmdb_client.fetch_trailer_key(tmdb_id, kind=kind)
    except tmdb_client.TmdbError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # providers is a nice-to-have; a failure here shouldn't sink the whole
    # detail response — same graceful degrade as the rest of the modal.
    try:
        providers = tmdb_client.fetch_watch_providers(tmdb_id, kind=kind)
    except tmdb_client.TmdbError:
        providers = None

    return MovieDetails(cast=cast, trailer_key=trailer_key, providers=providers)


@app.post("/feedback", status_code=201)
def submit_feedback(
    payload: FeedbackRequest, user: sqlite3.Row = Depends(auth.get_current_user)
) -> dict[str, str]:
    recommendation = db.get_recommendation(payload.recommendation_id, user["id"])
    if recommendation is None:
        raise HTTPException(status_code=404, detail="Recomendación no encontrada.")

    db.save_feedback(user["id"], payload.recommendation_id, payload.status)
    return {"status": "ok"}
