import json
import os
import urllib.request
from pathlib import Path
from urllib.error import HTTPError, URLError

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
RESEND_URL = "https://api.resend.com/emails"
REQUEST_TIMEOUT = 10
DEFAULT_FROM = "Butaca <onboarding@resend.dev>"
DEFAULT_RESET_URL = "https://butaca.xyz/reset-password"


class MailError(Exception):
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
    return bool(os.environ.get("RESEND_API_KEY"))


def _send_request(body: bytes, api_key: str) -> None:
    request = urllib.request.Request(
        RESEND_URL,
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            response.read()
    except HTTPError as exc:
        # El motivo real (dominio sin verificar, key inválida) viene en el body,
        # no en el status — sin esto el log queda en "HTTP Error 403: Forbidden".
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise MailError(f"Resend rechazó el mail ({exc.code}): {detail}") from exc
    except URLError as exc:
        raise MailError(f"No pude mandar el mail vía Resend: {exc}") from exc


def send_password_reset_email(to_email: str, reset_token: str) -> None:
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        raise MailError("RESEND_API_KEY no está configurada.")

    from_address = os.environ.get("RESEND_FROM_EMAIL", DEFAULT_FROM)
    reset_url_base = os.environ.get("BUTACA_RESET_URL", DEFAULT_RESET_URL)
    reset_link = f"{reset_url_base}?token={reset_token}"

    body = json.dumps(
        {
            "from": from_address,
            "to": [to_email],
            "subject": "Recuperá tu contraseña de Butaca",
            "html": (
                "<p>Pediste recuperar tu contraseña de Butaca.</p>"
                f'<p><a href="{reset_link}">Hacé click acá para elegir una nueva</a> '
                "(el link expira en 1 hora).</p>"
                "<p>Si no fuiste vos, ignorá este mail.</p>"
            ),
        }
    ).encode("utf-8")

    _send_request(body, api_key)
