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
4. Tests de backend en verde antes de cerrar (294 tests a la fecha)
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

<!-- SESSION_STATE:START -->
## Estado actual
_Última actualización: 2026-08-05_

**Qué se hizo (2026-08-05 — sesión corta, un bug reportado con capturas de `/recommend`, sin commitear todavía):**

- Matías mandó capturas de `/recommend` (modo "Perfil completo") con picks de 82%/78% mezclados con **35%/40%/55%** en la misma tanda, más una palabra inventada por el LLM ("Zodiacomodoro") en un "why". Primero pensé que las capturas eran de `/weekly` (que sí es floor-free a propósito) — Matías corrigió: eran de `/recommend`, donde el piso de 60 sí es un invariante.
- **Causa real encontrada:** cuando "Nuevos picks" agota el pool nuevo y cae a `filled_with_old` (relleno con picks fuertes ya mostrados antes), el código llama a `llm_client.predict_fit` en vez de `refine_recommendations` — `predict_fit` es la misma función de `/weekly`, sin piso de score a propósito ahí. Además `refine_recommendations` (el camino normal) solo descartaba `match_score <= 50`, dejando pasar el hueco 51-59 (de ahí el 55%).
- **Fix:** un filtro único después de la llamada al LLM en `_finish_recommend` ([main.py:1147](backend/app/main.py:1147)) que descarta cualquier pick devuelto con `match_score < MIN_MATCH_SCORE`, cubre los dos caminos. Puede devolver menos de 6 picks si el LLM le baja el puntaje a varios — preferible a mostrar un match flojo disfrazado de fuerte.
- **"Zodiacomodoro"** no era un bug de renderizado (no hay highlighting en el frontend, era el find-in-page del navegador) — es una palabra inventada por el LLM (nemotron o el fallback llama). Se agregó una regla dura al `WRITING_RULES` compartido ([llm_client.py:198](backend/app/llm_client.py:198)) prohibiendo palabras pegadas/inventadas — mitiga, no elimina (comportamiento probabilístico, mismo patrón que el fix de "tenés chances de encantarte").
- Test nuevo `test_recommend_zip_filled_with_old_still_respects_match_floor` en `test_main.py` — verificado a mano que falla sin el fix (reproduce el escenario real: agota el pool con dos llamadas seguidas, mockea el LLM devolviendo 35%). 395 tests en verde.

**Dónde retomar:** Nada a medio hacer en el fix. Falta: (1) commitear (`CLAUDE.md`, `backend/app/llm_client.py`, `backend/app/main.py`, `backend/tests/test_main.py` están modificados sin stagear), (2) verificar el prompt nuevo contra la API real de NVIDIA como se hace siempre con cambios de prompt (los tests no atrapan "sigue inventando palabras"), (3) deployar y confirmar en producción que "Nuevos picks" repetido varias veces ya no mezcla scores bajos.

**Bloqueos / decisiones pendientes:** Ninguno técnico. Sigue pendiente lo de la sesión anterior: definir qué sumar a las 3 features "wow" (`TASKS.md`, `wow-features-2026-08-03`) antes de codearlas — Matías no lo tocó esta sesión.

**Contexto que no es obvio del código:**
- **`predict_fit` y `refine_recommendations` tienen semánticas de piso distintas a propósito** (`llm_client.py`): `predict_fit` nunca pierde un título porque `/weekly` necesita el set fijo completo aunque el match sea malo; `refine_recommendations` elige y puede descartar. Mezclarlas (usar `predict_fit` dentro de `/recommend` vía `filled_with_old`) fue lo que rompió el invariante de piso — el fix vive en `main.py`, no en `llm_client.py`, justamente para no tocar el comportamiento de `/weekly`.
- **`/recommend/sessions/{id}/refine`** (usado para el refine progresivo de una sesión ya mostrada, no activamente enganchado en el frontend hoy) también llama a `predict_fit` directo, sin el filtro nuevo — mismo hueco potencial, pero fuera de alcance porque no era lo reportado y ese endpoint depende a propósito de nunca perder un pick ya mostrado. Si en algún momento se vuelve a enganchar en el frontend, revisar si necesita el mismo piso.
- **La captura que mandó Matías tenía dos causas superpuestas**: el 55% venía del hueco 51-59 de `refine_recommendations` (camino normal), el 35%/40% del `predict_fit` sin piso (camino `filled_with_old`) — ambas se acumulan porque "Nuevos picks" clickeado varias veces agota el pool nuevo rápido con el catálogo real de TMDb.
- **Los tests de `test_main.py` corren desde la raíz del repo, no desde `backend/`** — `python -m pytest` (no `cd backend && pytest`), porque los imports son `from backend.app import ...`.
<!-- SESSION_STATE:END -->

