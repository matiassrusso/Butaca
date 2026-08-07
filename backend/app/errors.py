"""Mensajes de error user-facing en español e inglés.

Pedido de Matías (2026-08-06): con el toggle ES/EN, el `detail` de cada
HTTPException se muestra tal cual en pantalla — sin esto, la página en inglés
seguía diciendo "Subí el .zip que exporta Letterboxd.".

**De dónde sale el idioma acá:** del header `Accept-Language`, NO del parámetro
`lang` que ya reciben los endpoints de recomendación. Son dos cosas distintas a
propósito:

- `lang` (query/form/body) le dice al LLM en qué idioma ESCRIBIR el "why". Solo
  lo tienen los endpoints que llaman al modelo.
- `Accept-Language` es en qué idioma le HABLAMOS al usuario. Aplica a todos los
  endpoints, incluidos los de auth ("Usuario o contraseña incorrectos."), que no
  tienen ni necesitan un parámetro de idioma propio.

El frontend manda el header en cada request (ver frontend/src/lib/apiLang.ts).

Los errores de admin/internos (token de administrador, recálculo de vibras) NO
están acá a propósito: nunca los ve un usuario final.
"""

from fastapi import Header

MESSAGES: dict[str, dict[str, str]] = {
    # ─── Catálogo / TMDb ────────────────────────────────────────────────
    "tmdb_unconfigured": {
        "es": "Catálogo de TMDb no configurado.",
        "en": "The TMDb catalog isn't configured.",
    },
    "weekly_empty": {
        "es": "TMDb no devolvió películas en tendencia esta semana.",
        "en": "TMDb didn't return any trending movies this week.",
    },
    "title_not_found": {
        "es": "No encontré ese título en TMDb.",
        "en": "I couldn't find that title on TMDb.",
    },
    "title_unanalyzable": {
        "es": "No pude analizar ese título.",
        "en": "I couldn't analyze that title.",
    },
    "invalid_kind": {"es": "Tipo de título inválido.", "en": "Invalid title type."},
    # ─── Auth ───────────────────────────────────────────────────────────
    "user_exists": {"es": "Ese usuario ya existe.", "en": "That username is taken."},
    "account_exists": {
        "es": "Esta cuenta ya está registrada.",
        "en": "This account is already registered.",
    },
    "bad_credentials": {
        "es": "Usuario o contraseña incorrectos.",
        "en": "Wrong username or password.",
    },
    "wrong_password": {"es": "Contraseña incorrecta.", "en": "Wrong password."},
    "google_disabled": {
        "es": "El login con Google no está habilitado.",
        "en": "Google sign-in isn't enabled.",
    },
    "reset_token_invalid": {
        "es": "Token de recuperación inválido o expirado.",
        "en": "That reset link is invalid or expired.",
    },
    "verify_token_invalid": {
        "es": "Token de verificación inválido o expirado.",
        "en": "That verification link is invalid or expired.",
    },
    # {seconds} — el lockout por intentos fallidos
    "too_many_attempts": {
        "es": "Demasiados intentos fallidos. Probá de nuevo en {seconds}s.",
        "en": "Too many failed attempts. Try again in {seconds}s.",
    },
    # ─── Recomendación ──────────────────────────────────────────────────
    "rate_limited": {
        "es": "Llegaste al límite de recomendaciones de hoy. Probá de nuevo mañana.",
        "en": "You've hit today's recommendation limit. Try again tomorrow.",
    },
    "invalid_mode": {
        "es": "Modo de recomendación inválido.",
        "en": "Invalid recommendation mode.",
    },
    "invalid_kind_filter": {"es": "Filtro de tipo inválido.", "en": "Invalid type filter."},
    "no_usable_ratings": {
        "es": "No encontré ratings ni reviews usables para armar recomendaciones.",
        "en": "I couldn't find any usable ratings or reviews to build recommendations from.",
    },
    # {n} — MAX_SELECTED_OPTIONS
    "too_many_options": {
        "es": "Elegí como mucho {n} opciones.",
        "en": "Pick at most {n} options.",
    },
    "no_genre_selected": {
        "es": "Elegí al menos un género para este modo.",
        "en": "Pick at least one genre for this mode.",
    },
    "watchlist_empty": {
        "es": "Tu watchlist está vacía. Importá el zip de Letterboxd (el import por username no la trae).",
        "en": "Your watchlist is empty. Import the Letterboxd zip (the username import doesn't include it).",
    },
    "watchlist_unmatched": {
        "es": "No pude matchear tu watchlist contra el catálogo de TMDb.",
        "en": "I couldn't match your watchlist against the TMDb catalog.",
    },
    "not_a_zip": {
        "es": "Subí el .zip que exporta Letterboxd.",
        "en": "Upload the .zip that Letterboxd exports.",
    },
    "zip_too_big": {"es": "Ese zip es demasiado grande.", "en": "That zip is too large."},
    # {n} — MIN_MANUAL_RATINGS
    "not_enough_ratings": {
        "es": "Puntuá al menos {n} títulos para armar tu perfil.",
        "en": "Rate at least {n} titles to build your profile.",
    },
    "no_saved_profile": {
        "es": "Todavía no tenés un perfil guardado — importá tu historial primero.",
        "en": "You don't have a saved profile yet — import your history first.",
    },
    "session_not_found": {"es": "Sesión no encontrada.", "en": "Session not found."},
    "recommendation_not_found": {
        "es": "Recomendación no encontrada.",
        "en": "Recommendation not found.",
    },
}


def normalize_lang(lang: str | None) -> str:
    """'en' solo ante un pedido explícito de inglés; cualquier otra cosa (o
    nada) cae a español, que es el idioma por defecto del sitio."""
    if not lang:
        return "es"
    # Accept-Language real puede venir "en-US,en;q=0.9,es;q=0.8" — alcanza con
    # mirar el primer tag, que es el de mayor prioridad. El frontend manda un
    # "es"/"en" pelado, esto es para que un cliente de verdad tampoco rompa.
    primary = lang.split(",")[0].strip().lower()
    return "en" if primary.startswith("en") else "es"


def msg(key: str, lang: str | None = "es", **params: object) -> str:
    entry = MESSAGES[key]
    return entry[normalize_lang(lang)].format(**params)


def request_lang(accept_language: str | None = Header(default=None)) -> str:
    """Dependencia de FastAPI: el idioma en el que le hablamos al usuario."""
    return normalize_lang(accept_language)
