from typing import Literal

from pydantic import BaseModel, Field


class RatedItem(BaseModel):
    title: str
    rating: float = Field(ge=0, le=5)
    review: str = ""
    watched_date: str = ""
    tags: list[str] = Field(default_factory=list)
    # 'import' = rating numerico real de Letterboxd (zip/username). 'star' =
    # rating preciso del selector actual de Butaca. 'manual' = rating sintético
    # histórico de los tres botones viejos. 'like' = like/favorito de
    # Letterboxd sin estrellas puestas. 'game' = ganador inferido del juego
    # "¿cuál te gustó más?" (comparación pairwise).
    # 'manual', 'like' y 'game' llevan un rating sintetico — el llm_client usa
    # esto para no citarlo con una precisión de "(4.5/5)" que el usuario nunca dio.
    source: Literal["import", "manual", "like", "star", "game"] = "import"
    # id de TMDb ya resuelto, cuando la fuente lo trae (tmdb:movieId del feed
    # RSS de username) — evita una búsqueda por texto (más rápido, sin
    # riesgo de matchear un remake con el mismo nombre) en
    # _enrich_loved_ratings_with_genre_tags y taste_profile.build_taste_profile
    tmdb_id: int | None = None


class RecommendRequest(BaseModel):
    mood: str = ""
    ratings: list[RatedItem] = Field(default_factory=list)


class ManualRating(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    rating: float = Field(ge=0.5, le=5, multiple_of=0.5)


class ManualRecommendRequest(BaseModel):
    # onboarding without Letterboxd: the user rated a handful of seed titles
    ratings: list[ManualRating] = Field(default_factory=list)
    mood: str = ""
    mode: str = "profile"
    kind_filter: str = "both"
    genres: str = ""
    refine: bool = True


class ProfileRecommendRequest(BaseModel):
    # regenerate picks from the profile already saved in the DB, no new
    # source needed — the "usar mi perfil" shortcut for repeat manual users
    mood: str = ""
    mode: str = "profile"
    kind_filter: str = "both"
    genres: str = ""
    refine: bool = True


class OnboardingTitle(BaseModel):
    title: str
    year: int
    kind: str = "movie"
    tmdb_id: int | None = None
    poster_path: str | None = None
    # solo se llena en /onboarding/titles para un título que el usuario ya
    # puntuó antes (de cualquier fuente) — precarga la grilla manual en vez
    # de forzar a re-puntuar lo mismo cada sesión
    rating: float | None = None
    rating_source: Literal["import", "manual", "like", "star", "game"] | None = None


class OnboardingTitlesResponse(BaseModel):
    titles: list[OnboardingTitle]


class PairwiseMatchResponse(BaseModel):
    """Un par para el juego "¿cuál te gustó más?" — None en cualquiera de
    los dos lados si no se pudo armar un par completo (pool agotado)."""

    left: OnboardingTitle | None = None
    right: OnboardingTitle | None = None


class PairwiseChoiceRequest(BaseModel):
    # ambos títulos ya vienen del historial del usuario (ver /games/pairwise)
    # con un rating real propio -- esto no persiste un rating nuevo, solo la
    # preferencia relativa (winner sobre loser) para desempatar más adelante.
    winner_title: str = Field(min_length=1, max_length=300)
    loser_title: str = Field(min_length=1, max_length=300)


class TriviaQuestion(BaseModel):
    # puro entretenimiento (Matías lo pidió sabiendo que no genera señal de
    # gusto, a diferencia del pairwise) -- no se persiste nada, el puntaje
    # vive solo en el cliente. correct_answer viaja en la respuesta porque no
    # hay nada sensible que proteger acá.
    title: str
    poster_path: str | None = None
    question: str
    options: list[str]
    correct_answer: str


class CatalogStatsResponse(BaseModel):
    movies: int
    series: int
    genres: int


class PickOption(BaseModel):
    key: str
    label: str
    group: str


class PickOptionsResponse(BaseModel):
    options: list[PickOption]


class Recommendation(BaseModel):
    id: int | None = None
    tmdb_id: int | None = None
    title: str
    year: int
    kind: str
    why: str
    match_score: int
    tags: list[str]
    director: str | None = None
    poster_path: str | None = None
    backdrop_path: str | None = None
    overview: str = ""
    vote_average: float | None = None
    # a diferencia de RecommendResponse.refined (todo el lote), esto es por
    # pick: cuando el LLM inventa un título fuera de la lista de candidatos
    # (medido: "Zodiac"/"Obsession"), ese hueco se rellena con el heurístico
    # tal cual, y sin esto no había forma de distinguir esas cards en pantalla
    # de las que sí tienen un why del LLM (2026-08-03, TASKS.md).
    refined: bool = False


class RecommendResponse(BaseModel):
    taste_summary: str
    recommendations: list[Recommendation]
    discarded_rows: int = 0
    session_id: int | None = None
    # False on the fast (heuristic) response and when the LLM refine failed;
    # True once the picks have been through the LLM refine step.
    refined: bool = False
    ephemeral: bool = False


class RecommendationSession(BaseModel):
    id: int
    mood: str
    taste_summary: str
    created_at: str
    recommendations: list[Recommendation]


class RecommendationHistoryResponse(BaseModel):
    sessions: list[RecommendationSession]


class WatchedItem(BaseModel):
    title: str
    rating: float
    review: str
    created_at: str
    watched_date: str = ""
    # pedido de Matías (2026-07-31): la bitácora (/history) mostraba estrellas
    # 1-5 para todo, aunque los ratings de "manual"/"like" son sintéticos (ver
    # RatedItem.source) — el frontend usa esto para mostrar "te encantó"/
    # "te gustó"/"no te gustó" en vez de estrellas cuando no fue preciso
    source: Literal["import", "manual", "like", "star", "game"] = "import"


class WatchedHistoryResponse(BaseModel):
    items: list[WatchedItem]


class UserCredentials(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=200)


# basic shape check, not full RFC 5322 — good enough to catch typos without
# adding a dependency (pydantic's EmailStr needs the extra email-validator package)
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class RegisterRequest(UserCredentials):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=200)


