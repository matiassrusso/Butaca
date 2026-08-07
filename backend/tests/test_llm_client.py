import json
import threading
import time

import pytest

from backend.app import llm_client
from backend.app.models import RatedItem, Recommendation, RecommendResponse
from backend.app.recommender import TAG_PHRASES


@pytest.fixture(autouse=True)
def _clear_refine_cache():
    # module-global cache (same idiom as tmdb_client's _DISCOVER_CACHE) —
    # clear between tests so one test's cached refine result can't leak into
    # another test that reuses the same mood/candidates.
    llm_client._REFINE_CACHE.clear()
    llm_client._VERDICT_CACHE.clear()
    llm_client._INFLIGHT_VERDICTS.clear()
    yield
    llm_client._REFINE_CACHE.clear()
    llm_client._VERDICT_CACHE.clear()
    llm_client._INFLIGHT_VERDICTS.clear()


HEURISTIC = RecommendResponse(
    taste_summary="resumen heurístico",
    recommendations=[
        Recommendation(
            title="Fake Thriller", year=2020, kind="movie", why="heurística",
            match_score=70, tags=["dark", "psychological"],
        ),
        Recommendation(
            title="Fake Comedy", year=2019, kind="movie", why="heurística",
            match_score=60, tags=["funny", "light"],
        ),
    ],
)


def test_refine_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    with pytest.raises(llm_client.LlmError):
        llm_client.refine_recommendations([], "funny", HEURISTIC)


