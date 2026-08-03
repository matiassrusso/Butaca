import hmac
import logging
import os
import random
import sqlite3
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, File, Form, HTTPException, Header, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import (
    auth,
    catalog,
    db,
    letterboxd_scrape,
    letterboxd_zip,
    llm_client,
    mailer,
    onboarding_titles,
    taste_profile,
    tmdb_client,
    vibes_clustering,
)
from .models import (
    AuthResponse,
    CatalogStatsResponse,
    DeleteAccountRequest,
    EmailVerificationConfirmRequest,
    FeedbackRequest,
    ManualRecommendRequest,
    MovieDetails,
    OnboardingTitle,
    OnboardingTitlesResponse,
    PairwiseChoiceRequest,
    PairwiseMatchResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    PickOption,
    PickOptionsResponse,
    ProfileRecommendRequest,
    RatedItem,
    LetterboxdUsernameRequest,
    RateTitleRequest,
    RecommendationHistoryResponse,
    PasswordResetStartResponse,
    Recommendation,
    RegisterResponse,
    RecommendRequest,
    RecommendResponse,
    RegisterRequest,
    TasteProfileResponse,
    TriviaQuestion,
    UserCredentials,
    WatchedHistoryResponse,
)
from .recommender import GENRE_OPTIONS, PICK_OPTIONS, recommend

MAX_ZIP_SIZE = 20 * 1024 * 1024  # 20MB — real Letterboxd exports run in the tens of KB
VALID_MODES = {"profile", "recent", "genres", "watchlist"}
VALID_KIND_FILTERS = {"movie", "series", "both"}
RECENT_WINDOW = 10  # how many of the user's most-recently-watched titles count as "lo último que vi"
# picker "a tu elección": cada opción elegida es un request aparte a TMDb
# (tmdb_client.fetch_candidates_for_options) — sin tope, elegir 25 opciones
# dispara 50 requests en un solo /recommend.
MAX_SELECTED_OPTIONS = 5
MIN_MANUAL_RATINGS = 10  # onboarding without Letterboxd needs at least this many rated seed titles
DEFAULT_RECOMMEND_DAILY_LIMIT = 20  # per user; protects TMDb/NIM quotas. 0 = off.
WATCHLIST_MATCH_CAP = 60  # how many watchlist titles to resolve against TMDb per request
MOVEMENT_MEMBER_CAP = 40  # títulos por movimiento elegido que se resuelven contra TMDb
MIN_MOVEMENT_SIZE = 6  # un movimiento con menos títulos que una tanda de picks no se ofrece
SWIPE_BATCH_SIZE = 20  # cuántos títulos sin puntuar se ofrecen por tanda en la sección de swipe
SWIPE_CLUSTER_OVERSAMPLE = 3  # margen para sobrevivir el filtro de "ya puntuado"
TRIVIA_OPTION_COUNT = 4  # una correcta + 3 distractores
TRIVIA_ATTEMPTS = 4  # cuántos pools random se prueban antes de rendirse (ver _build_trivia_question)
_VIBE_RECOMPUTE_LOCK = threading.Lock()

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
            source=item.get("source", "import"),
            tmdb_id=item.get("tmdb_id"),
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


@app.get("/recommend/options", response_model=PickOptionsResponse)
def recommend_options() -> PickOptionsResponse:
    """Opciones del picker "a tu elección" (modo genres) — reemplaza el
    array `genreOptions` que el frontend tenía hardcodeado y duplicado a
    mano (a 7 opciones tolerable, a 25+ garantiza que se desincronice).
    Sin auth, como /catalog/stats: es metadata pública del picker, no datos
    de usuario."""
    options = [PickOption(key=o["key"], label=o["label"], group=o["group"]) for o in PICK_OPTIONS]
    # un movimiento con menos títulos que una tanda de picks no se puede
    # ofrecer: por más que se amplíe el pool, el cluster ES el catálogo (en la
    # muestra real quedaron 10 de 52 clusters con 1 a 5 miembros).
    movements = db.get_vibe_clusters(level=2, min_size=MIN_MOVEMENT_SIZE)
    # el LLM etiqueta cada cluster por separado, así que dos pueden terminar
    # con el mismo nombre (pasó en la muestra real: "Animales con emociones"
    # y "animales con emociones"). El picker los muestra en mayúsculas: dos
    # chips idénticos que el usuario no puede distinguir. Se ofrece el más
    # grande de cada nombre; el tag del otro sigue siendo válido si llega.
    by_label: dict[str, dict] = {}
    for row in sorted(movements, key=lambda r: -r["size"]):
        by_label.setdefault(row["label"].strip().casefold(), row)
    options.extend(
        PickOption(key=f"vibe-l2:{row['cluster_id']}", label=row["label"], group="movimientos")
        for row in sorted(by_label.values(), key=lambda r: r["cluster_id"])
    )
    return PickOptionsResponse(options=options)


@app.get("/catalog/stats", response_model=CatalogStatsResponse)
def catalog_stats() -> CatalogStatsResponse:
    if not tmdb_client.is_configured():
        raise HTTPException(status_code=503, detail="Catálogo de TMDb no configurado.")
    try:
        stats = tmdb_client.fetch_catalog_stats()
    except tmdb_client.TmdbError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return CatalogStatsResponse(**stats)


def _adjust_match_scores(heuristic: RecommendResponse) -> RecommendResponse:
    """El vocabulario de tags que usa recommend() para puntuar es chico
    (genero + KEYWORD_TAG_MAP, una allowlist angosta) y para un perfil de
    gusto activo/diverso satura rápido: varios candidatos terminan con el
    mismo match_score exacto (reportado por Matías, 2026-07-31 — 4 de 5
    semanales en 81%; confirmado contra logs de producción que
    KEYWORD_TAG_MAP no matcheaba nada para esos 4 títulos puntuales, así
    que el enrichment de la ronda anterior no alcanzaba a diferenciarlos).
    vote_average de TMDb es dato real que sí varía por título — se usa acá
    como desempate suave, SOLO en /weekly (recommend() no se toca, lo usa
    también /recommend) y solo cuando ya hay evidencia real: nunca sobre
    el piso de 50, que es "sin evidencia" a propósito (ver
    frontend/src/lib/match.ts, isUnknownMatch)."""
    nudged = []
    for rec in heuristic.recommendations:
        if rec.match_score != 50 and rec.vote_average is not None:
            nudge = round((rec.vote_average - 7.0) * 3)
            rec = rec.model_copy(update={"match_score": max(1, min(99, rec.match_score + nudge))})
        nudged.append(rec)
    return heuristic.model_copy(update={"recommendations": nudged})


