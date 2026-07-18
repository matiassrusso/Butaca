import os

import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    os.environ["PELIPICK_DB_PATH"] = str(tmp_path / "test.db")
    yield
    os.environ.pop("PELIPICK_DB_PATH", None)


@pytest.fixture(autouse=True)
def no_real_tmdb(monkeypatch):
    # backend/.env may hold a real TMDB_API_KEY on dev machines; tests must
    # not depend on live network calls or non-deterministic TMDb results.
    monkeypatch.delenv("TMDB_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def no_real_nvidia(monkeypatch):
    # same deal as TMDB_API_KEY, but for the LLM refine step.
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def no_real_resend(monkeypatch):
    # same deal as TMDB_API_KEY, but for the password reset email.
    monkeypatch.delenv("RESEND_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def no_debug_mode(monkeypatch):
    # a dev machine may have PELIPICK_DEBUG=1 set locally; tests that rely on
    # the token NOT being exposed by default must not depend on that.
    monkeypatch.delenv("PELIPICK_DEBUG", raising=False)