class GoogleAuthRequest(BaseModel):
    # access token que devuelve el popup de Google Identity Services
    access_token: str = Field(min_length=1, max_length=4000)


class AuthResponse(BaseModel):
    token: str
    username: str


class RegisterResponse(AuthResponse):
    # only populated with BUTACA_DEBUG=1 when Resend isn't sending the mail —
    # same escape hatch as the password reset flow, never exposed in prod
    verification_token: str | None = None


class EmailVerificationConfirmRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class DeleteAccountRequest(BaseModel):
    # password re-confirmation: the session token alone shouldn't be enough to
    # wipe an account
    password: str = Field(min_length=1, max_length=200)


class PasswordResetRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)


class PasswordResetStartResponse(BaseModel):
    status: Literal["ok"]
    reset_token: str | None = None


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=8, max_length=200)


class FeedbackRequest(BaseModel):
    recommendation_id: int
    status: Literal["interested", "not_interested", "seen"]


class SiteFeedbackRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    email: str = Field(default="", max_length=320)


class RateTitleRequest(BaseModel):
    # puntuar un título suelto directo desde el modal ("Ya la vi" → elegí
    # cuánto te gustó, o el botón de "no estoy de acuerdo con el match" al
    # votar similares) — sin recommendation_id porque tiene que andar
    # también para picks de /weekly, que no tienen fila en
    # recommendations_served (pedido de Matías, 2026-07-31)
    title: str = Field(min_length=1, max_length=300)
    rating: float = Field(ge=0.5, le=5, multiple_of=0.5)
    tmdb_id: int | None = None
    review: str = ""


class WatchlistAddRequest(BaseModel):
    # "La quiero ver" en /rate: suma a la watchlist sin puntuar nada
    title: str = Field(min_length=1, max_length=300)
    tmdb_id: int | None = None


class ChatMessage(BaseModel):
    role: Literal["user", "agent"]
    # el tope de largo es la primera línea de defensa del prompt: sin esto un
    # solo mensaje pegado infla la llamada al LLM sin límite
    content: str = Field(min_length=1, max_length=1000)


