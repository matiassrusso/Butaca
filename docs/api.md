# API actual

Base local esperada:

- `http://127.0.0.1:8001`

## `GET /health`

Chequeo básico del backend.

### Response

```json
{
  "status": "ok"
}
```

## Auth

Todo lo que toca datos de usuario (`/recommend/zip`, `/feedback`) requiere
sesión. La sesión es un token opaco, no JWT: se guarda en la tabla `sessions`
y se manda como header `Authorization: Bearer <token>`.

## `POST /auth/register`

### Body

```json
{
  "username": "mati",
  "password": "algo de 8+ caracteres"
}
```

### Response (201)

```json
{
  "token": "opaque-session-token",
  "username": "mati"
}
```

`409` si el username ya existe.

## `POST /auth/login`

Mismo body que `register`. Devuelve `200` con el mismo shape, `401` si el
usuario no existe o la contraseña es incorrecta, y `429` cuando ese username
acumula demasiados intentos fallidos seguidos.

Rate limiting actual:

- 1er y 2do fallo: `401`
- 3er fallo consecutivo: lock de 30s
- después escala con backoff exponencial, con tope de 15 minutos
- un login exitoso limpia el contador de fallos

## `POST /auth/forgot-password`

Inicia recuperación de contraseña.

### Body

```json
{
  "username": "mati"
}
```

### Response (200)

```json
{
  "status": "ok",
  "reset_token": null
}
```

El backend siempre genera y guarda el token internamente (hasheado en
SQLite), pero **por default nunca lo devuelve en la response** — ni para
usuarios que existen ni para los que no, así no hay forma de distinguir uno
de otro desde afuera. Sin eso, cualquiera podía pedir el reset de cualquier
usuario y tomar la cuenta sin tocar su email.

`reset_token` solo viaja en la respuesta si el backend corre con
`BUTACA_DEBUG=1` en `backend/.env` — para poder probar el flujo de punta a
punta en local sin un proveedor de mail configurado. **Nunca debe estar
seteado en producción.** Cuando haya proveedor de mail real, este debug
override se saca y el token se manda solo por email.

## `POST /auth/reset-password`

Consume el token de recuperación y cambia la contraseña.

### Body

```json
{
  "token": "temporary-reset-token",
  "password": "nueva-clave-segura"
}
```

### Response

`204 No Content` si el cambio se aplicó.

`400` si el token es inválido o expiró. Al resetear la contraseña, el backend
invalida todas las sesiones activas de ese usuario.

## `POST /auth/logout`

Requiere `Authorization: Bearer <token>`. Borra la sesión. `204` siempre
(idempotente).

## `GET /recommend/options`

Opciones del picker "a tu elección" (`mode=genres` en los endpoints de
abajo). Sin auth, público como `/catalog/stats` — es metadata del picker,
no datos de usuario.

```json
{
  "options": [
    {"key": "action", "label": "Acción", "group": "generos"},
    {"key": "mindbender", "label": "MindBender", "group": "vibras"}
  ]
}
```

Fuente de verdad: `PICK_OPTIONS` en `backend/app/recommender.py`. El
frontend reemplaza acá el array `genreOptions` que antes tenía hardcodeado.

## `POST /recommend`

Endpoint viejo para mandar ratings ya parseados. No requiere auth, no
persiste nada — quedó igual que antes, sin uso desde el frontend.

### Body

```json
{
  "mood": "psychological",
  "ratings": [
    {
      "title": "Enemy",
      "rating": 4.5,
      "review": "psychological and weird in a good way"
    }
  ]
}
```

## `POST /recommend/zip`

Endpoint usado por la web. **Requiere auth.** Recibe el `.zip` completo que
exporta Letterboxd (no JSON — es `multipart/form-data`, porque un zip es
binario). Ver [letterboxd-zip-format.md](letterboxd-zip-format.md) para el
detalle de qué archivos lee adentro del zip.

### Headers

```
Authorization: Bearer <token>
Content-Type: multipart/form-data
```

### Body (form fields)

```
mood: psychological           (opcional, legacy — sesga qué página de TMDb se pide)
mode: profile | recent | genres   (default: profile)
kind_filter: movie | series | both   (default: both)
genres: "action,romance"      (obligatorio si mode=genres, claves separadas por coma)
file: <el .zip como binario>
```

### Idioma: header `Accept-Language` (agregado 2026-08-06)

**Todos** los endpoints leen el idioma de `Accept-Language`. Es la única
fuente: no hay query param, form field ni campo de JSON para esto. Cualquier
valor que no empiece con `en` cae a `es`, incluido el header ausente. Se
parsea el primer tag, así que un `Accept-Language` de browser real
(`en-US,en;q=0.9,es;q=0.8`) resuelve a `en`.

```
Accept-Language: en
```

