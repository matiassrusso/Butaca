import json
import logging
import os
import re
import time
import unicodedata
import urllib.request
from collections import Counter, OrderedDict
from pathlib import Path
from urllib.error import URLError

from .models import RatedItem, RecommendResponse
from .recommender import TAG_PHRASES, capitalize_sentence, positive_tags_from_text

logger = logging.getLogger(__name__)

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
CHAT_COMPLETIONS_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
# NVIDIA NIM model catalog (build.nvidia.com). Super over Nano/Ultra: more
# reasoning capacity than Nano (12B vs 3B active params, still MoE so not as
# slow as its 120B total suggests) without Ultra's frontier-scale latency.
# chat_template_kwargs.enable_thinking=false below (a real API parameter for
# this model family, not a system-prompt trick) skips its extended
# chain-of-thought entirely — that hidden reasoning is what made Gemini's
# "thinking" variant take ~20s per call before.
MODEL = "nvidia/nemotron-3-super-120b-a12b"
# Fallback chain: se intenta cada modelo en orden, con un reintento por modelo
# ante fallas transitorias (timeout / 5xx). Ambos son NVIDIA NIM con la misma
# key — cubre un modelo puntual rate-limiteado o que devuelva basura, NO una
# caída total del endpoint (mismo host); para eso haría falta otro proveedor.
NVIDIA_MODELS = [MODEL, "meta/llama-3.1-70b-instruct"]
ATTEMPTS_PER_MODEL = 2
RETRY_BACKOFF_SECONDS = 1.0
REQUEST_TIMEOUT = 20

# Same OrderedDict TTL+LRU idiom as tmdb_client's _DISCOVER_CACHE — avoids
# repeating the call (and burning free-tier quota) when picks are
# regenerated with the same mood/candidates.
REFINE_CACHE_TTL_SECONDS = 15 * 60
REFINE_CACHE_MAX_ENTRIES = 64

_REFINE_CACHE: OrderedDict[tuple[str, tuple], tuple[float, dict]] = OrderedDict()
# cache DISTINTA de _REFINE_CACHE, no reusada: esa cachea por (mood,
# candidatos) sin el usuario, lo cual está bien para /recommend (perfiles
# distintos casi nunca comparten exactamente el mismo pool de candidatos
# personalizados) pero rompería acá — las 5 películas semanales son
# LITERALMENTE las mismas para todos, así que sin el user_id en la clave el
# segundo usuario que pidiera /weekly recibiría la predicción del primero.
_WEEKLY_PREDICTION_CACHE: OrderedDict[tuple[int, tuple], tuple[float, dict]] = OrderedDict()


class LlmError(Exception):
    pass


def _load_env_file() -> None:
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_env_file()


def is_configured() -> bool:
    return bool(os.environ.get("NVIDIA_API_KEY"))


def _phrase_for_tags(tags: list[str]) -> str:
    phrases = [TAG_PHRASES.get(tag, tag) for tag in tags]
    if not phrases:
        return ""
    if len(phrases) == 1:
        return phrases[0]
    return ", ".join(phrases[:-1]) + " y " + phrases[-1]


def _build_taste_digest(ratings: list[RatedItem]) -> str:
    # a raw list of "title (rating): review" lines makes the model infer
    # taste patterns itself, which it does inconsistently; naming the
    # patterns explicitly (recurring tags, standout titles) up front gives
    # it a concrete anchor to reference instead of writing generic praise
    if not ratings:
        return "Sin historial todavía."

    loved = sorted((r for r in ratings if r.rating >= 4), key=lambda r: r.rating, reverse=True)
    disliked = sorted((r for r in ratings if r.rating <= 2.5), key=lambda r: r.rating)
    average = sum(r.rating for r in ratings) / len(ratings)

    tag_counts: Counter[str] = Counter()
    for item in loved:
        tag_counts.update(positive_tags_from_text(item.review))
    top_tags = [tag for tag, _ in tag_counts.most_common(5)]

    lines = [f"{len(ratings)} títulos puntuados, promedio {average:.1f}/5."]
    if top_tags:
        lines.append(f"Patrones que se repiten en lo que más valoró: {_phrase_for_tags(top_tags)}.")
    if loved:
        lines.append("Le encantaron especialmente: " + ", ".join(r.title for r in loved[:5]) + ".")
    if disliked:
        lines.append("No le gustaron: " + ", ".join(r.title for r in disliked[:5]) + ".")

    return " ".join(lines)


def _rating_label(rating: float) -> str:
    # segunda persona — el LLM cita esta frase literal en el "why" (reportado
    # por Matías, 2026-07-31: decía "que ya puntuaste como 'le encantó'",
    # mezclando el "puntuaste" en segunda persona con la frase en tercera)
    if rating >= 4:
        return "te encantó"
    if rating <= 2:
        return "no te gustó"
    return "te gustó"


