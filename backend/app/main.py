import os
import sqlite3

from fastapi import Depends, FastAPI, File, Form, HTTPException, Header, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from . import auth, catalog, db, letterboxd_zip, llm_client, tmdb_client
from .models import (
    AuthResponse,
    FeedbackRequest,
    MovieDetails,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RecommendationHistoryResponse,
    PasswordResetStartResponse,
    RecommendRequest,
    RecommendResponse,
    UserCredentials,
    WatchedHistoryResponse,
)
from .recommender import GENRE_OPTIONS, recommend

MAX_ZIP_SIZE = 20 * 1024 * 1024  # 20MB — real Letterboxd exports run in the tens of KB
VALID_MODES = {"profile", "recent", "genres"}
VALID_KIND_FILTERS = {"movie", "series", "both"}
RECENT_WINDOW = 10  # how many of the user's most-recently-watched titles count as "lo último que vi"


def _debug_mode() -> bool:
    return os.environ.get("PELIPICK_DEBUG", "").strip().lower() in {"1", "true", "yes"}

app = FastAPI(title="PeliPick API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/auth/register", response_model=AuthResponse, status_code=201)
def register(payload: UserCredentials) -> AuthResponse:
    if db.get_user_by_username(payload.username) is not None:
        raise HTTPException(status_code=409, detail="Ese usuario ya existe.")

    password_hash, password_salt = auth.hash_password(payload.password)
    user_id = db.create_user(payload.username, password_hash, password_salt)
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


@app.post("/recommend/zip", response_model=RecommendResponse)
async def recommend_titles_from_zip(
    mood: str = Form(""),
    mode: str = Form("profile"),
    kind_filter: str = Form("both"),
    genres: str = Form(""),
    file: UploadFile = File(...),
    user: sqlite3.Row = Depends(auth.get_current_user),
) -> RecommendResponse:
    if mode not in VALID_MODES:
        raise HTTPException(status_code=400, detail="Modo de recomendación inválido.")
    if kind_filter not in VALID_KIND_FILTERS:
        raise HTTPException(status_code=400, detail="Filtro de tipo inválido.")

    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Subí el .zip que exporta Letterboxd.")

    data = await file.read()
    if len(data) > MAX_ZIP_SIZE:
        raise HTTPException(status_code=400, detail="Ese zip es demasiado grande.")

    try:
        ratings, extra_seen = letterboxd_zip.parse_letterboxd_zip(data)
    except letterboxd_zip.ZipParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not ratings:
        raise HTTPException(
            status_code=400,
            detail="No encontré ratings ni reviews usables en ese zip.",
        )

    candidates = catalog.CATALOG
    if tmdb_client.is_configured():
        try:
            candidates = tmdb_client.fetch_candidates(mood)
        except tmdb_client.TmdbError:
            candidates = catalog.CATALOG

    # exclude titles already recommended to this user before, so hitting
    # "nuevos picks" and regenerating with the same zip+mood surfaces
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
    )

    if llm_client.is_configured():
        try:
            response = llm_client.refine_recommendations(ratings, mood, response)
        except llm_client.LlmError:
            pass

    db.save_rated_items(
        user["id"], [(item.title, item.rating, item.review) for item in ratings]
    )
    session_id = db.create_recommendation_session(user["id"], mood, response.taste_summary)
    inserted_ids = db.save_recommendations(
        session_id,
        user["id"],
        mood,
        [item.model_dump() for item in response.recommendations],
    )
    for item, new_id in zip(response.recommendations, inserted_ids):
        item.id = new_id

    return response


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

    return MovieDetails(cast=cast, trailer_key=trailer_key)


@app.post("/feedback", status_code=201)
def submit_feedback(
    payload: FeedbackRequest, user: sqlite3.Row = Depends(auth.get_current_user)
) -> dict[str, str]:
    recommendation = db.get_recommendation(payload.recommendation_id, user["id"])
    if recommendation is None:
        raise HTTPException(status_code=404, detail="Recomendación no encontrada.")

    db.save_feedback(user["id"], payload.recommendation_id, payload.status)
    return {"status": "ok"}
