"""Verificación del access token de Google Sign-In.

Se valida contra el endpoint `tokeninfo` de Google en vez de chequear nada
localmente: validar un JWT firmado necesitaría PyJWT + cryptography (o
google-auth) y el resto del backend no tiene ninguna dependencia de red/cripto
— mailer y tmdb_client ya salen con urllib. El costo es un request extra por
login, que en un flujo de autenticación no es camino caliente.

Por qué access token y no ID token: el flujo de ID token obliga a usar el botón
que renderiza Google (`renderButton`), que no se puede restilar y desentonaba
con el sistema de diseño del sitio. Con `initTokenClient` el botón es nuestro.
La verificación de seguridad es equivalente — ver el chequeo de `aud` abajo.
"""

import json
import os
import urllib.parse
import urllib.request
from urllib.error import HTTPError, URLError

TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
REQUEST_TIMEOUT = 10


class GoogleAuthError(Exception):
    pass


def is_configured() -> bool:
    return bool(client_id())


def client_id() -> str:
    return os.environ.get("GOOGLE_CLIENT_ID", "").strip()


def _get_json(url: str, headers: dict[str, str] | None = None) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "Butaca/1.0", **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise GoogleAuthError("El token de Google no es válido.") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GoogleAuthError("No pude verificar el token con Google.") from exc


def _fetch_tokeninfo(access_token: str) -> dict:
    return _get_json(f"{TOKENINFO_URL}?{urllib.parse.urlencode({'access_token': access_token})}")


def _fetch_userinfo(access_token: str) -> dict:
    return _get_json(USERINFO_URL, {"Authorization": f"Bearer {access_token}"})


def verify_access_token(access_token: str) -> dict:
    """Devuelve {sub, email, email_verified, name} o levanta GoogleAuthError.

    Chequea `aud`/`azp` contra nuestro client id: sin eso, un access token
    emitido para CUALQUIER otra app de Google sería aceptado acá y permitiría
    entrar como cualquier usuario (el "confused deputy", el error clásico de
    esta integración).
    """
    expected_aud = client_id()
    if not expected_aud:
        raise GoogleAuthError("GOOGLE_CLIENT_ID no está configurada.")

    info = _fetch_tokeninfo(access_token)
    # tokeninfo de access tokens usa `aud`; `azp` aparece en tokens emitidos a
    # través de un cliente autorizado. Alcanza con que uno de los dos sea el
    # nuestro, pero ninguno puede ser de otra app.
    if expected_aud not in {info.get("aud"), info.get("azp")}:
        raise GoogleAuthError("El token de Google es de otra aplicación.")

    sub = info.get("sub")
    email = info.get("email")
    email_verified = str(info.get("email_verified", "")).lower() == "true"
    name = info.get("name") or ""

    # tokeninfo no siempre trae el perfil; userinfo sí, y usa el mismo token
    if not email or not sub:
        profile = _fetch_userinfo(access_token)
        sub = sub or profile.get("sub")
        email = email or profile.get("email")
        email_verified = email_verified or bool(profile.get("email_verified"))
        name = name or profile.get("name") or ""

    if not sub or not email:
        raise GoogleAuthError("Google no devolvió un usuario utilizable.")
    if not email_verified:
        # sin esto, alguien con una cuenta Google de mail no verificado podría
        # quedarse con la cuenta local de ese mismo mail
        raise GoogleAuthError("Tu email de Google no está verificado.")

    return {"sub": sub, "email": email, "name": name, "email_verified": True}