def test_refine_requires_candidates(monkeypatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")

    with pytest.raises(llm_client.LlmError):
        llm_client.refine_recommendations([], "funny", RecommendResponse(taste_summary="", recommendations=[]))


def test_refine_reorders_and_overrides_why(monkeypatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")

    def fake_call_nvidia(prompt: str, api_key: str) -> dict:
        return {
            "taste_summary": "resumen del agente",
            "picks": [
                {
                    "title": "Fake Comedy",
                    "why": "porque te reís poco últimamente",
                    "match_score": 78,
                },
                {
                    "title": "Fake Thriller",
                    "why": "porque te gusta lo oscuro",
                    "match_score": 91,
                },
            ],
        }

    monkeypatch.setattr(llm_client, "_call_nvidia_with_fallback", fake_call_nvidia)

    ratings = [RatedItem(title="Old Movie", rating=4.5, review="genial")]
    result = llm_client.refine_recommendations(ratings, "funny", HEURISTIC)

    assert result.taste_summary == "Resumen del agente"
    assert [r.title for r in result.recommendations] == ["Fake Comedy", "Fake Thriller"]
    assert result.recommendations[0].why == "Porque te reís poco últimamente"
    assert result.recommendations[0].match_score == 78
    assert result.recommendations[0].tags == ["funny", "light"]
    assert all(rec.refined for rec in result.recommendations)


def test_refine_backfills_six_when_model_returns_fewer_picks(monkeypatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    candidates = RecommendResponse(
        taste_summary="heurístico",
        recommendations=[
            Recommendation(
                title=f"Candidate {index}",
                year=2000 + index,
                kind="movie",
                why="heurística",
                match_score=50,
                tags=["dark"],
            )
            for index in range(8)
        ],
    )
    monkeypatch.setattr(
        llm_client,
        "_call_nvidia_with_fallback",
        lambda prompt, api_key: {
            "taste_summary": "refinado",
            "picks": [
                {"title": f"Candidate {index}", "why": "buen fit", "match_score": 80 + index}
                for index in range(4)
            ],
        },
    )

    result = llm_client.refine_recommendations([], "", candidates)

    assert len(result.recommendations) == 6
    assert [rec.title for rec in result.recommendations[:4]] == [
        "Candidate 0",
        "Candidate 1",
        "Candidate 2",
        "Candidate 3",
    ]
    # los 4 primeros los eligió el LLM; los 2 de relleno son heurística tal
    # cual (2026-08-03, TASKS.md: sin esto no había forma de distinguirlos)
    assert all(rec.refined for rec in result.recommendations[:4])
    assert not any(rec.refined for rec in result.recommendations[4:])


def test_refine_drops_a_pick_with_a_negative_verdict(monkeypatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    candidates = RecommendResponse(
        taste_summary="heurístico",
        recommendations=[
            Recommendation(
                title=f"Candidate {index}",
                year=2000 + index,
                kind="movie",
                why="heurística",
                match_score=60,
                tags=["dark"],
            )
            for index in range(7)
        ],
    )
    monkeypatch.setattr(
        llm_client,
        "_call_nvidia_with_fallback",
        lambda prompt, api_key: {
            "taste_summary": "refinado",
            "picks": [
                {
                    "title": f"Candidate {index}",
                    "why": "no es para vos" if index == 0 else "buen fit",
                    "match_score": 20 if index == 0 else 80,
                }
                for index in range(7)
            ],
        },
    )

    result = llm_client.refine_recommendations([], "", candidates)

    assert len(result.recommendations) == 6
    assert "Candidate 0" not in {rec.title for rec in result.recommendations}
    assert all(rec.match_score > 50 for rec in result.recommendations)


def test_refine_ignores_titles_outside_the_candidate_list(monkeypatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")

    def fake_call_nvidia(prompt: str, api_key: str) -> dict:
        return {"taste_summary": "x", "picks": [{"title": "Made Up Movie", "why": "no existe"}]}

    monkeypatch.setattr(llm_client, "_call_nvidia_with_fallback", fake_call_nvidia)

    with pytest.raises(llm_client.LlmError):
        llm_client.refine_recommendations([], "funny", HEURISTIC)


def test_call_nvidia_wraps_network_errors(monkeypatch) -> None:
    def raise_url_error(*args, **kwargs):
        raise llm_client.URLError("boom")

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", raise_url_error)

    with pytest.raises(llm_client.LlmError):
        llm_client._call_nvidia("prompt", "fake-key")


def test_call_nvidia_requests_json_object_format(monkeypatch) -> None:
    # el modelo devuelve JSON inválido de forma intermitente sin esto; regresión
    # del "refine caía siempre al heurístico" reportado desde producción
    captured = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"choices": [{"message": {"content": "{\\"ok\\": true}"}}]}'

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data)
        return _Resp()

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)

    llm_client._call_nvidia("prompt", "fake-key")

    assert captured["body"]["response_format"] == {"type": "json_object"}


def test_call_nvidia_omits_thinking_flag_for_non_nemotron_models(monkeypatch) -> None:
    # el fallback (llama) rechaza chat_template_kwargs con 400; solo Nemotron
    # lo acepta
    captured = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"choices": [{"message": {"content": "{\\"ok\\": true}"}}]}'

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data)
        return _Resp()

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)

    llm_client._call_nvidia("prompt", "fake-key", "meta/llama-3.1-70b-instruct")
    assert "chat_template_kwargs" not in captured["body"]

    llm_client._call_nvidia("prompt", "fake-key", llm_client.MODEL)
    assert captured["body"]["chat_template_kwargs"] == {"enable_thinking": False}


def test_fallback_retries_same_model_before_switching(monkeypatch) -> None:
    monkeypatch.setattr(llm_client.time, "sleep", lambda _s: None)
    calls: list[str] = []

    def fake_call(prompt, api_key, model):
        calls.append(model)
        # el primer intento del modelo primario falla, el segundo (reintento) anda
        if len(calls) == 1:
            raise llm_client.LlmError("timeout transitorio")
        return {"picks": [{"title": "X", "why": "ok"}]}

    monkeypatch.setattr(llm_client, "_call_nvidia", fake_call)

    result = llm_client._call_nvidia_with_fallback("prompt", "fake-key")

    assert result == {"picks": [{"title": "X", "why": "ok"}]}
    # reintentó el primario, no saltó al fallback
    assert calls == [llm_client.MODEL, llm_client.MODEL]