@app.get("/weekly", response_model=RecommendResponse)
def weekly_picks(user: sqlite3.Row | None = Depends(auth.get_optional_user)) -> RecommendResponse:
    """Pedido de Matías (2026-07-30): 5 recomendaciones semanales, iguales
    para todos — 3 de TMDb /trending/movie/week real + 2 de variedad de
    épocas (tmdb_client.WEEKLY_CLASSIC_SLOTS, pedido 2026-07-31: antes las
    5 daban siempre estrenos del año actual), sin curación editorial a
    mano en ningún lado. Público: sin sesión (o sin historial) se devuelven sin
    personalizar, con match_score neutro y why genérico — recommend() ya
    degrada así solo con ratings=[]. Con sesión y algo de historial, se
    puntúan contra el perfil real; si el LLM está configurado, además
    predice explícitamente si le va a gustar o no a esa persona en
    particular (llm_client.predict_fit, prompt de predicción, no de
    recomendación). exclude_seen=False a propósito: el catálogo acá es fijo
    (las mismas 5 para todos), así que ya haber puntuado/marcado vista
    alguna de esas 5 no puede hacerla desaparecer — solo afecta el
    match_score/why, nunca cuáles 5 se muestran."""
    if not tmdb_client.is_configured():
        raise HTTPException(status_code=503, detail="Catálogo de TMDb no configurado.")
    try:
        trending = tmdb_client.fetch_weekly_trending()
    except tmdb_client.TmdbError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not trending:
        raise HTTPException(status_code=502, detail="TMDb no devolvió películas en tendencia esta semana.")

    ratings = _rebuild_ratings(user["id"]) if user else []
    profile = db.get_taste_profile(user["id"]) if user else None

    # sin esto, match_score queda ciego a cualquier título amado sin reseña
    # (likes, favoritos, botones del modo manual) — se le escapaba a /weekly
    # porque /recommend lo hace en _finish_recommend pero acá nunca se
    # llamó (bug reportado por Matías, 2026-07-31: 50% match para Spider-Man
    # pese a que el "why" del LLM sí sabía que lo había amado).
    _enrich_loved_ratings_with_genre_tags(ratings)

    # min_score=0: acá el catálogo es un set fijo (las mismas 5 de la semana),
    # no un pool para elegir — el piso de recommender.MIN_MATCH_SCORE es para
    # /recommend, donde SÍ hay de dónde elegir. Un match débil en /weekly se
    # muestra igual, con su score bajo/S/D.
    heuristic = recommend(
        ratings, mood="", catalog=trending, also_seen=frozenset(), profile=profile,
        exclude_seen=False, min_score=0,
    )
    heuristic = _adjust_match_scores(heuristic)

    if user and ratings and llm_client.is_configured():
        try:
            return llm_client.predict_fit(user["id"], ratings, heuristic)
        except llm_client.LlmError as exc:
            logger.warning("Weekly LLM prediction failed, falling back to heuristic: %s", exc)

    return heuristic


@app.get("/titles/search", response_model=OnboardingTitlesResponse)
def titles_search(
    q: str, user: sqlite3.Row = Depends(auth.get_current_user)
) -> OnboardingTitlesResponse:
    """Buscador de la navbar (pedido de Matías, 2026-07-31): cualquier peli o
    serie, no solo las de la lista semilla del onboarding — de ahí
    search_any_titles (/search/multi) y no search_titles (movies-only).
    Degrada a lista vacía ante cualquier problema de TMDb: un buscador que
    devuelve nada es molesto, uno que tira 502 rompe la navbar entera."""
    if len(q.strip()) < 2 or not tmdb_client.is_configured():
        return OnboardingTitlesResponse(titles=[])
    try:
        results = tmdb_client.search_any_titles(q)
    except tmdb_client.TmdbError:
        return OnboardingTitlesResponse(titles=[])
    return OnboardingTitlesResponse(titles=[OnboardingTitle(**r) for r in results])


@app.get("/titles/{tmdb_id}/verdict", response_model=Recommendation)
def title_verdict(
    tmdb_id: int, kind: str = "movie", user: sqlite3.Row = Depends(auth.get_current_user)
) -> Recommendation:
    """El veredicto de Butaca sobre UN título que el usuario buscó: cuánto le
    va a gustar (match_score) y qué opina el agente (why).

    Deliberadamente la misma tubería que /weekly, paso por paso — enriquecer
    el título, enriquecer el historial, puntuar, ajustar score, veredicto del
    LLM — para que el número y el tono sean IGUALES a los de la home y
    /recommend. Ese es el pedido de Matías (2026-07-31): "que siempre sea lo
    mismo no importa dónde estés"."""
    if not tmdb_client.is_configured():
        raise HTTPException(status_code=503, detail="Catálogo de TMDb no configurado.")
    if kind not in ("movie", "series"):
        raise HTTPException(status_code=400, detail="Tipo de título inválido.")

    try:
        item = tmdb_client.fetch_title_by_id(tmdb_id, kind=kind)
    except tmdb_client.TmdbError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="No encontré ese título en TMDb.")

    tmdb_client.enrich_with_keyword_tags(item, kind)

    ratings = _rebuild_ratings(user["id"])
    profile = db.get_taste_profile(user["id"])
    _enrich_loved_ratings_with_genre_tags(ratings)

    # min_score=0: acá se opina sobre EL título que el usuario buscó, no se
    # elige de un pool — el veredicto tiene que salir aunque sea un mal match.
    heuristic = recommend(
        ratings, mood="", catalog=[item], also_seen=frozenset(), profile=profile,
        exclude_seen=False, min_score=0,
    )
    if not heuristic.recommendations:
        raise HTTPException(status_code=502, detail="No pude analizar ese título.")
    heuristic = _adjust_match_scores(heuristic)

    if ratings and llm_client.is_configured():
        try:
            heuristic = llm_client.predict_fit(user["id"], ratings, heuristic)
        except llm_client.LlmError as exc:
            logger.warning("Title verdict LLM failed, falling back to heuristic: %s", exc)

    return heuristic.recommendations[0]


def _require_admin_token(x_admin_token: str | None) -> None:
    # gated by a shared secret in BUTACA_ADMIN_TOKEN. When that env isn't
    # set (any environment that hasn't opted in) the endpoint 404s as if it
    # didn't exist, so it's never reachable in prod without deliberate setup.
    expected = os.environ.get("BUTACA_ADMIN_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=404, detail="No encontrado.")
    if not x_admin_token or not hmac.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=403, detail="Token de administrador inválido.")


@app.get("/admin/stats")
def admin_stats(x_admin_token: str | None = Header(default=None)) -> dict:
    _require_admin_token(x_admin_token)
    return db.get_admin_stats()


# corrido en un thread aparte (ver recompute_vibes): una corrida pesada de
# verdad (semilla nueva, cache frío) puede tardar 10+ min, y Render corta el
# request bastante antes de eso — devolver 200 al toque y dejar que el job
# siga en background saca ese riesgo del todo. _VIBE_RECOMPUTE_LOCK sigue
# siendo la única fuente de verdad sobre si hay una corrida en curso; este
# dict es solo para que /admin/vibes/recompute/status tenga algo que mostrar.
_VIBE_RECOMPUTE_STATE: dict = {"status": "idle"}


