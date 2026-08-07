import json
import logging
import os
import re
import threading
import time
import unicodedata
import urllib.request
from collections import Counter, OrderedDict
from pathlib import Path
from urllib.error import URLError

from .models import RatedItem, RecommendResponse
from .recommender import (
    MIN_MATCH_SCORE,
    TAG_PHRASES,
    capitalize_sentence,
    positive_tags_from_text,
)

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

_REFINE_CACHE: OrderedDict[tuple, tuple[float, dict]] = OrderedDict()
# cache DISTINTA de _REFINE_CACHE, no reusada: esa cachea por (mood,
# candidatos) sin el usuario, lo cual está bien para /recommend (perfiles
# distintos casi nunca comparten exactamente el mismo pool de candidatos
# personalizados) pero rompería acá — las 5 películas semanales son
# LITERALMENTE las mismas para todos, así que sin el user_id en la clave el
# segundo usuario que pidiera /weekly recibiría la predicción del primero.
_VERDICT_CACHE: OrderedDict[tuple[int, tuple, str, str], tuple[float, dict]] = OrderedDict()

# kickoff_verdict evita disparar dos veces el mismo predict_fit en background
# -- sin esto, varios polls de /weekly llegando antes de que el primero
# termine dispararían una llamada nueva a NVIDIA cada uno.
_INFLIGHT_VERDICTS: set[tuple[int, tuple, str, str]] = set()
_INFLIGHT_LOCK = threading.Lock()


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


def _rating_label(rating: float, lang: str = "es") -> str:
    # segunda persona — el LLM cita esta frase literal en el "why" (reportado
    # por Matías, 2026-07-31: decía "que ya puntuaste como 'le encantó'",
    # mezclando el "puntuaste" en segunda persona con la frase en tercera)
    labels = _RATING_LABELS_BY_LANG[normalize_lang(lang)]
    if rating >= 4:
        return labels["loved"]
    if rating <= 2:
        return labels["disliked"]
    return labels["liked"]


