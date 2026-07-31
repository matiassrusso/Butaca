@AGENTS.md

# Butaca

Motor de recomendaciones de pelis y series basado en el gusto real de una persona (import completo del export de Letterboxd), no en promedios genéricos.

## Claude's Role

Avanzar el MVP siguiendo la regla práctica del proyecto: cada iteración debería mover calidad real de recomendación o claridad real del flujo de uso — si no, probablemente es complejidad de más. Coordinar con otros agentes vía `TASKS.md` cuando corresponda.

If a session is drifting without moving hacia calidad de recomendación o claridad de flujo, nudge me back: "¿Esto mejora la calidad del pick o la claridad del flujo? Si no, ¿vale la pena ahora?"

## Process

1. Definición corta del alcance (ver `docs/product-mvp.md`)
2. Implementación en `backend` (FastAPI + SQLite) y/o `frontend` (React + Vite + Tailwind)
3. Si hay varios agentes en paralelo: coordinación por `TASKS.md` (worktrees separados, marcar In Progress → Done, nunca mergear a `main` solo)
4. Tests de backend en verde antes de cerrar (284 tests a la fecha)
5. Deployeado: frontend [butaca.xyz](https://butaca.xyz/) (Vercel), backend [api.butaca.xyz](https://api.butaca.xyz) (Render, free tier — cold start en la primera request)

## Key People

Solo yo (Matías), con posible coordinación multi-agente (Claude, Codex) documentada en `TASKS.md`.

## Folder Structure

- `backend/` — FastAPI + SQLite/Postgres: auth (con mail de recuperación vía Resend), catálogo TMDb, agente NVIDIA NIM, import de Letterboxd
- `frontend/` — React + Vite + Tailwind, tema "Hybrid critic notebook" (papel/tinta/terracota, dark mode real, portado desde una iteración en Lovable — ver `DESIGN.md`)
- `docs/` — `product-mvp.md`, `design-directions.md`, `architecture.md`, `mvp-status.md`, `api.md`, `tmdb-setup.md`, `nvidia-setup.md`, `letterboxd-zip-format.md`, `letterboxd-username-import.md`, `build-log.md`
- `00 System/` — scripts/config reusables de este proyecto (vacío por ahora)
- `01 Skills/` — skills en markdown de este proyecto (vacío por ahora)
- `02 Attachments/` — imágenes/screenshots (vacío por ahora)
- `03 Iteration Logs/` — notas de qué mejorar entre iteraciones (arranca con el feedback de amigos pre-lanzamiento del 2026-07-23)

## Rules & Conventions

- **`(C)` prefix** — Archivos creados por Claude llevan prefijo `(C)`
- **Editing rule** — Antes de editar un archivo sin el prefijo `(C)`, pedir permiso primero
- **Skills** — Automatizaciones reusables de este proyecto van en `01 Skills/` como markdown, no como Claude Code skills
- **Workflow multi-agente:** leer `TASKS.md` antes de tocar código; marcar tarea In Progress con nombre de agente; al terminar, mover a Done y resumir archivos tocados; nunca mergear a `main` sin avisar
- Requiere `TMDB_API_KEY` y `NVIDIA_API_KEY` en `backend/.env` (ver `docs/tmdb-setup.md` y `docs/nvidia-setup.md`); `RESEND_API_KEY` opcional para mail real de recuperación
- Recuperación de contraseña: manda mail real vía Resend si `RESEND_API_KEY` está seteada; si no, el token solo sale de la respuesta con `BUTACA_DEBUG=1`

## Current Status

> <!-- SESSION_STATE:START -->
> **Last updated:** 2026-07-31 (sesión: 3 bugs de `/weekly` post-feedback +
> 3 features pedidas + 3 bugs más de features en producción — match_score
> plano, why autoreferencial, bitácora — + el match_score seguía repitiéndose
> tras el primer intento, resuelto con desempate por vote_average)
>
> ### ⚠️ Leer primero al retomar
>
> Todo lo reportado hasta ahora está resuelto y deployado (push
> `bc52b2b`..`10ddce2`). Nada bloqueante pendiente — falta que Matías lo
> pruebe en producción una vez que Render termine el redeploy, sobre todo:
> - El botón **"¿No estás de acuerdo?"** del modal (vota similares de TMDb)
>   — no se pudo probar en el browser local porque la TMDb key local está
>   vieja (401), solo queda cubierto por los 6 tests de backend
>   (`fetch_similar_titles` + `GET /movies/{id}/similar`).
> - El mix de **variedad de épocas** en `/weekly` (3 trending + 2 de una
>   década que rota por semana ISO) — es una decisión de diseño de esta
>   sesión, no algo que Matías haya especificado en detalle; puede querer
>   ajustar el ratio 3/2 o las décadas (`tmdb_client.WEEKLY_CLASSIC_DECADES`).
> - El desempate de match_score por `vote_average` (`_differentiate_weekly_match_scores`
>   en `main.py`) es una solución pragmática, no una reescritura del
>   scoring — el vocabulario de tags sigue siendo chico de fondo (ver
>   "Contexto" abajo). Si vuelve a verse plano con otro set de trending,
>   ese es el lugar para ajustar el multiplicador (`* 3`) o el enfoque.
>
> **Qué se hizo el 2026-07-31, tercera ronda** (1 commit, `10ddce2`,
> 282→284 tests) — el match_score seguía repitiéndose tras el fix de la
> segunda ronda:
> - Matías mandó una captura mostrando 4 de las 5 semanales con
>   exactamente el mismo 81% (el fix de keyword tags de la ronda anterior
>   no alcanzó). Antes de tocar nada más, se confirmó la causa real contra
>   **logs de producción vía la API de Render** (`RENDER_API_KEY`, service
>   `srv-d9cnhqu1a83c739eono0`): los logs de `_enrich_with_keyword_tags`
>   mostraban `KEYWORD_TAG_MAP` sin match para Spider-Man, Supergirl, The
>   Odyssey y Grave of the Fireflies esa semana puntual (solo Cinema
>   Paradiso tuvo "coming-of-age") — la allowlist de keywords es
>   demasiado angosta para diferenciar ese set en particular, el fix
>   anterior funciona pero no siempre alcanza.
> - Nuevo desempate en `weekly_picks()`: cuando ya hay evidencia real
>   (`match_score != 50`) se usa `vote_average` de TMDb —dato real, no
>   inventado, que sí varía por título— para separar candidatos que el
>   tag-matching no puede diferenciar. Acotado a `/weekly` en `main.py`
>   (`_differentiate_weekly_match_scores`), `recommend()` no se toca — lo
>   usa también `/recommend` y ahí el problema no se manifestó igual.
>
> **Qué se hizo el 2026-07-31, segunda ronda** (1 commit, `0c2b95b`,
> 278→282 tests) — 3 bugs más encontrados por Matías probando las features
> recién shippeadas en producción:
> - **Las 5 semanales daban el mismo match_score (81%)**, sin importar el
>   título. Causa: `fetch_weekly_trending` nunca enriquecía sus candidatos
>   con keyword tags de TMDb (`_enrich_with_keyword_tags`, que sí corre
>   para `/recommend` vía `fetch_personalized_candidates`) — con solo el
>   vocabulario chico de ~12 tags de género, un perfil de gusto diverso
>   satura `positive_tags` hasta cubrirlos todos, y cualquier candidato
>   matchea "completo" dando el mismo bonus. Ahora los candidatos
>   semanales también reciben keywords.
> - **El why de "The Odyssey" se comparaba consigo misma** ("es una
>   versión moderna de la misma mitología que ya amaste en tu The Odyssey
>   puntuado"). Causa: `exclude_seen=False` en `/weekly` (fix de la
>   primera ronda) permite que un candidato coincida con un título que el
>   usuario ya puntuó — `predict_weekly_fit` se lo mandaba al LLM como
>   candidato Y como historial al mismo tiempo, sin avisarle que eran la
>   misma película. Ahora esos títulos se sacan del pool que se le manda
>   al LLM y reciben directo un why honesto ("Ya la viste — te encantó.")
>   con el rating real.
> - **La bitácora (`/history`) mostraba estrellas 1-5 para todo rating**,
>   aunque los de "Ya la vi"/modo manual son sintéticos (un botón, no
>   estrellas puestas en Letterboxd) — mismo criterio que ya se había
>   aplicado al why del LLM, pero nunca se llevó a esta pantalla. Nueva
>   columna "Dónde" (Letterboxd/Butaca) + el rating se muestra como
>   estrellas solo si `source="import"`, si no como texto ("te
>   encantó"/"te gustó"/"no te gustó"). Sumado un toggle "Tu reseña" para
>   ver la reseña completa de Letterboxd sin recortar (antes se cortaba a
>   una línea siempre visible).
>
> **Qué se hizo el 2026-07-31, primera ronda** (4 commits, `c0d0931`..`3562bd5`, 263→278 tests):
> - **3 bugs de `/weekly` reportados con capturas** (feedback fresco de la
>   sesión anterior, en `NOTAS_DEL_PROYECTO.md`): solo 3 de 5 pelis
>   (`fetch_weekly_trending` solo pedía página 1 de TMDb, ahora pagina
>   hasta 3), why citando puntaje inventado en likes/favoritos de
>   Letterboxd (nuevo `source="like"`, el check de `llm_client` pasó a ser
>   positivo: solo `"import"` cita puntaje exacto).
> - Al probar en producción, Matías encontró que **el fix anterior no
>   alcanzaba**: seguían apareciendo 2/5 en vez de 5 (bug distinto:
>   `recommend()` excluye del catálogo cualquier título ya puntuado por el
>   usuario — correcto para `/recommend`, pero rompía la promesa de
>   `/weekly` de "las mismas 5 para todos"; nuevo `exclude_seen=False` solo
>   ahí), 50% match inconsistente con un why entusiasta (`/weekly` nunca
>   corría `_enrich_loved_ratings_with_genre_tags` antes de puntuar, a
>   diferencia de `/recommend` — ahora sí), y el why seguía en tercera
>   persona al citar el rating ("que ya puntuaste como 'le encantó'" —
>   `_rating_label` pasó a "te encantó"/"no te gustó"/"te gustó").
> - **3 features pedidas, en orden de prioridad:**
>   1. **Unknown match**: `match_score=50` es "sin evidencia" por diseño
>      del propio backend — el frontend ahora lo etiqueta "Match
>      desconocido"/"S/D" en vez de un número que parece preciso y no lo es
>      (Home, Recommend, History, MovieModal; helper en `frontend/src/lib/match.ts`).
>   2. **"Ya la vi" con mini-menú de rating** (me encantó/bien/no me
>      gustó) que persiste a `rated_items` vía nuevo `POST /profile/rate`
>      — sin depender de un `recommendation_id` real, así anda también
>      desde `/weekly` (id=-1). Compone con el nuevo botón **"¿No estás de
>      acuerdo?"**: pide similares de TMDb (`GET /movies/{id}/similar`,
>      nuevo `tmdb_client.fetch_similar_titles`) y reusa el mismo mini-menú
>      para votarlos.
>   3. **Variedad de épocas en `/weekly`**: 3 de las 5 siguen siendo
>      trending real, 2 se reservan para lo mejor puntuado de una década
>      que rota por semana ISO (TMDb discover, 100% real, sin curación a
>      mano) — best-effort, si discover falla se rellena con más trending.
>
> **Qué se hizo el 2026-07-30** (10 commits, `f7ef842`..`a889137`, 230→263 tests):
> - Exploration slice enriquecida con keyword tags (+ fix de un bug propio:
>   el cap se aplicaba mal y las series de exploration nunca se enriquecían).
> - `KEYWORD_TAG_MAP` ampliado con 9 keywords nuevos verificados a mano
>   contra TMDb.
> - **Rediseño del banner "Usar mi perfil"** (modo manual "Sin cuenta"): era
>   todo-o-nada, ahora `GET /onboarding/titles` precarga lo ya puntuado
>   (de cualquier fuente) y queda editable en el mismo lugar.
> - **Typewriter para el "why"** al abrir el poster (pedido de Matías) — de
>   paso, dos bugs reales encontrados y arreglados: el modal se quedaba con
>   el why viejo si el refine del LLM llegaba con el modal abierto, y
>   `StrictMode` mataba la animación real en dev.
> - **Dos bugs de fondo reportados por Matías con capturas, arreglados:**
>   (1) puntuar en "Sin cuenta" y después generar con Letterboxd recomendaba
>   de vuelta esas mismas películas — la exclusión solo miraba el request
>   puntual, nunca el historial completo persistido; (2) el why citaba
>   `(4.5/5)` para ratings sintéticos del modo manual — nueva columna
>   `rated_items.source` ('import'/'manual') que el prompt del LLM usa para
>   no inventar precisión.
> - Búsqueda en "Sin cuenta" pasó de un dropdown angosto a posters directo
>   en la grilla de abajo.
> - `tmdb:movieId` del RSS de username: se usa directo (`fetch_title_by_id`)
>   en vez de buscar por título — menos requests, sin riesgo de matchear un
>   remake homónimo.
> - `CREDITS_ENRICH_CAP` 20→30; investigado kimi-k2.6 (404 confirmado en
>   vivo, problema de cuenta del lado de NVIDIA — se queda en llama);
>   **onboarding swipe/Tinder como preferencia del usuario** (toggle
>   Grilla/Swipe, no reemplazo).
> - **Recomendaciones semanales en la home** (`GET /weekly`, público): 5
>   pelis de `/trending/movie/week` de TMDb, iguales para todos (cacheado
>   por semana ISO), personalizadas con match_score + predicción del LLM
>   para quien tiene sesión. Ver bugs 1-2 de arriba, encontrados apenas
>   deployado.
>
> **Pendientes reales** (detalle en `Pending` de `TASKS.md`):
> - Que Matías pruebe en producción todo lo del 2026-07-31 (ambas rondas)
>   y confirme si el diseño elegido para variedad de épocas y el
>   match_score le sirve tal cual.
> - Bauti reportó "Load failed" importando por username; **despriorizado por
>   Matías**, sin logs no se pudo confirmar la causa.
> - Borrar el proyecto viejo de Neon (São Paulo) — Matías lo tiene que
>   hacer él, es borrado permanente de datos.
> - Renombrar la carpeta local del proyecto y la lista del `CLAUDE.md` raíz
>   del vault (fuera de este repo, requiere permiso).
>
> **Descartado a propósito** (no volver a proponerlo sin que Matías lo pida):
> el fallback del LLM queda en `llama-3.1-70b` (kimi-k2.6 confirmado 404 en
> vivo contra la key real, problema de entitlement de cuenta del lado de
> NVIDIA — hay un thread sin resolver en su foro); las cuentas de prueba en
> producción quedan; el auto-renew de `butaca.xyz` queda apagado.
>
> **Contexto que no se ve leyendo el código:**
> - `NOTAS_DEL_PROYECTO.md` (raíz del repo) es donde Matías deja feedback
>   libre con capturas — no es un archivo `(C)`, no editarlo sin permiso,
>   pero SÍ leerlo siempre al retomar (ver arriba).
> - La TMDb key del `backend/.env` **local** sigue vieja (401) — mismo
>   hallazgo que sesiones anteriores, sin cambios. Todo lo de esta sesión
>   que necesitaba TMDb real se verificó con mocks de `fetch` en el browser
>   local o contra producción/la API real vía curl directo.
> - `RENDER_API_KEY` sigue en una env var de usuario de Windows para leer
>   logs de prod (service id: `srv-d9cnhqu1a83c739eono0`).
> - El feed RSS de Letterboxd trae `<tmdb:movieId>` bajo el namespace
>   `xmlns:tmdb="https://themoviedb.org"` — confirmado contra el feed real
>   de un perfil público (`scorsese`) vía curl directo antes de escribir
>   código, no adivinado.
> - `backend/requirements.txt` y `docs/architecture.md` siguen figurando
>   como modificados en `git status` — sigue siendo solo ruido de line
>   endings (CRLF/LF) de sesiones viejas, sin cambio real de contenido.
> - Verificación de la primera ronda (2026-07-31): 278 tests de backend +
>   typecheck de frontend limpio + probado a mano en el dev server local
>   (funciona porque `NVIDIA_API_KEY` sí anda local, aunque `TMDB_API_KEY`
>   siga vieja — el modo manual "Sin cuenta" degrada a catálogo mock y
>   generó recomendaciones reales con el LLM). Confirmado con captura de
>   red: `POST /profile/rate` → 201, badge "S/D" y "Match desconocido"
>   visibles en la grilla y el modal. El botón "¿No estás de acuerdo?" no
>   se vio en local porque el catálogo mock no trae `tmdb_id` — cubierto
>   solo por tests de backend, sin verificación visual.
> - Verificación de la segunda ronda (2026-07-31): 282 tests de backend +
>   typecheck limpio + probado a mano en el dev server local, esta vez
>   con un zip sintético real subido vía curl (`Whiplash`, rating 4.5,
>   reseña con texto) además del modo manual — confirmado visualmente
>   que `/history` muestra "Letterboxd" + estrellas + toggle "Tu reseña"
>   para el ítem del zip, y "Butaca" + "Te encantó" (texto, sin
>   estrellas) para los 11 ítems puntuados a mano en sesiones previas.
> - Verificación de la tercera ronda (2026-07-31): 284 tests de backend.
>   Esta vez, en vez de adivinar la causa, se leyeron logs reales de
>   producción vía la API de Render (`GET /v1/logs`, filtrando por
>   `text=<título>`) para confirmar qué keywords de TMDb llegaban de
>   verdad y por qué no matcheaban — diagnóstico basado en datos
>   reales, no en hipótesis sobre el catálogo mock local.
> <!-- SESSION_STATE:END -->
>
> **2026-07-31 (sesión 3) — 1 commit (`10ddce2`), 282→284 tests:** Matías
> mandó una captura mostrando 4 de las 5 semanales con el mismo 81% pese
> al fix de keywords de la sesión 2 — no alcanzó. Se confirmó la causa
> real contra logs de producción (API de Render) en vez de asumir: para
> ese set puntual de trending, `KEYWORD_TAG_MAP` no matcheaba nada para 4
> de los 5 títulos. Se agregó un desempate por `vote_average` de TMDb
> (dato real, varía por título) acotado a `/weekly`, sin tocar
> `recommend()` (compartido con `/recommend`).
>
> **2026-07-31 (sesión 2) — 1 commit (`0c2b95b`), 278→282 tests:** Matías
> probó en producción las features de la sesión anterior y encontró 3
> bugs más: las 5 semanales daban el mismo match_score (81%, causa:
> `/weekly` nunca enriquecía candidatos con keyword tags de TMDb, a
> diferencia de `/recommend`), el why de "The Odyssey" se comparaba
> consigo misma (causa: `exclude_seen=False` permite que un candidato
> semanal coincida con algo ya puntuado, y el prompt del LLM no le
> avisaba que eran la misma película — ahora esos casos ni pasan por el
> LLM, reciben un why directo con el rating real), y la bitácora
> (`/history`) mostraba estrellas 1-5 para ratings sintéticos del modo
> manual (nueva columna "Dónde" + texto en vez de estrellas cuando
> `source != "import"`, más un toggle "Tu reseña"). Los 3 arreglados y
> verificados a mano con un zip real subido por curl.
>
> **2026-07-31 (sesión 1) — 4 commits (`c0d0931`..`3562bd5`), 263→278
> tests:** retomé el feedback fresco de la sesión anterior. Arreglé los 3
> bugs de `/weekly` reportados con capturas (pelis incompletas, why con
> puntaje inventado en likes); Matías probó en producción y encontró que
> la corrección no alcanzaba del todo — 2 bugs más de fondo
> (`exclude_seen` silencioso, falta de enrichment en `/weekly`) y el why
> seguía en tercera persona en un caso puntual. Arreglados los 3,
> confirmado con curl contra producción. Después implementé las 3
> features pedidas en orden: Unknown match, "Ya la vi" con rate directo +
> botón de desacuerdo (vota similares de TMDb), variedad de épocas en las
> semanales. Ver "Qué se hizo" arriba para el detalle completo.
>
> **2026-07-30 — sesión larga, 10 commits (`f7ef842`..`a889137`), 230→263
> tests:** ver "Qué se hizo" arriba para el resumen; detalle completo
> commit por commit en `TASKS.md` (sección `Pending`, cada ítem tiene su
> propia entrada con lo que se probó y cómo). Apenas deployadas las
> recomendaciones semanales, Matías encontró 2 bugs reales probando en
> producción (ver "Leer primero al retomar") — quedan para la próxima
> sesión, no se investigaron todavía.
>
> **2026-07-29 — keyword tags de TMDb + feedback ronda 2, 11 commits
> (`e49a81a`..`8d82ce2`), 215 → 228 tests:** dos frentes. (1) **Feedback ronda
> 2 de amigos:** el modo manual guardaba el perfil pero no había forma de
> reusarlo, así que había que re-tildar las mismas ~10 pelis en cada sesión —
> resuelto con `POST /recommend/profile` (regenera con `_rebuild_ratings`,
> `persist=False` para no duplicar `rated_items`) + banner "Usar mi perfil" en
> el paso 1 del wizard; también se separó el aviso de que el import por
> username trae solo lo reciente. (2) **Keyword tags de TMDb**, salido de un
> video sobre Flick: en vez de replicar su pipeline de embeddings + Leiden
> (necesita un corpus de reviews que no tenemos), se explotó data que ya
> estaba a la vista — `/movie/{id}/keywords`, que el proyecto nunca consumía
> usando solo los 19 `genre_ids` gruesos. `KEYWORD_TAG_MAP` (19 strings
> verificados → 10 tags), `fetch_keywords` calcado de `fetch_taste_credits`,
> entradas de `TAG_PHRASES`/`POSITIVE_HINTS`, y enganche en el loop de
> enriquecimiento (movies **y series**, que antes no recibían ninguno). Tres
> detalles no obvios: tope de 2 tags por título porque el scoring divide el
> match positivo por `len(tags)` y un tag sin match **diluye** el score; el
> `except TmdbError: continue` de credits pasó a `pass`/`else` porque son
> enriquecimientos independientes; y nunca mutar `item["tags"]` in place
> (`_clone_items` es copia shallow → contaminaría `_PERSONALIZED_CACHE`). Los
> dos tests críticos se validaron reintroduciendo los bugs a propósito. Hizo
> falta un commit extra (`8445e9d`) porque el enriquecimiento **moría en
> silencio**: 18 candidatos sin un solo tag y sin logs no se distinguía "map
> angosto" de "roto" — con el log agregado, veredicto en producción: funciona,
> 0 fallos en 20 candidatos, hit rate ~30%. Detalle largo en
> `docs/build-log.md` (entrada 2026-07-29).
>
> **2026-07-23 (sesión 3) — bugs post-feedback + refine del LLM, 4 commits
> (`0feed46`..`eb393be`), 213 tests:** Matías siguió probando en producción y
> salieron cosas, todas resueltas y deployadas (detalle en `docs/build-log.md`):
> - **Poster equivocado en onboarding:** "Toy Story" (1995) mostraba Toy
>   Story 5 — `search_title(title, year)` ahora fija el año
>   (`primary_release_year`) porque `results[0]` de TMDb ordena por
>   popularidad y devolvía el estreno de franquicia.
> - **Tilt 3D + glare** en los posters de la grilla "Sin cuenta" (faltaban).
> - **Default del wizard a Películas** en vez de Ambas.
> - **El refine del LLM caía SIEMPRE al heurístico en prod** (los 6 "why"
>   calcados "tira para el foco..."): NVIDIA devolvía JSON casi-válido de
>   forma intermitente (comillas sin escapar, trailing commas). Fix de raíz:
>   `response_format: {"type":"json_object"}` (medido 8/8 vs 4/6).
>   Diagnosticado con los logs de Render + repro contra la API real.
> - **Reintento + fallback de modelo:** nemotron → reintento →
>   `llama-3.1-70b` → reintento → heurístico. Cubre modelo puntual caído/con
>   basura y red; NO caída total ni rate limit de cuenta (misma key/host).
>
> **2026-07-23 (sesión 2) — feedback de amigos, 19/20 resueltos en 6 commits
> (`7512cf3`..`58f0715`):** el feedback juntado en sesión 1 (Gaspi, Pedro,
> Simón, Gerardo + notas propias, 20 puntos en
> `03 Iteration Logs/(C) 2026-07-23 feedback-amigos-pre-lanzamiento.md`) se
> redujo a 4 problemas de fondo y se atacó casi todo:
> - **Lote rápido** (1,4,5,6,12,13,19): CTA del home abre registro directo
>   (`/login?register=1`), contraste del badge del hero, "Sync con
>   Letterboxd" solo sin sesión, tooltip del toggle de tema, navbar sin
>   "Home" y en español, instrucción de cómo exportar el zip en el dropzone.
> - **`/recommend` rediseñado como wizard de 3 pasos** (3,8,9,10,11,17):
>   Tu historial → Qué ver → Formato, cada decisión explicada en contexto,
>   paso 2 bloqueado sin fuente válida, modos con descripción, recap +
>   `<details>` "¿cómo se calculan tus picks?" antes de generar, aviso
>   honesto del límite del modo manual, stepper clickeable hacia atrás.
> - **Grilla de resultados** (2): `lg:grid-cols-3`, 6 picks en 2 filas.
> - **Navbar estilo YouTube** (14,15): pill terracota "Recomendar" + avatar
>   con dropdown (Perfil, Archivo, tema, Salir); `useTheme` extraído.
> - **Perfil real** (16,20): `GET /profile/summary` nuevo (cuenta +
>   actividad + still de la mejor puntuada como avatar), header de
>   `/profile` con identidad y 4 stats; el mapa de afinidad pasó a sección.
> Todo verificado en el preview local y deployado. Detalle en
> `docs/build-log.md` (entrada 2026-07-23 sesión 2).
>
> **Status (histórico, pre-dominio — los tests y URLs de acá abajo están superados por la cabecera de arriba):** Activo, MVP deployeado, rediseño visual completo ("Hybrid critic notebook", ver `DESIGN.md` y `docs/mvp-status.md`) — frontend [pelipick.vercel.app](https://pelipick.vercel.app/), backend [pelipick-backend.onrender.com](https://pelipick-backend.onrender.com). 160 tests de backend. Cerrados los 3 pendientes de MVP que quedaban: reporte de filas descartadas del CSV base (`discarded_rows` en `/recommend/zip`, aunque el cartel al usuario se sacó el 2026-07-20, ver abajo), observabilidad mínima (`logging.basicConfig` + log INFO por recomendación completada), y mail real de recuperación de contraseña vía Resend (`backend/app/mailer.py`, campo `email` en `users`, flujo completo en el frontend con `ResetPassword.tsx`) — falta que Matías cree la cuenta de Resend y setee `RESEND_API_KEY` para que funcione en producción. Migrado el agente de IA de Gemini a NVIDIA NIM (`nvidia/nemotron-3-super-120b-a12b`, `chat_template_kwargs.enable_thinking=false`): Gemini tenía un modo "thinking" que no se podía desactivar (~20s por call) y forzaba una cadena de 4 modelos de fallback por cuota diaria; NVIDIA da un solo endpoint compatible con OpenAI, +100 modelos gratis con una key, y este modelo (familia Nemotron 3, más nueva que la Llama-Nemotron original) permite apagar el razonamiento vía un parámetro real de la API sin perder calidad de instruction-following.
>
> **2026-07-18 (sesión 2):** comparación con el prototipo visual de Lovable → se integró "current picks" en el home (última sesión real del usuario) y "catalog statistics" reales en el footer (`GET /catalog/stats`, no los números inventados del mock). Se arregló el mapa de afinidad, roto en producción por `datetime()` de SQLite corriendo contra Postgres (Neon) — sumado un exception handler global para que futuros 500 no manejados no se disfracen de "Failed to fetch". Fix de performance grande a pedido de Matías: pool de conexiones a Postgres + schema/migraciones corriendo una sola vez por proceso en vez de por request (login de ~8s a ~2.85s en producción, medido con curl), y paralelización con `ThreadPoolExecutor` de las llamadas a TMDb en el perfil de gusto (un import de 45 títulos nuevos de ~100s+ a ~11.6s). Detalle completo en `docs/build-log.md` (entrada 2026-07-18).
>
> **2026-07-20:** rediseño de `/recommend` comparando línea por línea contra la página real de Lovable (no solo el home): 6 picks en vez de 5, grilla a 2 columnas, animación de tilt 3D + glare en los posters al hover (hook compartido `useTiltCard.ts`, reusado en "Current picks" del home), línea "Dir. X • género" cuando se conoce el director. Reescrito `match_score`: de aditivo-y-clampeado (varios picks fuertes quedaban indistinguibles en 99%) a `50 + 49*tanh(puntos/40)` con evidencia proporcional a los tags del candidato. "↻ Nuevos picks" pasó a regenerar in-place en vez de volver al menú, lo que expuso un bug real (reproducido en logs: `picks=0`) — la exclusión de "ya recomendado antes" agotaba el pool y el backend devolvía una lista vacía con 200 OK que el frontend mostraba como "no pude leer la fuente" (mensaje falso); fix con reintento sin esa exclusión. Sacado el cartel de "N filas no se pudieron importar" (tenía además un bug de gramática): esas filas son logs sin rating en Letterboxd, uso normal, no un error. Detalle completo en `docs/build-log.md` (entrada 2026-07-20).

Detalle completo en `docs/mvp-status.md`.