<details>
<summary>Estado detallado anterior</summary>

> <!-- SESSION_STATE_ARCHIVE:START -->
> **Last updated:** 2026-07-31 (deploy, estrellas y renovación de picks) — se
> reparó el build que impedía desplegar `DisagreePanel`, se agregó CI real,
> los ratings pasaron a estrellas de 0.5 a 5, y `Nuevos picks` dejó de
> repetir títulos ya vistos. Estado final de esa sesión: commit `aad2436`,
> 306 tests. Cerró detectando el bug de match_score mezclado que esta sesión
> (2026-08-02) resolvió — ver "Estado actual" arriba.
>
> **Last updated:** 2026-07-31 (sesión larga, 14 commits `c0d0931`..`5b65581`,
> 263→294 tests: cuatro rondas de bugs de `/weekly` reportados desde
> producción, tres features pedidas, y al final la unificación grande — una
> sola voz de LLM y una sola interacción para todo el sitio + buscador global
> + rediseño del flujo de "no estoy de acuerdo")
>
> ### ⚠️ Dónde retomar
>
> **Nada bloqueante y nada a medio hacer.** Todo está commiteado, pusheado y
> deployándose. Lo que sigue es **que Matías pruebe en producción** (Render
> tarda unos minutos en redeployar) y reporte. Tres cosas concretas para
> mirar primero, en orden, porque son las que NO se pudieron verificar de
> verdad en local:
> 1. **La calidad de los "similares"** del flujo de votación. Se cambió
>    `/similar` por `/recommendations` de TMDb justamente porque para "The
>    Gentlemen" traía "Stuart Little" y "Around the World in 80 Days" — pero
>    la mejora solo se puede juzgar con la key real. Si sigue trayendo
>    cualquier cosa, el siguiente paso sería filtrar por género/tags contra
>    el título original en `tmdb_client.fetch_similar_titles`.
> 2. **El buscador de la navbar** (`/titles/search` + `/titles/{id}/verdict`)
>    — probado solo con `fetch` mockeado.
> 3. **El mix de variedad de épocas** en `/weekly` (3 trending + 2 de una
>    década que rota por semana ISO).
>
> ### Decisiones que quedaron abiertas para Matías (no son bugs)
>
> - **El buscador no existe en mobile**: `SearchBox` es `hidden sm:block`
>   porque la navbar no tiene lugar en pantallas chicas. Decisión consciente
>   para no romper el layout, no un olvido — si lo quiere en mobile hay que
>   resolver el patrón (¿ícono que abre un overlay?).
> - **El "why" en la card**: quedó visible en la home y en el archivo, pero
>   oculto en `/recommend` (donde se revela con el typewriter al abrir el
>   póster, decisión del 2026-07-30). NO se unificó a propósito: la sección
>   semanal de la home está construida alrededor de mostrarlo y sacarlo la
>   vaciaría bastante. Si quiere que sea igual en los tres lados es un
>   cambio chico, pero es su llamada.
> - El ratio 3/2 y las décadas de la variedad de épocas
>   (`tmdb_client.WEEKLY_CLASSIC_DECADES`).
> - El desempate de match_score por `vote_average` (`_adjust_match_scores`
>   en `main.py`) es pragmático, no una reescritura del scoring — el
>   vocabulario de tags sigue siendo chico de fondo. Si vuelve a verse
>   plano, ese es el lugar para ajustar el multiplicador (`* 3`).
>
> **Qué se hizo el 2026-07-31, quinta ronda — rediseño del "no estoy de
> acuerdo"** (1 commit, `5b65581`, 293→294 tests):
> - Matías mandó captura del flujo viejo: una lista plana de 6 títulos con
>   tres botones cada uno, **sin opción de "no la vi"** (un título que no
>   viste te trababa) y sin avanzar sola. Pidió un cuadro chico que se abra
>   desde el botón, con el póster, que pregunte primero si la viste y recién
>   después qué te pareció, y **6 votos de 6 películas distintas** para
>   recalcular.
> - `DisagreePanel` (en `MovieModal.tsx`) hace exactamente eso: una peli por
>   vez con su póster, dos pasos, contador de progreso. "No la vi" saltea
>   **sin contar como voto**. Al sexto llama a `GET /titles/{id}/verdict` y
>   el resultado pisa lo que muestra el modal (estado local `recalculated`,
>   así no hay que tocar los 4 lugares que abren el modal).
> - **Problema de fondo del mismo flujo, arreglado de paso:** los similares
>   salían de `/similar` de TMDb, que matchea por keywords/géneros sueltos y
>   devuelve cualquier cosa — votar "Stuart Little" para calibrar "The
>   Gentlemen" no aporta nada, o sea que los 6 votos hubieran sido inútiles
>   aunque la UI fuera perfecta. Ahora usa `/recommendations` (sale del
>   comportamiento real de usuarios de TMDb), con `/similar` de fallback si
>   viene vacío. `SIMILAR_TITLES_LIMIT` 6→20 para tener margen para salteos.
> - Si se queda sin títulos antes de los 6, avisa y ofrece recalcular con
>   los que juntó en vez de trabarse.
>
> **Qué se hizo el 2026-07-31, cuarta ronda — la unificación** (2 commits,
> `81f589b`+`4c52f1e`, 285→293 tests). Pedido de Matías: *"TODA la página
> debería tener el mismo sistema de LLM, con los mismos prompts y los mismos
> tonos... la idea es que siempre sea lo mismo no importa dónde estés. Con la
> interacción también"* + un buscador global:
> - **Una sola voz de LLM**: `AGENT_VOICE` + `WRITING_RULES` + `SCORE_RULE`
>   son constantes compartidas que arman los dos prompts. Lo único que cambia
>   entre pantallas es la TAREA (elegir de un pool en `/recommend` vs opinar
>   sobre títulos ya elegidos en `/weekly` y el buscador). Hay un test que
>   falla si un prompt deja de compartir la voz. Renombrado todo lo que era
>   weekly-específico pero ya no lo es: `predict_weekly_fit`→`predict_fit`,
>   `_build_weekly_prompt`→`_build_verdict_prompt`, `_WEEKLY_PREDICTION_CACHE`
>   →`_VERDICT_CACHE`, `_differentiate_weekly_match_scores`→`_adjust_match_scores`.
> - **Una sola interacción**: el póster interactivo estaba copiado en tres
>   lugares y se había desincronizado — **History no tenía tilt, ni glare, ni
>   era clickeable** (no había forma de abrir el modal desde el archivo), y
>   **Home nunca pasaba `seenWhys`**, así que el typewriter no corría ahí.
>   Ahora todo sale de `PosterCard` (`frontend/src/components/PosterCard.tsx`);
>   cada pantalla pasa su bloque de texto como children.
> - **Buscador global** (`SearchBox` en la navbar, arriba a la derecha):
>   cualquier peli o serie, debounce 300ms. Backend nuevo:
>   `tmdb_client.search_any_titles()` contra `/search/multi` (el
>   `search_titles` viejo es movies-only, correcto para la lista semilla del
>   onboarding), `GET /titles/search` (degrada a lista vacía ante cualquier
>   error de TMDb: un 502 rompería la navbar en cada tecla) y
>   `GET /titles/{id}/verdict`, que corre **la misma tubería que `/weekly`**
>   paso por paso para que el número y el tono sean idénticos a los del resto
>   del sitio (incluye el mismo trato de "ya la viste").
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
> - Verificación de la cuarta ronda (2026-07-31): 293 tests + typecheck
>   limpio + probado a mano en el dev server local. El buscador se probó
>   con `window.fetch` mockeado en el browser (la TMDb key local sigue
>   vieja): devolvió película y serie, y al clickear abrió el modal con
>   veredicto real. El typewriter se verificó **midiendo el largo del
>   texto en el tiempo** en vez de a ojo: History 6→12→17→23→28 chars y
>   Home 5→11→17→22→28, o sea que efectivamente anima en las dos
>   pantallas donde antes no lo hacía. Sin errores de consola.
> - **El prompt del LLM se probó contra la API real de NVIDIA** (que sí
>   anda local, a diferencia de TMDb), dos corridas seguidas, antes de
>   commitear el fix de los why calcados. Ese es el camino para validar
>   cambios de prompt en este proyecto: `_build_verdict_prompt` +
>   `_call_nvidia_with_fallback` con un perfil de prueba, y leer la
>   salida. Los tests no pueden atrapar "suena repetitivo".
> - Verificación de la quinta ronda (2026-07-31): 294 tests + typecheck
>   limpio. El flujo de votación se probó con `fetch` mockeado midiendo el
>   estado paso a paso: dos "No la vi" dejaron el contador en **0/6**
>   (confirmando que saltear no cuenta como voto), los seis votos
>   siguientes lo llevaron a 6/6 puntuando **seis títulos distintos**, y al
>   sexto el modal pasó de 60% a **91%** con el why recalculado — o sea que
>   el recálculo llega de verdad a la pantalla, no solo se dispara.
> - **Truco útil para probar el modal en local:** el botón "¿No estás de
>   acuerdo?" solo aparece si `rec.tmdb_id != null`, y el catálogo mock que
>   usa `/recommend` sin TMDb key **no trae `tmdb_id`** — así que desde
>   `/history` o `/recommend` nunca se ve. Para probarlo hay que entrar por
>   el buscador de la navbar, que sí devuelve `tmdb_id`.
> <!-- SESSION_STATE_ARCHIVE:END -->