def _ratings_lines(ratings: list[RatedItem]) -> str:
    # los items "manual" (los tres botones históricos de Butaca) y "like"
    # (like/favorito de Letterboxd sin estrellas) tienen un
    # rating sintético internamente (para el scoring), pero el usuario nunca
    # dio un puntaje preciso — citarlo como "(4.5/5)" en el why sería un dato
    # inventado (reportado por Matías, 2026-07-30; el caso "like" seguía
    # colándose porque su source es "import", 2026-07-31).
    return (
        "\n".join(
            (
                f"- {item.title} ({item.rating}/5): {item.review or 'sin reseña'}"
                if item.source in {"import", "star"}
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


# ─── Voz compartida del agente ──────────────────────────────────────────────
# Pedido de Matías (2026-07-31): "TODA la página debería tener el mismo sistema
# de LLM, con los mismos prompts y los mismos tonos, no importa si es en
# /weekly o en /recommend o donde sea". Lo único que cambia entre pantallas es
# la TAREA (elegir de un pool / opinar sobre títulos ya elegidos); quién habla,
# cómo escribe y cómo trata los puntajes sale de acá, compartido por todos los
# prompts. Si hay que ajustar el tono, se ajusta UNA vez, acá.

AGENT_VOICE = (
    "Sos el crítico de cine de Butaca: conocés a fondo el gusto de esta persona y le "
    "hablás directo, en español argentino natural, como un amigo que sabe de cine y no "
    "le va a mentir para quedar bien."
)

# Reglas de escritura. Nacieron de un bug concreto (2026-07-31): el prompt daba
# frases de EJEMPLO ("te va a encantar porque...") como referencia de tono y el
# modelo las copiaba literal — todos los textos arrancaban igual, "encantar" se
# repetía en cada uno, y mezclar dos ejemplos produjo "tenés chances de
# encantarte", que ni siquiera es español. Por eso son reglas, no ejemplos.
WRITING_RULES = (
    "CÓMO ESCRIBIR (reglas duras, valen para todo lo que devuelvas):\n"
    "- Hablale SIEMPRE en segunda persona (vos). Nunca en tercera: nada de \"le va a "
    "encantar\" ni \"su perfil\".\n"
    "- Arrancá cada texto DISTINTO. Nada de que varios empiecen con la misma fórmula.\n"
    "- Prohibido abrir con \"Te va a encantar porque\" en más de uno.\n"
    "- Variá el verbo: enganchar, cerrar, funcionar, costar, aburrir, sorprender, "
    "resonar, chocar. No uses \"encantar\" más de una vez en toda la respuesta.\n"
    "- Si algo es tibio o no le va a gustar, decilo derecho y sin adornos: un \"no creo "
    "que te cierre\" honesto vale más que un elogio inflado.\n"
    "- Argentino natural, como se lo contarías a un amigo. Nada de construcciones raras: "
    "\"tenés chances de encantarte\" está MAL, no es español.\n"
    "- No repitas la misma estructura de comparación (\"al igual que con X o Y\") en "
    "todos: a veces citá un solo título, a veces ninguno y describí el patrón.\n"
    "- Cada texto tiene que tener un ESQUELETO distinto, no solo palabras distintas. Si "
    "uno abre nombrando lo que al usuario le gustó, otro tiene que abrir por la película "
    "misma, otro por una advertencia, otro por lo que va a sentir. Dos textos que se "
    "puedan resumir con el mismo molde (\"te gustaron X como A y B, y esta tiene lo "
    "mismo...\") están MAL, aunque cambien las palabras.\n"
    "- Citá SOLO títulos que aparezcan literalmente en el perfil de arriba. Está "
    "PROHIBIDO nombrar una película que el usuario no puntuó, aunque supongas que la vio "
    "o que le gustaría. Si no hay un título que te sirva, describí el patrón sin nombrar "
    "ninguno. Nunca aclares entre paréntesis que estás suponiendo.\n"
    "- Citá siempre algo concreto de su perfil o su historial — nada de elogios genéricos "
    "que podrían aplicar a cualquier usuario.\n"
    "- Escribí SOLO palabras reales de español, separadas por espacios. Prohibido pegar "
    "dos palabras o títulos en una sola (ej: \"Zodiacomodoro\") — si dudás de un título, no "
    "lo nombres."
)

SCORE_RULE = (
    "Si citás el puntaje de un título de 'Reseñas completas', usá EXACTAMENTE el que "
    "aparece ahí (no inventes un número si el título dice 'sin puntaje numérico')."
)

MATCH_SCORE_RULE = (
    "Para cada título devolvé también match_score: un entero de 1 a 99 que estime cuánto "
    "le va a gustar a esta persona. 50 significa que no hay evidencia; el número y el "
    "veredicto escrito nunca pueden contradecirse."
)

# ─── English variants ───────────────────────────────────────────────────────
# Pedido de Matías (2026-08-06): toggle ES/EN en toda la página, con los "why"
# del LLM también en inglés. Solo se traducen las reglas que controlan el
# OUTPUT (voz, escritura, score) — el contexto que arma _profile_block (tags,
# reseñas del usuario) sigue en español siempre: es información que el modelo
# lee, no algo que le mostremos al usuario, y un LLM sigue una instrucción de
# "respondé en inglés" sin problema aunque el contexto esté en otro idioma.
AGENT_VOICE_EN = (
    "You're Butaca's film critic: you know this person's taste inside and out and talk "
    "to them straight, in natural, casual English, like a friend who knows movies and "
    "won't lie to you just to look good."
)

WRITING_RULES_EN = (
    "HOW TO WRITE (hard rules, apply to everything you return):\n"
    "- ALWAYS talk to them in second person (\"you\"). Never third person: no \"they'll "
    "love it\" or \"their profile\".\n"
    "- Open each text DIFFERENTLY. Don't let several start with the same formula.\n"
    "- Forbidden to open with \"You're going to love this because\" in more than one.\n"
    "- Vary your verbs: hook, land, click, cost you, bore, surprise, hit, clash. Don't use "
    "\"love\" more than once in the whole response.\n"
    "- If something's lukewarm or a bad fit, say so plainly, no sugarcoating: an honest "
    "\"I don't think this'll click for you\" beats an inflated compliment.\n"
    "- Natural English, like you'd tell a friend. No stiff or awkward constructions.\n"
    "- Don't repeat the same comparison structure (\"just like X or Y\") in every one: "
    "sometimes cite one title, sometimes none and just describe the pattern.\n"
    "- Each text needs a different SKELETON, not just different words. If one opens naming "
    "what the user liked, another has to open with the movie itself, another with a "
    "warning, another with how it'll make them feel. Two texts that boil down to the same "
    "template (\"you liked X like A and B, and this has the same...\") are WRONG, even "
    "with different words.\n"
    "- Only cite titles that literally appear in the profile above. It's FORBIDDEN to name "
    "a movie the user didn't rate, even if you assume they saw it or would like it. If "
    "there's no title that fits, describe the pattern without naming one. Never clarify in "
    "parentheses that you're guessing.\n"
    "- Always cite something concrete from their profile or history — no generic praise "
    "that could apply to any user.\n"
    "- Write ONLY real English words, separated by spaces. Never glue two words or titles "
    "together into one (e.g. \"Zodiacobsession\") — if you're unsure about a title, don't "
    "name it."
)

SCORE_RULE_EN = (
    "If you cite a title's score from 'Full reviews', use EXACTLY the one that appears "
    "there (don't make up a number if the title says 'no numeric score')."
)

MATCH_SCORE_RULE_EN = (
    "For each title also return match_score: an integer from 1 to 99 estimating how much "
    "this person will like it. 50 means there's no evidence; the number and the written "
    "verdict can never contradict each other."
)

_AGENT_VOICE_BY_LANG = {"es": AGENT_VOICE, "en": AGENT_VOICE_EN}
_WRITING_RULES_BY_LANG = {"es": WRITING_RULES, "en": WRITING_RULES_EN}
_SCORE_RULE_BY_LANG = {"es": SCORE_RULE, "en": SCORE_RULE_EN}
_MATCH_SCORE_RULE_BY_LANG = {"es": MATCH_SCORE_RULE, "en": MATCH_SCORE_RULE_EN}
_RATING_LABELS_BY_LANG = {
    "es": {"loved": "te encantó", "liked": "te gustó", "disliked": "no te gustó"},
    "en": {"loved": "you loved it", "liked": "you liked it", "disliked": "you didn't like it"},
}
_ALREADY_SEEN_PREFIX_BY_LANG = {"es": "Ya la viste", "en": "You already watched this"}


def normalize_lang(lang: str) -> str:
    return "en" if lang == "en" else "es"


def _profile_block(ratings: list[RatedItem]) -> str:
    return (
        f"Perfil de gusto detectado: {_build_taste_digest(ratings)}\n\n"
        f"Reseñas completas del usuario (hasta 40):\n{_ratings_lines(ratings)}"
    )


def _build_prompt(
    ratings: list[RatedItem], mood: str, heuristic: RecommendResponse, lang: str = "es"
) -> str:
    """Tarea: elegir y ordenar picks de un pool de candidatos (/recommend).
    La voz y las reglas de escritura son las mismas que en _build_verdict_prompt
    — ver AGENT_VOICE arriba."""
    lang = normalize_lang(lang)
    language_line = (
        "" if lang == "es" else "Write your ENTIRE response (taste_summary and every why) in English.\n\n"
    )
    return (
        f"{_AGENT_VOICE_BY_LANG[lang]}\n\n"
        f"{language_line}"
        f"{_profile_block(ratings)}\n\n"
        f"Mood de hoy: {mood or 'sin preferencia'}\n\n"
        # el piso sale de recommender.MIN_MATCH_SCORE en vez de estar escrito a
        # mano: decía "entre 51 y 99" mientras _finish_recommend descartaba todo
        # lo que estuviera abajo de 60, o sea que le pedíamos al modelo puntajes
        # que después tirábamos — y cada uno tirado achicaba la tanda (reportado
        # por Matías, 2026-08-07: 4 picks, el más bajo en 65).
        f"Candidatos ya filtrados por un motor heurístico. Elegí y ordená exactamente 6 "
        f"si hay al menos 6. Estos son PICKS FINALES: todos deben tener match_score entre "
        f"{MIN_MATCH_SCORE} y 99 y un why que explique por qué sí pueden funcionarle. Un "
        f"pick que no te dé para {MIN_MATCH_SCORE} o más no va: si tu veredicto sería que "
        f"no le va a gustar, no incluyas ese título, elegí otro del pool. "
        f"Usando SOLO títulos de esta lista (no inventes ni agregues otros):\n"
        f"{_candidate_lines(heuristic)}\n\n"
        "Devolvé un resumen breve del gusto del usuario que use el perfil de arriba, no una "
        "frase genérica, y para cada pick elegido una razón de 1-2 frases.\n\n"
        f"{_WRITING_RULES_BY_LANG[lang]}\n\n"
        f"{_SCORE_RULE_BY_LANG[lang]}\n\n"
        f"{_MATCH_SCORE_RULE_BY_LANG[lang]}\n\n"
        # reforzado cerca del final a propósito (2026-08-03, TASKS.md): un
        # candidato inventado ("Zodiac", "Obsession" — ninguno estaba en la
        # lista) tira ese pick al heurístico sin que se note en pantalla. La
        # instrucción de "SOLO títulos de esta lista" ya existe más arriba,
        # pero repetirla acá, pegada al schema de salida, es donde más pesa.
        "IMPORTANTE: cada \"title\" que devuelvas tiene que ser una copia exacta de un título "
        "de la lista de candidatos de arriba. No seleccionés una película o serie real que no "
        "esté en esa lista, aunque le quede mejor al usuario.\n\n"
        "Respondé ÚNICAMENTE con un JSON válido, sin texto ni markdown alrededor, con esta forma "
        'exacta: {"taste_summary": "...", "picks": [{"title": "...", "why": "...", '
        '"match_score": 85}, ...]}'
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


def _refine_cache_key(
    ratings: list[RatedItem], mood: str, heuristic: RecommendResponse, lang: str = "es"
) -> tuple[str, str, tuple, str]:
    candidates = tuple(
        rec.tmdb_id if rec.tmdb_id is not None else rec.title.strip().lower()
        for rec in heuristic.recommendations
    )
    return (_profile_block(ratings), mood.strip().lower(), candidates, normalize_lang(lang))


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


def _pick_match_score(pick: dict, fallback: int) -> int:
    try:
        score = int(pick.get("match_score"))
    except (TypeError, ValueError):
        return fallback
    return score if 1 <= score <= 99 else fallback


def refine_recommendations(
    ratings: list[RatedItem], mood: str, heuristic: RecommendResponse, lang: str = "es"
) -> RecommendResponse:
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise LlmError("NVIDIA_API_KEY no configurada.")
    if not heuristic.recommendations:
        raise LlmError("No hay candidatos para refinar.")

    cache_key = _refine_cache_key(ratings, mood, heuristic, lang)
    result = _get_cached_refine(cache_key)
    cache_hit = result is not None
    if result is None:
        result = _call_nvidia_with_fallback(_build_prompt(ratings, mood, heuristic, lang), api_key)

    by_title = {_title_key(rec.title): rec for rec in heuristic.recommendations}
    reordered = []
    selected_keys = set()
    unmatched = []
    for pick in result.get("picks", []):
        raw_title = str(pick.get("title", ""))
        key = _title_key(raw_title)
        rec = by_title.get(key)
        if rec is None:
            unmatched.append(raw_title)
            continue
        if key in selected_keys:
            continue
        why = capitalize_sentence(str(pick.get("why", "")).strip())
        match_score = _pick_match_score(pick, rec.match_score)
        if match_score <= 50:
            continue
        reordered.append(
            rec.model_copy(
                update={
                    "why": why or rec.why,
                    "match_score": match_score,
                    "refined": True,
                }
            )
        )
        selected_keys.add(key)

    if unmatched:
        logger.warning(
            "NVIDIA devolvió %d título(s) fuera de la lista de candidatos: %s",
            len(unmatched),
            unmatched[:6],
        )

    if not reordered:
        raise LlmError("NVIDIA no devolvió picks válidos de la lista de candidatos.")

    if len(heuristic.recommendations) >= 6:
        for rec in heuristic.recommendations:
            if len(reordered) >= 6:
                break
            if _title_key(rec.title) not in selected_keys:
                reordered.append(rec)
                selected_keys.add(_title_key(rec.title))

    # Recién acá: cachear antes de validar dejaba una respuesta inservible
    # pegada 15 minutos, así que cada reintento en esa ventana fallaba igual
    # sin volver a preguntarle al modelo.
    if not cache_hit:
        _store_cached_refine(cache_key, result)

    taste_summary = capitalize_sentence(str(result.get("taste_summary", "")).strip()) or heuristic.taste_summary
    return RecommendResponse(taste_summary=taste_summary, recommendations=reordered[:6])


def _build_verdict_prompt(
    ratings: list[RatedItem], heuristic: RecommendResponse, lang: str = "es"
) -> str:
    """Tarea: opinar sobre títulos YA elegidos (no elegirlos). La usan las
    semanales de la home y el buscador — en los dos casos el set viene dado y
    lo único que falta es el veredicto para esta persona.

    `heuristic` acá ya viene filtrado de títulos que el usuario puntuó antes
    (predict_fit los saca del pool), así que el count es dinámico en vez de
    hardcodeado — antes decía "las 5" aunque quedaran 4 o 3."""
    lang = normalize_lang(lang)
    count = len(heuristic.recommendations)
    plural = count > 1
    language_line = (
        "" if lang == "es" else "Write your ENTIRE response (every why) in English.\n\n"
    )
    return (
        f"{_AGENT_VOICE_BY_LANG[lang]}\n\n"
        f"{language_line}"
        f"{_profile_block(ratings)}\n\n"
        f"{'Estos son' if plural else 'Este es'} {count} "
        f"{'títulos que ya están elegidos' if plural else 'título que ya está elegido'} — no "
        f"elegís vos cuál mostrar. Tu trabajo es decir, para "
        f"{'CADA UNO' if plural else 'ese título'}, si le va a gustar o no a ESTA persona en "
        f"particular{f'. Escribí sobre {count}, ninguno de menos' if plural else ''}:\n"
        f"{_candidate_lines(heuristic)}\n\n"
        f"Para cada uno, 1-2 frases con tu veredicto.\n\n"
        f"{_WRITING_RULES_BY_LANG[lang]}\n\n"
        f"{_SCORE_RULE_BY_LANG[lang]}\n\n"
        f"{_MATCH_SCORE_RULE_BY_LANG[lang]}\n\n"
        "Respondé ÚNICAMENTE con un JSON válido, sin texto ni markdown alrededor, con esta forma "
        'exacta: {"picks": [{"title": "...", "why": "...", "match_score": 85}, ...]}'
        + (f" — un elemento por cada uno de los {count}, nunca menos." if plural else ".")
    )


def _verdict_cache_key(
    user_id: int, ratings: list[RatedItem], heuristic: RecommendResponse, lang: str = "es"
) -> tuple[int, tuple, str, str]:
    candidates = tuple(
        rec.tmdb_id if rec.tmdb_id is not None else rec.title.strip().lower()
        for rec in heuristic.recommendations
    )
    return (user_id, candidates, _profile_block(ratings), normalize_lang(lang))


def _predictable_recs(
    ratings: list[RatedItem], heuristic: RecommendResponse
) -> tuple[dict[str, RatedItem], list]:
    # /weekly no excluye del catálogo lo que el usuario ya puntuó (el set de
    # 5 es fijo para todos) — así que un candidato puede ser algo que ya
    # vio. Pedirle al LLM que lo "prediga" igual lo confundía: el prompt le
    # manda el título como candidato Y como parte de su historial, y
    # terminaba comparando el título consigo mismo como si fueran dos cosas
    # distintas (reportado por Matías, 2026-07-31 — caso "The Odyssey"). A
    # esos se les pone directo un why honesto con el rating real, sin
    # pasar por el LLM.
    seen_by_key = {_title_key(item.title): item for item in ratings}
    predictable = [
        rec for rec in heuristic.recommendations if _title_key(rec.title) not in seen_by_key
    ]
    return seen_by_key, predictable


def _apply_verdict_result(
    ratings: list[RatedItem],
    heuristic: RecommendResponse,
    result: dict | None,
    lang: str = "es",
) -> RecommendResponse:
    lang = normalize_lang(lang)
    seen_by_key, _ = _predictable_recs(ratings, heuristic)
    by_title = {_title_key(rec.title): rec for rec in heuristic.recommendations}
    updates_by_key: dict[str, dict] = {}
    for pick in (result or {}).get("picks", []):
        key = _title_key(str(pick.get("title", "")))
        if key not in by_title:
            continue
        why = capitalize_sentence(str(pick.get("why", "")).strip())
        if why:
            rec = by_title[key]
            updates_by_key[key] = {
                "why": why,
                "match_score": _pick_match_score(pick, rec.match_score),
            }

    recommendations = []
    for rec in heuristic.recommendations:
        key = _title_key(rec.title)
        seen_item = seen_by_key.get(key)
        if seen_item:
            prefix = _ALREADY_SEEN_PREFIX_BY_LANG[lang]
            updates = {"why": f"{prefix} — {_rating_label(seen_item.rating, lang)}."}
        else:
            updates = updates_by_key.get(key)
            updates = {**updates, "refined": True} if updates else {}
        recommendations.append(rec.model_copy(update=updates))
    return RecommendResponse(taste_summary=heuristic.taste_summary, recommendations=recommendations)


def predict_fit(
    user_id: int, ratings: list[RatedItem], heuristic: RecommendResponse, lang: str = "es"
) -> RecommendResponse:
    """Veredicto del agente sobre títulos YA elegidos: '¿le va a gustar o no a
    esta persona?'. La contracara de refine_recommendations, que además ELIGE
    del pool.

    La usan las semanales de la home (set fijo de 5, pedido 2026-07-30) y el
    buscador (un solo título, pedido 2026-07-31) — misma voz, mismo prompt,
    mismo manejo de 'ya la viste'. A diferencia de refine_recommendations el
    set es fijo: ningún título se pierde aunque el LLM no lo cubra o devuelva
    basura para alguno; en ese caso queda con su why heurístico (mejor una
    card con razón genérica que una card faltante)."""
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise LlmError("NVIDIA_API_KEY no configurada.")
    if not heuristic.recommendations:
        raise LlmError("No hay candidatos para opinar.")

    cache_key = _verdict_cache_key(user_id, ratings, heuristic, lang)
    _, predictable = _predictable_recs(ratings, heuristic)

    result: dict | None = None
    if predictable:
        predictable_heuristic = RecommendResponse(
            taste_summary=heuristic.taste_summary, recommendations=predictable
        )
        cached = _VERDICT_CACHE.get(cache_key)
        cache_hit = False
        if cached is not None:
            expires_at, cached_result = cached
            if expires_at > _now_monotonic():
                _VERDICT_CACHE.move_to_end(cache_key)
                cache_hit = True
                result = cached_result
            else:
                del _VERDICT_CACHE[cache_key]
        if result is None:
            result = _call_nvidia_with_fallback(
                _build_verdict_prompt(ratings, predictable_heuristic, lang), api_key
            )
        if not cache_hit:
            _VERDICT_CACHE[cache_key] = (_now_monotonic() + REFINE_CACHE_TTL_SECONDS, result)
            _VERDICT_CACHE.move_to_end(cache_key)
            while len(_VERDICT_CACHE) > REFINE_CACHE_MAX_ENTRIES:
                _VERDICT_CACHE.popitem(last=False)

    return _apply_verdict_result(ratings, heuristic, result, lang)


def peek_verdict(
    user_id: int, ratings: list[RatedItem], heuristic: RecommendResponse, lang: str = "es"
) -> RecommendResponse | None:
    """Devuelve el veredicto YA cacheado sin llamar al LLM ni disparar nada
    -- para el fix async de /weekly (2026-08-03): la primera visita del día
    paga los ~7s de la llamada real a NVIDIA una sola vez en background
    (`kickoff_verdict`); esta función es lo que consultan esa misma request
    (para saber si ya hay algo) y los polls del frontend que le siguen."""
    if not heuristic.recommendations:
        return None
    _, predictable = _predictable_recs(ratings, heuristic)
    if not predictable:
        # nada que predecir -- todos los picks ya los vio, el resultado
        # "ya la viste" es el final, no hay nada async pendiente
        return _apply_verdict_result(ratings, heuristic, None, lang)
    cache_key = _verdict_cache_key(user_id, ratings, heuristic, lang)
    cached = _VERDICT_CACHE.get(cache_key)
    if cached is None:
        return None
    expires_at, cached_result = cached
    if expires_at <= _now_monotonic():
        return None
    return _apply_verdict_result(ratings, heuristic, cached_result, lang)


def kickoff_verdict(
    user_id: int, ratings: list[RatedItem], heuristic: RecommendResponse, lang: str = "es"
) -> None:
    """Dispara predict_fit en un thread de background si no hay uno ya
    corriendo para la misma clave (dedup vía _INFLIGHT_VERDICTS) -- así
    varios polls seguidos de /weekly antes de que el primero termine no
    disparan una llamada nueva a NVIDIA cada uno."""
    cache_key = _verdict_cache_key(user_id, ratings, heuristic, lang)
    with _INFLIGHT_LOCK:
        if cache_key in _INFLIGHT_VERDICTS:
            return
        _INFLIGHT_VERDICTS.add(cache_key)

    def _run() -> None:
        try:
            predict_fit(user_id, ratings, heuristic, lang)
        except LlmError as exc:
            logger.warning("Background weekly verdict failed: %s", exc)
        finally:
            with _INFLIGHT_LOCK:
                _INFLIGHT_VERDICTS.discard(cache_key)

    threading.Thread(target=_run, daemon=True).start()
