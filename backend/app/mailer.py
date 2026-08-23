import json
import os
import urllib.request
from html import escape
from pathlib import Path
from urllib.error import HTTPError, URLError

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
RESEND_URL = "https://api.resend.com/emails"
REQUEST_TIMEOUT = 10
DEFAULT_FROM = "Butaca <onboarding@resend.dev>"
DEFAULT_RESET_URL = "https://butaca.xyz/reset-password"
DEFAULT_VERIFY_URL = "https://butaca.xyz/verify-email"
USER_AGENT = "Butaca/1.0"


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


# Paleta "Hybrid critic notebook" en hex (los clientes de mail no soportan oklch
# ni fuentes web, así que van stacks web-safe): papel/tinta/terracota, radius 0,
# bordes gruesos editoriales. Un solo template para reset y verificación.
_PAPER = "#FAF7F0"
_OUTER = "#E7E1D5"
_INK = "#20242B"
_MUTED = "#8A8578"
_ACCENT = "#C2410C"
_SANS = "Helvetica, Arial, sans-serif"
_MONO = "'Courier New', Courier, monospace"
_SERIF = "Georgia, 'Times New Roman', serif"


def _render_email(
    *, preheader: str, kicker: str, heading: str, body: str, button_label: str, button_url: str, expiry_note: str
) -> str:
    return f"""\
<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light only"></head>
<body style="margin:0;padding:0;background:{_OUTER};">
<span style="display:none;max-height:0;overflow:hidden;opacity:0;">{preheader}</span>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_OUTER};padding:32px 12px;">
<tr><td align="center">
<table role="presentation" width="480" cellpadding="0" cellspacing="0" style="max-width:480px;width:100%;background:{_PAPER};border:2px solid {_INK};">
<tr><td style="padding:28px 32px 0 32px;">
<div style="font-family:{_MONO};font-size:12px;letter-spacing:3px;text-transform:uppercase;color:{_INK};font-weight:bold;">Butaca</div>
<div style="height:3px;background:{_ACCENT};width:44px;margin-top:12px;"></div>
</td></tr>
<tr><td style="padding:24px 32px 0 32px;">
<div style="font-family:{_MONO};font-size:10px;letter-spacing:2px;text-transform:uppercase;color:{_MUTED};">{kicker}</div>
<h1 style="margin:8px 0 0 0;font-family:{_SANS};font-size:26px;line-height:1.1;font-weight:800;color:{_INK};text-transform:uppercase;letter-spacing:-0.5px;">{heading}</h1>
<p style="margin:16px 0 0 0;font-family:{_SANS};font-size:15px;line-height:1.6;color:{_INK};">{body}</p>
</td></tr>
<tr><td style="padding:24px 32px 4px 32px;">
<a href="{button_url}" style="display:inline-block;background:{_ACCENT};color:{_PAPER};font-family:{_MONO};font-size:12px;letter-spacing:2px;text-transform:uppercase;text-decoration:none;padding:14px 28px;">{button_label} &rarr;</a>
<p style="margin:16px 0 0 0;font-family:{_MONO};font-size:10px;letter-spacing:1px;text-transform:uppercase;color:{_MUTED};">{expiry_note} &middot; Si no fuiste vos, ignorá este mail.</p>
</td></tr>
<tr><td style="padding:24px 32px 28px 32px;border-top:1px solid {_OUTER};">
<div style="font-family:{_SERIF};font-style:italic;font-size:15px;color:{_INK};">para el que mira con criterio</div>
<a href="https://butaca.xyz" style="font-family:{_MONO};font-size:10px;letter-spacing:2px;text-transform:uppercase;color:{_MUTED};text-decoration:none;">butaca.xyz</a>
</td></tr>
</table>
</td></tr>
</table>
</body></html>"""


def _send_request(body: bytes, api_key: str) -> None:
    request = urllib.request.Request(
        RESEND_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # Sin esto Cloudflare (delante de la API de Resend) corta con 403
            # "error code: 1010" por el User-Agent default de urllib. Cualquier
            # UA propio alcanza — no hace falta imitar un browser como en
            # letterboxd_scrape.py, ahí el bloqueo era por fingerprint TLS.
            "User-Agent": USER_AGENT,
        },
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
            "html": _render_email(
                preheader="Elegí una nueva contraseña para tu cuenta de Butaca.",
                kicker="[Recuperación]",
                heading="Recuperá tu clave",
                body="Pediste recuperar tu contraseña de Butaca. Usá el botón para elegir una nueva.",
                button_label="Elegir nueva contraseña",
                button_url=reset_link,
                expiry_note="El link expira en 1 hora",
            ),
        }
    ).encode("utf-8")

    _send_request(body, api_key)


def send_verification_email(to_email: str, verification_token: str) -> None:
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        raise MailError("RESEND_API_KEY no está configurada.")

    from_address = os.environ.get("RESEND_FROM_EMAIL", DEFAULT_FROM)
    verify_url_base = os.environ.get("BUTACA_VERIFY_URL", DEFAULT_VERIFY_URL)
    verify_link = f"{verify_url_base}?token={verification_token}"

    body = json.dumps(
        {
            "from": from_address,
            "to": [to_email],
            "subject": "Confirmá tu email en Butaca",
            "html": _render_email(
                preheader="Confirmá tu email para asegurar tu cuenta de Butaca.",
                kicker="[Registro nuevo]",
                heading="Confirmá tu email",
                body="Bienvenido a Butaca. Confirmá tu email para asegurar tu cuenta.",
                button_label="Confirmar email",
                button_url=verify_link,
                expiry_note="El link expira en 24 horas",
            ),
        }
    ).encode("utf-8")

    _send_request(body, api_key)


def send_site_feedback_email(to_email: str, message: str, email: str) -> None:
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        raise MailError("RESEND_API_KEY no está configurada.")

    from_address = os.environ.get("RESEND_FROM_EMAIL", DEFAULT_FROM)
    contact = escape(email) if email else "Sin email de contacto"
    safe_message = escape(message).replace("\n", "<br>")
    body = json.dumps(
        {
            "from": from_address,
            "to": [to_email],
            "subject": "Nueva sugerencia para Butaca",
            "html": _render_email(
                preheader="Llegó una nueva sugerencia desde Butaca.",
                kicker="[Feedback de producto]",
                heading="Nueva sugerencia",
                body=f"<strong>Contacto:</strong> {contact}<br><br>{safe_message}",
                button_label="Abrir Butaca",
                button_url="https://butaca.xyz",
                expiry_note="Feedback guardado en el panel de administración",
            ),
        }
    ).encode("utf-8")

    _send_request(body, api_key)