def test_fallback_switches_model_when_primary_exhausts_retries(monkeypatch) -> None:
    monkeypatch.setattr(llm_client.time, "sleep", lambda _s: None)
    calls: list[str] = []

    def fake_call(prompt, api_key, model):
        calls.append(model)
        if model == llm_client.MODEL:
            raise llm_client.LlmError("modelo primario caído")
        return {"picks": [{"title": "X", "why": "del fallback"}]}

    monkeypatch.setattr(llm_client, "_call_nvidia", fake_call)

    result = llm_client._call_nvidia_with_fallback("prompt", "fake-key")

    assert result["picks"][0]["why"] == "del fallback"
    # agotó los 2 intentos del primario y recién ahí pasó al fallback
    assert calls == [llm_client.MODEL, llm_client.MODEL, llm_client.NVIDIA_MODELS[1]]


def test_fallback_raises_when_all_models_fail(monkeypatch) -> None:
    monkeypatch.setattr(llm_client.time, "sleep", lambda _s: None)

    def always_fail(prompt, api_key, model):
        raise llm_client.LlmError(f"{model} caído")

    monkeypatch.setattr(llm_client, "_call_nvidia", always_fail)

    with pytest.raises(llm_client.LlmError):
        llm_client._call_nvidia_with_fallback("prompt", "fake-key")


def test_extract_json_parses_plain_json() -> None:
    assert llm_client._extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_strips_markdown_fence() -> None:
    fenced = '```json\n{"a": 1}\n```'
    assert llm_client._extract_json(fenced) == {"a": 1}


def test_build_taste_digest_handles_empty_history() -> None:
    assert llm_client._build_taste_digest([]) == "Sin historial todavía."


def test_build_taste_digest_names_patterns_and_standout_titles() -> None:
    ratings = [
        RatedItem(title="Loved Dark One", rating=5, review="a dark and psychological ride"),
        RatedItem(title="Loved Dark Two", rating=4.5, review="another dark, quiet story"),
        RatedItem(title="Hated It", rating=1, review="boring and empty"),
    ]

    digest = llm_client._build_taste_digest(ratings)

    assert "3 títulos puntuados" in digest
    assert "promedio 3.5/5" in digest
    assert "tono oscuro" in digest  # "dark" -> TAG_PHRASES
    assert "Loved Dark One" in digest and "Loved Dark Two" in digest
    assert "Le encantaron especialmente" in digest
    assert "Hated It" in digest and "No le gustaron" in digest


def test_build_prompt_includes_digest_and_grounding_instructions() -> None:
    ratings = [RatedItem(title="Old Movie", rating=5, review="dark and psychological")]

    prompt = llm_client._build_prompt(ratings, "funny", HEURISTIC)

    assert "Perfil de gusto detectado:" in prompt
    assert "Old Movie" in prompt
    assert "algo concreto de su perfil" in prompt
    assert "Fake Thriller" in prompt and "Fake Comedy" in prompt


def test_both_prompts_share_the_same_voice_and_writing_rules() -> None:
    # pedido de Matías (2026-07-31): "TODA la página debería tener el mismo
    # sistema de LLM, con los mismos prompts y los mismos tonos, no importa si
    # es en /weekly o en /recommend". Lo que cambia es la TAREA; la voz y las
    # reglas de escritura tienen que salir de la misma fuente.
    ratings = [RatedItem(title="Old Movie", rating=5, review="dark")]

    recommend_prompt = llm_client._build_prompt(ratings, "funny", HEURISTIC)
    verdict_prompt = llm_client._build_verdict_prompt(ratings, HEURISTIC)

    for shared in (llm_client.AGENT_VOICE, llm_client.WRITING_RULES, llm_client.SCORE_RULE):
        assert shared in recommend_prompt
        assert shared in verdict_prompt


