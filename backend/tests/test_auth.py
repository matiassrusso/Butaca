import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from backend.app import auth, db, google_auth
from backend.app.main import app

client = TestClient(app)


@pytest.fixture
def google_configured(monkeypatch):
    """Google Sign-In activo con un tokeninfo falso, para no pegarle a la API
    real. Devuelve una función para fijar qué contesta Google."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "butaca-test.apps.googleusercontent.com")
    payloads: dict[str, dict] = {}

    def fake_verify(access_token: str) -> dict:
        # el verificador real chequea aud/email_verified; acá reproducimos solo
        # el resultado, y los chequeos se testean aparte contra el módulo
        if access_token not in payloads:
            raise google_auth.GoogleAuthError("El token de Google no es válido.")
        return payloads[access_token]

    monkeypatch.setattr(google_auth, "verify_access_token", fake_verify)

    def register_token(token: str, *, sub: str, email: str, name: str = "") -> None:
        payloads[token] = {"sub": sub, "email": email, "name": name, "email_verified": True}

    return register_token


def _register(username: str, monkeypatch=None) -> dict:
    if monkeypatch is not None:
        monkeypatch.setenv("BUTACA_DEBUG", "1")
    return client.post(
        "/auth/register",
        json={"username": username, "password": "supersecret", "email": f"{username}@example.com"},
    ).json()


def _zip_bytes(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buffer.getvalue()


def test_register_creates_user_and_returns_token() -> None:
    response = client.post(
        "/auth/register",
        json={"username": "mati", "password": "supersecret", "email": "mati@example.com"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "mati"
    assert body["token"]


def test_guest_login_creates_usable_session() -> None:
    response = client.post("/auth/guest")

    assert response.status_code == 201
    body = response.json()
    assert body["username"].startswith("invitado-")
    assert body["token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 200
    assert me.json()["username"] == body["username"]
    assert me.json()["email"] is None


def test_google_login_creates_an_account(google_configured) -> None:
    google_configured("tok-nuevo", sub="google-1", email="nuevo@gmail.com")

    response = client.post("/auth/google", json={"access_token": "tok-nuevo"})

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "nuevo"
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {body['token']}"}).json()
    assert me["email"] == "nuevo@gmail.com"
    assert me["email_verified"] is True
    assert me["is_guest"] is False


def test_google_login_twice_reuses_the_same_account(google_configured) -> None:
    google_configured("tok-repe", sub="google-repe", email="repe@gmail.com")

    first = client.post("/auth/google", json={"access_token": "tok-repe"}).json()
    second = client.post("/auth/google", json={"access_token": "tok-repe"}).json()

    assert first["username"] == second["username"]
    assert first["token"] != second["token"]


def test_google_login_adopts_a_guest_session_so_history_survives(google_configured) -> None:
    guest = client.post("/auth/guest").json()
    guest_id = db.get_user_by_username(guest["username"])["id"]
    google_configured("tok-invitado", sub="google-inv", email="invitado@gmail.com")

    body = client.post(
        "/auth/google",
        headers={"Authorization": f"Bearer {guest['token']}"},
        json={"access_token": "tok-invitado"},
    ).json()

    claimed = db.get_user_by_username(body["username"])
    assert claimed["id"] == guest_id
    assert not claimed["is_guest"]


def test_google_login_links_an_existing_local_account(google_configured) -> None:
    client.post(
        "/auth/register",
        json={"username": "local", "password": "supersecret", "email": "local@gmail.com"},
    )
    local_id = db.get_user_by_username("local")["id"]
    google_configured("tok-local", sub="google-local", email="local@gmail.com")

    body = client.post("/auth/google", json={"access_token": "tok-local"}).json()

    assert body["username"] == "local"
    assert db.get_user_by_username("local")["id"] == local_id
    # y la contraseña original sigue sirviendo
    assert client.post(
        "/auth/login", json={"username": "local", "password": "supersecret"}
    ).status_code == 200


def test_google_login_rejects_an_invalid_token(google_configured) -> None:
    response = client.post("/auth/google", json={"access_token": "basura"})

    assert response.status_code == 401


def test_google_login_is_disabled_without_a_client_id(monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)

    response = client.post("/auth/google", json={"access_token": "cualquiera"})

    assert response.status_code == 503


def test_verify_access_token_rejects_a_token_issued_for_another_app(monkeypatch) -> None:
    """El agujero clásico de esta integración: sin chequear `aud`/`azp`, un
    access token de cualquier otra app de Google entraría como usuario
    válido."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "butaca.apps.googleusercontent.com")
    monkeypatch.setattr(
        google_auth,
        "_fetch_tokeninfo",
        lambda _token: {
            "aud": "otra-app.apps.googleusercontent.com",
            "azp": "otra-app.apps.googleusercontent.com",
            "sub": "123",
            "email": "atacante@gmail.com",
            "email_verified": "true",
        },
    )

    with pytest.raises(google_auth.GoogleAuthError):
        google_auth.verify_access_token("token-de-otra-app")