</details>

## Historial de sesiones

### 2026-08-05 — piso de match roto en "Nuevos picks", y una palabra inventada por el LLM
Matías mandó capturas de `/recommend` con 35%/40%/55% mezclados con 78%/82% y un
"why" con una palabra inventada ("Zodiacomodoro"). Al principio asumí que las
capturas eran de `/weekly` (floor-free a propósito) — se equivocó mi lectura,
Matías corrigió que eran de `/recommend`, donde el piso de 60 sí es un
invariante. La causa real: cuando "Nuevos picks" agota el pool nuevo y cae a
`filled_with_old`, el código usa `predict_fit` (la función floor-free de
`/weekly`) en vez de `refine_recommendations`, y de paso `refine_recommendations`
tampoco reforzaba el piso real (solo descartaba `<=50`, dejando pasar 51-59).
Un filtro único después del LLM en `_finish_recommend` cierra los dos caminos.
La palabra inventada no era un bug de renderizado (sin highlighting en el
frontend, era el find-in-page del navegador) — se le agregó una regla al
prompt compartido contra palabras pegadas, mitigación probabilística, no
garantía. Test nuevo verificado a mano fallando sin el fix. 395 tests en
verde, **sin commitear todavía** — queda para la próxima sesión.

### 2026-08-03 — se vació el board, y después el feedback en vivo reescribió medio trabajo
Arranqué cerrando lo que quedaba anotado: el techo de 86% (la causa real era
que los parámetros de `discover` de TMDb se combinan con AND, así que pedir
género + persona juntos devolvía un pool sin las películas obvias del
director), el sesgo anime/coreano de la muestra de vibras, el recompute a
background, el badge de picks heurísticos. Después construí lo que estaba
propuesto hace tiempo y nunca hecho: la sección de "puntuar más" y dos juegos.

