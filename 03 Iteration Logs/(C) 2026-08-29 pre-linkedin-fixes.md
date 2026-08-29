# (C) Backlog de fixes pre-LinkedIn — 2026-08-29

Registro vivo. Matías probó butaca.xyz y reportó 9 cosas rotas/mejorables antes de postear en LinkedIn. Regla de oro: primero arreglamos todo, después avanzamos.

## Los 9 reportes (crudos, como los dijo)

1. **Chat no recomienda nada concreto.** Le pidió "Tengo dos horas esta noche, tirame algo" y respondió con una descripción de una peli ("es un thriller que...") pero NUNCA dijo el título. El chat tiene que dar el título concreto.
2. **La caja del zip anda mal.** El dropzone de subir .zip (paso 1 del wizard). Roto — falta reproducir CÓMO.
3. **Recomendaciones tardan mucho.** Tope duro: <15s, ideal <10s. "Al usuario promedio no le gusta esperar."
4. **6 recomendaciones con heurístico.** Screenshot: los 6 picks con badge HEURÍSTICO, ninguno con why del LLM. Ligado a #3 (timeout → cae a heurístico).
5. **Perfil demasiado largo + no ve reseñas.** "Tus ratings y reseñas" hace la página larguísima → debería ser popup o página aparte. Y solo ve ratings, NO ve sus reseñas.
6. **"La quiero ver"** — no sabe si afina futuras recomendaciones; debería alimentar el perfil.
7. **Posters/datos mal + series vs pelis.** "Breaking Bad" aparece con poster equivocado (parece Mirror de Tarkovsky), año 1975 (mal), y ES UNA SERIE comparada contra una peli (Rocky) en el juego. No comparar series con películas.
8. **Juego limitado a 5 rondas.** Debería ser ilimitado (afinar gusto/perfil) + opción "saltear decisión" cuando te gustan los dos igual.
9. **Archivo guarda el why mal.** En /history [RECOMENDADAS], cada sesión debe guardar el texto del why TAL CUAL salió al pedir la recomendación (LLM si fue LLM, heurístico si fue heurístico).

## Triage (causas raíz confirmadas en código)

- **#3+#4+#9 = UNA causa: cadena LLM muerta.** Log prod 14:33: lightning + ultra-550b timeout 10s c/u, llama-3.1-8b → 410 Gone (retirado), Groq → 403 (Render). Todo cae a heurístico tras ~20s. El archivo guarda heurístico porque el refine SIEMPRE falla (el `/recommend/sessions/{id}/refine` ya persiste el why del LLM cuando funciona vía `update_session_refinement`). → **Yo.**
- **#1 chat sin título:** el prompt no obliga a nombrar el pick. → **Yo** (fix chico).
- **#7 poster/serie:** `_resolve_watched_title` (main.py ~2166) resuelve TODO como `kind="movie"`; `rated_items` sin columna `kind`; ids movie/TV de TMDb son espacios separados → serie por id devuelve peli random (Breaking Bad → Mirror 1975). `_pairwise_tied_pair` no filtra por kind. → **Codex/subagente** (worktree `kind`).
- **#5 perfil largo + sin reseñas:** puramente frontend — `get_watched_items` YA devuelve `review`, Profile.tsx no lo renderiza ni separa la lista. → **Codex/subagente** (worktree `profile-page`).
- **#6 "la quiero ver":** verificar wiring de watchlist en el scoring. → Yo (check).
- **#8 juego 5 rondas + saltear:** `_pairwise_tied_pair` solo muestra pares con MISMO rating por diseño (para no fabricar ratings). "Ilimitado" necesita rediseño. → **Decisión de Matías.**
- **#2 zip:** falta reproducir. → Repro en browser.

## Decisiones de Matías (respondidas)
- **#2 zip:** es solo VISUAL — el cartel del dropzone se ve roto, la subida anda. → fix CSS.
- **#6:** SÍ, watchlist como señal suave en el scoring.
- **#8:** el rating no es la preferencia actual. Comparar pares diversos (mismo tipo, distinto rating/género) y que la elección pese como señal real de gusto por encima de las estrellas. Ej: puede preferir La Odisea sobre Toy Story aunque le haya puesto menos rating. Combinar con #7: mismo-kind (no serie vs peli) pero relajar el rating igual.

## Hecho y DEPLOYADO (live en prod, commit 78876f9)
- ✅ **#3/#4/#9 — cadena LLM reconstruida** (`llm_client.py`): re-medido el catálogo (83 modelos, `scratchpad/nv_sweep.py`). Primario `nemotron-3-nano-30b-a3b` (~0.7-0.9s), fallbacks `lightning-30b` + `mistral-nemotron`. Sacados ultra-550b (503) y llama-3.1-8b (410). `REQUEST_TIMEOUT` 10→8s.
- ✅ **#1 — chat nombra el pick** (`_CHAT_TASK` ES/EN).

## Mergeado a main (NO deployado todavía — falta el frontend agent)
- ✅ **#7 backend — columna `kind`** (merge `dacadf0`): migración idempotente, `_resolve_watched_title` por kind correcto, `_pairwise_tied_pair` mismo-kind. 527 tests. **Gap: el frontend todavía no manda kind al puntuar** (lo está haciendo el agente de abajo). Filas viejas quedan 'movie' (Breaking Bad ya guardado mal sigue mal hasta re-ratear).
- ✅ **#5 perfil** (merge `ad6b146`): sacada la lista de 140+ items, botón → `/history` (que ya muestra reseñas + estrellas-vs-texto bien). Mató un bug: estrellas para ratings sintéticos.

## En curso / pendiente
- ⏳ **subagente frontend** (worktree `frontend-kind`, branch `fix/frontend-kind-cartel`): #7-frontend (mandar kind en los ~6 call sites de rate) + #2 (visual del cartel del dropzone). Al terminar: merge + test + build + deploy del batch.
- 🔜 **#6** (watchlist señal suave): sumar tags de watchlist a `preferred_tags` en `_finish_recommend` (espejo de "interested"). Ojo latencia — resolver watchlist contra TMDb es caro; hacerlo cacheado/capado o en el write path. NO apurar.
- 🔜 **#8** (juego): relajar `_pairwise_tied_pair` a mismo-kind cualquier-rating + skip + ilimitado, y que `pairwise_preferences` pese en el scoring (recommender._find_reference_title ya la usa para desempatar; ampliar). Frontend: `PairwiseGame.tsx` botón saltear.

## Nota operativa
- Codex `exec` en background quedó inestable acá (no-op + clasificador). El dispatch paralelo va por subagentes Claude. Regla `Bash(codex exec:*)` agregada a `.claude/settings.local.json` igual.
- Worktrees a limpiar al final: kind, profile-page, frontend-kind (+ los viejos: chat, emb, map, mobile-*, together, wrapped).

