import os

import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    os.environ["BUTACA_DB_PATH"] = str(tmp_path / "test.db")
    yield
    os.environ.pop("BUTACA_DB_PATH", None)


@pytest.fixture(autouse=True)
def no_real_tmdb(monkeypatch):
    # backend/.env may hold a real TMDB_API_KEY on dev machines; tests must
    # not depend on live network calls or non-deterministic TMDb results.
    monkeypatch.delenv("TMDB_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def no_real_nvidia(monkeypatch):
    # same deal as TMDB_API_KEY, but for the LLM refine step.
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    # desde 2026-09-09 Groq es el proveedor primario y is_configured() lo
    # cuenta: sin esto, la GROQ_API_KEY real del .env local haría que los tests
    # de "LLM no configurado" salgan a la red
    monkeypatch.delenv("GROQ_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def no_real_resend(monkeypatch):
    # same deal as TMDB_API_KEY, but for the password reset email.
    monkeypatch.delenv("RESEND_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def no_debug_mode(monkeypatch):
    # a dev machine may have BUTACA_DEBUG=1 set locally; tests that rely on
    # the token NOT being exposed by default must not depend on that.
    monkeypatch.delenv("BUTACA_DEBUG", raising=False)


@pytest.fixture(autouse=True)
def clear_vibe_map_cache():
    # mismo problema que _VERDICT_CACHE de acá abajo: el mapa de vibras se
    # cachea a nivel de módulo (la proyección solo cambia cuando corre el
    # recompute), así que sin esto el primer test que lo pide le deja sus
    # puntos a todos los que siguen, que corren con otra DB.
    from backend.app import main

    main._invalidate_vibe_map_cache()
    yield
    main._invalidate_vibe_map_cache()


@pytest.fixture(autouse=True)
def clear_llm_verdict_cache():
    # _VERDICT_CACHE/_INFLIGHT_VERDICTS son dicts a nivel de módulo, NO
    # aislados por test como la DB (isolated_db de arriba). Dos tests que
    # usan el mismo catálogo/perfil (ej. _WEEKLY_TRENDING + _MANUAL_RATINGS)
    # terminan con la MISMA clave de cache -- y como isolated_db resetea el
    # autoincrement de user_id en cada test, hasta el user_id puede
    # coincidir. Bug real encontrado escribiendo el fix async de /weekly
    # (2026-08-03): un test de "el LLM falla" leía el resultado cacheado de
    # otro test que corrió justo antes.
    from backend.app import llm_client

    llm_client._VERDICT_CACHE.clear()
    llm_client._INFLIGHT_VERDICTS.clear()
    yield
    llm_client._VERDICT_CACHE.clear()
    llm_client._INFLIGHT_VERDICTS.clear()


@pytest.fixture(autouse=True)
def fast_sqlite(monkeypatch):
    # ponytail: get_connection abre una conexión nueva por llamada y cada test
    # estrena una DB: medido en Windows, el schema costaba ~100ms y cada commit
    # ~8ms por el fsync (5ms y ~1ms sin él). En tests la durabilidad no
    # importa. db.sqlite3 es el módulo global, monkeypatch lo restaura solo.
    from backend.app import db

    real_connect = db.sqlite3.connect

    def connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("PRAGMA journal_mode=MEMORY")
        return conn

    monkeypatch.setattr(db.sqlite3, "connect", connect)


@pytest.fixture(autouse=True)
def fast_pbkdf2(monkeypatch):
    # 260k iteraciones son ~46ms por hash y la suite hashea cientos de veces;
    # ningún test asume un hash fijo (verify_password rehashea con la misma
    # constante), así que bajarla no cambia ningún resultado.
    from backend.app import auth

    monkeypatch.setattr(auth, "PBKDF2_ITERATIONS", 1_000)