def _ratings_lines(ratings: list[RatedItem]) -> str:
    # los items "manual" (botón Me encantó/Bien/No me gustó del modo "Sin
    # cuenta") y "like" (like/favorito de Letterboxd sin estrellas) tienen un
    # rating sintético internamente (para el scoring), pero el usuario nunca
    # dio un puntaje preciso — citarlo como "(4.5/5)" en el why sería un dato
    # inventado (reportado por Matías, 2026-07-30; el caso "like" seguía
    # colándose porque su source es "import", 2026-07-31).
    return (
        "\n".join(
            (
                f"- {item.title} ({item.rating}/5): {item.review or 'sin reseña'}"
                if item.source == "import"
                else f"- {item.title} ({_rating_label(item.rating)}, sin puntaje numérico): {item.review or 'sin reseña'}"
            )
            for item in ratings[:40]
        )
        or "sin historial"
    )


def _candidate_lines(heuristic: RecommendResponse) -> str:
    return "\n".join(
        f"- {rec.title} ({rec.year}, tags: {', '.join(rec.tags)}): {rec.overview[:200]}"
        for rec in heuristic.recommendations
    )


def _build_prompt(ratings: list[RatedItem], mood: str, heuristic: RecommendResponse) -> str:
    digest = _build_taste_digest(ratings)
    ratings_lines = _ratings_lines(ratings)
    candidate_lines = _candidate_lines(heuristic)
    return (
        "Sos un crítico de cine que arma recomendaciones muy personalizadas en español.\n\n"
        f"Perfil de gusto detectado: {digest}\n\n"
        f"Reseñas completas del usuario (hasta 40):\n{ratings_lines}\n\n"
        f"Mood de hoy: {mood or 'sin preferencia'}\n\n"
        "Candidatos ya filtrados por un motor heurístico. Elegí y ordená como mucho 6, "
        "usando SOLO títulos de esta lista (no inventes ni agregues otros):\n"
        f"{candidate_lines}\n\n"
        "Devolvé un resumen breve del gusto del usuario que use el perfil de arriba, no una "
        "frase genérica. Para cada pick elegido, una razón personalizada de 1-2 frases que "
        "nombre un patrón concreto del perfil o del historial (un tema recurrente, un tono, o "
        "una comparación explícita con un título que ya puntuó) — nada de elogios genéricos "
        "que podrían aplicar a cualquier usuario. Hablale DIRECTO en segunda persona (vos), "
        "nunca en tercera: \"te gustó\", \"venís de puntuar\", nunca \"le gustó\" o \"su perfil\". "
        "Si citás el puntaje de un título de "
        "'Reseñas completas' de arriba, usá EXACTAMENTE el que aparece ahí (no inventes un "
        "número si el título dice 'sin puntaje numérico').\n\n"
        "Respondé ÚNICAMENTE con un JSON válido, sin texto ni markdown alrededor, con esta forma "
        'exacta: {"taste_summary": "...", "picks": [{"title": "...", "why": "..."}, ...]}'
    )


def _extract_json(content: str) -> dict:
    # models occasionally wrap the JSON in a ```json fence despite being told
    # not to — strip that instead of failing the parse
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.removeprefix("json").strip()
    return json.loads(text)