def test_verify_access_token_rejects_an_unverified_email(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "butaca.apps.googleusercontent.com")
    monkeypatch.setattr(
        google_auth,
        "_fetch_tokeninfo",
        lambda _token: {
            "aud": "butaca.apps.googleusercontent.com",
            "sub": "123",
            "email": "sinverificar@gmail.com",
            "email_verified": "false",
        },
    )

    with pytest.raises(google_auth.GoogleAuthError):
        google_auth.verify_access_token("token-sin-verificar")


def test_verify_access_token_accepts_a_good_token(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "butaca.apps.googleusercontent.com")
    monkeypatch.setattr(
        google_auth,
        "_fetch_tokeninfo",
        lambda _token: {
            "aud": "butaca.apps.googleusercontent.com",
            "sub": "sub-ok",
            "email": "ok@gmail.com",
            "email_verified": "true",
            "name": "Matías",
        },
    )

    profile = google_auth.verify_access_token("token-bueno")

    assert profile["sub"] == "sub-ok"
    assert profile["email"] == "ok@gmail.com"


def test_verify_access_token_accepts_azp_when_aud_differs(monkeypatch) -> None:
    """Google puede devolver nuestro client id en `azp` en vez de `aud`."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "butaca.apps.googleusercontent.com")
    monkeypatch.setattr(
        google_auth,
        "_fetch_tokeninfo",
        lambda _token: {
            "aud": "otro-recurso",
            "azp": "butaca.apps.googleusercontent.com",
            "sub": "sub-azp",
            "email": "azp@gmail.com",
            "email_verified": "true",
        },
    )

    assert google_auth.verify_access_token("token-azp")["sub"] == "sub-azp"


def test_verify_access_token_falls_back_to_userinfo(monkeypatch) -> None:
    """tokeninfo no siempre trae el perfil; ahí se pide a userinfo con el
    mismo token en vez de fallar."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "butaca.apps.googleusercontent.com")
    monkeypatch.setattr(
        google_auth,
        "_fetch_tokeninfo",
        lambda _token: {"aud": "butaca.apps.googleusercontent.com", "scope": "openid email"},
    )
    monkeypatch.setattr(
        google_auth,
        "_fetch_userinfo",
        lambda _token: {"sub": "sub-ui", "email": "ui@gmail.com", "email_verified": True},
    )

    profile = google_auth.verify_access_token("token-sin-perfil")

    assert profile["sub"] == "sub-ui"
    assert profile["email"] == "ui@gmail.com"