def test_both_prompts_share_the_same_voice_in_english() -> None:
    # mismo invariante que el test de arriba pero para lang="en" (pedido de
    # Matías, 2026-08-06): si alguien traduce un prompt y se olvida del otro,
    # la voz se parte entre pantallas igual que se partía antes en español.
    ratings = [RatedItem(title="Old Movie", rating=5, review="dark")]

    recommend_prompt = llm_client._build_prompt(ratings, "funny", HEURISTIC, lang="en")
    verdict_prompt = llm_client._build_verdict_prompt(ratings, HEURISTIC, lang="en")

    for shared in (
        llm_client.AGENT_VOICE_EN,
        llm_client.WRITING_RULES_EN,
        llm_client.SCORE_RULE_EN,
    ):
        assert shared in recommend_prompt
        assert shared in verdict_prompt
    # las reglas en español no pueden colarse: el modelo mezclaría idiomas
    assert llm_client.WRITING_RULES not in recommend_prompt
    assert llm_client.WRITING_RULES not in verdict_prompt


def test_verdict_cache_is_keyed_by_language() -> None:
    # sin el idioma en la clave, el primer usuario que pide /weekly en español
    # deja cacheado ese resultado y el siguiente que lo pide en inglés recibe
    # los why en español (y viceversa).
    ratings = [RatedItem(title="Old Movie", rating=5, review="dark")]

    key_es = llm_client._verdict_cache_key(1, ratings, HEURISTIC, "es")
    key_en = llm_client._verdict_cache_key(1, ratings, HEURISTIC, "en")

    assert key_es != key_en


def test_refine_cache_is_keyed_by_language() -> None:
    ratings = [RatedItem(title="Old Movie", rating=5, review="dark")]

    key_es = llm_client._refine_cache_key(ratings, "funny", HEURISTIC, "es")
    key_en = llm_client._refine_cache_key(ratings, "funny", HEURISTIC, "en")

    assert key_es != key_en


def test_already_seen_why_is_translated() -> None:
    # el why de "ya la viste" no pasa por el LLM (se arma en Python), así que
    # sin traducirlo explícitamente quedaba en español dentro de una página en
    # inglés.
    ratings = [RatedItem(title="Fake Thriller", rating=5, review="dark")]

    result_en = llm_client._apply_verdict_result(ratings, HEURISTIC, None, lang="en")
    seen = next(r for r in result_en.recommendations if r.title == "Fake Thriller")

    assert "You already watched this" in seen.why
    assert "Ya la viste" not in seen.why


def test_build_prompt_does_not_cite_a_numeric_score_for_manual_ratings() -> None:
    # bug reportado por Matías (2026-07-30): un click de "Me encantó" en el
    # modo "Sin cuenta" es un rating sintético (4.5 interno para el scoring),
    # no un puntaje que el usuario haya dado — el prompt no puede citarlo
    # como "(4.5/5)", el LLM lo repetiría tal cual en el "why".
    ratings = [
        RatedItem(title="Import Movie", rating=4.5, review="", source="import"),
        RatedItem(title="Manual Movie", rating=4.5, review="", source="manual"),
    ]

    prompt = llm_client._build_prompt(ratings, "", HEURISTIC)

    assert "Import Movie (4.5/5)" in prompt
    assert "Manual Movie (4.5/5)" not in prompt
    assert "Manual Movie (te encantó, sin puntaje numérico)" in prompt


def test_build_prompt_cites_precise_butaca_star_rating() -> None:
    ratings = [RatedItem(title="Star Movie", rating=3.5, review="", source="star")]

    prompt = llm_client._build_prompt(ratings, "", HEURISTIC)

    assert "Star Movie (3.5/5)" in prompt


def test_build_prompt_does_not_cite_a_numeric_score_for_letterboxd_likes() -> None:
    # bug reportado por Matías (2026-07-31): los likes/favoritos de
    # Letterboxd sin estrellas puestas (source="like") son un rating
    # sintético igual que el modo manual, pero tenían source="import" antes
    # y se colaban citando "(4.5/5)" como si fuera un puntaje real.
    ratings = [RatedItem(title="Liked Movie", rating=4.5, review="", source="like")]

    prompt = llm_client._build_prompt(ratings, "", HEURISTIC)

    assert "Liked Movie (4.5/5)" not in prompt
    assert "Liked Movie (te encantó, sin puntaje numérico)" in prompt