def _call_nvidia(prompt: str, api_key: str, model: str = MODEL) -> dict:
    payload_body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
        # sin esto el modelo devuelve JSON casi-válido de forma intermitente
        # (comillas internas sin escapar, trailing commas) y ~1 de cada 3
        # refines caía al heurístico; con prompts largos reales, siempre.
        # json_object garantiza sintaxis parseable (medido: 8/8 vs 4/6).
        "response_format": {"type": "json_object"},
    }
    # enable_thinking solo aplica a la familia Nemotron; otros modelos NIM
    # (el fallback llama) rechazan el parámetro con 400
    if model.startswith("nvidia/nemotron"):
        payload_body["chat_template_kwargs"] = {"enable_thinking": False}
    body = json.dumps(payload_body).encode("utf-8")
    request = urllib.request.Request(
        CHAT_COMPLETIONS_URL,
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            payload = json.loads(response.read())
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise LlmError(f"No pude consultar NVIDIA ({model}): {exc}") from exc

    try:
        text = payload["choices"][0]["message"]["content"]
        return _extract_json(text)
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise LlmError(f"Respuesta de NVIDIA ({model}) con formato inesperado: {exc}") from exc


def _call_nvidia_with_fallback(prompt: str, api_key: str) -> dict:
    """Prueba cada modelo de NVIDIA_MODELS en orden, con ATTEMPTS_PER_MODEL
    intentos por modelo (reintento ante fallas transitorias). Recién si todos
    fallan propaga el LlmError, que el llamador convierte en fallback al
    heurístico."""
    last_error: LlmError | None = None
    for model in NVIDIA_MODELS:
        for attempt in range(ATTEMPTS_PER_MODEL):
            try:
                return _call_nvidia(prompt, api_key, model)
            except LlmError as exc:
                last_error = exc
                logger.warning(
                    "NVIDIA %s falló (intento %d/%d): %s",
                    model,
                    attempt + 1,
                    ATTEMPTS_PER_MODEL,
                    exc,
                )
                if attempt + 1 < ATTEMPTS_PER_MODEL:
                    time.sleep(RETRY_BACKOFF_SECONDS)
    assert last_error is not None  # NVIDIA_MODELS nunca está vacío
    raise last_error


def _now_monotonic() -> float:
    return time.monotonic()


def _refine_cache_key(mood: str, heuristic: RecommendResponse) -> tuple[str, tuple]:
    candidates = tuple(
        rec.tmdb_id if rec.tmdb_id is not None else rec.title.strip().lower()
        for rec in heuristic.recommendations
    )
    return (mood.strip().lower(), candidates)


def _get_cached_refine(cache_key: tuple[str, tuple]) -> dict | None:
    cached = _REFINE_CACHE.get(cache_key)
    if cached is None:
        return None

    expires_at, result = cached
    if expires_at <= _now_monotonic():
        del _REFINE_CACHE[cache_key]
        return None

    _REFINE_CACHE.move_to_end(cache_key)
    return result


def _store_cached_refine(cache_key: tuple[str, tuple], result: dict) -> None:
    _REFINE_CACHE[cache_key] = (_now_monotonic() + REFINE_CACHE_TTL_SECONDS, result)
    _REFINE_CACHE.move_to_end(cache_key)
    while len(_REFINE_CACHE) > REFINE_CACHE_MAX_ENTRIES:
        _REFINE_CACHE.popitem(last=False)


_TRAILING_YEAR_RE = re.compile(r"[\s,]*[\(\[]?\b(19|20)\d{2}\b[\)\]]?\s*$")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _title_key(title: str) -> str:
    """Clave para matchear el título que devuelve el modelo contra el candidato.

    Comparar el string crudo es demasiado estricto: el modelo suele devolver
    "GoodFellas (1990)" o cambiar comillas/acentos, y con un solo desajuste se
    descartaban los 6 picks y todo caía al heurístico (síntoma: los 6 "why"
    idénticos). Esto normaliza acentos, puntuación y el año al final."""
    text = _TRAILING_YEAR_RE.sub("", title.strip())
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return _NON_ALNUM_RE.sub("", text)


def refine_recommendations(
    ratings: list[RatedItem], mood: str, heuristic: RecommendResponse
) -> RecommendResponse:
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise LlmError("NVIDIA_API_KEY no configurada.")
    if not heuristic.recommendations:
        raise LlmError("No hay candidatos para refinar.")

    cache_key = _refine_cache_key(mood, heuristic)
    result = _get_cached_refine(cache_key)
    cache_hit = result is not None
    if result is None:
        result = _call_nvidia_with_fallback(_build_prompt(ratings, mood, heuristic), api_key)

    by_title = {_title_key(rec.title): rec for rec in heuristic.recommendations}
    reordered = []
    unmatched = []
    for pick in result.get("picks", []):
        raw_title = str(pick.get("title", ""))
        rec = by_title.get(_title_key(raw_title))
        if rec is None:
            unmatched.append(raw_title)
            continue
        why = capitalize_sentence(str(pick.get("why", "")).strip())
        reordered.append(rec.model_copy(update={"why": why or rec.why}))

    if unmatched:
        logger.warning(
            "NVIDIA devolvió %d título(s) fuera de la lista de candidatos: %s",
            len(unmatched),
            unmatched[:6],
        )

    if not reordered:
        raise LlmError("NVIDIA no devolvió picks válidos de la lista de candidatos.")

    # Recién acá: cachear antes de validar dejaba una respuesta inservible
    # pegada 15 minutos, así que cada reintento en esa ventana fallaba igual
    # sin volver a preguntarle al modelo.
    if not cache_hit:
        _store_cached_refine(cache_key, result)

    taste_summary = capitalize_sentence(str(result.get("taste_summary", "")).strip()) or heuristic.taste_summary
    return RecommendResponse(taste_summary=taste_summary, recommendations=reordered[:6])


def _build_weekly_prompt(ratings: list[RatedItem], heuristic: RecommendResponse) -> str:
    digest = _build_taste_digest(ratings)
    ratings_lines = _ratings_lines(ratings)
    candidate_lines = _candidate_lines(heuristic)
    return (
        "Sos un crítico de cine que le predice a un usuario, hablándole directo a él, si le va a "
        "gustar una película en particular, en español.\n\n"
        f"Perfil de gusto detectado: {digest}\n\n"
        f"Reseñas completas del usuario (hasta 40):\n{ratings_lines}\n\n"
        "Estas son las 5 películas más populares de esta semana en TMDb — no elegís cuáles "
        "mostrar (eso ya está decidido y es igual para todos los usuarios), tu trabajo es "
        "predecir, para CADA UNA de las 5, si le va a gustar o no a ESTE usuario en particular. "
        f"Escribí sobre las 5, ninguna de menos:\n{candidate_lines}\n\n"
        "Para cada película, 1-2 frases en tono de predicción, hablándole DIRECTO en segunda "
        "persona (vos) — \"te va a encantar porque...\", \"es probable que no te enganche "
        "porque...\", \"tenés chances, aunque...\" — nunca en tercera persona (\"le va a "
        "encantar\", \"su perfil\"). Que citen un patrón concreto del perfil de arriba o una "
        "comparación explícita con un título que ya puntuó — nada de elogios genéricos que "
        "podrían aplicar a cualquier usuario. Si citás el "
        "puntaje de un título de 'Reseñas completas', usá EXACTAMENTE el que aparece ahí (no "
        "inventes un número si el título dice 'sin puntaje numérico').\n\n"
        "Respondé ÚNICAMENTE con un JSON válido, sin texto ni markdown alrededor, con esta forma "
        'exacta: {"picks": [{"title": "...", "why": "..."}, ...]} — un elemento por cada una de '
        "las 5, nunca menos."
    )


def predict_weekly_fit(
    user_id: int, ratings: list[RatedItem], heuristic: RecommendResponse
) -> RecommendResponse:
    """Variante de refine_recommendations para las 'recomendaciones de la
    semana' (pedido de Matías, 2026-07-30): mismo mecanismo de LLM, pero el
    prompt pide una PREDICCIÓN ('¿le va a gustar o no?') en vez de una
    justificación de por qué se eligió. A diferencia de refine_recommendations,
    acá el set de películas es fijo — nunca se puede perder ninguna de las 5
    aunque el LLM no las cubra todas o devuelva basura para alguna; en ese
    caso esa una se queda con el why heurístico (mejor una card con razón
    genérica que una card faltante)."""
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise LlmError("NVIDIA_API_KEY no configurada.")
    if not heuristic.recommendations:
        raise LlmError("No hay candidatos para predecir.")

    candidates = tuple(
        rec.tmdb_id if rec.tmdb_id is not None else rec.title.strip().lower()
        for rec in heuristic.recommendations
    )
    cache_key = (user_id, candidates)
    cached = _WEEKLY_PREDICTION_CACHE.get(cache_key)
    cache_hit = False
    if cached is not None:
        expires_at, cached_result = cached
        if expires_at > _now_monotonic():
            _WEEKLY_PREDICTION_CACHE.move_to_end(cache_key)
            cache_hit = True
            result = cached_result
        else:
            del _WEEKLY_PREDICTION_CACHE[cache_key]
            result = None
    else:
        result = None
    if result is None:
        result = _call_nvidia_with_fallback(_build_weekly_prompt(ratings, heuristic), api_key)

    by_title = {_title_key(rec.title): rec for rec in heuristic.recommendations}
    why_by_key: dict[str, str] = {}
    for pick in result.get("picks", []):
        key = _title_key(str(pick.get("title", "")))
        if key not in by_title:
            continue
        why = capitalize_sentence(str(pick.get("why", "")).strip())
        if why:
            why_by_key[key] = why

    if not cache_hit:
        _WEEKLY_PREDICTION_CACHE[cache_key] = (_now_monotonic() + REFINE_CACHE_TTL_SECONDS, result)
        _WEEKLY_PREDICTION_CACHE.move_to_end(cache_key)
        while len(_WEEKLY_PREDICTION_CACHE) > REFINE_CACHE_MAX_ENTRIES:
            _WEEKLY_PREDICTION_CACHE.popitem(last=False)

    recommendations = [
        rec.model_copy(update={"why": why_by_key.get(_title_key(rec.title), rec.why)})
        for rec in heuristic.recommendations
    ]
    return RecommendResponse(taste_summary=heuristic.taste_summary, recommendations=recommendations)