def test_claim_keeps_the_same_account_so_history_survives() -> None:
    guest = client.post("/auth/guest").json()
    headers = {"Authorization": f"Bearer {guest['token']}"}
    guest_id = db.get_user_by_username(guest["username"])["id"]

    response = client.post(
        "/auth/claim",
        headers=headers,
        json={"username": "reclamada", "password": "supersecret", "email": "reclamada@example.com"},
    )

    assert response.status_code == 200
    assert response.json()["username"] == "reclamada"
    # misma fila: lo que el invitado haya puntuado sigue colgando de este id
    claimed = db.get_user_by_username("reclamada")
    assert claimed["id"] == guest_id
    assert not claimed["is_guest"]
    assert db.get_user_by_username(guest["username"]) is None

    # y la contraseña nueva sirve para entrar
    assert client.post(
        "/auth/login", json={"username": "reclamada", "password": "supersecret"}
    ).status_code == 200


def test_claim_rotates_the_session_token() -> None:
    guest = client.post("/auth/guest").json()
    old_headers = {"Authorization": f"Bearer {guest['token']}"}

    body = client.post(
        "/auth/claim",
        headers=old_headers,
        json={"username": "rotada", "password": "supersecret", "email": "rotada@example.com"},
    ).json()

    assert client.get("/auth/me", headers=old_headers).status_code == 401
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {body['token']}"}).status_code == 200


def test_claim_rejects_a_username_taken_by_someone_else() -> None:
    client.post(
        "/auth/register",
        json={"username": "ocupado", "password": "supersecret", "email": "ocupado@example.com"},
    )
    guest = client.post("/auth/guest").json()

    response = client.post(
        "/auth/claim",
        headers={"Authorization": f"Bearer {guest['token']}"},
        json={"username": "ocupado", "password": "otrosecret", "email": "otro@example.com"},
    )

    assert response.status_code == 409


def test_claim_rejects_an_already_registered_account() -> None:
    registered = client.post(
        "/auth/register",
        json={"username": "yaesta", "password": "supersecret", "email": "yaesta@example.com"},
    ).json()

    response = client.post(
        "/auth/claim",
        headers={"Authorization": f"Bearer {registered['token']}"},
        json={"username": "otronombre", "password": "supersecret", "email": "otro2@example.com"},
    )

    assert response.status_code == 409


def test_me_reports_guest_flag() -> None:
    guest = client.post("/auth/guest").json()
    registered = client.post(
        "/auth/register",
        json={"username": "noinvitado", "password": "supersecret", "email": "no@example.com"},
    ).json()

    def me(token: str) -> dict:
        return client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()

    assert me(guest["token"])["is_guest"] is True
    assert me(registered["token"])["is_guest"] is False


def test_guest_login_generates_distinct_usernames() -> None:
    first = client.post("/auth/guest").json()
    second = client.post("/auth/guest").json()

    assert first["username"] != second["username"]


def test_register_rejects_malformed_email() -> None:
    response = client.post(
        "/auth/register",
        json={"username": "bademail", "password": "supersecret", "email": "not-an-email"},
    )

    assert response.status_code == 422


def test_register_rejects_duplicate_username() -> None:
    client.post(
        "/auth/register",
        json={"username": "dupe", "password": "supersecret", "email": "dupe@example.com"},
    )
    response = client.post(
        "/auth/register",
        json={"username": "dupe", "password": "othersecret", "email": "dupe2@example.com"},
    )

    assert response.status_code == 409


def test_login_succeeds_with_correct_password() -> None:
    client.post(
        "/auth/register",
        json={"username": "loginok", "password": "supersecret", "email": "loginok@example.com"},
    )
    response = client.post(
        "/auth/login", json={"username": "loginok", "password": "supersecret"}
    )

    assert response.status_code == 200
    assert response.json()["token"]


def test_login_rejects_wrong_password() -> None:
    client.post(
        "/auth/register",
        json={"username": "loginbad", "password": "supersecret", "email": "loginbad@example.com"},
    )
    response = client.post(
        "/auth/login", json={"username": "loginbad", "password": "wrongpassword"}
    )

    assert response.status_code == 401


