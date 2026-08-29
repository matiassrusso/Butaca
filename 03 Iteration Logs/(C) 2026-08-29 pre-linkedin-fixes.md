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

## 🔴 HALLAZGO CLAVE — el LLM no se arregla gratis (decisión de Matías pendiente)
El test end-to-end contra prod (guest + /recommend/manual) destapó lo real:
- **NVIDIA free-tier TIMEOUTEA desde la IP de Render** (lightning y super-120b, 10s c/u), aunque desde otras IPs responden 5-7s. Groq sigue 403 desde Render. → Render está deprioritizado/congestionado en el free-tier. **Mis mediciones locales (nv_sweep/nv_match) NO sirven para decidir** porque miden desde otra IP.
- Lección aparte: medir JSON válido no alcanza — hay que medir que el modelo ELIJA de la lista de candidatos. `nano-30b` respondía <1s pero devolvía **picks=0 siempre** → heurístico igual.
- **No se arregla rotando modelos gratis.** Solo hay 2 que eligen bien Y responden <10s (lightning, super-120b) y los dos timeoutean desde Render cuando el free-tier está saturado.
- **Damage control DEPLOYADO** (commit `2d5af9b`): 1 solo modelo (lightning) + timeout 8s → falla rápido a heurístico (~8s) en vez de colgar 20-30s. Los PICKS siguen siendo buenos (motor real de embeddings+scoring); solo el "why" queda genérico cuando el free-tier está saturado. Cuando NO está saturado, lightning da why real ~7s.
- **Decisión de fondo pendiente de Matías:** LLM pago confiable (el código ya habla formato OpenAI chat-completions → agregar OpenAI/gpt-4o-mini u otro endpoint compatible es un cambio chico; costo ~centavos por el volumen real, rate-limited) vs lanzar con why genérico por ahora.
- Aparte: latencia cold ~10-14s por la resolución del perfil contra TMDb (match_titles, ~150 llamadas). Se amortiza con la cache de 24h (usuarios que vuelven van rápido), pero el primer recommend de un usuario nuevo es lento. Issue separado del LLM.

## Hecho y DEPLOYADO (live en prod)
- ✅ **#1 — chat nombra el pick** (`_CHAT_TASK` ES/EN). (commit 78876f9)
- ✅ **#3/#4/#9 — cadena LLM**: ver hallazgo arriba. Damage control live; solución de fondo = decisión de pago.
- ✅ **#7 kind backend+frontend** (merges `dacadf0` + frontend-kind): series se resuelven bien, pairwise mismo-kind, frontend manda kind al puntuar. Filas viejas quedan 'movie'.
- ✅ **#5 perfil** (merge `ad6b146`): perfil corto + reseñas via /history.
- ✅ **#2 dropzone visual** (merge frontend-kind): el `<label>` era `display:inline` → borde punteado fragmentado; se agregó `block`.

## Mergeado a main (NO deployado todavía — falta el frontend agent)
- ✅ **#7 backend — columna `kind`** (merge `dacadf0`): migración idempotente, `_resolve_watched_title` por kind correcto, `_pairwise_tied_pair` mismo-kind. 527 tests. **Gap: el frontend todavía no manda kind al puntuar** (lo está haciendo el agente de abajo). Filas viejas quedan 'movie' (Breaking Bad ya guardado mal sigue mal hasta re-ratear).
- ✅ **#5 perfil** (merge `ad6b146`): sacada la lista de 140+ items, botón → `/history` (que ya muestra reseñas + estrellas-vs-texto bien). Mató un bug: estrellas para ratings sintéticos.

## Hecho (mergeado a main, pendiente de push/deploy)
- ✅ **#6 watchlist señal suave**: helper `_watchlist_preference_tags` (search_title ya trae tags de género + cachea 24h → barato, capado, paralelo) sumado a `preferred_tags` en `_finish_recommend`. Espejo de "interested". 2 tests.
- ✅ **#8 juego rediseñado**:
  - `_pairwise_pair` (renombrado de `_pairwise_tied_pair`): mismo-kind, rating >= 3.5 (lo que te gustó), cualquier puntaje → pool grande, ~ilimitado (antes empataba rating exacto → se agotaba en "5 rondas").
  - **La elección ahora PESA en el scoring**: `_pairwise_preference_tags` empuja los tags de los ganadores a `preferred_tags`, ponderado por victorias (antes solo elegía a quién citar en el "why"). Actualizado el comentario de `get_pairwise_win_counts`.
  - Frontend: botón "Me gustan los dos igual, saltear" en `PairwiseGame.tsx` + copy actualizado (games.ts, ya no dice "mismo puntaje").
  - Tests actualizados (mismo-kind distinto-rating, degrada sin 2 liked) + 1 nuevo (preference tags ponderados). 530 tests + build verdes.

## LLM — PENDIENTE decisión de Matías
- Le pasé la comparación de opciones de pago. Recomendación: OpenAI gpt-4o-mini (~$1-5/mes, cambio de código mínimo porque ya es formato OpenAI), con truco de NVIDIA-gratis-primario-timeout-corto → OpenAI-fallback para pagar casi nada. Espera que consiga la key (`OPENAI_API_KEY` en Render) y hago el wiring.
- Latencia cold ~10-14s (TMDb profile) sigue siendo issue aparte, no tocado.

## Nota operativa
- Codex `exec` en background quedó inestable acá (no-op + clasificador). El dispatch paralelo va por subagentes Claude. Regla `Bash(codex exec:*)` agregada a `.claude/settings.local.json` igual.
- Worktrees a limpiar al final: kind, profile-page, frontend-kind (+ los viejos: chat, emb, map, mobile-*, together, wrapped).