def _run_vibe_recompute() -> None:
    global _VIBE_RECOMPUTE_STATE
    try:
        result = vibes_clustering.recompute()
        _VIBE_RECOMPUTE_STATE = {"status": "done", "result": result}
    except (vibes_clustering.VibeError, tmdb_client.TmdbError) as exc:
        logger.warning("Vibe recompute failed: %s", exc)
        _VIBE_RECOMPUTE_STATE = {"status": "error", "error": str(exc)}
    finally:
        _VIBE_RECOMPUTE_LOCK.release()


@app.post("/admin/vibes/recompute")
def recompute_vibes(x_admin_token: str | None = Header(default=None)) -> dict:
    _require_admin_token(x_admin_token)
    if not _VIBE_RECOMPUTE_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="El recálculo de vibras ya está corriendo.")
    global _VIBE_RECOMPUTE_STATE
    _VIBE_RECOMPUTE_STATE = {"status": "running"}
    threading.Thread(target=_run_vibe_recompute, daemon=True).start()
    return {"status": "started"}


@app.get("/admin/vibes/recompute/status")
def vibe_recompute_status(x_admin_token: str | None = Header(default=None)) -> dict:
    _require_admin_token(x_admin_token)
    return _VIBE_RECOMPUTE_STATE


def _issue_email_verification(user_id: int, email: str | None) -> str:
    """Generate + persist a verification token and try to email it. Same
    degrade as the password reset flow: without Resend (or without an email on
    file) the mail is skipped and logged; the token is still returned so the
    caller can expose it under BUTACA_DEBUG for local testing."""
    token, token_hash = auth.create_email_verification_token()
    expires_at = auth.now_ts() + auth.EMAIL_VERIFICATION_TTL_SECONDS
    db.save_email_verification_token(user_id, token_hash, expires_at)

    if not mailer.is_configured():
        logger.warning("Verification email skipped: RESEND_API_KEY no está configurada.")
    elif not email:
        logger.warning("Verification email skipped: el usuario no tiene email cargado.")
    else:
        try:
            mailer.send_verification_email(email, token)
            logger.info("Verification email sent.")
        except mailer.MailError as exc:
            logger.warning("Verification email failed to send: %s", exc)

    return token


@app.post("/auth/register", response_model=RegisterResponse, status_code=201)
def register(payload: RegisterRequest) -> RegisterResponse:
    if db.get_user_by_username(payload.username) is not None:
        raise HTTPException(status_code=409, detail="Ese usuario ya existe.")

    password_hash, password_salt = auth.hash_password(payload.password)
    user_id = db.create_user(payload.username, password_hash, password_salt, payload.email)
    token = auth.create_token()
    db.create_session(token, user_id)

    verification_token = _issue_email_verification(user_id, payload.email)
    exposed = verification_token if _debug_mode() else None
    return RegisterResponse(token=token, username=payload.username, verification_token=exposed)


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


@app.post("/auth/verify-email", status_code=204)
def verify_email(payload: EmailVerificationConfirmRequest) -> None:
    # public like /auth/reset-password: the user clicks a mailed link and may
    # not have a live session in that tab
    token_record = db.get_email_verification_token(auth.hash_token(payload.token))
    if token_record is None or token_record["expires_at"] < auth.now_ts():
        raise HTTPException(status_code=400, detail="Token de verificación inválido o expirado.")
    db.mark_email_verified(token_record["user_id"])


@app.post("/auth/verify-email/resend", response_model=PasswordResetStartResponse)
def resend_verification(
    user: sqlite3.Row = Depends(auth.get_current_user),
) -> PasswordResetStartResponse:
    if user["email_verified"]:
        return PasswordResetStartResponse(status="ok", reset_token=None)
    token = _issue_email_verification(user["id"], user["email"])
    exposed = token if _debug_mode() else None
    return PasswordResetStartResponse(status="ok", reset_token=exposed)


@app.get("/auth/me")
def me(user: sqlite3.Row = Depends(auth.get_current_user)) -> dict:
    return {
        "username": user["username"],
        "email": user["email"],
        # never block features on this (see plan): it's a non-blocking prompt
        "email_verified": bool(user["email_verified"]),
        "letterboxd_username": user["letterboxd_username"],
    }


@app.put("/profile/letterboxd")
def set_letterboxd_username(
    payload: LetterboxdUsernameRequest, user: sqlite3.Row = Depends(auth.get_current_user)
) -> dict:
    """Tu cuenta de Letterboxd. Se autocompleta con el primer import por
    username; esto existe para corregirla (o desvincularla mandando "") si el
    primero fue el de otra persona. Ver recommend_titles_from_letterboxd por
    qué importa quién es el dueño."""
    db.set_letterboxd_username(user["id"], payload.letterboxd_username)
    return {"letterboxd_username": payload.letterboxd_username.strip() or None}


@app.post("/auth/logout", status_code=204)
def logout(authorization: str | None = Header(default=None)) -> None:
    if authorization and authorization.startswith("Bearer "):
        db.delete_session(authorization.removeprefix("Bearer ").strip())


@app.delete("/auth/account", status_code=204)
def delete_account(
    payload: DeleteAccountRequest,
    user: sqlite3.Row = Depends(auth.get_current_user),
) -> None:
    # re-confirm with the password: a leaked/borrowed session token must not be
    # enough to irreversibly wipe the account
    if not auth.verify_password(payload.password, user["password_hash"], user["password_salt"]):
        raise HTTPException(status_code=401, detail="Contraseña incorrecta.")
    db.delete_user_completely(user["id"], user["username"])


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


@app.get("/profile/summary")
def profile_summary(user: sqlite3.Row = Depends(auth.get_current_user)) -> dict:
    summary = db.get_profile_summary(user["id"])

    # avatar (feedback #16): un still de la peli mejor puntuada del usuario —
    # personal y determinístico en vez de random. Best-effort: sin TMDb (o si
    # falla la búsqueda) queda null y el frontend cae a la inicial.
    avatar_url = None
    if summary["top_title"]:
        try:
            match = tmdb_client.search_title(summary["top_title"])
            if match:
                avatar_url = match.get("backdrop_path") or match.get("poster_path")
        except Exception as exc:  # noqa: BLE001 - mismo criterio que _finish_recommend
            logger.warning("profile summary avatar lookup failed: %s", exc)
    summary["avatar_url"] = avatar_url
    return summary


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
            # el tmdb_id ya resuelto (RSS de username) evita una búsqueda por
            # texto — más rápido y sin riesgo de matchear un remake homónimo
            if item.tmdb_id is not None:
                match = tmdb_client.fetch_title_by_id(item.tmdb_id, "movie")
                if match:
                    return item, match
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