Ahí la sesión cambió de forma. Matías los probó y **no le gustaron**, y de
paso encontró un bug serio que yo no había pensado: el juego de comparar
películas te marcaba como **vista y gustada** cualquiera que votaras, aunque
nunca la hubieras visto. Lo llamó "grave error" y tenía razón — es fabricar
datos del usuario. No lo parcheé: lo rediseñé de raíz para que compare solo
cosas que ya viste y puntuaste igual, y que elegir un ganador no escriba
ningún rating. Lo mismo con la trivia (ahora pregunta sobre lo que viste) y
con "puntuar más", que se comió tres reportes más — salían casi solo series,
las tandas cortaban el flujo, y con historial grande se llegaba a un muro sin
salida ("esto no puede pasar"). Ese último era el más interesante: escaneaba
siempre desde la página 1 de TMDb confiando en la exclusión, así que al
agotar las primeras páginas no había forma de avanzar nunca más.

Cerró con `/weekly`: Matías notó que la home "se queda unos segundos y de la
nada aparece". Medí en vez de suponer — 7,3s reales contra la API de NVIDIA,
porque el veredicto del LLM corría sincrónico y bloqueaba la respuesta. Ahora
responde el heurístico al toque y refina en background con polling silencioso.
Verificado end-to-end contra NVIDIA real: ~12ms por request, el veredicto
personalizado entra a los ~8,5s.

