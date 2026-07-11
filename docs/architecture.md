# Arquitectura actual

## Resumen

Hoy `PeliPick` es una vertical slice local con dos partes:

- `frontend` en `React + TypeScript + Vite`
- `backend` en `FastAPI`

Ya hay base de datos (`SQLite`), login, catálogo real (`TMDb`, con fallback a
mock) y un agente de IA (`Gemini`) que refina el resumen de gusto y el orden/
razones de los picks. La ingesta es el `.zip` completo que exporta
Letterboxd (no un CSV suelto) — no hay scraping ni import por username
todavía.

## Flujo actual

1. El usuario se registra o entra con usuario/contraseña.
2. El usuario sube el `.zip` de su export de Letterboxd desde la web.
3. El frontend manda el zip como `multipart/form-data` al backend con su
   token de sesión.
4. El backend abre el zip en memoria y combina varias señales: rating base
   (`ratings.csv`/`reviews.csv`), boost por rewatch (`diary.csv`), likes sin
   puntuar (`likes/films.csv`), favoritos explícitos (`profile.csv`) y
   exclusión ampliada por todo lo visto (`watched.csv`) — ver
   [letterboxd-zip-format.md](letterboxd-zip-format.md).
5. El backend resume el gusto del usuario.
6. El backend trae candidatos de `TMDb` (o cae al catálogo mock si no hay key
   configurada o TMDb falla) y los scorea.
6.5. Si hay `GEMINI_API_KEY`, el agente reordena esos picks y reescribe el
   resumen y las razones (o cae de vuelta al resultado heurístico si falla).
7. El backend persiste los ratings importados y las recomendaciones servidas.
8. El backend devuelve hasta 5 recomendaciones explicadas.
9. El frontend renderiza el resumen y los picks, con botones de feedback por pick.
10. El feedback (me interesa / no me interesa / ya la vi) se guarda asociado al usuario y a la recomendación.
11. El usuario puede volver después a `/history` y revisitar sesiones pasadas sin resubir el zip.

## Frontend

Stack: `React + TypeScript + Vite + Tailwind v4 + Framer Motion + wouter`.
El tema visual ("cinematic", ámbar/dorado sobre negro) y las páginas se
generaron con otra IA (plataforma "Manus", que traía su propio server
Node/tRPC/Drizzle) y se adaptaron a mano: nos quedamos con la UI, tiramos su
backend entero y reconectamos las páginas a nuestro FastAPI vía `fetch` plano
(no tRPC).

Páginas:

- [frontend/src/pages/Home.tsx](C:\Users\matia\OneDrive\Escritorio\Webs\projects\pelipick\frontend\src\pages\Home.tsx): landing
- [frontend/src/pages/Login.tsx](C:\Users\matia\OneDrive\Escritorio\Webs\projects\pelipick\frontend\src\pages\Login.tsx): login/registro
- [frontend/src/pages/Recommend.tsx](C:\Users\matia\OneDrive\Escritorio\Webs\projects\pelipick\frontend\src\pages\Recommend.tsx): upload del zip + mood + resultados + feedback, todo en un solo flujo (fusiona lo que en el diseño original eran dos pasos separados)
- [frontend/src/pages/History.tsx](C:\Users\matia\OneDrive\Escritorio\Webs\projects\pelipick\frontend\src\pages\History.tsx): historial de sesiones de recomendación revisitables
- [frontend/src/pages/NotFound.tsx](C:\Users\matia\OneDrive\Escritorio\Webs\projects\pelipick\frontend\src\pages\NotFound.tsx)

Estado compartido:

- [frontend/src/hooks/useAuth.tsx](C:\Users\matia\OneDrive\Escritorio\Webs\projects\pelipick\frontend\src\hooks\useAuth.tsx): Context de auth (token en `localStorage`, valida contra `GET /auth/me` al cargar)

Deliberadamente no se portaron los componentes `shadcn/ui`/Radix del diseño
original: ninguna de las páginas reales los usaba (confirmado leyendo el
código fuente), todo está armado con clases de Tailwind directas.

Estilo:

- [frontend/src/index.css](C:\Users\matia\OneDrive\Escritorio\Webs\projects\pelipick\frontend\src\index.css)

## Backend

Entrada principal:

- [backend/app/main.py](C:\Users\matia\OneDrive\Escritorio\Webs\projects\pelipick\backend\app\main.py)

Piezas actuales:

- [backend/app/models.py](C:\Users\matia\OneDrive\Escritorio\Webs\projects\pelipick\backend\app\models.py): contratos de request/response
- [backend/app/csv_ingest.py](C:\Users\matia\OneDrive\Escritorio\Webs\projects\pelipick\backend\app\csv_ingest.py): parser de un CSV individual (`Name`/`Title`/`Film`, etc.), reusado por `letterboxd_zip.py`
- [backend/app/letterboxd_zip.py](C:\Users\matia\OneDrive\Escritorio\Webs\projects\pelipick\backend\app\letterboxd_zip.py): abre el zip del export, combina ratings/reviews/diary/likes/watched/profile
- [backend/app/recommender.py](C:\Users\matia\OneDrive\Escritorio\Webs\projects\pelipick\backend\app\recommender.py): resumen y ranking heurístico
- [backend/app/catalog.py](C:\Users\matia\OneDrive\Escritorio\Webs\projects\pelipick\backend\app\catalog.py): catálogo mock
- [backend/app/db.py](C:\Users\matia\OneDrive\Escritorio\Webs\projects\pelipick\backend\app\db.py): SQLite (stdlib `sqlite3`, sin ORM), schema e inserts/queries
- [backend/app/auth.py](C:\Users\matia\OneDrive\Escritorio\Webs\projects\pelipick\backend\app\auth.py): hashing de password (PBKDF2, stdlib) y dependencia de sesión
- [backend/app/tmdb_client.py](C:\Users\matia\OneDrive\Escritorio\Webs\projects\pelipick\backend\app\tmdb_client.py): cliente TMDb (stdlib `urllib`), mapea género + overview a tags propios
- [backend/app/llm_client.py](C:\Users\matia\OneDrive\Escritorio\Webs\projects\pelipick\backend\app\llm_client.py): cliente Gemini (stdlib `urllib`), refina resumen y picks del heurístico

## Decisiones deliberadas

- import del `.zip` completo de Letterboxd (multipart) en vez de pegar/subir
  un CSV suelto: el zip trae señal real que un solo CSV no tiene (likes,
  rewatches, favoritos, historial completo de visto) — ver
  `docs/letterboxd-zip-format.md`
- zip antes que scraping del perfil público: más simple para validar
  producto y no depende de que Letterboxd no cambie su HTML
- heurística simple antes que embeddings/agente libre: más control y menos humo
- `SQLite` vía stdlib en vez de un ORM: el esquema es chico (4 tablas), no
  justifica sumar `SQLAlchemy` todavía
- tokens de sesión opacos en vez de `JWT`: logout trivial (borrar la fila), sin
  sumar una librería de firma
- `TMDb` vía `urllib` stdlib, sin sumar `httpx`/`requests` al runtime del
  backend (solo se usan como dependencia de test)
- IDs de género de TMDb hardcodeados (son constantes públicas estables) en vez
  de fetchear y cachear `/genre/movie/list`
- si TMDb falla o no está configurada, cae al catálogo mock en vez de romper
  la respuesta — ver `docs/tmdb-setup.md`
- agente de IA con `Gemini` (free tier) en vez de pagar OpenAI de entrada —
  ver `docs/gemini-setup.md`; el LLM solo reordena/reescribe texto sobre
  candidatos ya filtrados por TMDb, nunca inventa títulos ni metadata
- si Gemini falla, no está configurada, o devuelve picks fuera de la lista de
  candidatos, cae al resultado heurístico sin romper la respuesta
- el ranking heurístico ordena por el score crudo (sin clamp), no por el
  `match_score` mostrado (clampeado a 99): con series reales sumadas al
  catálogo, muchos candidatos empatan en el score clampeado, y ordenar por
  ese valor hacía que el empate cayera siempre del lado de las películas
  (listadas antes que las series en el catálogo combinado)
- del zip de UI generado externamente, se descartó todo lo que las páginas
  reales no usaban (Radix, shadcn/ui, CVA, `react-hook-form`, `recharts`) en
  vez de portarlo "porque estaba" — se verificó con `grep` qué importaba cada
  página antes de decidir
- rate limiting de login por username (backoff exponencial, tope 15 min) y
  recuperación de contraseña con token de un solo uso, hasheado en SQLite,
  que expira a la hora e invalida sesiones viejas al usarse
- el token de reset **nunca** viaja en la respuesta de `/auth/forgot-password`
  salvo `PELIPICK_DEBUG=1` — sin eso, cualquiera con un username válido
  podía tomar la cuenta sin tocar el email del usuario (hallazgo encontrado
  en revisión, arreglado antes de mergear)
- caché en memoria de `/discover/movie` y `/discover/tv` (TTL 5 min, tope
  32 entradas, LRU) — evita pegarle a TMDb en cada request si el
  mood+página ya se pidió hace poco
- historial revisitable guardando una `recommendation_session` explícita por
  request de `/recommend/zip`, en vez de reconstruir sesiones por timestamp
  desde `recommendations_served` (más corto de implementar, pero frágil si dos
  requests caen en el mismo segundo)

## Limitaciones actuales

- catálogo real de `TMDb` (películas y series), pero el mapeo género/overview
  → tags es heurístico y coarse (no hay nuance real de tono/ritmo todavía)
- sin caché de resultados de Gemini
- el agente de IA reordena y reescribe texto, no rescorea ni trae candidatos
  propios — sigue acotado a lo que ya filtró el heurístico
- no hay scraping de Letterboxd por username, solo import del zip manual
- no usa los `Tags` propios del usuario en `diary.csv`/`reviews.csv` (casi
  nadie los completa, pero cuando existen son señal directa)
- recuperación de contraseña sin envío real de mail todavía — el flujo
  funciona pero el token no llega al usuario sin `PELIPICK_DEBUG=1`

## Próxima arquitectura probable

- perfil de gusto visual (necesita matchear el historial del usuario contra TMDb)
- historial de sesiones de recomendación revisitables
- cast y tráiler en el detalle de película — necesita guardar el id real
  de TMDb por título (hoy no viaja por el pipeline)
- scraping o import automático desde el username de Letterboxd, como
  alternativa al zip manual