def _movement_candidates(vibe_tags: list[str]) -> list[dict]:
    """Resuelve contra TMDb los títulos que el clustering puso en cada
    movimiento elegido.

    No se puede pedir un movimiento a TMDb: los clusters son nuestros, salen
    de embeddings de metadata. Antes esto traía el pool genérico de discover
    y esperaba que se solapara con el cluster — medido sobre la muestra real
    (52 clusters L2, pool de 78 títulos), solo 3 de 52 movimientos juntaban
    los 6 picks; el resto devolvía casi nada. La membresía ya está en
    title_clusters, así que se resuelve directo por id (fetch_title_by_id
    cachea 24h, mismo patrón paralelo que _watchlist_candidates)."""
    if not tmdb_client.is_configured() or not vibe_tags:
        return []
    keys: list[tuple[int, str]] = []
    for tag in vibe_tags:
        keys.extend(db.get_cluster_member_keys(int(tag.split(":")[1]), MOVEMENT_MEMBER_CAP))

    def _resolve(key: tuple[int, str]) -> dict | None:
        try:
            return tmdb_client.fetch_title_by_id(key[0], kind=key[1])
        except tmdb_client.TmdbError:
            return None

    with ThreadPoolExecutor(max_workers=taste_profile.MATCH_WORKERS) as pool:
        results = pool.map(_resolve, keys)
    return [item for item in results if item]


