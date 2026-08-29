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
# Fallback fuera de NVIDIA (mismo host que los 2 modelos de arriba, así que una
# degradación de NVIDIA los afecta a los tres por igual — ver 2026-08-11 en
# build-log). Groq corre en hardware propio (LPU) pensado para latencia baja;
# API compatible con OpenAI, mismo formato de request que NVIDIA NIM. Opcional:
# si GROQ_API_KEY no está seteada, se lo salta sin error (ver docs/groq-setup.md).
GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"
# NVIDIA NIM model catalog (build.nvidia.com). chat_template_kwargs.
# enable_thinking=false (real parámetro de API, no un truco de system prompt)
# apaga el chain-of-thought de la familia Nemotron 3.x — eso fue lo que hizo
# lento a Gemini antes (~20s/call sin poder apagarlo).
#
# El catálogo free-tier ROTA: modelos se retiran (410 Gone) y la congestión
# mueve cuál responde rápido. Historial de esta cadena:
#   - 2026-08-11: primario nemotron-3.5-lightning-30b, fallbacks ultra-550b +
#     llama-3.1-8b, con Groq de último recurso.
#   - 2026-08-29: TODA esa cadena estaba muerta en prod (log real: lightning y
#     ultra-550b timeout 10s cada uno, llama-3.1-8b → 410 Gone/retirado, Groq
#     → 403 desde Render) → todo caía a heurístico tras ~20s. Re-medido el
#     catálogo (83 modelos, prompt de refine real + json_object): el ganador
#     nuevo es nemotron-3-nano-30b-a3b en ~0.7-0.9s con JSON válido, muy por
#     encima del resto. lightning-30b quedó de fallback (3.7-4.4s, intermitente),
#     mistral-nemotron de último recurso (4.7-5.2s). ultra-550b (503/timeout) y
#     llama-3.1-8b (410) sacados por muertos. Groq sigue 403 desde Render.
# No revalidar esta elección sin medir de nuevo (scratchpad/nv_sweep.py) — la
# congestión free-tier varía con el tiempo.
MODEL = "nvidia/nemotron-3-nano-30b-a3b"
# Fallback chain: se intenta cada modelo una vez, sin reintento por modelo.
# Los tres andan hoy con JSON válido; cubre que el primario timeoutee o
# devuelva basura, NO una caída total del endpoint (mismo host) — para eso
# queda Groq más abajo (hoy 403 desde Render, pero fast-fail e inofensivo).
NVIDIA_MODELS = [
    MODEL,
    "nvidia/nemotron-3.5-lightning-30b-a3b",
    "mistralai/mistral-nemotron",
]
REQUEST_TIMEOUT = 8

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

    # De la reseña Y de los tags del título. Antes salía SOLO de la reseña, así
    # que una peli puntuada 5 sin reseña no aportaba nada al patrón de gusto y
    # el agente terminaba apoyando todos los "why" en las pocas con texto
    # (reportado por Matías, 2026-08-07). El scoring ya miraba las dos cosas
    # (recommender._collect_preference_tags), así que el match_score y lo que
    # el agente entendía de la persona venían de fuentes distintas.
    known_tags = set(TAG_PHRASES)
    tag_counts: Counter[str] = Counter()
    for item in loved:
        tag_counts.update(positive_tags_from_text(item.review))
        tag_counts.update(tag for tag in item.tags if tag in known_tags)
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
        f"- [{rec.kind}, tmdb_id={rec.tmdb_id if rec.tmdb_id is not None else 'none'}] "
        f"{rec.title} ({rec.year}, tags: {', '.join(rec.tags)}): {rec.overview[:200]}"
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
    # el modelo leía la lista de candidatos como si fuera historial y escribía
    # "lo que disfrutaste en Memento" sobre OTRO pick de la misma tanda, que el
    # usuario nunca vio (reportado por Matías, 2026-08-07). La regla de arriba
    # ya lo prohibía, pero no nombraba esta confusión puntual.
    "- La lista de títulos sobre los que escribís NO es su historial. Son cosas que "
    "todavía no vio. Está PROHIBIDO decir que vio, disfrutó o puntuó cualquiera de "
    "ellos, y PROHIBIDO comparar uno con otro de la misma lista como si conociera "
    "alguno. Lo único que el usuario vio es lo que está en el perfil y las reseñas.\n"
    "- Citá siempre algo concreto de su perfil o su historial — nada de elogios genéricos "
    "que podrían aplicar a cualquier usuario.\n"
    # todos los why salían con "tono oscuro + misterio psicológico" porque son
    # los tags que dominan el perfil (reportado por Matías, 2026-08-07)
    # el agente citaba la reseña en TODOS los why porque eran las únicas
    # entradas del perfil con texto jugoso (reportado por Matías, 2026-08-07)
    "- Las reseñas que escribió son UNA fuente, no LA fuente. La mayoría de lo que vio "
    "lo puntuó sin escribir nada, y esos puntajes valen igual: un 5 sin reseña dice "
    "tanto como uno con reseña. Apoyate en una reseña puntual solo cuando aporte algo "
    "que el puntaje solo no dice; si la citás en todos los textos, sobra.\n"
    "- No apoyes todos los textos en los mismos dos o tres rasgos. Si ya usaste uno "
    "(por ejemplo el tono oscuro, o lo psicológico), el siguiente tiene que entrar por "
    "otro lado: el ritmo, la estructura, las actuaciones, el humor, la época, la "
    "dirección, lo que va a sentir al terminarla. Repetir el mismo par de adjetivos en "
    "los 6 hace que se lean como el mismo texto.\n"
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
    "- The list of titles you're writing about is NOT their history. These are things they "
    "haven't seen yet. It's FORBIDDEN to say they watched, enjoyed or rated any of them, "
    "and FORBIDDEN to compare one against another from that same list as if they knew it. "
    "The only things the user has seen are in the profile and the reviews.\n"
    "- Always cite something concrete from their profile or history — no generic praise "
    "that could apply to any user.\n"
    "- The reviews they wrote are ONE source, not THE source. Most of what they watched "
    "they rated without writing anything, and those ratings count just as much: a 5 with "
    "no review says as much as one with a review. Lean on a specific review only when it "
    "adds something the rating alone doesn't; quoting one in every text is too much.\n"
    "- Don't lean every text on the same two or three traits. If you already used one (say "
    "the dark tone, or the psychological angle), the next one has to come in from somewhere "
    "else: the pacing, the structure, the performances, the humor, the era, the directing, "
    "how they'll feel when it ends. Repeating the same pair of adjectives across all 6 "
    "makes them read as the same text.\n"
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


