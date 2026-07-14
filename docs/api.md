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
`PELIPICK_DEBUG=1` en `backend/.env` — para poder probar el flujo de punta a
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

`mode` controla de dónde sale la señal de gusto para puntuar candidatos:

- `profile`: usa todo el historial de ratings/reviews del zip (comportamiento
  de siempre).
- `recent`: solo usa los últimos 10 títulos vistos (por `Watched Date` de
  `diary.csv`, o `Date` de `ratings.csv`/`reviews.csv` si no hay diary). La
  exclusión de ya vistos sigue cubriendo todo el historial, no solo la
  ventana reciente.
- `genres`: ignora el historial como filtro obligatorio y en cambio exige
  que cada recomendación tenga al menos una etiqueta de los géneros
  seleccionados en `genres` (lógica OR, no AND). Si hay más de un género
  seleccionado, el resultado intenta cubrir al menos un pick por género
  antes de completar el resto por score. Claves válidas: `action`,
  `romance`, `comedy`, `horror`, `drama`, `psychological`, `scifi` (ver
  `GENRE_OPTIONS` en `backend/app/recommender.py`).

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
      "created_at": "2026-07-14 12:03:41"
    }
  ]
}
```

Si el usuario no subió ningún zip todavía, devuelve `200` con `items: []`.

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

- persistencia en SQLite (`backend/pelipick.db`, path configurable con
  `PELIPICK_DB_PATH`)
- passwords con PBKDF2-HMAC-SHA256 + salt, sin librerías extra
- reset de contraseña con token efímero persistido en SQLite, todavía sin
  integración de email real
- no hay versionado de API todavía

Código relacionado:

- [backend/app/main.py](../backend/app/main.py)
- [backend/app/models.py](../backend/app/models.py)
- [backend/app/db.py](../backend/app/db.py)
- [backend/app/auth.py](../backend/app/auth.py)
