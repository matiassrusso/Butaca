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

## Hecho esta sesión

- ✅ **#3/#4/#9 — cadena LLM reconstruida** (`backend/app/llm_client.py`): re-medido el catálogo (83 modelos, `scratchpad/nv_sweep.py`). Nuevo primario `nemotron-3-nano-30b-a3b` (~0.7-0.9s, JSON OK), fallbacks `lightning-30b` (3.7-4.4s) + `mistral-nemotron` (~5s). Sacados ultra-550b (503/timeout) y llama-3.1-8b (410). `REQUEST_TIMEOUT` 10→8s. Comentario del historial actualizado. **525 tests verdes. SIN deployar todavía.**
- ✅ **#1 — chat nombra el pick** (`_CHAT_TASK` ES/EN): regla de nombrar título+año explícito al recomendar.

## Worktrees Codex preparados (dispatch bloqueado)
- `C:\Users\matia\butaca-wt\kind` (branch `fix/rated-items-kind`) — spec en scratchpad/spec-kind.md
- `C:\Users\matia\butaca-wt\profile-page` (branch `fix/profile-page`) — spec en scratchpad/spec-profile.md
- `codex exec` bloqueado por el clasificador de auto-mode. Pendiente decisión de Matías: permitir codex o usar subagentes Claude.

## Estado
(vivo)
</content>
