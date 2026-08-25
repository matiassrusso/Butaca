# (C) Backlog de pulido para el launch de LinkedIn — 2026-08-23

Registro vivo de la sesión. Se va actualizando a medida que avanzo, por si se corta el contexto.

## Contexto
Matías se prepara para publicar Butaca en LinkedIn. Quiere todo pulido. Fue reportando cosas en vivo (rápido, varias a la vez). Este archivo captura TODO lo pedido, el estado, y dónde retomar.

## Commits de la sesión (origin/main)
- `e8abf1c` OG preview + ocultar badge heurístico a visitantes sin sesión
- `7907252` mapa frontend: territorios, series vs pelis, anti-colisión labels, zoom/pan, buscador
- `26e898f` mapa backend: más títulos (764→1200) + mejores labels (seed ampliado, sampling coseno)
- `98f1d3e` fix recommend: conservar why del LLM (piso sobre score del motor, no el del LLM)
- `<hist>` feat history: ordenar bitácora por rating/título/cuándo/dónde (Codex)
- `1c852ed` chore: ocultar el mapa del launch (navbar + home) hasta rehacerlo

## Estado por ítem

### ✅ HECHO y deployado
1. **OG tags + imagen de preview** para LinkedIn (`frontend/index.html` + `frontend/public/og.png`).
2. **Badge HEURÍSTICO oculto para visitantes sin sesión** (`PosterCard.tsx`, gate `showScore`).
3. **Mapa v1** (frontend + backend): territorios, series=cuadrados/pelis=círculos, filtro, buscador, zoom/pan, anti-colisión labels; 1200 títulos, 63 movimientos, labels específicos. **PERO Matías lo rechazó** (ver #4 abajo).
4. **Fix heurístico 4/6** (`98f1d3e`): el piso de match ahora se aplica sobre el score del MOTOR, no sobre el score transitorio del LLM → se conserva el "why" del LLM en todos los picks flooreados >=60. Confirmado con logs de prod (`Match floor dropped 4 pick(s) below 60`). Deployándose.

### 🔴 URGENTE — decisión de diseño pendiente
5. **Rediseño del mapa.** Matías: "no se entiende qué categoriza ni dónde. Marvel separado de sci-fi (ambas ficción). Solo 6 regiones, ¿dónde están TODAS las categorías? Quiero las categorías principales/básicas arriba, y a medida que zoomeás que aparezcan sub-categorías nuevas. No me gusta nada como está."
   - **Causa raíz honesta:** es clustering NO supervisado (Leiden sobre embeddings), por eso agrupa "Marvel" junto (reparto/estilo compartido) en vez de una taxonomía de géneros limpia. El pitch actual ("nadie escribió las categorías a mano") choca con lo que Matías quiere (taxonomía de géneros reconocibles con drill-down).
   - **Dirección propuesta (a confirmar):** anclar el nivel TOP a géneros reales (los principales), y usar los clusters de embeddings solo para las SUB-categorías que aparecen al zoomear (zoom semántico). Cambia el relato del mapa → confirmar con Matías antes de construir.
   - Requiere: backend (clusterizar DENTRO de cada género en vez de dejar que Leiden decida el top) + frontend (zoom semántico: labels de género arriba, sub-movimientos al acercar).

### 🔴 Chat "gurú" — decisión de diseño pendiente
6. **Chat mucho más inteligente.** Matías: "no sabe responder cosas simples que debería. Ej: ¿tiene escenas de sexo? no sabe o dice mal. Debería ser un gurú/sabio de todas las películas: qué ver, detalles, datos curiosos, discutir, todo."
   - **Constraint honesto:** un LLM solo ALUCINA datos factuales de contenido (sexo/violencia). "¿tiene escenas de sexo?" confiable necesita una fuente: TMDb keywords/certification (limitado), o guía de contenido tipo IMDb parents guide/Common Sense (no gratis/fácil), o aceptar respuesta del LLM con disclaimer.
   - Hoy el chat está anclado SOLO al perfil de gusto del usuario. Matías quiere ampliarlo a experto de cine general.
   - Requiere decisión: fuente de datos de contenido + modelo/prompt + alcance.

### 🟡 Features claras (delegar a Codex / hacer)
7. **Reseñas de Letterboxd en el perfil** (feature #1 original). Mostrar, junto a las estrellas, la reseña que el usuario escribió. **La infra YA EXISTE**: `rated_items.review` (columna), import de Letterboxd la captura (`letterboxd_zip.py` prefiere `reviews.csv`), y `/history` ya tiene un toggle "Tu reseña". Falta: exponerla también en el PERFIL (`/profile`) junto al rating.
8. **Escribir reseñas en Butaca** (feature #2 original). Que cualquier usuario, además de puntuar, escriba una reseña. Reusar la columna `rated_items.review`. Falta: endpoint de escritura (o extender `/profile/rate`) + UI en el modal/rate para escribir/editar la reseña + mostrarla.
9. **Ordenar la bitácora** (`/history`) por la columna que quieras: rating, título, cuándo la viste, dónde la viste. Frontend, `History.tsx` + traducciones. → **DELEGADO A CODEX** (ver abajo).
10. **Reseñas/feedback de usuarios sobre Butaca → que le lleguen a Matías.** Nueva feature: que la gente pueda opinar de Butaca y Matías reciba ese feedback. Requiere: tabla + endpoint POST + forma de que Matías lo lea (admin endpoint o mail vía Resend) + UI (form).

## Notas técnicas (no obvias)
- **RENDER_API_KEY** en env de usuario. Service `srv-d9cnhqu1a83c739eono0`, owner `tea-d9cml0pkh4rs73d0k20g`. Se leen logs de prod y estado de deploys.
- **BUTACA_ADMIN_TOKEN** (para recompute del mapa): Matías lo compartió esta sesión. Endpoint `POST /admin/vibes/recompute` (background ~1-3min) + `/admin/vibes/recompute/status`. El recompute corre sobre el CÓDIGO YA DEPLOYADO, así que cambios de seed hay que deployarlos ANTES de recomputar.
- **TMDb key local vieja (401)** → local degrada a mock. Verificación real: contra prod o con mocks.
- **Verificación de frontend del mapa en local:** el mapa local está vacío (no hay clustering en SQLite local). Se levantó un mock server en :8001 sirviendo `/vibes/map` real, y el dev server (`butaca-frontend`, puerto 4173) consume eso. (Murió con el reinicio; rearmar si hace falta.)
- **Tests:** `python -m pytest backend/` desde la raíz (506 verdes). Frontend typecheck real: `npm run build`.
- **`refine_recommendations` vs `predict_fit`:** refine = selecciona+explica de un pool (puede vetar por score<=50); predict_fit = explica un set fijo. El match_score MOSTRADO en /recommend es SIEMPRE el del motor (estable), el del LLM solo se usaba para vetar.

## Decisiones tomadas (2026-08-23)
- **Mapa (#5):** SACADO del launch (hecho, `1c852ed`). Rediseño urgente pendiente: **géneros principales arriba**, y al **zoomear aparecen sub-categorías** (ej: entre sci-fi y acción → "superhéroes"). Estilo taxonomía con drill-down semántico, más pulido. La ruta `/map` sigue viva para trabajarla.
- **Chat (#6):** LLM experto + **datos reales de TMDb** (keywords/certificación) + **sumar una fuente dedicada de guía de contenido** (para sexo/violencia confiable). Pendiente de build.

## Estado actualizado
- ✅ Heurístico 4/6 (`98f1d3e`, deployado)
- ✅ Ordenar bitácora (Codex, deployado)
- ✅ Mapa oculto del launch (`1c852ed`, deployado)
- ✅ **Reseñas** (#7 + #8) — Codex, revisado y deployado (`8ea91c3`): review en perfil (sección de ratings + toggle) + textarea para escribir en el MovieModal (prefillea la existente, desactivada para imports de Letterboxd). Backend: `RateTitleRequest.review`, `/profile/rate` la guarda sin pisar imports, `/profile/summary` y `movie_details` la devuelven.
- ✅ **Feedback de usuarios → Matías** (#10) — Codex (murió por límite de sesión pero alcanzó a terminar), revisado y deployado (`06dbf10`): tabla `site_feedback`, `POST /site-feedback` (anónimo/logueado, rate-limit 5/día por user/IP), `GET /admin/site-feedback` (gateado por token), aviso por mail opcional (Resend) si está `BUTACA_FEEDBACK_EMAIL`. Front: página `/feedback` + link en el footer, ES/EN.
  - ⚠️ PENDIENTE DE MATÍAS: setear `BUTACA_FEEDBACK_EMAIL` en Render si querés que te llegue por mail (si no, lo leés en `GET /admin/site-feedback` con el `BUTACA_ADMIN_TOKEN`).
- ✅ **Ripple de reseñas** completado (`06dbf10`): VibesMap + SearchBox también mandan `review` en onRate (el commit de reseñas se los había salteado).
- ❌ **Research chat gurú** (#6): el Codex read-only (task `task-mt63ct1o`) probablemente murió con el límite de sesión, no devolvió plan. RE-CORRER cuando se encare el build del chat.
- 🔜 Pendientes sin arrancar: **rediseño del mapa** (#5, géneros + zoom a sub-categorías), **chat gurú** (#6, re-research + build).

## 2026-08-24 (noche) — auditoría autónoma total (Matías durmiendo)
Matías pidió: auditar TODA la web/código/backend, probar todas las funciones, arreglar todo lo posible, autónomo, usando agentes/Codex. Skills sugeridas: superpowers (metodología brainstorm→worktrees→plan→subagents→TDD→review; la adopto, NO instalo plugin overnight) y herdr (runtime tmux-para-agentes; descartada: needs curl|sh install, macOS/Linux, no aplica a auditar — el harness ya persiste el trabajo).

**Estado base:** mapa v2 + chat gurú mergeados/deployados (`89a754a`, live), mail seteado, 514 tests. Recompute del mapa corrió: `seeded=1201, l2_clusters=11, genres=23`.

**Estrategia (paceada para no re-tocar el límite de USO de Claude que mató a los 6 auditores):** el fan-out pesado de auditoría va por **Codex** (quota separada de OpenAI, no toca el límite de Claude), escribiendo hallazgos a archivos en `scratchpad/audit/`. Claude (main) queda liviano: orquesta, verifica en browser, consolida y arregla. Fixes independientes → Codex en worktrees, tests verdes, merge con review.

**Plan por fases:**
- Fase 1 — Auditoría (Codex, read-only, a archivos) + verificación visual del mapa (Claude browser).
- Fase 2 — Consolidar + triage (Claude): rankear por severidad, decidir fixes.
- Fase 3 — Arreglar todo (Claude + Codex en worktrees), tests verdes, deploy.
- Fase 4 — Reporte final para Matías.

**Hallazgos ya confirmados:**
- ✅ **FIX (alto): borrado de cuenta roto.** `delete_user_completely` (db.py) NO borraba 4 tablas con FK a users: `pairwise_preferences`, `swipe_asked_titles`, `swipe_pool_cursor`, `site_feedback` → en Postgres (prod) el `DELETE FROM users` falla por FK y el usuario no puede borrar su cuenta. Pre-existente para swipe/pairwise; site_feedback es de hoy. Arreglado + test extendido (`test_delete_account_wipes_user_and_all_their_rows` ahora siembra las 4 y chequea 0 huérfanos). 3 tests verdes.
- ⚠️ **Baja/pre-existente: `get_watched_items` dedup por título** (sin kind/tmdb_id) → un film y una serie con el mismo título colapsan en uno. Raro. Anotado, baja prioridad.
- ❌ **REFUTADO:** el lead "grounding del chat sin tests" era falso — existen `test_chat_injects_real_tmdb_grounding...`, `test_chat_without_a_title...`, `test_fetch_certification_*`.
- 🟡 **Mapa a tunear (verificado visual en prod, /map):** el concepto FUNCIONA (géneros reales top-level, movimientos como sub-categorías, copy on-message). 3 issues de pulido para Fase 3:
  1. **Géneros fragmentados por split movie/TV:** se ven "ACCIÓN" y "ACCIÓN Y AVENTURA" (TV 10759), "CIENCIA FICCIÓN" y "CIENCIA FICCIÓN Y FANTASÍA" (TV 10765) como territorios separados. Unificar ids TV → nombre canónico movie en vibes_clustering (10759→Acción, 10765→Ciencia ficción, 10768→Bélica, 10762→Familia, etc.).
  2. **Solo 11 movimientos L2** (v1 ~63), granularidad despareja, y "NEO-NOIR" aparece 2 veces (dos clusters, mismo label del LLM). Subir resolución de `_cluster_l2` (1.6 → probar ~4-6) para ~40-60 movimientos; deduplicar labels repetidos.
  3. **Géneros minúsculos** como territorio top-level (TELENOVELA=1, HISTORIA=3, MÚSICA=6, WESTERN=6) — filtrar por tamaño mínimo o foldear en Otros.
  Requiere editar vibes_clustering.py (esperar que termine el audit llm-tmdb-map que lo está leyendo) + re-deploy + re-recompute en prod.

## Hallazgos de auditoría (2026-08-24 noche) — consolidando
Raw completo en `scratchpad/audit/*.md`. Triage y decisión abajo. (Auditoría db-auth-security COMPLETA; backend-core/llm-tmdb-map/frontend en curso.)

### DB / Auth / Seguridad (Codex, completa; verificó que el fix de borrado de cuenta quedó completo)
- 🔴 **CONFIRMADO [ALTO] — account takeover por Google OAuth** (main.py:838-841): `/auth/google` linkea a cualquier cuenta local con ese email SIN chequear `email_verified`. Attacker pre-registra local con el mail de la víctima; la víctima entra por Google y cae en la cuenta del attacker. **FIX decidido (limpio, bajo riesgo):** linkear por email solo si `existing["email_verified"]`; si no, crear cuenta nueva. Aplicar en el pase consolidado de main.py.
- ⏸️ **[MEDIO] hardening de auth/abuse** (aplicar los seguros, flaggear los delicados — no hacer cirugía de auth a ciegas en un producto que se lanza):
  - forgot-password sin rate limit (spam de mails/invalidar token) — additivo, fixeable.
  - lockout de login global por username → 3 requests anónimos bloquean a un user 15min (DoS) — delicado, evaluar.
  - rate limit de /chat y /site-feedback en memoria (se resetea, no compartido) + `request.client.host` no confiable en Render (falta `--forwarded-allow-ips`) — persistir contador + config de proxy.
  - cupo diario de /recommend: COUNT antes del trabajo, registra al final → race que excede el tope — reserva atómica.
  - init de schema no idempotente + `_ensure_schema_ready` fuera de try/finally → posible 500 en cold-start + fuga de conexión del pool (10 máx Neon). Importante, riesgo medio al tocar.
  - reset de password en 4 transacciones separadas → reuso de token/estado parcial.
  - register/guest sin rate limit ni challenge → flood.
  - 🟢 [BAJO] `server_header` de uvicorn + faltan headers de hardening (HSTS/nosniff/referrer) — trivial, seguro.
- ✅ Verificado OK por el audit: sin SQLi, tokens hasheados (SHA-256) + compare_digest, /admin/* gateados, CORS allowlist, mails escapados.

### Backend core / motor / endpoints (Codex, completa; raw en scratchpad/audit/backend-core.md — ~25 hallazgos)
- 🟢 **FIX now (bugs claros, seguros):**
  - [alto] `catalog_stats()` usa `lang` sin declararlo (main.py:388) → 500/NameError en vez de 503 cuando TMDb no configurado (latente: prod tiene TMDb). Agregar `lang: str = Depends(errors.request_lang)`.
  - [alto] refine progresivo `/recommend/sessions/{id}/refine` (main.py:2403-2448) devuelve el score del LLM, no restaura el del motor → el badge cambia entre render rápido y refinado (rompe el invariante de score estable). Restaurar engine score por id/título, guardar solo el why. (Mismo tipo que el fix de `_finish_recommend`.)
  - [alto] `_finish_recommend` persiste ratings ANTES de validar genres/opciones (main.py:1315-1378) → un 400 igual muta historial/perfil. Validar antes de escribir.
  - [alto] zip-bomb: el tope de 20MB mide comprimido; el parser descomprime todo (main.py:1761 + letterboxd_zip.py) → RAM exhaustion en endpoint público. Chequear `ZipInfo.file_size` sumado + nº de filas antes de leer.
  - [alto] `_collect_preference_tags` (recommender.py:410-422) suma tags/pistas SIN mirar el rating → una peli MAL puntuada promueve sus géneros como gusto; reseña negativa con "action" cuenta como positivo. Bug de CALIDAD de recomendación. Derivar señal positiva solo de ratings positivos. (Verificar el flujo antes de tocar — Matías prioriza calidad.)
  - [bajo/medio, seguros] validar `kind` (movie|series) en /movies/{id}/details, /similar, /titles/swipe-batch (hoy caen a movie/tv silenciosamente → 400).
- 🟡 **Añadir caps generosos (models.py):** max_length/max_items en RatedItem.title/review/tags, mood, ratings, RateTitleRequest.review, SiteFeedbackRequest.email (validar formato) — additivo, seguro si generoso.
- ⏸️ **DOCUMENTAR (delicado/mayor, NO cirugía a ciegas):** reserva atómica de cupo diario + bypass por /recommend/together ephemeral + refine sin límite (quota abuse); `rated_items` sin columna `kind` (serie resuelta como movie — schema+migración+consumidores); tags de Letterboxd nunca persistidos (se pierden tras el import); sin upsert/dedup en import (reimport infla DB); paginación en history/summary/admin-feedback; legacy `/recommend` público sin auth/límites; together no aplica exclusiones del usuario actual.

### LLM / TMDb / Mapa (Codex, completa; raw en scratchpad/audit/llm-tmdb-map.md) — bugs en código de HOY
- Chat grounding agarra título equivocado en remakes (ignora el year) → datos de otra peli. Chat afirma "no la viste" en falso con historial >40. Sin grounding, no avisa que no tiene datos verificados. `_REFINE_CACHE`/link LLM→candidato colisionan movie/serie por id/título. Parser LLM deja escapar TypeError→500 en vez de fallback. `fetch_title_by_id` cachea errores transitorios como "no existe" 24h. **Resolución L2 medida: 5.5→47, 6.0→48 movimientos** (1.6 daba 11). Recompute thread deja estado colgado si falla raro. Todos en el spec de fixes.

### FIXES EN PROGRESO (2 ramas, Codex, en paralelo — quota OpenAI)
- **`fix/frontend-audit`** (worktree butaca-wt/chat, task bcq604ldu): arregla los ~40 hallazgos de frontend (flujos rotos: forgot-password response.ok, /recommend/options y /onboarding/titles que tragan errores, mapa sin puntos visibles/zoom táctil; fugas i18n ES/EN; a11y; layout-shift). Skip: code-splitting.
- **`fix/backend-audit`** (worktree butaca-wt/map, task b5usc39mb): spec en scratchpad/spec-backend-fixes.md. Arregla: OAuth takeover (link solo si email_verified), catalog_stats lang, refine restaura engine score, _finish_recommend valida antes de escribir, zip-bomb, kind validation, preference-tags por rating, robustez parser LLM, cache movie/serie, fetch_title_by_id negativos solo 404 + overview tags, **mapa: resolución 5.5 + unificar géneros movie/TV + foldear minúsculos**, recompute thread catch Exception, caps en models, limpiezas. NO toca (documentado, delicado): reserva atómica de cupo/quota, columna kind en rated_items, persistir tags Letterboxd, paginación, ids estables vibe-l2, rate limits de auth, doble llamada LLM del chat.

### RESULTADO (cerrado esta noche) ✅
- Ambas ramas revisadas por mí (con cuidado en OAuth/recommender/chat), mergeadas a main sin conflicto (`d243c9c`), **525 tests + `npm run build` verdes**, pusheado (`0e32f5a`), **backend + frontend deployados y live**.
- **Re-recompute del mapa hecho:** `l2_clusters=54` (era 11), `genres=17` (era 23, unificados movie/TV + minúsculos folded), `clustered=1201`. Verificado visual en /map: 17 géneros limpios (sin "Acción y Aventura"/"Ciencia ficción y Fantasía" duplicados; Acción 210, Sci-Fi 63), 54 movimientos ricos (Space Opera, Cyberpunk, Neo-noir, Giant Robot, Police Procedural, Teen Vampire Romance, etc.), controles +/- y pinch presentes, **0 errores de consola**. Home también limpia (skip link presente, sin errores).
- 🟡 **Wart menor del mapa (documentado, no bloqueante — feature oculta del launch):** "NEO-NOIR" aparece ~6 veces y hay casi-duplicados (TIME TRAVEL/VIAJE EN EL TIEMPO, ROMCOM/COMEDIA ROMÁNTICA, ANIME/SHOUNEN ANIME, MCU ×2). Es labeling independiente del LLM sobre clusters similares. Fix futuro: deduplicar labels L2 (append de género distintivo o merge de clusters con mismo label), o bajar un poco la resolución. Requiere iteración visual — mejor con Matías mirando.

### PENDIENTES PARA MATÍAS (documentados, NO tocados a propósito — necesitan tu criterio; ver detalle arriba en cada auditoría)
Seguridad/abuse (delicado, no cirugía de auth a ciegas en el launch): reserva atómica del cupo diario de /recommend + bypass por /recommend/together ephemeral; rate limit de refine; lockout de login por username (DoS); rate limit de forgot-password y register/guest; transacción única de reset; persistir contadores de rate limit (chat/feedback) + `--forwarded-allow-ips` en Render para IP real; headers de hardening (HSTS/nosniff/server_header). Datos: columna `kind` en `rated_items` (serie tratada como movie en varios lados); persistir tags de Letterboxd (hoy se pierden tras el import); upsert/dedup en import; paginación en history/summary/admin-feedback; ids estables de `vibe-l2` entre recomputes. Chat: la doble llamada al LLM por turno (latencia) — restructurar con cuidado.

## Known issues / deuda
- **Test flaky:** `test_profile_summary_counts_activity` falla ~1 de cada 5 corridas de la suite COMPLETA (aislado y en `test_main.py` solo siempre pasa). Causa: caches a nivel módulo (`_REFINE_CACHE` no se limpia en conftest, solo `_VERDICT_CACHE` y el vibe map) + user_ids que se repiten porque `isolated_db` resetea la DB por test. NO es bug de producto. Fix propuesto: limpiar `_REFINE_CACHE` (y cualquier otro cache keyed por user/profile) en un fixture autouse del conftest, como ya se hace con `_VERDICT_CACHE`.

## 2026-08-24 — mail + despacho paralelo de mapa y chat a Codex

- ✅ **BUTACA_FEEDBACK_EMAIL seteado** (#10) = `russolacernamatias@gmail.com` (Matías cambió el mail a este; NO el de matiasrussolacerna). Via Render API (`PUT /env-vars/{key}`) + redeploy (`dep-da6ci4670`, live). Confirmado el valor live contra la API. El feedback del launch ahora le llega por mail.
- 🟡 **Mapa v2 (#5)** — DESPACHADO a Codex. Worktree `C:\Users\matia\butaca-wt\map` (branch `feat/map-v2` @ 06dbf10). Spec: `scratchpad/spec-map-v2.md`. Log: `scratchpad/logs/codex-map.log`. Bash bg id: `bm12zd4ir`.
  - Diseño: géneros REALES de TMDb como nivel TOP (nombres reales, sin LLM), anclas de género por centroide de embeddings (géneros parecidos quedan cerca), título posicionado por mezcla de anclas de sus géneros + offset chico de embedding (→ superhéroes cae entre sci-fi y acción), L2 = Leiden GLOBAL como sub-categorías (movimientos) que aparecen al zoomear. Frontend: zoom semántico (géneros → movimientos → títulos).
  - Constraint respetado en el spec: L2 (`vibe-l2:N`) sigue alimentando el picker de `/recommend`, schema de `title_clusters`/`cluster_labels` intacto. Se agregan columnas x/y a `title_clusters` (layout pre-computado en recompute).
  - Verificación real (recompute + render en prod) queda para después del merge; local no tiene clustering ni TMDb key válida.
- 🟡 **Chat gurú (#6)** — DESPACHADO a Codex. Worktree `C:\Users\matia\butaca-wt\chat` (branch `feat/chat-guru` @ 06dbf10). Spec: `scratchpad/spec-chat-guru.md`. Log: `scratchpad/logs/codex-chat.log`. Bash bg id: `bovxowfjl`.
  - Diseño: LLM experto de cine general + grounding RAG-lite con datos reales de TMDb (extracción de título → search → details/keywords/certificación inyectados como verdad en el prompt). Guía de contenido = keywords + certificación de TMDb (honesto cuando no alcanza). NO scraping IMDb ni fuente paga.
  - **Ceiling nombrado para Matías:** una guía de contenido más rica (severidad sexo/violencia tipo IMDb parents guide) NO tiene API gratis en vivo — es dataset pago (AWS) o dataset estático de Kaggle (gratis pero desactualizado). Decisión suya si se invierte en eso más adelante. Por ahora TMDb keywords+cert.

## Dónde retomar (al volver: revisar los dos Codex)
1. `bm12zd4ir` (mapa) y `bovxowfjl` (chat) corriendo en background. Cuando terminen: leer `CODEX_RESULT.md` de cada worktree + el log, revisar el diff, correr tests/build, verificar visualmente (mapa necesita recompute en prod; chat se puede probar con NVIDIA real local). Después mergear a main con aviso.
2. Post-merge del mapa: deployar y correr `POST /admin/vibes/recompute` (token en notas técnicas) para regenerar layout con el código nuevo.
3. Flaky test pendiente (deuda): limpiar `_REFINE_CACHE` en conftest.