def _add_vibe_cluster_tags(candidates: list[dict]) -> None:
    """Attach cached L2 tags without mutating TMDb cache-owned tag lists.

    Solo se llama cuando el usuario eligió un movimiento: el scoring de
    recommend() divide el match positivo por len(tags), así que un tag que
    nadie puede matchear DILUYE el score (mismo motivo por el que los keyword
    tags están capeados en 2 por título). Como solo los títulos de la muestra
    clusterizada lo reciben, colgarlo siempre penalizaría justo a esos frente
    a los que quedaron afuera de la muestra."""
    keys = list({(item["tmdb_id"], item["kind"]) for item in candidates if item.get("tmdb_id") is not None})
    assignments = db.get_title_clusters_by_tmdb_ids(keys)
    for item in candidates:
        cluster_id = assignments.get((item.get("tmdb_id"), item.get("kind")))
        if cluster_id is not None:
            item["tags"] = sorted(set(item["tags"]) | {f"vibe-l2:{cluster_id}"})


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
    persist: bool = True,
    ephemeral: bool = False,
) -> RecommendResponse:
    """Shared tail of both /recommend/zip and /recommend/letterboxd: once a
    source has produced (ratings, extra_seen), the rest of the flow —
    candidates, exclusion, scoring, LLM refine, persistence — is identical.
    refine=False skips the (slow) LLM step and returns the heuristic picks
    immediately; the frontend then calls /recommend/sessions/{id}/refine to
    swap in the LLM-written reasons without blocking the first render.
    persist=False when ratings were just read back from the DB (the "usar mi
    perfil" shortcut) — re-saving them would insert duplicate rated_items."""
    _enforce_recommend_rate_limit(user["id"])

    if not ratings:
        raise HTTPException(
            status_code=400,
            detail="No encontré ratings ni reviews usables para armar recomendaciones.",
        )

    _enrich_loved_ratings_with_genre_tags(ratings)

    if persist:
        # save ratings before computing the taste profile (moved up from the
        # end of this function) so the profile reflects this import and can
        # bias *this* request's own candidates below, not just future ones —
        # see docs/(C) plan-de-trabajo.md §4 for why this used to run too late.
        db.save_rated_items(
            user["id"],
            [
                (item.title, item.rating, item.review, item.watched_date, item.source, item.tmdb_id)
                for item in ratings
            ],
        )

    # el historial completo del usuario, sin importar la fuente (zip,
    # username, manual) — hoisted acá arriba porque tanto el perfil como la
    # exclusión de "ya vistas" más abajo tienen que leer del mismo lugar
    watched = [item.model_dump() for item in ratings] if ephemeral else db.get_watched_items(user["id"])

    # Guarded broadly: this is a personalization/caching side effect, not the
    # point of the request — a TMDb hiccup (or a mocked search_title missing
    # fields it expects, see TASKS.md) should degrade to the unpersonalized
    # pool below, not fail an otherwise-servable recommend call.
    profile: dict | None = None
    if tmdb_client.is_configured():
        try:
            profile = taste_profile.build_taste_profile(watched)
            if not ephemeral:
                db.save_taste_profile(user["id"], profile)
        except Exception:
            logger.warning("Taste profile computation failed, falling back to unpersonalized candidates", exc_info=True)
            profile = None

    # parseo de "a tu elección" ANTES del fetch de candidatos — el picker
    # maneja su propio pedido a TMDb (fetch_candidates_for_options), no
    # post-filtra el pool de perfil/mood como antes (bug reportado
    # 2026-08-02: opciones angostas nunca traían señal suficiente).
    selected_genres = [key.strip() for key in genres.split(",") if key.strip()]
    if len(selected_genres) > MAX_SELECTED_OPTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Elegí como mucho {MAX_SELECTED_OPTIONS} opciones.",
        )
    # tupla ordenada (orden de selección), una entrada por opción elegida —
    # no un frozenset aplanado (bug reportado 2026-08-02: cobertura por tag
    # suelto, no por opción, con orden de iteración no determinístico).
    vibe_labels = {
        f"vibe-l2:{row['cluster_id']}": row["label"]
        for row in db.get_vibe_clusters(level=2)
    }
    selected_static_options = [key for key in selected_genres if key in GENRE_OPTIONS]
    selected_vibe_tags = [key for key in selected_genres if key in vibe_labels]
    required_any_groups = tuple(
        [frozenset(GENRE_OPTIONS[key]) for key in selected_static_options]
        + [frozenset({tag}) for tag in selected_vibe_tags]
    )
    if mode == "genres" and not required_any_groups:
        raise HTTPException(
            status_code=400, detail="Elegí al menos un género para este modo."
        )

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
    elif mode == "genres":
        candidates = catalog.CATALOG
        if tmdb_client.is_configured():
            try:
                candidates = tmdb_client.fetch_candidates_for_options(selected_static_options, kind_filter)
                # cada movimiento aporta sus propios títulos (los del cluster),
                # igual que cada género aporta su propio fetch dirigido.
                candidates += _movement_candidates(selected_vibe_tags)
                seen_candidates: set[tuple[int | None, str]] = set()
                deduped_candidates = []
                for item in candidates:
                    key = (item.get("tmdb_id"), item["kind"])
                    if key not in seen_candidates:
                        seen_candidates.add(key)
                        deduped_candidates.append(item)
                candidates = deduped_candidates
            except tmdb_client.TmdbError as exc:
                logger.warning("TMDb options fetch failed, falling back to mock catalog: %s", exc)
                candidates = catalog.CATALOG
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

    if selected_vibe_tags:
        _add_vibe_cluster_tags(candidates)

    # explicit feedback is a hard exclusion, unlike "already recommended"
    # (relaxed on retry below): a title the user marked seen or not_interested
    # must never resurface, so fold it into extra_seen up front. The tags of
    # not_interested picks feed a scoring penalty in recommend().
    feedback = (
        {"seen_titles": [], "not_interested": []}
        if ephemeral
        else db.get_feedback_signals(user["id"])
    )
    extra_seen = set(extra_seen) | set(feedback["seen_titles"]) | {
        item["title"] for item in feedback["not_interested"]
    }
    rejected_tags: Counter[str] = Counter()
    for item in feedback["not_interested"]:
        rejected_tags.update(item["tags"])

    # exclude titles already recommended to this user before, so hitting
    # "nuevos picks" and regenerating with the same source+mood surfaces
    # different movies instead of the same deterministic top 5
    already_recommended = set() if ephemeral else db.get_recently_recommended_titles(user["id"])
    # bug real (reportado por Matías, 2026-07-30): puntuar en "Sin cuenta" y
    # después generar con el .zip/username de Letterboxd (u otra sesión
    # manual) recomendaba de vuelta esas mismas películas — `extra_seen`
    # solo trae lo puntuado EN ESTE request puntual, `ratings` acá abajo
    # también, así que una fuente nueva no sabía nada de lo puntuado por
    # otra. `watched` (arriba) es el historial completo y unificado sin
    # importar la fuente — se suma acá para que la exclusión sea real
    # "todo lo que alguna vez viste", no solo "lo que trajo este import".
    also_seen = (
        frozenset(extra_seen)
        | frozenset(already_recommended)
        | frozenset(item["title"] for item in watched)
    )

    # "según lo último que vi" narrows the taste signal to the user's most
    # recently watched titles instead of their whole history — exclusion
    # (also_seen) now genuinely covers everything they've ever watched,
    # regardless of source
    preference_ratings = None
    if mode == "recent":
        preference_ratings = sorted(
            ratings, key=lambda item: item.watched_date, reverse=True
        )[:RECENT_WINDOW]

    pairwise_win_counts = db.get_pairwise_win_counts(user["id"])

    def _score(pool: list[dict], seen: frozenset[str], limit: int) -> RecommendResponse:
        return recommend(
            ratings,
            mood,
            catalog=pool,
            also_seen=seen,
            kind_filter=kind_filter,
            required_any_groups=required_any_groups or None,
            preference_ratings=preference_ratings,
            profile=profile,
            rejected_tags=rejected_tags or None,
            limit=limit,
            extra_phrases=vibe_labels,
            pairwise_win_counts=pairwise_win_counts,
        )

    use_llm = refine and llm_client.is_configured()
    candidate_limit = 12 if use_llm else 6
    response = _score(candidates, also_seen, candidate_limit)

    # un match < recommender.MIN_MATCH_SCORE ya viene descartado de response
    # (invariante de Matías, TASKS.md 2026-08-02) — si eso deja el pool corto,
    # se pide un pool más grande a TMDb antes de resignarse a mostrar menos
    # de 6. No aplica a watchlist: ese catálogo es un set cerrado del import,
    # no hay "más" para pedir.
    if mode != "watchlist" and len(response.recommendations) < 6 and tmdb_client.is_configured():
        # guardado ancho a propósito, igual que el resto de los
        # enriquecimientos best-effort de esta función: esto es un intento
        # extra por conseguir más picks fuertes, nunca debe tumbar un
        # /recommend que ya tiene una respuesta válida (aunque corta).
        try:
            # mode="genres" con fetch_candidates(mood, pages=4) desperdiciaba
            # 4 páginas enteras: esos ítems no llevan tag de ninguna opción
            # elegida, así que el filtro duro de recommend() los descartaba a
            # todos (bug encontrado 2026-08-02 diseñando este picker).
            # un movimiento es un set cerrado (los miembros del cluster, ya
            # traídos enteros arriba): pedir más páginas de discover para él
            # es el mismo desperdicio que describe el comentario de arriba,
            # así que solo se ensanchan las opciones estáticas.
            broader = (
                tmdb_client.fetch_candidates_for_options(selected_static_options, kind_filter, pages=3)
                if mode == "genres"
                else tmdb_client.fetch_candidates(mood, pages=4)
            )
        except Exception:
            logger.warning("Broader TMDb candidate fetch failed, keeping the shorter pool", exc_info=True)
            broader = []
        if broader:
            logger.info("Strong-match pool too small (%d), fetching a broader TMDb pool", len(response.recommendations))
            existing_titles = {item["title"].casefold() for item in candidates}
            candidates = candidates + [
                item for item in broader if item["title"].casefold() not in existing_titles
            ]
            if selected_vibe_tags:
                _add_vibe_cluster_tags(candidates)
            response = _score(candidates, also_seen, candidate_limit)

    # Only reintroduce old picks when there aren't six genuinely new ones.
    # Filling the LLM's 12-candidate shortlist with old high-scoring titles
    # made "Nuevos picks" select the exact same six again.
    filled_with_old = False
    if len(response.recommendations) < 6 and already_recommended:
        logger.info("Candidate pool partially exhausted by already-recommended exclusion, filling without it")
        # solo se relaja already_recommended (soft, "no lo repitas de vuelta
        # tan rápido") — extra_seen/watched siguen siendo hard exclusions,
        # nunca hay que recomendar algo que el usuario ya vio de verdad
        relaxed = _score(
            candidates,
            frozenset(extra_seen) | frozenset(item["title"] for item in watched),
            6,
        )

        existing = {item.title.casefold() for item in response.recommendations}
        for item in relaxed.recommendations:
            if item.title.casefold() not in existing:
                response.recommendations.append(item)
                existing.add(item.title.casefold())
                filled_with_old = True
            if len(response.recommendations) == 6:
                break

    refined = False
    if refine and not use_llm:
        logger.warning("LLM refine skipped: NVIDIA_API_KEY no está configurada.")
    elif use_llm:
        try:
            # predict_fit preserves the chosen set. refine_recommendations is
            # allowed to drop candidates, so after a fallback fill it could
            # discard every genuinely new title in favor of old high scorers.
            response = (
                llm_client.predict_fit(user["id"], ratings, response)
                if filled_with_old
                else llm_client.refine_recommendations(ratings, mood, response)
            )
            refined = True
        except llm_client.LlmError as exc:
            logger.warning("LLM refine failed, falling back to heuristic why: %s", exc)

    response.recommendations = response.recommendations[:6]

    session_id = None
    if ephemeral:
        for index, item in enumerate(response.recommendations, start=1):
            item.id = -index
    else:
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
    response.ephemeral = ephemeral
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

    # Pedido de Matías (2026-07-31): "capaz le estás mostrando la página a algún
    # amigo y pone su usuario y te cambia todos tus ratings de Butaca".
    # Importar persiste al perfil, así que el username tiene dueño: el primero
    # que se usa queda registrado como tuyo, y cualquier otro genera
    # recomendaciones sin guardar nada (persist=False).
    stored_username = (user["letterboxd_username"] or "").strip().lower()
    requested_username = username.strip().lower()
    if not stored_username:
        db.set_letterboxd_username(user["id"], username)
    is_own_account = not stored_username or stored_username == requested_username

    return _finish_recommend(
        ratings, extra_seen, mood, mode, kind_filter, genres, user,
        refine=_refine_enabled(refine) if is_own_account else True,
        persist=is_own_account,
        ephemeral=not is_own_account,
    )


