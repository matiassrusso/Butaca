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
4. Tests de backend en verde antes de cerrar (213 tests a la fecha)
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

> **Last updated:** 2026-07-23, sesión 3 (bugs post-feedback + fix del refine del LLM)
>
> ### ⚠️ Leer primero al retomar
>
> **El proyecto se llama `Butaca`** (antes PeliPick), con dominio propio en
> vivo: frontend en [butaca.xyz](https://butaca.xyz/) (Vercel), backend en
> [api.butaca.xyz](https://api.butaca.xyz) (Render). Las URLs `pelipick.*`
> siguen funcionando en paralelo pero ya no son la identidad real. Todo lo
> operativo grande ya está cerrado: dominio, Resend activo, UptimeRobot
> activo, `NVIDIA_API_KEY` en producción, Ola 4 completa, y el **feedback de
> amigos pre-lanzamiento trabajado 19/20**. **213 tests de backend en verde.**
>
> **Primero al retomar:** confirmar en butaca.xyz que los picks salen con
> razón real del LLM (no la plantilla "tira para el foco..."). El fix del
> refine (ver sesión 3 abajo) está deployado y live, pero falta la
> confirmación en vivo pidiendo una tanda de picks.
>
> **Pendientes reales** (detalle en `Pending` de `TASKS.md`):
> - Confirmar picks con razón real del LLM en producción (arriba).
> - Decidir el fallback del LLM: quedarnos con `llama-3.1-70b` (anda) o
>   investigar cómo invocar `kimi-k2.6` (aparece en el catálogo con la misma
>   key pero da 404 por el endpoint estándar).
> - Punto 7 del feedback (onboarding manual estilo swipe) — decidir recién
>   cuando los amigos prueben el wizard nuevo.
> - Borrar el usuario de prueba `test-resend-qa` en producción.
> - Activar auto-renew de `butaca.xyz` antes del 21-07-2027.
> - Borrar el proyecto viejo de Neon (São Paulo) cuando el nuevo lleve unos
>   días estable.
> - Renombrar la carpeta local del proyecto y la lista del `CLAUDE.md` raíz
>   del vault (fuera de este repo, requiere permiso).
> - Mejoras chicas del import por username: aprovechar `tmdb:movieId` del
>   RSS y avisar en el frontend que esa vía trae solo historial reciente.
> - La TMDb key del `backend/.env` **local** está vieja (401): corriendo
>   local las recs degradan al catálogo mock. Producción tiene la key buena.
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