# "¿Qué vemos juntos?" (/recommend/together): el perfil que recibe el prompt es
# la MEZCLA de dos personas, así que atribuirle a "vos" un puntaje que puso la
# otra es directamente falso. Visto en vivo la primera vez que corrió la
# feature: "eso que resonó con vos en Punch-Drunk Love", una película que el
# usuario nunca vio (venía del historial del amigo). Es una mitigación
# probabilística, no una garantía — misma clase de regla que la de palabras
# pegadas de WRITING_RULES.
TOGETHER_NOTE = (
    "IMPORTANTE: el perfil de arriba es la MEZCLA de DOS personas que van a ver algo JUNTAS. "
    'No sabés cuál de las dos puntuó cada título, así que nunca digas "vos", "te gustó" ni cites '
    'un puntaje como si fuera de una sola. Hablá siempre en plural ("a ustedes", "les") y citá el '
    'historial como gusto compartido ("algo que ya vieron"). El pick tiene que funcionarles a las '
    "dos: si algo le pega a una sola, no es un buen pick para esta tanda."
)
TOGETHER_NOTE_EN = (
    "IMPORTANT: the profile above is the BLEND of TWO people who are going to watch something "
    'TOGETHER. You don\'t know which of them rated each title, so never say "you loved it" or '
    'quote a score as if it belonged to one of them. Always speak to both of them ("the two of '
    'you", "you both") and cite their history as shared taste ("something you\'ve both seen"). '
    "The pick has to work for BOTH: if it only lands for one of them, it isn't a good pick here."
)
TOGETHER_NOTE_BY_LANG = {"es": TOGETHER_NOTE, "en": TOGETHER_NOTE_EN}


def _build_prompt(
    ratings: list[RatedItem],
    mood: str,
    heuristic: RecommendResponse,
    lang: str = "es",
    audience_note: str = "",
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
        # vacío en todos los caminos menos /recommend/together — ver TOGETHER_NOTE
        f"{audience_note}{chr(10) * 2 if audience_note else ''}"
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
        "esté en esa lista, aunque le quede mejor al usuario. En particular, los títulos del "
        "perfil y de las reseñas NO son elegibles: esos ya los vio, recomendárselos de vuelta "
        "no le sirve de nada. Están ahí solo para que entiendas su gusto y los cites.\n\n"
        "Respondé ÚNICAMENTE con un JSON válido, sin texto ni markdown alrededor, con esta forma "
        'exacta: {"taste_summary": "...", "picks": [{"title": "...", "kind": "movie|series", '
        '"tmdb_id": 123, "why": "...", "match_score": 85}, ...]}'
    )