@app.get("/onboarding/titles", response_model=OnboardingTitlesResponse)
def onboarding_titles_endpoint(
    user: sqlite3.Row = Depends(auth.get_current_user),
) -> OnboardingTitlesResponse:
    """Títulos semilla para un usuario sin Letterboxd, mezclados con
    cualquier título que ya haya puntuado antes (de cualquier fuente, no solo
    modo manual) para que vuelva y vea sus propias puntuaciones precargadas y
    editables — reemplaza el banner "Usar mi perfil", que era todo o nada:
    una vez usado no dejaba sumar títulos nuevos ni cambiar los ya puntuados.
    Posters/ids se resuelven contra TMDb en paralelo (mismo patrón que
    _watchlist_candidates); sin TMDb key degradan a title/year solo
    (poster_path=None)."""
    seeds = onboarding_titles.ONBOARDING_TITLES
    watched = db.get_watched_items(user["id"])
    rating_by_title = {
        item["title"].strip().lower(): (item["rating"], item.get("source", "import"))
        for item in watched
    }

    seed_keys = {seed["title"].strip().lower() for seed in seeds}
    # títulos puntuados que no están en la lista semilla (sumados a mano en
    # una sesión anterior vía /onboarding/search, o traídos de un zip/username
    # previo): sin año curado, se resuelven contra TMDb por título solo, mismo
    # best-effort que search_title ya usa en el resto del proyecto
    extra = [
        {"title": item["title"], "year": None}
        for item in watched
        if item["title"].strip().lower() not in seed_keys
    ]
    entries = seeds + extra

    matches: dict[str, dict | None] = {}
    if tmdb_client.is_configured():
        def _match(entry: dict) -> tuple[str, dict | None]:
            try:
                # el año curado fija la película exacta — sin él, "Toy Story"
                # resolvía al Toy Story 5 en cartelera, no al de 1995
                return entry["title"], tmdb_client.search_title(entry["title"], entry.get("year"))
            except tmdb_client.TmdbError:
                return entry["title"], None

        with ThreadPoolExecutor(max_workers=taste_profile.MATCH_WORKERS) as pool:
            matches = dict(pool.map(_match, entries))

    titles = [
        OnboardingTitle(
            title=entry["title"],
            year=entry["year"] or (matches.get(entry["title"]) or {}).get("year") or 0,
            kind=(matches.get(entry["title"]) or {}).get("kind") or "movie",
            tmdb_id=(matches.get(entry["title"]) or {}).get("tmdb_id"),
            poster_path=(matches.get(entry["title"]) or {}).get("poster_path"),
            rating=(rating_by_title.get(entry["title"].strip().lower()) or (None, None))[0],
            rating_source=(rating_by_title.get(entry["title"].strip().lower()) or (None, None))[1],
        )
        for entry in entries
    ]
    return OnboardingTitlesResponse(titles=titles)


@app.get("/onboarding/search", response_model=OnboardingTitlesResponse)
def onboarding_search_endpoint(
    q: str,
    user: sqlite3.Row = Depends(auth.get_current_user),
) -> OnboardingTitlesResponse:
    """Search TMDb for a film the user has seen but that isn't in the seed
    list, so they can add it to their onboarding ratings. Degrades to an empty
    list without a TMDb key or on any TMDb hiccup — a failed search must not
    block onboarding."""
    if len(q.strip()) < 2 or not tmdb_client.is_configured():
        return OnboardingTitlesResponse(titles=[])
    try:
        results = tmdb_client.search_titles(q)
    except tmdb_client.TmdbError:
        return OnboardingTitlesResponse(titles=[])
    return OnboardingTitlesResponse(titles=[OnboardingTitle(**r) for r in results])


def _unwatched_candidate_pool(user_id: int, count: int, extra_exclude: set[str] = frozenset()) -> list[dict]:
    """Tanda random de títulos sin puntuar, dicts crudos con shape de TMDb
    (title/year/kind/tmdb_id/poster_path). Sale de title_clusters (la
    muestra clusterizada de la Fase 4, variada por construcción) en vez de
    discover por popularidad — mismo motivo que la semilla de vibras:
    discover ordenado por popularidad muestra siempre los mismos
    blockbusters. Se completa con onboarding_titles.py si el cluster no
    alcanza (usuario con casi todo puntuado, o title_clusters vacío/sin
    correr la Fase 4 en este ambiente). Compartido por /titles/swipe-batch y
    el juego "¿cuál te gustó más?"."""
    if not tmdb_client.is_configured():
        return []

    watched_titles = {item["title"].strip().lower() for item in db.get_watched_items(user_id)}
    seen_titles = watched_titles | extra_exclude

    def _resolve_by_id(key: tuple[int, str]) -> dict | None:
        try:
            return tmdb_client.fetch_title_by_id(key[0], kind=key[1])
        except tmdb_client.TmdbError:
            return None

    cluster_keys = db.get_random_cluster_keys(count * SWIPE_CLUSTER_OVERSAMPLE)
    with ThreadPoolExecutor(max_workers=taste_profile.MATCH_WORKERS) as pool:
        resolved = list(pool.map(_resolve_by_id, cluster_keys))

    picked = []
    for item in resolved:
        if not item:
            continue
        key = item["title"].strip().lower()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        picked.append(item)

    if len(picked) < count:
        extra_seed = [t for t in onboarding_titles.ONBOARDING_TITLES if t["title"].strip().lower() not in seen_titles]

        def _match_curated(entry: dict) -> dict | None:
            try:
                return tmdb_client.search_title(entry["title"], entry.get("year"))
            except tmdb_client.TmdbError:
                return None

        with ThreadPoolExecutor(max_workers=taste_profile.MATCH_WORKERS) as pool:
            extra_resolved = list(pool.map(_match_curated, extra_seed))
        for item in extra_resolved:
            if not item:
                continue
            key = item["title"].strip().lower()
            if key in seen_titles:
                continue
            seen_titles.add(key)
            picked.append(item)

    random.shuffle(picked)
    return picked[:count]