def _fake_nvidia(call_count: list[int]):
    def fake_call_nvidia(prompt: str, api_key: str) -> dict:
        call_count.append(1)
        return {
            "taste_summary": "resumen del agente",
            "picks": [
                {"title": "Fake Comedy", "why": "porque te reís poco últimamente"},
                {"title": "Fake Thriller", "why": "porque te gusta lo oscuro"},
            ],
        }

    return fake_call_nvidia


def test_refine_recommendations_caches_same_mood_and_candidates(monkeypatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    calls: list[int] = []
    monkeypatch.setattr(llm_client, "_call_nvidia_with_fallback", _fake_nvidia(calls))

    first = llm_client.refine_recommendations([], "funny", HEURISTIC)
    second = llm_client.refine_recommendations([], "funny", HEURISTIC)

    assert len(calls) == 1  # second call served from cache, no new NVIDIA hit
    assert first.taste_summary == second.taste_summary
    assert [r.title for r in first.recommendations] == [r.title for r in second.recommendations]


def test_refine_recommendations_cache_misses_on_different_mood(monkeypatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    calls: list[int] = []
    monkeypatch.setattr(llm_client, "_call_nvidia_with_fallback", _fake_nvidia(calls))

    llm_client.refine_recommendations([], "funny", HEURISTIC)
    llm_client.refine_recommendations([], "romance", HEURISTIC)

    assert len(calls) == 2


def test_refine_recommendations_cache_misses_on_different_profiles(monkeypatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    calls: list[int] = []
    monkeypatch.setattr(llm_client, "_call_nvidia_with_fallback", _fake_nvidia(calls))

    llm_client.refine_recommendations(
        [RatedItem(title="Alien", rating=5)], "funny", HEURISTIC
    )
    llm_client.refine_recommendations(
        [RatedItem(title="Alien", rating=1)], "funny", HEURISTIC
    )

    assert len(calls) == 2


def test_refine_recommendations_cache_misses_on_different_candidates(monkeypatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    calls: list[int] = []
    monkeypatch.setattr(llm_client, "_call_nvidia_with_fallback", _fake_nvidia(calls))

    other_heuristic = RecommendResponse(
        taste_summary="otro resumen",
        recommendations=[
            Recommendation(
                title="Fake Comedy", year=2019, kind="movie", why="heurística",
                match_score=60, tags=["funny", "light"],
            ),
        ],
    )

    llm_client.refine_recommendations([], "funny", HEURISTIC)
    llm_client.refine_recommendations([], "funny", other_heuristic)

    assert len(calls) == 2


def test_refine_recommendations_cache_expires_after_ttl(monkeypatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    calls: list[int] = []
    monkeypatch.setattr(llm_client, "_call_nvidia_with_fallback", _fake_nvidia(calls))

    fake_now = [1000.0]
    monkeypatch.setattr(llm_client, "_now_monotonic", lambda: fake_now[0])

    llm_client.refine_recommendations([], "funny", HEURISTIC)
    fake_now[0] += llm_client.REFINE_CACHE_TTL_SECONDS + 1
    llm_client.refine_recommendations([], "funny", HEURISTIC)

    assert len(calls) == 2


def test_title_key_ignores_year_accents_and_punctuation() -> None:
    # El modelo suele devolver el título con el año pegado o con la puntuación
    # cambiada; antes eso descartaba el pick entero.
    assert llm_client._title_key("GoodFellas (1990)") == llm_client._title_key("Goodfellas")
    assert llm_client._title_key("Amélie, 2001") == llm_client._title_key("Amelie")
    assert llm_client._title_key("Spider-Man: No Way Home") == llm_client._title_key(
        "Spider Man No Way Home"
    )


def test_refine_matches_titles_with_year_suffix(monkeypatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")

    def fake_call_nvidia(prompt: str, api_key: str) -> dict:
        return {
            "taste_summary": "resumen del agente",
            "picks": [{"title": "Fake Thriller (2020)", "why": "por el tono oscuro"}],
        }

    monkeypatch.setattr(llm_client, "_call_nvidia_with_fallback", fake_call_nvidia)

    result = llm_client.refine_recommendations([], "dark", HEURISTIC)

    assert [r.title for r in result.recommendations] == ["Fake Thriller"]
    assert result.recommendations[0].why == "Por el tono oscuro"


def test_refine_does_not_cache_a_response_that_failed_validation(monkeypatch) -> None:
    # Cachear antes de validar dejaba la respuesta mala pegada el TTL entero,
    # así que todo reintento fallaba igual sin volver a llamar al modelo.
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    calls: list[int] = []

    def failing_then_ok(prompt: str, api_key: str) -> dict:
        calls.append(1)
        if len(calls) == 1:
            return {"taste_summary": "x", "picks": [{"title": "Peli Inventada", "why": "no"}]}
        return {"taste_summary": "ok", "picks": [{"title": "Fake Thriller", "why": "sí"}]}

    monkeypatch.setattr(llm_client, "_call_nvidia_with_fallback", failing_then_ok)

    with pytest.raises(llm_client.LlmError):
        llm_client.refine_recommendations([], "dark", HEURISTIC)

    result = llm_client.refine_recommendations([], "dark", HEURISTIC)

    assert len(calls) == 2  # volvió a preguntar en vez de servir la respuesta mala
    assert [r.title for r in result.recommendations] == ["Fake Thriller"]


def test_predict_fit_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    with pytest.raises(llm_client.LlmError):
        llm_client.predict_fit(1, [], HEURISTIC)


def test_predict_fit_overwrites_why_for_matched_picks(monkeypatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    monkeypatch.setattr(
        llm_client,
        "_call_nvidia_with_fallback",
        lambda prompt, api_key: {
            "picks": [
                {"title": "Fake Thriller", "why": "le va a encantar por el tono oscuro"},
                {"title": "Fake Comedy", "why": "probablemente no le enganche"},
            ]
        },
    )

    result = llm_client.predict_fit(1, [], HEURISTIC)

    by_title = {r.title: r.why for r in result.recommendations}
    assert by_title["Fake Thriller"] == "Le va a encantar por el tono oscuro"
    assert by_title["Fake Comedy"] == "Probablemente no le enganche"


def test_predict_fit_never_drops_a_candidate_the_llm_missed(monkeypatch) -> None:
    # el set de las 5 semanales es fijo — si el LLM solo predice para una,
    # la otra tiene que sobrevivir con su why heurístico, no desaparecer
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    monkeypatch.setattr(
        llm_client,
        "_call_nvidia_with_fallback",
        lambda prompt, api_key: {"picks": [{"title": "Fake Thriller", "why": "le va a encantar"}]},
    )

    result = llm_client.predict_fit(1, [], HEURISTIC)

    assert [r.title for r in result.recommendations] == ["Fake Thriller", "Fake Comedy"]
    assert result.recommendations[1].why == "heurística"  # el why original de HEURISTIC, sin tocar
    assert result.recommendations[0].refined
    assert not result.recommendations[1].refined


def test_predict_fit_skips_the_llm_for_a_title_the_user_already_rated(monkeypatch) -> None:
    # bug reportado por Matías (2026-07-31, caso "The Odyssey"): /weekly no
    # excluye del catálogo lo que el usuario ya puntuó (el set de 5 es fijo
    # para todos), así que un candidato puede coincidir con un título de su
    # historial. Pedirle al LLM que lo prediga igual lo mandaba como
    # candidato Y como historial, y terminaba comparando el título consigo
    # mismo. Estos casos no deben ni llegar al prompt del LLM.
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    captured_prompts: list[str] = []

    def fake_call(prompt: str, api_key: str) -> dict:
        captured_prompts.append(prompt)
        return {"picks": [{"title": "Fake Comedy", "why": "le va a encantar"}]}

    monkeypatch.setattr(llm_client, "_call_nvidia_with_fallback", fake_call)

    ratings = [RatedItem(title="Fake Thriller", rating=4.5, review="", source="import")]
    result = llm_client.predict_fit(1, ratings, HEURISTIC)

    by_title = {r.title: r.why for r in result.recommendations}
    assert by_title["Fake Thriller"] == "Ya la viste — te encantó."
    assert by_title["Fake Comedy"] == "Le va a encantar"
    # "Fake Thriller" sigue apareciendo en "Reseñas completas" (es historial
    # real), pero no como candidato a predecir — esa línea tiene su propio
    # formato ("- título (año, tags: ...)") que no debe estar
    assert "- Fake Thriller (2020" not in captured_prompts[0]
    assert "- Fake Comedy (2019" in captured_prompts[0]
    by_refined = {r.title: r.refined for r in result.recommendations}
    assert by_refined["Fake Comedy"]  # predicho por el LLM
    assert not by_refined["Fake Thriller"]  # "ya la viste" es honesto, no una opinión del LLM


def test_predict_fit_skips_the_llm_entirely_when_all_candidates_already_seen(monkeypatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")

    def fail_if_called(prompt: str, api_key: str) -> dict:
        raise AssertionError("no debería llamar al LLM si ya vio las 5")

    monkeypatch.setattr(llm_client, "_call_nvidia_with_fallback", fail_if_called)

    ratings = [
        RatedItem(title="Fake Thriller", rating=4.5, review="", source="import"),
        RatedItem(title="Fake Comedy", rating=1.5, review="", source="import"),
    ]
    result = llm_client.predict_fit(1, ratings, HEURISTIC)

    by_title = {r.title: r.why for r in result.recommendations}
    assert by_title["Fake Thriller"] == "Ya la viste — te encantó."
    assert by_title["Fake Comedy"] == "Ya la viste — no te gustó."


def test_predict_fit_cache_is_isolated_per_user(monkeypatch) -> None:
    # bug evitado a propósito: las 5 películas semanales son las MISMAS para
    # todos, así que sin el user_id en la clave de cache el usuario 2
    # recibiría la predicción cacheada del usuario 1
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    calls: list[int] = []

    def fake_call(prompt: str, api_key: str) -> dict:
        calls.append(1)
        why = f"predicción para el llamado {len(calls)}"
        return {"picks": [{"title": "Fake Thriller", "why": why}, {"title": "Fake Comedy", "why": why}]}

    monkeypatch.setattr(llm_client, "_call_nvidia_with_fallback", fake_call)

    result_user_1 = llm_client.predict_fit(1, [], HEURISTIC)
    result_user_2 = llm_client.predict_fit(2, [], HEURISTIC)

    assert len(calls) == 2  # cada usuario disparó su propia llamada al LLM
    assert result_user_1.recommendations[0].why != result_user_2.recommendations[0].why


def test_predict_fit_caches_same_user_same_candidates(monkeypatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    calls: list[int] = []

    def fake_call(prompt: str, api_key: str) -> dict:
        calls.append(1)
        return {"picks": [{"title": "Fake Thriller", "why": "x"}, {"title": "Fake Comedy", "why": "y"}]}

    monkeypatch.setattr(llm_client, "_call_nvidia_with_fallback", fake_call)

    llm_client.predict_fit(1, [], HEURISTIC)
    llm_client.predict_fit(1, [], HEURISTIC)

    assert len(calls) == 1


def test_predict_fit_cache_changes_when_profile_changes(monkeypatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    calls: list[int] = []

    def fake_call(prompt: str, api_key: str) -> dict:
        calls.append(1)
        return {"picks": [{"title": "Fake Thriller", "why": "x"}, {"title": "Fake Comedy", "why": "y"}]}

    monkeypatch.setattr(llm_client, "_call_nvidia_with_fallback", fake_call)

    llm_client.predict_fit(1, [RatedItem(title="Alien", rating=1.5)], HEURISTIC)
    llm_client.predict_fit(1, [RatedItem(title="Alien", rating=4.5)], HEURISTIC)

    assert len(calls) == 2  # perfil distinto -- no puede reusar la predicción del otro


def test_peek_verdict_returns_none_on_cache_miss() -> None:
    assert llm_client.peek_verdict(1, [], HEURISTIC) is None


def test_peek_verdict_returns_the_cached_result_without_calling_the_llm(monkeypatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    monkeypatch.setattr(
        llm_client,
        "_call_nvidia_with_fallback",
        lambda prompt, api_key: {"picks": [{"title": "Fake Thriller", "why": "le va a encantar"}]},
    )
    llm_client.predict_fit(1, [], HEURISTIC)  # warms the cache

    def fail_if_called(prompt: str, api_key: str) -> dict:
        raise AssertionError("peek_verdict no debería llamar al LLM")

    monkeypatch.setattr(llm_client, "_call_nvidia_with_fallback", fail_if_called)

    result = llm_client.peek_verdict(1, [], HEURISTIC)

    assert result is not None
    by_title = {r.title: r.why for r in result.recommendations}
    assert by_title["Fake Thriller"] == "Le va a encantar"


def test_peek_verdict_is_the_final_result_when_everything_was_already_seen() -> None:
    # nada que predecir -- el "ya la viste" es el resultado final, no hay
    # nada async pendiente detrás (si no, el frontend de /weekly haría
    # polling para siempre esperando un `refined` que nunca llega)
    ratings = [
        RatedItem(title="Fake Thriller", rating=4.5, review="", source="import"),
        RatedItem(title="Fake Comedy", rating=1.5, review="", source="import"),
    ]

    result = llm_client.peek_verdict(1, ratings, HEURISTIC)

    assert result is not None
    by_title = {r.title: r.why for r in result.recommendations}
    assert by_title["Fake Thriller"] == "Ya la viste — te encantó."


def test_kickoff_verdict_populates_the_cache_in_the_background(monkeypatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    monkeypatch.setattr(
        llm_client,
        "_call_nvidia_with_fallback",
        lambda prompt, api_key: {"picks": [{"title": "Fake Thriller", "why": "le va a encantar"}]},
    )

    assert llm_client.peek_verdict(1, [], HEURISTIC) is None
    llm_client.kickoff_verdict(1, [], HEURISTIC)
    # no es _SyncThread -- el thread real puede tardar un toque en arrancar
    for _ in range(50):
        if llm_client.peek_verdict(1, [], HEURISTIC) is not None:
            break
        time.sleep(0.02)

    result = llm_client.peek_verdict(1, [], HEURISTIC)
    assert result is not None
    assert result.recommendations[0].why == "Le va a encantar"


def test_kickoff_verdict_deduplicates_concurrent_calls(monkeypatch) -> None:
    # varios polls de /weekly llegando antes de que el primer background
    # termine no deberían disparar una llamada nueva a NVIDIA cada uno
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    calls: list[int] = []
    release = threading.Event()

    def slow_call(prompt: str, api_key: str) -> dict:
        calls.append(1)
        release.wait(timeout=2)
        return {"picks": [{"title": "Fake Thriller", "why": "le va a encantar"}]}

    monkeypatch.setattr(llm_client, "_call_nvidia_with_fallback", slow_call)

    llm_client.kickoff_verdict(1, [], HEURISTIC)
    time.sleep(0.05)  # asegura que el primer thread ya entró a _call_nvidia_with_fallback
    llm_client.kickoff_verdict(1, [], HEURISTIC)  # mismo user/candidatos/perfil -- debe ser un no-op
    release.set()

    for _ in range(50):
        if llm_client.peek_verdict(1, [], HEURISTIC) is not None:
            break
        time.sleep(0.02)

    assert len(calls) == 1


def test_taste_digest_counts_ratings_without_a_review() -> None:
    """El digest que lee el agente salía SOLO del texto de las reseñas, así que
    una peli puntuada 5 sin reseña no aportaba nada al patrón y todos los "why"
    terminaban apoyados en las pocas con texto (Matías, 2026-08-07). El scoring
    ya miraba las dos fuentes; esto las empareja."""
    sin_resena = [
        RatedItem(title="Sin Reseña Uno", rating=5, review="", tags=["dark", "psychological"]),
        RatedItem(title="Sin Reseña Dos", rating=5, review="", tags=["dark", "mysterious"]),
    ]

    digest = llm_client._build_taste_digest(sin_resena)

    # sin el fix, no había línea de patrones en absoluto
    assert "Patrones que se repiten" in digest
    assert TAG_PHRASES["dark"] in digest