class ChatRequest(BaseModel):
    # el historial lo sostiene el cliente y lo manda entero en cada turno (no
    # hay tabla de conversaciones a propósito); el backend igual lo recorta a
    # llm_client.CHAT_HISTORY_TURNS antes de armar el prompt
    messages: list[ChatMessage] = Field(default_factory=list, max_length=60)


class ChatResponse(BaseModel):
    reply: str


class LetterboxdUsernameRequest(BaseModel):
    # "" desvincula la cuenta; el largo tope es el de Letterboxd
    letterboxd_username: str = Field(default="", max_length=100)


class AllowTogetherRequest(BaseModel):
    allowed: bool


class CastMember(BaseModel):
    name: str
    character: str = ""
    profile_path: str | None = None


class MovieDetails(BaseModel):
    cast: list[CastMember]
    trailer_key: str | None = None
    # {"link": str|None, "flatrate": [{"name", "logo_path"}], "rent": [...], "buy": [...]}
    # from TMDb /watch/providers (JustWatch). None when unavailable/failed.
    providers: dict | None = None
    user_rating: float | None = None
    rating_source: Literal["import", "manual", "like", "star", "game"] | None = None
    user_review: str = ""


class GenreWeight(BaseModel):
    genre: str
    weight: float


class DecadeCount(BaseModel):
    decade: int
    count: int


class PersonCount(BaseModel):
    name: str
    count: int


class TasteProfileResponse(BaseModel):
    matched_count: int
    total_count: int
    genre_breakdown: list[GenreWeight]
    decade_breakdown: list[DecadeCount]
    top_directors: list[PersonCount]
    top_actors: list[PersonCount]


# ─── "Tu año en Butaca" (resumen anual) ──────────────────────────────────


class WrappedYear(BaseModel):
    year: int
    count: int


class WrappedTitle(BaseModel):
    title: str
    rating: float
    # 'import'/'star' = puntaje real; el resto es sintético y la UI no muestra
    # estrellas para esos (mismo criterio que /history)
    source: str
    review: str = ""
    # se resuelven contra TMDb, best-effort: quedan en None sin catálogo
    poster_path: str | None = None
    release_year: int | None = None
    tmdb_id: int | None = None
    kind: str | None = None


class WrappedMonth(BaseModel):
    month: int
    count: int


class WrappedMatchPoint(BaseModel):
    month: str  # "YYYY-MM"
    avg_match: int
    count: int


class WrappedLabelCount(BaseModel):
    label: str
    count: int


class WrappedResponse(BaseModel):
    # None solo cuando el usuario no tiene un solo título con fecha usable
    year: int | None
    available_years: list[WrappedYear]
    enough_data: bool
    total: int
    precise_count: int
    # cuántos de los `total` se contaron por fecha real de visto (el resto, por
    # cuándo se registró) — la UI lo dice en vez de mostrar un número opaco
    dated_count: int
    review_count: int
    average_rating: float | None
    by_month: list[WrappedMonth]
    top_month: int | None
    favorites: list[WrappedTitle]
    picks_count: int
    match_curve: list[WrappedMatchPoint]
    vibes: list[WrappedLabelCount]
    decades: list[DecadeCount]
    movements: list[WrappedLabelCount]


# ─── Mapa interactivo de vibras ───────────────────────────────────────────


class VibeMapPoint(BaseModel):
    # un título del mapa de vibras. x/y salen del layout jerárquico anclado a
    # clusters (vibes_clustering.project_2d), en [-1, 1] aprox.
    tmdb_id: int
    kind: str
    title: str
    year: int
    poster_path: str | None = None
    x: float
    y: float
    group_id: int  # cluster L1: el color y la leyenda
    movement_id: int  # cluster L2: el movimiento con nombre propio
    # lo puntuó/vio ESTE usuario (siempre False sin sesión)
    rated: bool = False


class VibeMapCluster(BaseModel):
    id: int
    label: str
    size: int


class VibeMapResponse(BaseModel):
    points: list[VibeMapPoint]
    groups: list[VibeMapCluster]  # L1, los que pintan el mapa
    movements: list[VibeMapCluster]  # L2, el nombre fino de cada isla