@app.get("/titles/swipe-batch", response_model=OnboardingTitlesResponse)
def swipe_batch(user: sqlite3.Row = Depends(auth.get_current_user)) -> OnboardingTitlesResponse:
    """Tanda random de títulos sin puntuar para la sección de swipe "marcá lo
    que viste" (idea de Matías, 2026-08-02): un lugar donde volver cuando
    quiera y sumar de a poco, sin depender del onboarding (una vez) o un
    reimport de Letterboxd."""
    picked = _unwatched_candidate_pool(user["id"], SWIPE_BATCH_SIZE)
    titles = [
        OnboardingTitle(
            title=item["title"],
            year=item.get("year") or 0,
            kind=item.get("kind") or "movie",
            tmdb_id=item.get("tmdb_id"),
            poster_path=item.get("poster_path"),
        )
        for item in picked
    ]
    return OnboardingTitlesResponse(titles=titles)


def _resolve_watched_title(row: dict) -> dict | None:
    """rated_items solo guarda title/tmdb_id -- year/poster se resuelven
    contra TMDb al vuelo (mismo patrón que /onboarding/titles). tmdb_id sin
    "kind" en el schema viene del tmdb:movieId del feed de username, así que
    asumir "movie" ahí es consistente con el resto del proyecto."""
    try:
        if row.get("tmdb_id"):
            return tmdb_client.fetch_title_by_id(row["tmdb_id"], kind="movie")
        return tmdb_client.search_title(row["title"])
    except tmdb_client.TmdbError:
        return None


def _pairwise_tied_pair(user_id: int) -> tuple[dict, dict] | tuple[None, None]:
    """Dos títulos que el usuario YA vio y puntuó IGUAL -- comparar
    preferencia sobre algo no visto no tiene sentido (bug real reportado por
    Matías, 2026-08-03: el juego venía de un pool de títulos sin ver, y
    elegir cualquiera de los dos los marcaba como vistos+gustados en la
    bitácora sin que el usuario los hubiera visto nunca). Empatar en rating
    además hace que la comparación sirva de desempate real más adelante
    (ver recommender._find_reference_title)."""
    watched = db.get_watched_items(user_id)
    by_rating: dict[float, list[dict]] = {}
    for item in watched:
        by_rating.setdefault(item["rating"], []).append(item)
    tied_groups = [group for group in by_rating.values() if len(group) >= 2]
    if not tied_groups:
        return None, None
    a, b = random.sample(random.choice(tied_groups), 2)
    return a, b


@app.get("/games/pairwise", response_model=PairwiseMatchResponse)
def pairwise_match(user: sqlite3.Row = Depends(auth.get_current_user)) -> PairwiseMatchResponse:
    """Un par de títulos que el usuario YA vio y puntuó igual, para el juego
    "¿cuál te gustó más?". None en cualquiera de los dos lados si no hay dos
    títulos empatados en rating (historial muy chico, o todos con ratings
    distintos) -- el frontend lo trata igual que un pool agotado."""
    if not tmdb_client.is_configured():
        return PairwiseMatchResponse()
    row_a, row_b = _pairwise_tied_pair(user["id"])
    if row_a is None or row_b is None:
        return PairwiseMatchResponse()
    resolved_a, resolved_b = _resolve_watched_title(row_a), _resolve_watched_title(row_b)
    if not resolved_a or not resolved_b:
        return PairwiseMatchResponse()

    def _to_option(row: dict, resolved: dict) -> OnboardingTitle:
        return OnboardingTitle(
            title=row["title"],
            year=resolved.get("year") or 0,
            kind=resolved.get("kind") or "movie",
            tmdb_id=resolved.get("tmdb_id") or row.get("tmdb_id"),
            poster_path=resolved.get("poster_path"),
        )

    return PairwiseMatchResponse(left=_to_option(row_a, resolved_a), right=_to_option(row_b, resolved_b))


@app.post("/games/pairwise/choose", status_code=201)
def pairwise_choose(
    payload: PairwiseChoiceRequest, user: sqlite3.Row = Depends(auth.get_current_user)
) -> dict[str, str]:
    """El ganador ya tiene un rating real -- los dos títulos vienen del
    propio historial del usuario, no se inventa un rating nuevo. Se guarda
    como preferencia relativa (pairwise_preferences), que
    recommender._find_reference_title usa para desempatar entre "amados"
    con el mismo rating al elegir a cuál citar en el "why"."""
    db.record_pairwise_preference(user["id"], payload.winner_title, payload.loser_title)
    return {"status": "recorded"}


def _year_trivia_question(subject: dict, others: list[dict]) -> TriviaQuestion | None:
    distractor_years = {
        item["year"] for item in others if item.get("year") and item["year"] != subject.get("year")
    }
    if not subject.get("year") or len(distractor_years) < TRIVIA_OPTION_COUNT - 1:
        return None
    options = [str(subject["year"])] + [str(y) for y in list(distractor_years)[: TRIVIA_OPTION_COUNT - 1]]
    random.shuffle(options)
    return TriviaQuestion(
        title=subject["title"],
        poster_path=subject.get("poster_path"),
        question=f'¿De qué año es "{subject["title"]}"?',
        options=options,
        correct_answer=str(subject["year"]),
    )


def _director_trivia_question(subject: dict, others: list[dict]) -> TriviaQuestion | None:
    def _director_of(item: dict) -> str | None:
        try:
            return tmdb_client.fetch_taste_credits(item["tmdb_id"], kind=item.get("kind", "movie")).get("director")
        except tmdb_client.TmdbError:
            return None

    correct = _director_of(subject) if subject.get("tmdb_id") else None
    if not correct:
        return None

    with ThreadPoolExecutor(max_workers=taste_profile.MATCH_WORKERS) as pool:
        other_directors = list(pool.map(_director_of, others))
    distractors = {d for d in other_directors if d and d != correct}
    if len(distractors) < TRIVIA_OPTION_COUNT - 1:
        return None

    options = [correct] + list(distractors)[: TRIVIA_OPTION_COUNT - 1]
    random.shuffle(options)
    return TriviaQuestion(
        title=subject["title"],
        poster_path=subject.get("poster_path"),
        question=f'¿Quién dirigió "{subject["title"]}"?',
        options=options,
        correct_answer=correct,
    )


def _build_trivia_question(user_id: int) -> TriviaQuestion | None:
    """Puro entretenimiento (Matías la pidió sabiendo que no genera señal de
    gusto, a diferencia de "¿cuál te gustó más?"). "year" es más robusto (ya
    viene resuelto, sin request extra) que "director" (necesita credits de
    varios títulos y puede no alcanzar distractores distintos) — se
    reintenta con un pool random nuevo en cada intento en vez de fallar en
    silencio ante un pool desfavorable puntual."""
    for _ in range(TRIVIA_ATTEMPTS):
        pool = _unwatched_candidate_pool(user_id, TRIVIA_OPTION_COUNT + 1)
        if len(pool) < TRIVIA_OPTION_COUNT + 1:
            continue
        subject, *others = pool
        builder = _director_trivia_question if random.random() < 0.4 else _year_trivia_question
        question = builder(subject, others)
        if question is not None:
            return question
    return None


