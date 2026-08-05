# Setup de Google Sign-In

Configurado el 2026-08-05. Esta doc es cómo se armó, por qué así, y qué mirar
si deja de andar.

## Por qué Google y no Apple

Apple exige el Apple Developer Program (99 USD/año) más un dominio verificado
y relay de mails. Para este proyecto no se justifica, y el login de invitado
ya cubre el caso de "probar sin fricción". Decisión de Matías el 2026-08-05.

## Por qué access token y no ID token

El flujo de ID token obliga a usar `google.accounts.id.renderButton`, que es un
widget que dibuja Google y **no se puede restilar**: desentonaba fuerte con el
sistema de diseño (mono uppercase, radius 0, bordes gruesos). Con
`initTokenClient` el popup lo abre Google pero el botón es nuestro.

El cambio se hizo el 2026-08-05 a pedido de Matías, después de tener el flujo
de ID token andando. La verificación de seguridad es equivalente: en los dos
casos se le pregunta a Google por el token y se chequea contra nuestro client
id (ver abajo).

## Por qué se valida contra `tokeninfo` y no localmente

Validar un JWT firmado localmente necesita `PyJWT` + `cryptography` (o
`google-auth`), y el backend no tiene **ninguna** dependencia de red o cripto:
`mailer.py` y `tmdb_client.py` ya salen a internet con `urllib` de stdlib. Se
siguió ese patrón y se le pregunta a Google directamente
(`https://oauth2.googleapis.com/tokeninfo?access_token=...`).

El costo es un request extra por login. Es aceptable porque autenticarse no es
camino caliente — no se hace por recomendación ni por título, se hace una vez
por sesión.

Si `tokeninfo` no trae el perfil (pasa según los scopes concedidos), se cae a
`userinfo` con el mismo token en vez de fallar.

## Lo crítico: el chequeo de `aud`/`azp`

`google_auth.verify_access_token` compara el `aud` (o el `azp`) del token
contra nuestro `GOOGLE_CLIENT_ID`. **Sin ese chequeo, un access token emitido
para cualquier otra app de Google sería aceptado acá**, y quien lo tuviera
entraría como el usuario que quisiera — el "confused deputy", el agujero
clásico de esta integración.

Hay un test que lo cubre
(`test_verify_access_token_rejects_a_token_issued_for_another_app`) y se validó
reintroduciendo el bug a propósito: sacando la comparación, el test falla con
`DID NOT RAISE`.

Lo mismo con `email_verified`: solo se aceptan tokens de mails verificados por
Google, porque el flujo ata una cuenta de Google a una cuenta local del mismo
mail — sin ese chequeo, alguien con una cuenta Google de mail sin verificar se
quedaría con la cuenta local de ese mail.

## Cómo sacar el Client ID

1. https://console.cloud.google.com/apis/credentials → *Crear credenciales* →
   *ID de cliente de OAuth* → tipo **Aplicación web**.
2. Antes te pide configurar la pantalla de consentimiento.
3. **Orígenes de JavaScript autorizados** (los tres):
   - `https://butaca.xyz`
   - `https://www.butaca.xyz`
   - `http://localhost:4173`
4. URIs de redireccionamiento: ninguno. Este flujo (ID token vía Google
   Identity Services) no los usa.

Si falta `www`, quien entre por ahí ve el botón fallar. Los cambios de orígenes
tardan unos minutos en propagar.

## Dónde va

El Client ID **no es un secreto** (viaja al browser en cada carga), pero va por
env var para no hardcodearlo. Son dos nombres distintos:

| Dónde | Variable | Notas |
|---|---|---|
| `backend/.env` | `GOOGLE_CLIENT_ID` | gitignored |
| Render (backend) | `GOOGLE_CLIENT_ID` | |
| `frontend/.env.local` | `VITE_GOOGLE_CLIENT_ID` | gitignored |
| Vercel (frontend) | `VITE_GOOGLE_CLIENT_ID` | **Vite la inyecta en build time: hace falta redeploy** |

Template en `backend/.env.example`.

## Cómo se usa

- [backend/app/google_auth.py](../backend/app/google_auth.py) — verificación
  del token. `_fetch_tokeninfo` y `_fetch_userinfo` están separados del chequeo
  a propósito, para que los tests puedan mockear la respuesta de Google sin
  tocar la red.
- `POST /auth/google` en [main.py](../backend/app/main.py) — recibe
  `access_token` y resuelve a qué cuenta corresponde, en este orden:
  1. `google_sub` conocido → esa cuenta.
  2. Cuenta local con el mismo email → **se atan** (evita duplicados; seguro
     porque Google ya verificó el mail).
  3. Sesión de invitado abierta → la cuenta de Google se ata a **esa** cuenta,
     así el invitado no pierde lo que puntuó (misma lógica que `/auth/claim`).
  4. Nada de lo anterior → usuario nuevo, username derivado del mail.
- [frontend/src/components/GoogleSignInButton.tsx](../frontend/src/components/GoogleSignInButton.tsx)
  carga Google Identity Services y arma un `initTokenClient`. El botón es
  nuestro (mono uppercase, radius 0, borde grueso, invierte en hover) con el
  logo "G" oficial como SVG inline.

  El recuadro del logo va en **blanco fijo, no `bg-background`**: en dark mode
  `bg-background` es oscuro, y las guidelines de Google piden el logo sobre
  fondo claro. Además el botón se invierte a tinta en hover, así que ni
  siquiera en light alcanzaba con seguir al tema.

Se guarda el `sub` de Google, **no el mail**: el mail de una cuenta de Google
puede cambiar, el `sub` no. Columna `users.google_sub`, con índice único.

## Si Google no está configurado

Degrada limpio, igual que Resend:

- Backend: `POST /auth/google` devuelve **503**.
- Frontend: sin `VITE_GOOGLE_CLIENT_ID` el componente devuelve `null` y ni
  siquiera carga el script de Google. El login por usuario/contraseña y el de
  invitado siguen intactos.

Truco de diagnóstico: pegarle a `/auth/google` con un token cualquiera.
**503** = el backend no leyó la env var. **401** = sí la leyó y llegó a
consultar a Google.

## Tests

`backend/tests/test_auth.py`. El fixture `google_configured` mockea
`verify_access_token` para los tests de flujo (crear cuenta, adoptar invitado,
atar cuenta local), y los tests de seguridad mockean `_fetch_tokeninfo` /
`_fetch_userinfo` para ejercitar los chequeos reales de `aud`/`azp` y
`email_verified`.

Nunca pegan contra la API real de Google.

## Lo que quedó sin verificar

El login real con una cuenta de Google no se probó de punta a punta desde el
agente — implica autenticarse con una cuenta personal. Sí se verificó todo el
camino alrededor: el botón abre el popup real
(`accounts.google.com/o/oauth2/v2/auth`), y el backend lee la variable y pega
contra la API real de Google (rechaza un token falso con 401).

**Ojo con el flujo de ID token**: el login con ID token sí lo confirmó Matías
a mano el 2026-08-05 ("anda bien todo"). El cambio a access token es posterior
y solo está verificado hasta la apertura del popup — falta que alguien complete
un login real con el flujo nuevo.