Al final propuse tres features "para asombrarse" (mapa de embeddings, "Tu año
en Butaca", chat con tu perfil); le gustaron las tres pero quiere sumarles
cosas antes de arrancar. 17 commits `c60f70c`..`d09f734`, 345 → 376 tests.

### 2026-08-02 (sesión 3) — Fase 4 cerrada: vibes por clustering real, en producción
Retomé donde lo dejó Codex. El error que había quedado sin capturar era cuota
de Gemini, con una causa que no se veía a escala chica: el free tier cuenta
cada texto de un `batchEmbedContents` como un request, así que un batch de 100
gasta la ventana entera y la muestra no entra en un día. Matías preguntó si
NVIDIA no tenía algo que sirviera y resultó ser mejor — medí la calidad de los
dos sobre los mismos 650 títulos antes de cambiar (empate) y decidí por lo
operativo: 940 embeddings en una pasada contra una pared de 1.000 por día.
Verificar con datos reales encontró 6 bugs que los tests no podían ver, el más
serio sin relación con vibras: **el pool de Neon servía conexiones que el
servidor ya había cerrado**, algo que afecta producción entera y es el mejor
candidato para el "Load failed" de Bauti que estaba sin diagnosticar. Cerró
con 39 movimientos vivos en butaca.xyz ("Cine mudo romántico", "Cine negro
francés", "Cine de la Resistencia", "Romance con chaebol"), 345 tests, CI
verde y deploy live. Matías fue reportando cosas al final que quedaron
anotadas como tasks en vez de implementadas, por decisión suya: el techo de
86% del match_score, el why heurístico de relleno, el sesgo anime/coreano de
la muestra, y dos features nuevas (sección de "qué películas vi" con swipe, y
juegos dentro del sitio). Commits `fc3b2e3`..`0c71a9d`.

### 2026-08-02 — piso de match real en /recommend
Retomé el bug que Matías detectó al cerrar la sesión anterior (picks de 88%
mezclados con 45%, 55%, 60% y S/D). Causa raíz en `recommender.recommend()`:
no había piso de score a propósito, así que si el pool elegible no llegaba a
6, se rellenaba con lo que hubiera. Con Matías definimos el piso real en 60
(no solo descartar ≤50) y que, si eso deja el pool corto, primero se pide un
pool más grande a TMDb antes de resignarse a mostrar menos de 6 — nunca se
rellena con lo flojo. `/weekly` y el veredicto de un título buscado quedan
afuera del piso a propósito: ahí no hay pool del que elegir. 308 tests (33
nuevos/reescritos, sin cambios de frontend). Antes de esto, Codex había
dejado el bug diagnosticado y documentado en `TASKS.md` pero sin tocar
código — ver commit `3f5fac0`.

### 2026-08-02 (sesión 2) — picker "a tu elección" + vibras estilo Flick
Matías me contó de un video sobre Flick (app que categoriza pelis por
"vibes" con embeddings) y pidió meter esa idea en Butaca, arrancando por
ampliar el picker de género. Investigué el video a fondo (pidió el
transcript completo) antes de diseñar nada: Flick corre DOS sistemas
separados — metadata→embeddings→Leiden da categorías históricas/de
movimiento de cine, pero las vibes "de verdad" (MindBender, Feel-Good)
salen de clusterizar reseñas de usuarios, algo que Butaca no puede replicar
(68 títulos con reseña real en toda la base). Con Matías acordamos un mix:
Sistema 1 real (embeddings+Leiden, pieza grande, quedó documentada para
Codex en `docs/(C) plan-fase4-vibes-embeddings.md`) más vibras curadas a
mano con keywords de TMDb como proxy honesto (Fase 3, ya hecha). De paso
rediseñé el picker de género completo (`GENRE_OPTIONS` estático de 7 →
`PICK_OPTIONS` de 26 con fetch dirigido a TMDb por opción) porque la
arquitectura vieja post-filtraba un pool ajeno y nunca iba a servir para
opciones angostas — encontré 2 bugs reales de scoring en el camino (piso
de 60 que un solo tag nunca cruzaba, cobertura no determinística). Verifiqué
la `GEMINI_API_KEY` nueva de Matías con requests reales (embedding y
batchEmbedContents confirmados) antes de dejarlo documentado. 320 tests,
frontend probado a mano en el browser. Commit `5af2817`.

### 2026-07-31 — deploy, estrellas y renovación de picks
Se destrabó el deploy roto por TypeScript, se agregó CI y se verificó el nuevo `DisagreePanel`. Después se reemplazaron los tres ratings por estrellas de 0.5 a 5 y se corrigieron persistencia/edición, precedencia de Letterboxd y repetición de `Nuevos picks`. Todo terminó desplegado con 306 tests, build y CI verdes. Al cerrar, Matías detectó el siguiente bug prioritario: `/recommend` mezcla picks fuertes con 45%, 55%, 60% y S/D; la próxima sesión arranca diagnosticando el ranking para devolver solo recomendaciones realmente fuertes.
>
> **2026-07-31 (sesión 5) — 1 commit (`5b65581`), 293→294 tests:** Matías
> probó el buscador (anda bien) y mandó captura del flujo de "no estoy de
> acuerdo": no le gustaba la presentación ni que faltara "no la vi", y pidió
> un cuadro chico con el póster, dos pasos (¿la viste? → ¿qué te pareció?) y
> 6 votos de 6 películas distintas para recalcular. Hecho con
> `DisagreePanel`. De paso salió un problema de fondo: los similares venían
> de `/similar` de TMDb y eran basura ("Stuart Little" para "The
> Gentlemen"), así que los 6 votos no hubieran servido — se cambió a
> `/recommendations`. Verificado con mocks: 60% → 91% tras los 6 votos.
>
> **2026-07-31 (sesión 4) — 3 commits (`b16013b`, `81f589b`, `4c52f1e`),
> 284→293 tests:** Matías señaló que los why salían calcados entre sí y
> abusaban de "encantar" ("tenés chances de encantarte" ni siquiera es
> español) — la causa eran las frases de EJEMPLO del prompt, que el modelo
> copiaba como plantilla; se reemplazaron por reglas de escritura y se
> verificó contra la API real de NVIDIA. Después pidió la unificación
> grande: misma voz de LLM y misma interacción en todo el sitio, más un
> buscador global. Se extrajeron `AGENT_VOICE`/`WRITING_RULES`/`SCORE_RULE`
> compartidos, se unificó el póster en `PosterCard` (History no era ni
> clickeable, Home no tenía typewriter) y se sumó el buscador de la navbar
> con `GET /titles/search` + `GET /titles/{id}/verdict`, que corre la misma
> tubería que `/weekly`. Ver "Leer primero al retomar" por los dos puntos
> de diseño que quedaron deliberadamente sin unificar.
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