def test_login_rejects_unknown_username() -> None:
    response = client.post(
        "/auth/login", json={"username": "ghost", "password": "whatever1"}
    )

    assert response.status_code == 401


def test_login_rate_limits_after_repeated_failures(monkeypatch) -> None:
    client.post(
        "/auth/register",
        json={"username": "ratelimit", "password": "supersecret", "email": "ratelimit@example.com"},
    )
    monkeypatch.setattr("backend.app.main.auth.now_ts", lambda: 1_000)

    assert (
        client.post(
            "/auth/login", json={"username": "ratelimit", "password": "wrongpassword"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/auth/login", json={"username": "ratelimit", "password": "wrongpassword"}
        ).status_code
        == 401
    )

    locked = client.post(
        "/auth/login", json={"username": "ratelimit", "password": "wrongpassword"}
    )
    assert locked.status_code == 429
    assert "30s" in locked.json()["detail"]

    blocked = client.post(
        "/auth/login", json={"username": "ratelimit", "password": "supersecret"}
    )
    assert blocked.status_code == 429

    monkeypatch.setattr("backend.app.main.auth.now_ts", lambda: 1_031)
    unblocked = client.post(
        "/auth/login", json={"username": "ratelimit", "password": "supersecret"}
    )
    assert unblocked.status_code == 200


def test_recommend_zip_requires_auth() -> None:
    response = client.post(
        "/recommend/zip",
        data={"mood": ""},
        files={"file": ("export.zip", b"not-a-real-zip", "application/zip")},
    )

    assert response.status_code == 401


def test_auth_me_returns_username_for_valid_token() -> None:
    client.post(
        "/auth/register",
        json={"username": "meuser", "password": "supersecret", "email": "meuser@example.com"},
    )
    login = client.post("/auth/login", json={"username": "meuser", "password": "supersecret"})
    token = login.json()["token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["username"] == "meuser"


def test_auth_me_rejects_missing_or_invalid_token() -> None:
    assert client.get("/auth/me").status_code == 401
    assert (
        client.get("/auth/me", headers={"Authorization": "Bearer nonsense"}).status_code
        == 401
    )


def test_get_optional_user_returns_none_without_token() -> None:
    assert auth.get_optional_user(authorization=None) is None
    assert auth.get_optional_user(authorization="Bearer nonsense") is None


def test_get_optional_user_returns_user_with_valid_token() -> None:
    token = _register("optionaluser")["token"]

    user = auth.get_optional_user(authorization=f"Bearer {token}")

    assert user is not None
    assert user["username"] == "optionaluser"


def test_expired_session_is_rejected() -> None:
    token = _register("expiredsession")["token"]
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    # vencer la sesión a mano (el token vive hasheado en la DB)
    with db.get_connection() as conn:
        conn.execute(
            "UPDATE sessions SET expires_at = 1 WHERE token = ?",
            (db._hash_token(token),),
        )

    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_session_tokens_are_stored_hashed() -> None:
    token = _register("hashedsession")["token"]

    with db.get_connection() as conn:
        raw_match = conn.execute("SELECT 1 FROM sessions WHERE token = ?", (token,)).fetchone()
        hashed_match = conn.execute(
            "SELECT 1 FROM sessions WHERE token = ?", (db._hash_token(token),)
        ).fetchone()

    assert raw_match is None  # el token crudo nunca toca la DB
    assert hashed_match is not None


def test_forgot_password_returns_token_and_reset_invalidates_old_sessions(monkeypatch) -> None:
    # BUTACA_DEBUG exposes the reset token in the response so the flow can
    # be exercised end-to-end without a real email provider configured.
    monkeypatch.setenv("BUTACA_DEBUG", "1")

    register = client.post(
        "/auth/register",
        json={"username": "resetuser", "password": "supersecret", "email": "resetuser@example.com"},
    )
    old_token = register.json()["token"]

    forgot = client.post("/auth/forgot-password", json={"username": "resetuser"})
    assert forgot.status_code == 200
    reset_token = forgot.json()["reset_token"]
    assert reset_token

    response = client.post(
        "/auth/reset-password",
        json={"token": reset_token, "password": "newersecret"},
    )
    assert response.status_code == 204

    assert (
        client.get("/auth/me", headers={"Authorization": f"Bearer {old_token}"}).status_code
        == 401
    )
    assert (
        client.post(
            "/auth/login", json={"username": "resetuser", "password": "supersecret"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/auth/login", json={"username": "resetuser", "password": "newersecret"}
        ).status_code
        == 200
    )


def test_forgot_password_sends_email_when_mailer_configured(monkeypatch) -> None:
    client.post(
        "/auth/register",
        json={"username": "mailuser", "password": "supersecret", "email": "mailuser@example.com"},
    )

    sent = {}

    def fake_send(to_email: str, reset_token: str) -> None:
        sent["to_email"] = to_email
        sent["reset_token"] = reset_token

    monkeypatch.setattr("backend.app.main.mailer.is_configured", lambda: True)
    monkeypatch.setattr("backend.app.main.mailer.send_password_reset_email", fake_send)

    response = client.post("/auth/forgot-password", json={"username": "mailuser"})

    assert response.status_code == 200
    assert sent["to_email"] == "mailuser@example.com"
    assert sent["reset_token"]


def test_forgot_password_survives_mailer_failure(monkeypatch) -> None:
    client.post(
        "/auth/register",
        json={"username": "mailfail", "password": "supersecret", "email": "mailfail@example.com"},
    )

    from backend.app.mailer import MailError

    def fake_send(to_email: str, reset_token: str) -> None:
        raise MailError("resend is down")

    monkeypatch.setattr("backend.app.main.mailer.is_configured", lambda: True)
    monkeypatch.setattr("backend.app.main.mailer.send_password_reset_email", fake_send)

    response = client.post("/auth/forgot-password", json={"username": "mailfail"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "reset_token": None}


def test_forgot_password_is_generic_for_unknown_username() -> None:
    response = client.post("/auth/forgot-password", json={"username": "ghost"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "reset_token": None}


def test_forgot_password_hides_token_by_default_even_for_existing_user() -> None:
    # BUTACA_DEBUG is unset here (conftest clears it) — this is the real
    # default behavior: no token in the response, existing user or not.
    client.post(
        "/auth/register",
        json={"username": "notexposed", "password": "supersecret", "email": "notexposed@example.com"},
    )

    response = client.post("/auth/forgot-password", json={"username": "notexposed"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "reset_token": None}


def test_reset_password_rejects_expired_token(monkeypatch) -> None:
    monkeypatch.setenv("BUTACA_DEBUG", "1")
    client.post(
        "/auth/register",
        json={"username": "expired", "password": "supersecret", "email": "expired@example.com"},
    )
    monkeypatch.setattr("backend.app.main.auth.now_ts", lambda: 2_000)
    reset_token = client.post(
        "/auth/forgot-password", json={"username": "expired"}
    ).json()["reset_token"]

    monkeypatch.setattr(
        "backend.app.main.auth.now_ts",
        lambda: 2_000 + 3_600 + 1,
    )
    response = client.post(
        "/auth/reset-password",
        json={"token": reset_token, "password": "newersecret"},
    )

    assert response.status_code == 400


# ─── Email verification ─────────────────────────────────────────────────────


def test_register_issues_verification_and_verify_confirms(monkeypatch) -> None:
    body = _register("verifyme", monkeypatch)
    token = body["verification_token"]
    assert token  # exposed because BUTACA_DEBUG=1

    headers = {"Authorization": f"Bearer {body['token']}"}
    assert client.get("/auth/me", headers=headers).json()["email_verified"] is False

    confirm = client.post("/auth/verify-email", json={"token": token})
    assert confirm.status_code == 204

    assert client.get("/auth/me", headers=headers).json()["email_verified"] is True


def test_auth_me_reports_unverified_by_default() -> None:
    body = _register("freshuser")
    headers = {"Authorization": f"Bearer {body['token']}"}

    me = client.get("/auth/me", headers=headers).json()

    assert me["email_verified"] is False
    assert me["email"] == "freshuser@example.com"


def test_verify_email_rejects_invalid_token() -> None:
    response = client.post("/auth/verify-email", json={"token": "x" * 40})
    assert response.status_code == 400


def test_verify_email_rejects_expired_token(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.main.auth.now_ts", lambda: 5_000)
    body = _register("verifyexpired", monkeypatch)
    token = body["verification_token"]

    monkeypatch.setattr(
        "backend.app.main.auth.now_ts", lambda: 5_000 + auth_ttl() + 1
    )
    response = client.post("/auth/verify-email", json={"token": token})

    assert response.status_code == 400


def auth_ttl() -> int:
    from backend.app import auth

    return auth.EMAIL_VERIFICATION_TTL_SECONDS


def test_resend_verification_returns_token_under_debug_and_noop_once_verified(monkeypatch) -> None:
    body = _register("resendme", monkeypatch)
    headers = {"Authorization": f"Bearer {body['token']}"}

    resend = client.post("/auth/verify-email/resend", headers=headers)
    assert resend.status_code == 200
    new_token = resend.json()["reset_token"]
    assert new_token

    assert client.post("/auth/verify-email", json={"token": new_token}).status_code == 204

    # already verified: no new token issued
    again = client.post("/auth/verify-email/resend", headers=headers)
    assert again.status_code == 200
    assert again.json()["reset_token"] is None


# ─── Delete account ─────────────────────────────────────────────────────────


def test_delete_account_rejects_wrong_password() -> None:
    body = _register("delwrongpw")
    headers = {"Authorization": f"Bearer {body['token']}"}

    response = client.request(
        "DELETE", "/auth/account", json={"password": "notmypassword"}, headers=headers
    )

    assert response.status_code == 401
    # account still usable
    assert client.get("/auth/me", headers=headers).status_code == 200


def test_delete_account_requires_auth() -> None:
    response = client.request("DELETE", "/auth/account", json={"password": "whatever"})
    assert response.status_code == 401


def test_delete_account_wipes_user_and_all_their_rows() -> None:
    body = _register("delfull")
    headers = {"Authorization": f"Bearer {body['token']}"}
    user_id = db.get_user_by_username("delfull")["id"]

    # seed rated_items + recommendation_sessions + recommendations_served
    seed = client.post(
        "/recommend/zip",
        headers=headers,
        data={"mood": ""},
        files={
            "file": (
                "export.zip",
                _zip_bytes({"ratings.csv": "Name,Rating,Review\nMad Max: Fury Road,4.5,great"}),
                "application/zip",
            )
        },
    )
    assert seed.status_code == 200

    response = client.request(
        "DELETE", "/auth/account", json={"password": "supersecret"}, headers=headers
    )
    assert response.status_code == 204

    # session invalidated, login impossible, user gone
    assert client.get("/auth/me", headers=headers).status_code == 401
    assert (
        client.post("/auth/login", json={"username": "delfull", "password": "supersecret"}).status_code
        == 401
    )
    assert db.get_user_by_username("delfull") is None

    # no orphan rows left behind in any user-scoped table
    with db.get_connection() as conn:
        for table in (
            "rated_items",
            "recommendation_sessions",
            "recommendations_served",
            "feedback",
            "taste_profiles",
            "watchlist_items",
            "sessions",
        ):
            n = conn.execute(
                f"SELECT COUNT(*) AS n FROM {table} WHERE user_id = ?", (user_id,)
            ).fetchone()["n"]
            assert n == 0, f"orphan rows left in {table}"