Define dos cosas:

1. **Los textos generados** — el `why` de cada pick y el `taste_summary`.
   Cubre los dos caminos, no solo el del LLM: `llm_client` arma sus prompts
   con la voz y las reglas de escritura en el idioma pedido, y `recommender`
   tiene su propio vocabulario de frases y plantillas por idioma para el
   `why` heurístico (el que se muestra sin sesión, cuando el LLM falla, y en
   los picks que el LLM no llega a cubrir).
2. **El `detail` de los errores** (`backend/app/errors.py`) — se muestra tal
   cual en pantalla, así que en inglés tiene que salir en inglés. Aplica
   también a los endpoints de auth, que no generan texto pero sí devuelven
   errores que el usuario lee ("Wrong username or password.").

El idioma **es parte de la clave de caché** de los dos caches del
`llm_client` (`_REFINE_CACHE` y `_VERDICT_CACHE`). Sin eso, el primer usuario
que pide `/weekly` en español dejaría cacheado ese resultado y el siguiente
que lo pide en inglés recibiría los `why` en español.

El frontend lo manda solo, en cada request: `frontend/src/lib/apiLang.ts`
envuelve `fetch` una vez al arrancar en vez de tocar las ~40 llamadas sueltas.

`mode` controla de dónde sale la señal de gusto para puntuar candidatos:

- `profile`: usa todo el historial de ratings/reviews del zip (comportamiento
  de siempre).
- `recent`: solo usa los últimos 10 títulos vistos (por `Watched Date` de
  `diary.csv`, o `Date` de `ratings.csv`/`reviews.csv` si no hay diary). La
  exclusión de ya vistos sigue cubriendo todo el historial, no solo la
  ventana reciente.
- `genres` ("a tu elección" desde 2026-08-02): ignora el historial como
  filtro obligatorio y en cambio pide su propio pool a TMDb, dirigido a las
  opciones elegidas en `genres` (`tmdb_client.fetch_candidates_for_options`
  — un request a `/discover` por opción y por `kind_filter`, nunca combina
  géneros/keywords de opciones distintas en un mismo request). Lógica OR
  entre opciones, no AND; si hay más de una seleccionada, el resultado
  intenta cubrir al menos un pick por opción (en el orden en que se
  eligieron) antes de completar el resto por score. Máximo 5 opciones por
  request (`MAX_SELECTED_OPTIONS` en `backend/app/main.py`, 400 si se
  pasa). Claves válidas y sus grupos ("generos" / "vibras", las de "vibras"
  son categorías tipo Flick armadas con keywords de TMDb en vez de
  clustering — ver `docs/build-log.md` 2026-08-02): `GET /recommend/options`
  las lista dinámicamente, fuente de verdad es `PICK_OPTIONS` en
  `backend/app/recommender.py`.

`kind_filter` filtra el catálogo de candidatos por `movie`, `series`, o
ambos (`both`).

### Response

```json
{
  "taste_summary": "Tu historial tira más a cine de autor...",
  "recommendations": [
    {
      "id": 1,
      "tmdb_id": 808,
      "title": "Perfect Blue",
      "year": 1997,
      "kind": "movie",
      "why": "coincide con patrones que venís premiando.",
      "match_score": 99,
      "tags": ["psychological", "dark", "stylized", "thriller"]
    }
  ]
}
```

`400` si el archivo no termina en `.zip`, si supera 20MB, si no es un zip
válido, si no tiene `ratings.csv` ni `reviews.csv` adentro, o si algún CSV
interno viene mal formado.

Cada rating importado y cada recomendación servida quedan persistidos en
SQLite, asociados al usuario autenticado.

## `POST /recommend/letterboxd`

Alternativa a `/recommend/zip` que no requiere exportar nada: scrapea el
diario público de un username de Letterboxd en vez de leer un zip. Ver
[letterboxd-username-import.md](letterboxd-username-import.md) para el
detalle de qué se puede leer así y qué no.

### Body (form fields)

```
username: scorsese            (obligatorio)
mood: psychological           (opcional, legacy)
mode: profile | recent | genres   (default: profile)
kind_filter: movie | series | both   (default: both)
genres: "action,romance"      (obligatorio si mode=genres)
```

Mismo `mode`/`kind_filter`/`genres`/response shape que `/recommend/zip` (ver
arriba) — comparten toda la lógica de recomendación, solo cambia de dónde
sale `(ratings, extra_seen)`.

`400` si el username está vacío, si no existe un usuario de Letterboxd con
ese nombre, si su diario no tiene entradas públicas, o si Letterboxd no
responde.

## `GET /history`

Requiere auth. Devuelve las sesiones de recomendación ya generadas por el
usuario autenticado, ordenadas de la más nueva a la más vieja.

### Response

