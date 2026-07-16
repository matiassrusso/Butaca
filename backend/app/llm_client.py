import json
import os
import socket
import urllib.request
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from urllib.error import URLError

from .models import RatedItem, RecommendResponse
from .recommender import TAG_PHRASES, capitalize_sentence, positive_tags_from_text

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
GENERATE_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# best model first, each with its own free-tier daily quota bucket — the
# top pick (gemini-flash-latest) is the newest/best but capped at 20
# requests/day and easy to exhaust while testing; when it (or the next one)
# is out of quota for the day, _call_gemini falls through to the next model
# instead of giving up and dropping straight to the heuristic why.
GEMINI_MODELS = ["gemini-flash-latest", "gemini-2.5-flash", "gemini-3-flash", "gemini-3.1-flash-lite"]
# gemini-flash-latest reasons internally before answering (visible as
# thoughtSignature in the response) — observed ~19s time-to-first-byte even
# for a trivial prompt, so a short timeout was silently discarding every
# real call and falling back to the heuristic every time.
REQUEST_TIMEOUT = 30

_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "taste_summary": {"type": "STRING"},
        "picks": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "title": {"type": "STRING"},
                    "why": {"type": "STRING"},
                },
                "required": ["title", "why"],
            },
        },
    },
    "required": ["taste_summary", "picks"],
}


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
    return bool(os.environ.get("GEMINI_API_KEY"))


def _phrase_for_tags(tags: list[str]) -> str:
    phrases = [TAG_PHRASES.get(tag, tag) for tag in tags]
    if not phrases:
        return ""
    if len(phrases) == 1:
        return phrases[0]
    return ", ".join(phrases[:-1]) + " y " + phrases[-1]


def _build_taste_digest(ratings: list[RatedItem]) -> str:
    # a raw list of "title (rating): review" lines makes Gemini infer taste
    # patterns itself, which it does inconsistently; naming the patterns
    # explicitly (recurring tags, standout titles) up front gives it a
    # concrete anchor to reference instead of writing generic praise
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


def _build_prompt(ratings: list[RatedItem], mood: str, heuristic: RecommendResponse) -> str:
    digest = _build_taste_digest(ratings)
    ratings_lines = (
        "\n".join(
            f"- {item.title} ({item.rating}/5): {item.review or 'sin reseña'}"
            for item in ratings[:40]
        )
        or "sin historial"
    )
    candidate_lines = "\n".join(
        f"- {rec.title} ({rec.year}, tags: {', '.join(rec.tags)}): {rec.overview[:200]}"
        for rec in heuristic.recommendations
    )
    return (
        "Sos un crítico de cine que arma recomendaciones muy personalizadas en español.\n\n"
        f"Perfil de gusto detectado: {digest}\n\n"
        f"Reseñas completas del usuario (hasta 40):\n{ratings_lines}\n\n"
        f"Mood de hoy: {mood or 'sin preferencia'}\n\n"
        "Candidatos ya filtrados por un motor heurístico. Elegí y ordená como mucho 5, "
        "usando SOLO títulos de esta lista (no inventes ni agregues otros):\n"
        f"{candidate_lines}\n\n"
        "Devolvé un resumen breve del gusto del usuario que use el perfil de arriba, no una "
        "frase genérica. Para cada pick elegido, una razón personalizada de 1-2 frases que "
        "nombre un patrón concreto del perfil o del historial (un tema recurrente, un tono, o "
        "una comparación explícita con un título que ya puntuó) — nada de elogios genéricos "
        "que podrían aplicar a cualquier usuario."
    )


@contextmanager
def _force_ipv4_dns():
    # ponytail: on networks where the local IPv6 route to Google's endpoint
    # is broken but IPv4 works (observed here — generativelanguage's AAAA
    # records hang to the full REQUEST_TIMEOUT with no error, while the A
    # records respond in ~1s), urlopen tries the (unreachable) IPv6 address
    # first and never gets to IPv4 within the timeout, so every call fails
    # silently and this feature never actually runs. Forcing AF_INET here
    # skips straight past that. Scoped to just this call, not global.
    original = socket.getaddrinfo

    def ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
        return original(host, port, socket.AF_INET, type, proto, flags)

    socket.getaddrinfo = ipv4_only
    try:
        yield
    finally:
        socket.getaddrinfo = original


def _call_one_model(model: str, body: bytes, api_key: str) -> dict:
    request = urllib.request.Request(
        f"{GENERATE_URL_TEMPLATE.format(model=model)}?key={api_key}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with _force_ipv4_dns(), urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            payload = json.loads(response.read())
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise LlmError(f"No pude consultar Gemini ({model}): {exc}") from exc

    try:
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise LlmError(f"Respuesta de Gemini ({model}) con formato inesperado: {exc}") from exc


def _call_gemini(prompt: str, api_key: str) -> dict:
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.4,
                "responseMimeType": "application/json",
                "responseSchema": _RESPONSE_SCHEMA,
            },
        }
    ).encode("utf-8")

    last_error: LlmError | None = None
    for model in GEMINI_MODELS:
        try:
            return _call_one_model(model, body, api_key)
        except LlmError as exc:
            last_error = exc
    raise last_error


def refine_recommendations(
    ratings: list[RatedItem], mood: str, heuristic: RecommendResponse
) -> RecommendResponse:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise LlmError("GEMINI_API_KEY no configurada.")
    if not heuristic.recommendations:
        raise LlmError("No hay candidatos para refinar.")

    result = _call_gemini(_build_prompt(ratings, mood, heuristic), api_key)

    by_title = {rec.title.strip().lower(): rec for rec in heuristic.recommendations}
    reordered = []
    for pick in result.get("picks", []):
        rec = by_title.get(str(pick.get("title", "")).strip().lower())
        if rec is None:
            continue
        why = capitalize_sentence(str(pick.get("why", "")).strip())
        reordered.append(rec.model_copy(update={"why": why or rec.why}))

    if not reordered:
        raise LlmError("Gemini no devolvió picks válidos de la lista de candidatos.")

    taste_summary = capitalize_sentence(str(result.get("taste_summary", "")).strip()) or heuristic.taste_summary
    return RecommendResponse(taste_summary=taste_summary, recommendations=reordered[:5])