@app.get("/games/trivia", response_model=TriviaQuestion | None)
def trivia_question(user: sqlite3.Row = Depends(auth.get_current_user)) -> TriviaQuestion | None:
    """Trivia de director/año sobre títulos del mismo pool que
    /titles/swipe-batch. None cuando no se pudo armar una pregunta con
    distractores reales suficientes (pool muy chico) -- el frontend lo trata
    igual que el pool agotado del pairwise, ofreciendo reintentar."""
    return _build_trivia_question(user["id"])


@app.post("/recommend/manual", response_model=RecommendResponse)
def recommend_titles_manual(
    payload: ManualRecommendRequest,
    user: sqlite3.Row = Depends(auth.get_current_user),
) -> RecommendResponse:
    """Onboarding without Letterboxd: the user rated a handful of seed titles
    by hand. Build RatedItems and hand off to the shared _finish_recommend."""
    _validate_recommend_params(payload.mode, payload.kind_filter)

    if len(payload.ratings) < MIN_MANUAL_RATINGS:
        raise HTTPException(
            status_code=400,
            detail=f"Puntuá al menos {MIN_MANUAL_RATINGS} títulos para armar tu perfil.",
        )

    ratings = [
        RatedItem(title=item.title, rating=item.rating, source="star") for item in payload.ratings
    ]
    # every rated title is one the user has seen — never recommend it back
    extra_seen = {item.title for item in ratings}

    return _finish_recommend(
        ratings,
        extra_seen,
        payload.mood,
        payload.mode,
        payload.kind_filter,
        payload.genres,
        user,
        refine=payload.refine,
    )


@app.post("/recommend/profile", response_model=RecommendResponse)
def recommend_titles_from_profile(
    payload: ProfileRecommendRequest,
    user: sqlite3.Row = Depends(auth.get_current_user),
) -> RecommendResponse:
    """Regenerar picks con el perfil ya guardado, sin pedir la fuente de
    nuevo — feedback: los usuarios de modo manual tenían que re-puntuar las
    mismas pelis cada vez que volvían, aunque el perfil ya estaba guardado."""
    _validate_recommend_params(payload.mode, payload.kind_filter)

    ratings = _rebuild_ratings(user["id"])
    if len(ratings) < MIN_MANUAL_RATINGS:
        raise HTTPException(
            status_code=400,
            detail="Todavía no tenés un perfil guardado — importá tu historial primero.",
        )

    return _finish_recommend(
        ratings, set(), payload.mood, payload.mode, payload.kind_filter, payload.genres,
        user, refine=payload.refine, persist=False,
    )


@app.post("/recommend/sessions/{session_id}/refine", response_model=RecommendResponse)
def refine_session(
    session_id: int, user: sqlite3.Row = Depends(auth.get_current_user)
) -> RecommendResponse:
    """Second half of progressive rendering: re-run the LLM over a session's
    already-served heuristic picks and persist the rewritten reasons. Returns
    refined=False (200, not an error) when the LLM isn't configured or fails,
    so the frontend just keeps the heuristic text.

    Usa predict_fit y NO refine_recommendations aunque el nombre diga "refine":
    los picks de esta sesión YA se le mostraron al usuario, así que la tarea es
    opinar sobre un set fijo, no elegir de un pool. refine_recommendations
    elige y descarta — devolvía menos picks de los que la sesión tenía, y los
    que no cubría se quedaban con el why heurístico persistido para siempre.
    Eso es lo que Matías vio en "Current picks" de la home (2026-07-31): 1 de 3
    con voz del LLM y 2 con el texto genérico del motor."""
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

    if not llm_client.is_configured():
        logger.warning("Session refine skipped: NVIDIA_API_KEY no está configurada.")
        return heuristic
    if not recommendations:
        return heuristic

    try:
        refined = llm_client.predict_fit(
            user["id"], _rebuild_ratings(user["id"]), heuristic
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
    tmdb_id: int,
    kind: str = "movie",
    title: str = "",
    user: sqlite3.Row = Depends(auth.get_current_user),
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

    rated = db.get_preferred_rated_item(user["id"], title, tmdb_id)
    return MovieDetails(
        cast=cast,
        trailer_key=trailer_key,
        providers=providers,
        user_rating=rated["rating"] if rated else None,
        rating_source=rated["source"] if rated else None,
    )


@app.get("/movies/{tmdb_id}/similar", response_model=OnboardingTitlesResponse)
def similar_titles(
    tmdb_id: int, kind: str = "movie", user: sqlite3.Row = Depends(auth.get_current_user)
) -> OnboardingTitlesResponse:
    """Botón "no estoy de acuerdo con el match" del modal (pedido de
    Matías, 2026-07-31): si un título llega sin evidencia real en el
    perfil (ej. ama a Spider-Man pero nunca puntuó nada de esa saga),
    ofrece similares de TMDb para votar — mismo shape que
    /onboarding/titles, así el frontend reusa la misma grilla de rating."""
    if not tmdb_client.is_configured():
        raise HTTPException(status_code=503, detail="Catálogo de TMDb no configurado.")
    try:
        similar = tmdb_client.fetch_similar_titles(tmdb_id, kind=kind)
    except tmdb_client.TmdbError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return OnboardingTitlesResponse(
        titles=[
            OnboardingTitle(
                title=item["title"],
                year=item["year"],
                kind=item["kind"],
                tmdb_id=item.get("tmdb_id"),
                poster_path=item.get("poster_path"),
            )
            for item in similar
        ]
    )


@app.post("/feedback", status_code=201)
def submit_feedback(
    payload: FeedbackRequest, user: sqlite3.Row = Depends(auth.get_current_user)
) -> dict[str, str]:
    recommendation = db.get_recommendation(payload.recommendation_id, user["id"])
    if recommendation is None:
        raise HTTPException(status_code=404, detail="Recomendación no encontrada.")

    db.save_feedback(user["id"], payload.recommendation_id, payload.status)
    return {"status": "ok"}


@app.post("/profile/rate", status_code=201)
def rate_title(
    payload: RateTitleRequest, user: sqlite3.Row = Depends(auth.get_current_user)
) -> dict[str, str | float]:
    """Guarda un rating explícito de Butaca, en pasos de media estrella."""
    existing = db.get_preferred_rated_item(
        user["id"], payload.title, payload.tmdb_id
    )
    if existing and existing["source"] == "import":
        return {
            "status": "preserved",
            "rating": existing["rating"],
            "source": "import",
        }
    db.save_rated_items(
        user["id"], [(payload.title, payload.rating, "", "", "star", payload.tmdb_id)]
    )
    db.invalidate_taste_profile(user["id"])
    return {"status": "saved", "rating": payload.rating, "source": "star"}