```json
{
  "sessions": [
    {
      "id": 2,
      "mood": "psychological",
      "taste_summary": "Tu historial tira más a cine de autor...",
      "created_at": "2026-07-11 18:40:12",
      "recommendations": [
        {
          "id": 9,
          "tmdb_id": 808,
          "title": "Perfect Blue",
          "year": 1997,
          "kind": "movie",
          "why": "coincide con patrones que venís premiando.",
          "match_score": 99,
          "tags": ["psychological", "dark", "stylized", "thriller"],
          "poster_path": "https://image.tmdb.org/t/p/w500/...",
          "backdrop_path": "https://image.tmdb.org/t/p/w780/...",
          "overview": "Mima, una idol pop...",
          "vote_average": 8.3
        }
      ]
    }
  ]
}
```

Si el usuario no tiene historial todavía, devuelve `200` con `sessions: []`.

## `GET /history/watched`

Requiere auth. Devuelve las películas que el usuario ya vio, a partir de lo
importado del `.zip` de Letterboxd (tabla `rated_items`), separado de las
sesiones de recomendación de `/history`. Ordenadas de la más nueva a la más
vieja, deduplicadas por título (si el mismo título aparece más de una vez —
p. ej. subiste el zip dos veces — se queda con la fila más reciente).

### Response

```json
{
  "items": [
    {
      "title": "Whiplash",
      "rating": 4.5,
      "review": "psychological and intense",
      "watched_date": "2025-05-28",
      "created_at": "2026-07-14 12:03:41"
    }
  ]
}
```

`watched_date` viene de `diary.csv` cuando está disponible; si falta, llega
vacío y el frontend muestra `created_at` como fallback.

Si el usuario no subió ningún zip todavía, devuelve `200` con `items: []`.

## `GET /profile/taste`

Requiere auth. Arma el perfil de gusto visual: géneros (pesados por rating),
décadas, y directores/actores favoritos, cruzando `rated_items` del usuario
contra TMDb.

`503` si no hay `TMDB_API_KEY` configurada.

Acota el trabajo para que la carga no dependa de cientos de requests
secuenciales a TMDb en exports grandes: matchea (búsqueda por título) los 150
títulos mejor puntuados del usuario, y de esos pide créditos
(director/cast) solo para los 50 mejores. `matched_count` informa cuántos
títulos matchearon realmente contra `total_count` (el total de vistas del
usuario) para que el frontend pueda avisar si el perfil quedó parcial.

### Response

```json
{
  "matched_count": 8,
  "total_count": 10,
  "genre_breakdown": [
    {"genre": "Drama", "weight": 18.5}
  ],
  "decade_breakdown": [
    {"decade": 2010, "count": 5}
  ],
  "top_directors": [
    {"name": "Christopher Nolan", "count": 2}
  ],
  "top_actors": [
    {"name": "Tom Hardy", "count": 1}
  ]
}
```

## `GET /movies/{tmdb_id}/details`

Requiere auth. Devuelve cast (top 10) y key de YouTube del tráiler para una
película o serie de TMDb. El modal de detalle pide este endpoint al abrirse
para recomendaciones con `tmdb_id`.

### Query params

- `kind`: `movie` (default) o `series`

### Response

```json
{
  "cast": [
    {"name": "Actor", "character": "Personaje", "profile_path": "https://image.tmdb.org/t/p/w185/..."}
  ],
  "trailer_key": "youtube-video-key"
}
```

`trailer_key` es `null` si no hay tráiler oficial en YouTube. `503` si no
hay `TMDB_API_KEY` configurada, `502` si TMDb falla.

Solo funciona para recomendaciones que vinieron del catálogo real de TMDb —
las del catálogo mock no tienen `tmdb_id` (viene `null` en `Recommendation`).

## `POST /feedback`

Requiere auth. Guarda feedback explícito sobre un pick ya servido.

### Body

```json
{
  "recommendation_id": 1,
  "status": "interested"
}
```

`status` es uno de `interested`, `not_interested`, `seen`.

`201` si se guardó. `404` si la `recommendation_id` no existe o no es del
usuario autenticado (no distinguimos "no existe" de "es de otro usuario" para
no filtrar esa info).

## Notas

- persistencia en SQLite (`backend/butaca.db`, path configurable con
  `BUTACA_DB_PATH`)
- passwords con PBKDF2-HMAC-SHA256 + salt, sin librerías extra
- reset de contraseña con token efímero persistido en SQLite, todavía sin
  integración de email real
- no hay versionado de API todavía

Código relacionado:

- [backend/app/main.py](../backend/app/main.py)
- [backend/app/models.py](../backend/app/models.py)
- [backend/app/db.py](../backend/app/db.py)
- [backend/app/auth.py](../backend/app/auth.py)