def _extract_json(content: str) -> dict:
    # models occasionally wrap the JSON in a ```json fence despite being told
    # not to — strip that instead of failing the parse
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.removeprefix("json").strip()
    return json.loads(text)


def _call_nvidia(
    prompt: str, api_key: str, model: str = MODEL, url: str = CHAT_COMPLETIONS_URL
) -> dict:
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
    # enable_thinking solo aplica a la familia Nemotron de NVIDIA; otros
    # modelos (el fallback llama de NVIDIA, y Groq) rechazan el parámetro
    if model.startswith("nvidia/nemotron"):
        payload_body["chat_template_kwargs"] = {"enable_thinking": False}
    body = json.dumps(payload_body).encode("utf-8")
    request = urllib.request.Request(
        url,
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
        if not isinstance(text, str):
            raise TypeError("choices[0].message.content no es texto")
        result = _extract_json(text)
        if not isinstance(result, dict):
            raise TypeError("el JSON raíz no es un objeto")
        if "picks" in result and (
            not isinstance(result["picks"], list)
            or not all(isinstance(pick, dict) for pick in result["picks"])
        ):
            raise TypeError("picks no es una lista de objetos")
        return result
    except (KeyError, IndexError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        raise LlmError(f"Respuesta de NVIDIA ({model}) con formato inesperado: {exc}") from exc


def _call_nvidia_with_fallback(prompt: str, api_key: str) -> dict:
    """Prueba cada modelo de NVIDIA_MODELS en orden una vez."""
    last_error: LlmError | None = None
    for model in NVIDIA_MODELS:
        try:
            return _call_nvidia(prompt, api_key, model)
        except LlmError as exc:
            last_error = exc
            logger.warning("NVIDIA %s falló: %s", model, exc)

    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        try:
            return _call_nvidia(prompt, groq_key, GROQ_MODEL, url=GROQ_CHAT_COMPLETIONS_URL)
        except LlmError as exc:
            last_error = exc
            logger.warning("Groq %s falló: %s", GROQ_MODEL, exc)

    assert last_error is not None  # NVIDIA_MODELS nunca está vacío
    raise last_error


def _now_monotonic() -> float:
    return time.monotonic()


def _refine_cache_key(
    ratings: list[RatedItem],
    mood: str,
    heuristic: RecommendResponse,
    lang: str = "es",
    audience_note: str = "",
) -> tuple[str, str, tuple, str, str]:
    candidates = tuple(_candidate_identity(rec) for rec in heuristic.recommendations)
    # audience_note entra en la clave: el mismo historial con y sin la nota de
    # "son dos personas" tiene que dar dos respuestas distintas, no reusar una
    return (
        _profile_block(ratings),
        mood.strip().lower(),
        candidates,
        normalize_lang(lang),
        audience_note,
    )


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


def _candidate_identity(rec: Recommendation) -> tuple:
    if rec.tmdb_id is not None:
        return rec.kind, rec.tmdb_id
    return rec.kind, _title_key(rec.title), rec.year


def _pick_match_score(pick: dict, fallback: int) -> int:
    try:
        score = int(pick.get("match_score"))
    except (TypeError, ValueError):
        return fallback
    return score if 1 <= score <= 99 else fallback


def _select_picks(
    result: dict, heuristic: RecommendResponse
) -> tuple[list, set[tuple], list[str]]:
    """Mapea los picks que devolvió el modelo contra los candidatos reales.

    Devuelve (picks_válidos, claves_elegidas, títulos_que_no_matchearon).
    Extraído para poder correrlo dos veces: una por la respuesta original y
    otra por la del reintento (ver refine_recommendations)."""
    by_identity = {_candidate_identity(rec): rec for rec in heuristic.recommendations}
    by_title: dict[str, list[Recommendation]] = {}
    for rec in heuristic.recommendations:
        by_title.setdefault(_title_key(rec.title), []).append(rec)
    reordered: list = []
    selected_keys: set[tuple] = set()
    unmatched: list[str] = []
    for pick in result["picks"]:
        raw_title = str(pick.get("title", ""))
        kind = pick.get("kind")
        tmdb_id = pick.get("tmdb_id")
        if kind in {"movie", "series"} and isinstance(tmdb_id, int):
            rec = by_identity.get((kind, tmdb_id))
        else:
            matches = by_title.get(_title_key(raw_title), [])
            rec = matches[0] if len(matches) == 1 else None
        if rec is None:
            unmatched.append(raw_title)
            continue
        key = _candidate_identity(rec)
        if key in selected_keys:
            continue
        why = capitalize_sentence(str(pick.get("why", "")).strip())
        match_score = _pick_match_score(pick, rec.match_score)
        if match_score <= 50:
            continue
        reordered.append(
            rec.model_copy(
                update={"why": why or rec.why, "match_score": match_score, "refined": True}
            )
        )
        selected_keys.add(key)
    return reordered, selected_keys, unmatched


def refine_recommendations(
    ratings: list[RatedItem],
    mood: str,
    heuristic: RecommendResponse,
    lang: str = "es",
    audience_note: str = "",
) -> RecommendResponse:
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise LlmError("NVIDIA_API_KEY no configurada.")
    if not heuristic.recommendations:
        raise LlmError("No hay candidatos para refinar.")

    cache_key = _refine_cache_key(ratings, mood, heuristic, lang, audience_note)
    result = _get_cached_refine(cache_key)
    cache_hit = result is not None
    if result is None:
        result = _call_nvidia_with_fallback(
            _build_prompt(ratings, mood, heuristic, lang, audience_note), api_key
        )

    reordered, selected_keys, unmatched = _select_picks(result, heuristic)

    # Reintento con corrección explícita cuando NINGÚN pick matcheó.
    #
    # El modelo devuelve JSON perfectamente válido pero elige títulos que no
    # están en la lista de candidatos — casi siempre películas del historial
    # del propio usuario, que ya vio (medido con el perfil de Matías,
    # 2026-08-07: una tanda entera devolvió 6 de 6 así, y se perdieron los 6
    # "why"). Como la respuesta no es un error, el reintento de
    # _call_nvidia_with_fallback no se dispara: solo cubre timeouts y JSON roto.
    #
    # La regla del prompt que prohíbe esto ya existe y aun así pasa, así que
    # este es el segundo intento nombrándole lo que rechazó. Solo cuando la
    # pérdida es total: reintentar también las tandas parciales duplicaría la
    # llamada casi siempre, por una mejora bastante menor.
    if not reordered and unmatched and not cache_hit:
        logger.info("Ningún pick del LLM matcheó; reintentando con corrección explícita")
        result = _call_nvidia_with_fallback(
            _build_prompt(ratings, mood, heuristic, lang, audience_note)
            + "\n\nINTENTO ANTERIOR RECHAZADO: devolviste "
            + ", ".join(f'"{title}"' for title in unmatched[:6])
            + ". Ninguno de esos está en la lista de candidatos de arriba — varios "
            "son títulos que el usuario YA VIO y que están en su perfil solo para "
            "que entiendas su gusto. Elegí de nuevo, COPIANDO los títulos "
            "exactamente como aparecen en la lista de candidatos.",
            api_key,
        )
        reordered, selected_keys, unmatched = _select_picks(result, heuristic)

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
            if _candidate_identity(rec) not in selected_keys:
                reordered.append(rec)
                selected_keys.add(_candidate_identity(rec))

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
        'exacta: {"picks": [{"title": "...", "kind": "movie|series", "tmdb_id": 123, '
        '"why": "...", "match_score": 85}, ...]}'
        + (f" — un elemento por cada uno de los {count}, nunca menos." if plural else ".")
    )


def _verdict_cache_key(
    user_id: int, ratings: list[RatedItem], heuristic: RecommendResponse, lang: str = "es"
) -> tuple[int, tuple, str, str]:
    candidates = tuple(_candidate_identity(rec) for rec in heuristic.recommendations)
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
    by_identity = {_candidate_identity(rec): rec for rec in heuristic.recommendations}
    by_title: dict[str, list[Recommendation]] = {}
    for rec in heuristic.recommendations:
        by_title.setdefault(_title_key(rec.title), []).append(rec)
    updates_by_key: dict[str, dict] = {}
    for pick in (result or {}).get("picks", []):
        kind = pick.get("kind")
        tmdb_id = pick.get("tmdb_id")
        if kind in {"movie", "series"} and isinstance(tmdb_id, int):
            rec = by_identity.get((kind, tmdb_id))
        else:
            matches = by_title.get(_title_key(str(pick.get("title", ""))), [])
            rec = matches[0] if len(matches) == 1 else None
        if rec is None:
            continue
        key = _title_key(rec.title)
        why = capitalize_sentence(str(pick.get("why", "")).strip())
        if why:
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


def _profile_facts(profile: dict | None) -> str:
    """Directores/actores/décadas/géneros ya agregados por taste_profile.
    _profile_block sale de los ratings crudos y no los tiene: el chat es la
    única pantalla donde el usuario puede preguntar "¿qué directores me
    gustan?" y esperar una respuesta directa."""
    if not profile:
        return ""
    def _names(key: str) -> str:
        return ", ".join(entry["name"] for entry in profile.get(key, [])[:5])
    def _labels(key: str, field: str) -> str:
        return ", ".join(str(entry[field]) for entry in profile.get(key, [])[:5])

    parts = []
    if directors := _names("top_directors"):
        parts.append(f"Directores que más se repiten: {directors}.")
    if actors := _names("top_actors"):
        parts.append(f"Actores que más se repiten: {actors}.")
    if genres := _labels("genre_breakdown", "genre"):
        parts.append(f"Géneros con más peso: {genres}.")
    if decades := _labels("decade_breakdown", "decade"):
        parts.append(f"Décadas que más ve: {decades}.")
    return " ".join(parts)


# Sin tope, una charla larga manda el historial entero en CADA turno: el
# prompt (y la cuota de NVIDIA, compartida con recomendaciones y veredictos)
# crece sin techo. El historial lo sostiene el cliente, así que el tope real
# se aplica acá, no confiando en lo que mande.
CHAT_HISTORY_TURNS = 10


def _chat_history_lines(messages: list[tuple[str, str]], lang: str = "es") -> str:
    labels = {"es": ("Usuario", "Vos"), "en": ("User", "You")}[normalize_lang(lang)]
    return "\n".join(
        f"{labels[0] if role == 'user' else labels[1]}: {content}"
        for role, content in messages[-CHAT_HISTORY_TURNS:]
    )


# La tarea del chat necesita levantar UNA regla de WRITING_RULES: la que
# prohíbe nombrar títulos fuera del perfil. Existe porque en /recommend y
# /weekly los títulos salen de un pool cerrado y nombrar otro rompe el
# matcheo; en una charla libre, poder decir "mirate Heat" ES la feature. Lo
# que NO se levanta es lo importante: sigue prohibido afirmar que el usuario
# vio algo que no puntuó (ese era el bug de fondo, no el nombrar títulos).
_CHAT_TITLE_OVERRIDE = (
    "EXCEPCIÓN a la regla de títulos, solo acá: en esta charla SÍ podés nombrar películas "
    "y series que no están en su historial, porque parte de tu trabajo es recomendarle "
    "cosas nuevas. Lo que sigue PROHIBIDO es dar por sentado que las vio: si no está en el "
    "perfil de arriba, no podés inferir si la vio: la lista está recortada. Preguntale en vez de suponerlo. "
    "Si en su mensaje nombra películas como ejemplo de lo que busca ('tipo X, Y, Z'), son "
    "referencia de gusto, no un pedido: no se las devuelvas como recomendación, buscá algo "
    "distinto que comparta ese clima. Tampoco repitas un título que ya nombraste vos o que "
    "el usuario ya nombró antes en esta charla, salvo que te pida hablar de ese título puntual. "
    "Cuando recomiendes algo para ver AHORA, no elijas un título que ya está en el perfil de "
    "arriba (ya lo vio y lo puntuó) — nombralo solo para compararlo, nunca como el plan de la "
    "noche, salvo que el usuario pida explícitamente volver a verlo."
)
_CHAT_TITLE_OVERRIDE_EN = (
    "EXCEPTION to the title rule, only here: in this conversation you CAN name movies and "
    "shows that aren't in their history, because part of your job is recommending new "
    "things. What's still FORBIDDEN is assuming they watched them: if it's not in the "
    "profile above, you cannot infer whether they watched it: the list is truncated. Ask instead of assuming. "
    "If they name movies as examples of what they're after ('like X, Y, Z'), those are "
    "taste references, not a request — don't hand them back as the recommendation, find "
    "something different that shares that vibe. Also don't repeat a title you already "
    "suggested or that they already named earlier in this chat, unless they explicitly "
    "ask about that specific title. When you recommend something to watch NOW, don't pick "
    "a title that's already in the profile above (they've already seen and rated it) — only "
    "name it for comparison, never as tonight's plan, unless they explicitly ask to rewatch it."
)
_CHAT_TASK = (
    "Sos un experto y sabio de cine que además conoce el gusto de esta persona. Respondé "
    "su último mensaje: podés contestar preguntas factuales (trama sin spoilers grandes "
    "salvo que los pida, reparto, dirección, año, duración, contexto y datos curiosos), "
    "dar opiniones, discutir y recomendar. El perfil de gusto es personalización, no tu "
    "única fuente. Mantené la charla concisa, pero usá más de cuatro frases si una pregunta "
    "factual o detallada lo necesita. Si el mensaje no tiene nada que ver con cine, decilo "
    "con humor y volvé al tema. Si te pide algo para ver o le recomendás una película o serie, "
    "NOMBRALA de forma explícita (título, y el año si ayuda a desambiguar) — nunca la describas "
    "sin decir cuál es. Podés dar una recomendación principal clara y a lo sumo una o dos "
    "alternativas, pero siempre con el título dicho."
)
_CHAT_TASK_EN = (
    "You're a film expert and sage who also knows this person's taste. Answer their last "
    "message: you can handle factual questions (plot without major spoilers unless requested, "
    "cast, direction, year, runtime, context and trivia), offer opinions, discuss and "
    "recommend. Their taste profile personalizes your answer; it is not your only source. "
    "Keep the conversation concise, but use more than four sentences when a factual or detailed "
    "question needs it. If the message has nothing to do with film, say so with some humor and steer back. "
    "If they ask for something to watch or you recommend a movie or show, NAME it explicitly "
    "(title, plus the year if it helps disambiguate) — never describe one without saying which it is. "
    "You can give one clear main pick and at most one or two alternatives, but always with the title stated."
)
_CHAT_NO_HISTORY = (
    "OJO: esta persona todavía no puntuó nada, así que no conocés su gusto. No inventes que "
    "sabés qué le gusta: decíselo de frente y sugerile que importe su historial de "
    "Letterboxd o puntúe algunos títulos para que la puedas ayudar en serio."
)
_CHAT_NO_HISTORY_EN = (
    "HEADS UP: this person hasn't rated anything yet, so you don't know their taste. Don't "
    "pretend you do: tell them straight and suggest importing their Letterboxd history or "
    "rating a few titles so you can actually help."
)
_CHAT_TASK_BY_LANG = {"es": _CHAT_TASK, "en": _CHAT_TASK_EN}
_CHAT_OVERRIDE_BY_LANG = {"es": _CHAT_TITLE_OVERRIDE, "en": _CHAT_TITLE_OVERRIDE_EN}
_CHAT_NO_HISTORY_BY_LANG = {"es": _CHAT_NO_HISTORY, "en": _CHAT_NO_HISTORY_EN}

# Pedido de Matías (2026-08-12): "que en base a [lo que vio, lo que le gustó,
# lo que no, lo que le interesa, lo que no] te recomiende". El chat ya
# recibía ratings (visto+puntuado) y el resumen de perfil, pero nunca
# watchlist ("me interesa ver", nunca la vio) ni feedback de picks pasados
# ("le interesó"/"no le interesó" un pick que nunca llegó a puntuar) — la
# misma señal que ya usa recommend() vía db.get_feedback_signals, que acá
# nunca se leía.
_CHAT_SIGNALS_NOTE_BY_LANG = {
    "es": (
        "Estas señales son distintas de lo que vio y puntuó arriba: la watchlist es lo que "
        "quiere ver pero TODAVÍA NO VIO (no la trates como historial), y el feedback es lo "
        "que opinó de picks que le sugirió Butaca antes SIN llegar a puntuarlos. Usalas: si "
        "viene al caso podés recordarle algo de su watchlist en vez de inventar un título "
        "nuevo. Nunca vuelvas a sugerir algo que ya rechazó o que ya marcó como visto."
    ),
    "en": (
        "These signals are different from what they watched and rated above: the watchlist "
        "is stuff they want to watch but HAVEN'T SEEN YET (don't treat it as history), and "
        "the feedback is what they thought of past Butaca suggestions they never got around "
        "to rating. Use them: when relevant you can bring up something from their watchlist "
        "instead of inventing a new title. Never suggest something they already turned down "
        "or already marked as watched."
    ),
}


def _chat_signals_block(watchlist: list[str], feedback: dict | None, lang: str) -> str:
    feedback = feedback or {}
    if lang == "es":
        labels = {
            "watchlist": "Watchlist, quiere ver y todavía NO vio",
            "interested": "Le interesó un pick sugerido antes (sin puntuarlo)",
            "not_interested": "Rechazó un pick sugerido antes (no le interesó)",
            "seen": "Marcó como ya vista (sin puntuarla)",
        }
    else:
        labels = {
            "watchlist": "Watchlist, wants to watch and HASN'T seen yet",
            "interested": "Was interested in a past suggested pick (never rated)",
            "not_interested": "Turned down a past suggested pick (not interested)",
            "seen": "Marked as already seen (never rated)",
        }
    lines = []
    if watchlist:
        lines.append(f"{labels['watchlist']}: {', '.join(watchlist[:30])}.")
    if interested := [item["title"] for item in feedback.get("interested", [])]:
        lines.append(f"{labels['interested']}: {', '.join(interested[:20])}.")
    if not_interested := [item["title"] for item in feedback.get("not_interested", [])]:
        lines.append(f"{labels['not_interested']}: {', '.join(not_interested[:20])}.")
    if seen := feedback.get("seen_titles", []):
        lines.append(f"{labels['seen']}: {', '.join(seen[:20])}.")
    if not lines:
        return ""
    return "\n".join(lines) + f"\n{_CHAT_SIGNALS_NOTE_BY_LANG[lang]}\n"


_CONTENT_KEYWORD_MARKERS = (
    "sex", "sexual", "nudity", "nude", "erotic", "violence", "violent", "gore", "blood",
    "drug", "cocaine", "heroin", "alcohol", "rape",
)


def extract_chat_title(messages: list[tuple[str, str]]) -> dict | None:
    """Cheap, best-effort title extraction for chat grounding."""
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        return None
    context = "\n".join(
        f"{'Usuario' if role == 'user' else 'Butaca'}: {content}"
        for role, content in messages[-3:]
    )
    prompt = (
        "Del ultimo mensaje del usuario y este breve contexto, extrae la pelicula o serie concreta "
        "sobre la que pregunta. Si no hay una, devuelve titulo vacio. Responde solo JSON exacto "
        '{"title": "...", "year": null}.\n\n'
        f"{context}"
    )
    try:
        result = _call_nvidia_with_fallback(prompt, api_key)
    except LlmError:
        return None
    title = str(result.get("title") or "").strip()
    if not title or title.lower() in {"null", "none", "n/a"}:
        return None
    year = result.get("year")
    return {"title": title[:200], "year": year if isinstance(year, int) else None}


def _chat_grounding_block(grounding: dict | None, lang: str) -> str:
    if not grounding:
        return (
            "No tenés datos verificados de TMDb sobre el título: no afirmes trama, reparto, "
            "duración ni contenido como hechos; aclaralo.\n"
            if lang == "es"
            else "You have no verified TMDb data about the title: do not state plot, cast, runtime or content as facts; say so clearly.\n"
        )
    content_keywords = [
        keyword for keyword in grounding.get("keywords", [])
        if any(marker in keyword.lower() for marker in _CONTENT_KEYWORD_MARKERS)
    ]
    kind = grounding.get("kind")
    if lang == "es":
        kind_label = "película" if kind == "movie" else "serie"
        unavailable = "No disponible"
        content_instruction = (
            "Para preguntas factuales o de contenido, anclate a estos datos. Para sexo, desnudez, "
            "violencia o drogas usá estas keywords y la clasificación: si no lo confirman, decí "
            "honestamente que no podés confirmarlo con estos datos y ofrecé la clasificación como referencia."
        )
        header = f"DATOS REALES DE TMDB SOBRE {grounding.get('title', '')} (tratalos como verdad; no los contradigas)"
        fields = (
            f"Tipo: {kind_label} | Año: {grounding.get('year') or unavailable}\n"
            f"Géneros: {', '.join(grounding.get('genres', [])) or unavailable}\n"
            f"Director: {grounding.get('director') or unavailable}\n"
            f"Reparto principal: {', '.join(grounding.get('actors', [])) or unavailable}\n"
            f"Sinopsis: {grounding.get('overview') or unavailable}\n"
            f"Duración: {str(grounding['runtime']) + ' min' if grounding.get('runtime') else unavailable} | "
            f"Nota TMDb: {grounding.get('vote_average') if grounding.get('vote_average') is not None else unavailable}\n"
            f"Clasificación US: {grounding.get('certification') or unavailable}\n"
            f"Señales de contenido (keywords): {', '.join(content_keywords) or 'Sin señales específicas en las keywords de TMDb'}"
        )
    else:
        kind_label = "movie" if kind == "movie" else "series"
        unavailable = "Unavailable"
        content_instruction = (
            "For factual or content questions, ground your answer in these facts. For sex, nudity, "
            "violence or drugs, use these keywords and the certification: if they do not confirm it, "
            "say honestly that you cannot confirm it from this data and offer the rating as context."
        )
        header = f"REAL TMDB DATA ABOUT {grounding.get('title', '')} (treat it as truth; do not contradict it)"
        fields = (
            f"Type: {kind_label} | Year: {grounding.get('year') or unavailable}\n"
            f"Genres: {', '.join(grounding.get('genres', [])) or unavailable}\n"
            f"Director: {grounding.get('director') or unavailable}\n"
            f"Lead cast: {', '.join(grounding.get('actors', [])) or unavailable}\n"
            f"Overview: {grounding.get('overview') or unavailable}\n"
            f"Runtime: {str(grounding['runtime']) + ' min' if grounding.get('runtime') else unavailable} | "
            f"TMDb rating: {grounding.get('vote_average') if grounding.get('vote_average') is not None else unavailable}\n"
            f"US certification: {grounding.get('certification') or unavailable}\n"
            f"Content signals (keywords): {', '.join(content_keywords) or 'No specific TMDb keyword signals'}"
        )
    return f"{header}\n{fields}\n{content_instruction}\n"


def _build_chat_prompt(
    ratings: list[RatedItem],
    profile: dict | None,
    messages: list[tuple[str, str]],
    lang: str = "es",
    watchlist: list[str] | None = None,
    feedback: dict | None = None,
    grounding: dict | None = None,
) -> str:
    """Tarea: conversar. Misma voz y mismas reglas de escritura que
    _build_prompt y _build_verdict_prompt — ver AGENT_VOICE arriba."""
    lang = normalize_lang(lang)
    language_line = "" if lang == "es" else "Write your ENTIRE reply in English.\n\n"
    facts = _profile_facts(profile)
    signals = _chat_signals_block(watchlist or [], feedback, lang)
    grounding_block = _chat_grounding_block(grounding, lang)
    no_history = "" if ratings else f"{_CHAT_NO_HISTORY_BY_LANG[lang]}\n\n"
    return (
        f"{_AGENT_VOICE_BY_LANG[lang]}\n\n"
        f"{language_line}"
        f"{_profile_block(ratings)}\n"
        f"{facts}\n\n"
        f"{signals}\n"
        f"{grounding_block}\n"
        f"{no_history}"
        f"{_CHAT_TASK_BY_LANG[lang]}\n\n"
        f"{_chat_history_lines(messages, lang)}\n\n"
        f"{_WRITING_RULES_BY_LANG[lang]}\n\n"
        f"{_CHAT_OVERRIDE_BY_LANG[lang]}\n\n"
        f"{_SCORE_RULE_BY_LANG[lang]}\n\n"
        "Respondé ÚNICAMENTE con un JSON válido, sin texto ni markdown alrededor, con esta "
        'forma exacta: {"reply": "..."}'
    )


def chat_reply(
    ratings: list[RatedItem],
    profile: dict | None,
    messages: list[tuple[str, str]],
    lang: str = "es",
    watchlist: list[str] | None = None,
    feedback: dict | None = None,
    grounding: dict | None = None,
) -> str:
    """La versión conversacional del agente (/chat). Sin cache: cada turno es
    distinto del anterior por definición, así que una clave de cache nunca
    pegaría dos veces — el tope de gasto lo pone el rate limit del endpoint."""
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise LlmError("NVIDIA_API_KEY no configurada.")

    prompt = _build_chat_prompt(ratings, profile, messages, lang, watchlist, feedback, grounding)
    result = _call_nvidia_with_fallback(prompt, api_key)
    reply = capitalize_sentence(str(result.get("reply", "")).strip())
    if not reply:
        raise LlmError("El modelo devolvió una respuesta vacía.")
    return reply


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
