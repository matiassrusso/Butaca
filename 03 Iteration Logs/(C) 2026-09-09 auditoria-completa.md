# (C) Auditoría completa de Butaca — 2026-09-09

Registro vivo. Matías pidió auditar todo el proyecto (qué anda, qué no) y anotar todo lo encontrado, con foco especial en `/recommend` lento y siempre heurístico. **Solo diagnóstico: no se tocó código.** Las soluciones se discuten después.

Cada hallazgo lleva severidad y confianza. Confianza = qué tan verificado está (medido en prod / medido local / leído en código).

---

## 1. `/recommend` lento y heurístico — CONFIRMADO en prod hoy, causa raíz nueva

### Lo medido (guest descartable + `POST /recommend/manual`, 12 ratings, prod real)

| Llamada | Tiempo | `refined` | whys del LLM |
|---|---|---|---|
| 1ª (perfil frío) | **28.2s** | False | 0/6 |
| 2ª (perfil cacheado) | **9.0s** | False | 0/6 |

Desglose de la 1ª, leído de los logs de Render con timestamps:
- ~3s: resolver el perfil contra TMDb (`match_titles`).
- **~16s: enriquecimiento de candidatos** (credits + keywords, ~200 llamadas a TMDb **secuenciales**, ~80-100ms cada una).
- **8s: timeout del LLM** (`REQUEST_TIMEOUT = 8`, un solo modelo).
- ~1s: scoring, embeddings, DB.

La 2ª es 8s de timeout del LLM + 1s de todo lo demás. O sea: **cada recomendación paga 8s de espera fija para no obtener nada**, y encima siempre sale heurística.

### Estado real de la cadena LLM (log de prod 14:09 UTC hoy)
```
NVIDIA nemotron-3.5-lightning-30b-a3b falló: The read operation timed out
Groq llama-3.3-70b-versatile falló: HTTP Error 403: Forbidden
LLM refine failed, falling back to heuristic why
```
Lo mismo aparece en los únicos dos usos del LLM de los últimos 7 días (09-02 y 09-08, verdicts de `/weekly` en background). **Nadie llamó a `/recommend` en prod en los últimos 7 días** (`/admin/stats`: 0 sesiones en 7 días), o sea que el reporte de Matías es de antes y hoy el problema sigue idéntico.

### 🔴 Hallazgo clave: el 403 de Groq NUNCA fue un bloqueo de IP de Render. Es el User-Agent.
Verificado desde mi IP, misma key:
- `curl` con UA default → **200**.
- `curl -A "Python-urllib/3.14"` → **403**.
- El backend usa `urllib.request` sin setear `User-Agent` → manda `Python-urllib/3.x` → Cloudflare de Groq lo bloquea.

La teoría "Cloudflare filtra IPs de hosting" (comentarios en `llm_client.py`, `docs/groq-setup.md`, logs de 08-11 y 08-29) **está equivocada** y hay que corregirla en los tres lugares. Nunca se probó desde Render con otro UA porque en los sandboxes se probaba con curl/requests, que sí mandan un UA aceptable.

Además: **`llama-3.3-70b-versatile` ya no existe en Groq** (404 `model_not_found` desde acá). Catálogo actual con chat: `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `qwen/qwen3.6-27b`, `qwen/qwen3.8-27b`. O sea que Groq estaba doblemente muerto: UA bloqueado Y modelo retirado.

Medido con el prompt de refine real (lista de candidatos, JSON), UA custom, desde mi IP:

| Modelo (Groq) | Latencia | picks matcheados | Nota |
|---|---|---|---|
| `openai/gpt-oss-120b` + `reasoning_effort: low` | **1.1-1.3s** | 6/6 | Español correcto, no siempre voseo puro (el prompt real tiene reglas más fuertes) |
| `openai/gpt-oss-20b` + `reasoning_effort: low` | 0.6-0.8s | 6/6 | Ignoró la escala de score en mi muestra (puso 0-10) |
| `qwen/qwen3.6-27b` | — | — | 429 al primer intento (rate limit ajustado) |
| `qwen/qwen3.8-27b` | 1.2s | 6/6 | |

Ojo: `response_format: json_object` con `max_tokens` chico falla en gpt-oss-120b/qwen (el razonamiento consume el presupuesto). Sin `max_tokens` y con `reasoning_effort: low` anda.

**Falta verificar desde Render** (solo se puede deployando): que con UA custom el 403 desaparezca también desde ahí, y los límites del free tier de Groq (RPM/TPD) con el volumen real. Confianza alta en que es el UA; confianza media en que el free tier alcance.

### Estado de NVIDIA hoy (desde mi IP, prompt real, timeout 20s)

| Modelo | Resultado |
|---|---|
| `nemotron-3.5-lightning-30b-a3b` (el ÚNICO de prod) | **timeout 3/3** (sigue en el catálogo, pero no responde) |
| `nemotron-3-super-120b-a12b` | 7.7-8.2s, 6/6 (2 de 3); 1 timeout |
| `nemotron-3-ultra-550b-a55b`, `mistral-nemotron` | timeout |
| `nemotron-3-nano-30b`, `llama-3.3-70b`, `llama-3.1-8b` | **410 Gone** (retirados) |
| `qwen3-235b` | 404 |

Conclusión: la cadena de prod es `lightning (muerto) → Groq (403 por UA + modelo retirado) → heurístico`. Nada puede salir bien hoy.

### Otras dos causas de lentitud, independientes del LLM (confianza alta, leído en código + logs)
- **[medio] El frontend nunca usa el render progresivo.** `POST /recommend/sessions/{id}/refine` existe en el backend justamente para devolver los picks al toque y traer los "why" del LLM después, pero `Recommend.tsx` manda siempre `refine: true` (llamada sincrónica) y **no hay ni una referencia a `/refine` en todo el historial de git del frontend**. Nunca se cableó. Con eso, los picks aparecerían en ~1s (perfil cacheado) y el why llegaría después sin bloquear.
- **[medio] Enriquecimiento secuencial** en `tmdb_client.fetch_personalized_candidates`: `for item in movies[:30]` con 2 HTTP por ítem (credits + keywords), por cada pool (varios pools de movies + series + exploration). Sin `ThreadPoolExecutor`, aunque el mismo archivo ya lo usa en `fetch_candidates_for_options`. Son los ~16s del perfil frío. Los duplicados en el log (The Dark Knight ×5) son hits de cache, no llamadas extra.

### Efecto colateral: `/weekly` tampoco personaliza
El verdict de la home corre en background con la misma cadena → falla siempre → ningún usuario logueado ve verdicts personalizados en la home desde hace semanas.

---

## 2. CI rota desde el 2026-08-29 (6 pushes seguidos en rojo) — 🔴 alto, confianza alta

```
backend/app/llm_client.py:597: def _candidate_identity(rec: Recommendation) -> tuple:
NameError: name 'Recommendation' is not defined
```
`Recommendation` se usa en anotaciones de `llm_client.py` pero **no está importado** (solo `RatedItem, RecommendResponse`). Local pasa porque Python 3.14 evalúa anotaciones de forma diferida (PEP 649); CI usa 3.12 y explota al importar. Prod anda, así que Render está usando ≥3.14 por default — **frágil**: si Render cambia el default o alguien pinea 3.12/3.13, el backend muere al boot. Fix: una línea de import. Nadie lo vio porque los 530 tests pasan local.

Extra menor: CI avisa que `actions/checkout@v4` y `setup-python@v5` corren en Node 20 deprecado.

---

## 3. Trabajo sin commitear en el worktree principal — 🟡 decisión de Matías

3 archivos modificados (`StarRating.tsx`, `translations/recommend.ts`, `Recommend.tsx`, +218/-30), sin nota de sesión que los explique:
- **Tab "Mi perfil" en el paso 1 del wizard**: picker primario Mi perfil / Letterboxd / A mano, Letterboxd agrupa zip+username, default a "Mi perfil" si ya tenés ≥10 puntuadas, texto "Cómo funciona" arriba, nota "se guarda en tu perfil". Llama a `POST /recommend/profile` (que ya existía).
- **Estrellas arrastrables en touch** (`StarRating.tsx`): capa `pointer` sobre la fila, snap a 0.5, confirma al soltar.

`npm run build` pasa con esto adentro. Detalle: para saber `rated_count` hace `GET /profile/summary`, que devuelve **la lista completa de items** — pesado para perfiles grandes, solo para un número. ¿Se termina y commitea, o se descarta?

---

## 4. Seguridad / ops — lo que sigue abierto del 2026-08-24 (verificado hoy) + una cosa nueva

- 🔴 **[nuevo, causado por esta auditoría]** Al consultar `/admin/stats` pasé el token también como query string además del header; el header es el que se usa, pero **la URL con el token quedó en los access logs de Render** (`GET /admin/stats?token=...`). Los logs son privados de tu cuenta, pero conviene **rotar `BUTACA_ADMIN_TOKEN`** (env var en Render + redeploy). Mi error, lo reporto.
- 🟡 API sin headers de hardening: sin HSTS/nosniff/referrer-policy (Vercel sí manda HSTS para el frontend); `x-render-origin-server: uvicorn` expone el server.
- 🟡 Rate limits en memoria (chat 30/día, feedback 5/día, cupo de recommend): se resetean con cada reinicio/deploy de Render; `request.client.host` sin `--forwarded-allow-ips` → la IP que ve el backend puede ser la del proxy.
- 🟡 Sin rate limit en `forgot-password`, `register`, `guest` (flood / spam de mails). Lockout de login por username → DoS trivial a un usuario.
- 🟡 Cupo diario de `/recommend`: COUNT antes + INSERT después → race que lo excede. `/recommend/together` (ephemeral) lo bypassea.
- 🟢 OK verificado antes: sin SQLi, tokens hasheados, `/admin/*` gateado, CORS allowlist, OAuth solo linkea si `email_verified`.

---

## 5. Docs y contexto desactualizados — 🟡 confianza alta

- `CLAUDE.md` "Estado actual" quedó en el **2026-08-11**: faltan las sesiones del 08-23, 08-24 (auditoría nocturna, mapa v2, chat gurú, reseñas, feedback) y 08-29 (kind, juego, watchlist). Dice 490 tests; son **530**.
- `AGENTS.md` dice 207 tests y estado de julio.
- `llm_client.py` (comentario de la cadena), `docs/groq-setup.md`, logs 08-11 y 08-29: llevan la teoría equivocada del bloqueo de IP (ver §1).
- Memoria del proyecto decía que la TMDb key local daba 401: **hoy da 200**. Corregido en memoria.

---

## 6. Uso real de prod (`/admin/stats`, hoy)

| Métrica | Valor |
|---|---|
| Usuarios | 24 |
| Sesiones de recomendación | 151 total · **0 últimos 7 días** · 25 últimos 30 días |
| Picks servidos | 898 |
| Feedback en picks | 144 (~6% interesa / ~6% no / ~3% ya vista) |
| Feedback del sitio (`/feedback`) | 0 entradas |

Lectura: la página está viva y estable pero sin uso en la última semana. No hay señal de usuarios nuevos post-LinkedIn todavía (o el post no salió).

---

## 7. Lo que anda bien (verificado hoy)

- Backend prod live en `48cb103` (= HEAD de main), Render `not_suspended`, autodeploy on, Oregon, free.
- `/health` 0.65s (caliente), `/weekly` 0.26s, `/catalog/stats` 0.28s, `/vibes/map` 1.05s (266KB), `/recommend/options` 0.28s.
- Frontend butaca.xyz carga bien, **0 errores de consola**, HSTS presente.
- **530 tests backend en verde local** (6:43 — lento, ver §8). `npm run build` en verde (incluye el WIP de §3).
- Env vars de prod completas: TMDB, NVIDIA, GROQ, RESEND, DATABASE_URL, GOOGLE_CLIENT_ID, BUTACA_ADMIN_TOKEN, BUTACA_FEEDBACK_EMAIL. **No hay `OPENAI_API_KEY`** (la decisión de LLM pago sigue sin tomarse — con §1 quizás ya no haga falta).
- TMDb key local: 200 (anda).

---

## 8. Deuda de código / higiene — 🟢 baja, confianza alta

- `_finish_recommend` calcula `selected_genres` / `vibe_labels` / `required_any_groups` **dos veces** (líneas ~1360 y ~1430): el fix "validar antes de escribir" del 08-24 agregó el bloque arriba y dejó el viejo abajo. Una query extra a `vibe_clusters` por request.
- Suite de tests: 530 tests en **6 min 43 s** local. Vale la pena ver qué tarda (¿sleeps? ¿red?).
- Test flaky conocido (`test_profile_summary_counts_activity`, cache `_REFINE_CACHE` sin limpiar en conftest): hoy pasó, sigue sin fix.
- Bundle del frontend: un chunk >500kB (sin code-splitting).
- `/titles/search` exige login (401 anónimo) — el buscador de la navbar no sirve a visitantes. ¿Intencional?
- **Worktrees zombies**: 8 en `C:\Users\matia\butaca-wt\` (chat, emb, map, mobile-audit, mobile-stars, together, wrapped) + `.claude/worktrees/nifty-margulis-b14e64` (branch con -29k líneas, claramente vieja). 12 branches locales ya mergeadas + `backup-before-history-rewrite` + remota `claude/recommendations-slow-heuristic-9m0huf`. Limpiar con `git worktree remove` / `git branch -d`.

---

## 9. Decisiones de producto que siguen abiertas (arrastradas)

- LLM pago (OpenAI gpt-4o-mini) — **probablemente innecesario si §1 se confirma desde Render**.
- Wrapped modo público; monetización (donaciones); mapa: dedupe de labels L2 (NEO-NOIR ×6); chat: doble llamada al LLM por turno; filas viejas de `rated_items` con `kind='movie'` (Breaking Bad mal guardado hasta re-ratear); persistir tags de Letterboxd; paginación en history/summary.

---

## Propuesta de orden para la charla de soluciones (no ejecutado)

1. **LLM (una tarde):** UA custom en `_call_nvidia` + Groq `openai/gpt-oss-120b` con `reasoning_effort: low` + `max_tokens` sin tope chico; cadena `Groq (timeout 6s) → NVIDIA super-120b (8s) → heurístico`. Deployar y **verificar desde Render con logs** antes de festejar. Corregir los tres lugares con la teoría de la IP.
2. **Render progresivo en el frontend:** `refine: false` + llamar a `/recommend/sessions/{id}/refine` (ya existe, ya tiene tests). Picks al toque, why después.
3. **Paralelizar el enriquecimiento** (`ThreadPoolExecutor`, ya usado en el mismo archivo). 28s frío → ~10s.
4. **CI:** importar `Recommendation`. Una línea.
5. Rotar `BUTACA_ADMIN_TOKEN`.
6. Decidir el WIP sin commitear (§3).
7. Actualizar CLAUDE.md/AGENTS.md/groq-setup.md.
8. Higiene de worktrees/branches.

Meta de Matías (08-29): **<15s tope, <10s ideal.** Con 1+2+3, el usuario que vuelve vería picks en ~1-2s y el why del LLM en ~2-3s; el usuario nuevo, ~10s.

---

## Ruta de soluciones — ejecutada (misma sesión, tarde)

Fase de pensamiento: tres agentes en paralelo (estrategia LLM con mediciones reales contra Groq/NVIDIA; diseño del render progresivo en el frontend; plan de perf/CI/headers en backend). Informes en el scratchpad de la sesión (`llm-strategy.md`, `plan-progressive-frontend.md`, `plan-backend-perf.md`). Después, ejecución en worktrees separados.

### Decisiones tomadas (con los números que las sostienen)
- **Cadena LLM: Groq primero, NVIDIA fuera de la cadena sincrónica.** Medido con el prompt real (3 corridas por modelo): `qwen/qwen3.8-27b` 2-3s y el mejor rioplatense; `openai/gpt-oss-120b` (`reasoning_effort: low`) 1,6-1,8s; `openai/gpt-oss-20b` 1,1s pero tutea; NVIDIA `super-120b` 18-20s. Cada modelo de Groq es un bucket de cuota independiente (8K TPM / 1K RPD / 200K TPD por modelo) → ~190 refines/día gratis entre los tres, contra 30-50/día de uso real. Un 429 pasa al siguiente en 0,1s. Timeout 6s. La key de NVIDIA sigue para embeddings. Alternativa descartada: OpenAI pago — si algún día aprieta, Groq Dev Tier (~USD 4/mes estimado) mantiene código y calidad medida.
- **Render progresivo cableado en el frontend** (`refine: false` + `POST /recommend/sessions/{id}/refine`): picks al toque, why del LLM después, chip "escribiendo…" mientras tanto. Cambio semántico explícito: el LLM ahora opina sobre los 6 picks del motor en vez de elegir 6 de 12 (es la semántica del endpoint, que ya existía).
- **Flag `refined` persistido** (columna nueva en `recommendations_served`, migración idempotente): la bitácora y "Current picks" marcaban HEURÍSTICO en todo porque el dato no existía.
- **CI**: import de `Recommendation` + matriz Python 3.12/3.14. Render usa 3.14.3 default (confirmado en build log); no se pinea, el código ya no depende de la versión.
- **`--no-server-header`**: render.yaml NO se sincroniza con el servicio (el startCommand vive en el dashboard); se cambió vía API de Render (`PATCH /v1/services/{id}`).

### Resultado medido en prod (guest descartable, 2026-09-09 14:50 UTC)

| Paso | Antes | Ahora |
|---|---|---|
| `POST /recommend/manual`, perfil cacheado | 9,0s, heurístico | **1,1s**, picks al toque |
| `POST /recommend/manual`, perfil frío | 28,2s, heurístico | 12,3-12,5s (baja a ~3-4s con la paralelización, en curso) |
| `POST /recommend/sessions/{id}/refine` | no se llamaba nunca | **1,7-2,1s, 6/6 whys del LLM**, score del motor intacto |
| `/history` → `refined` | siempre HEURÍSTICO | flags reales (`[True]*6` tras el refine) |
| Log de prod | `Groq … 403 Forbidden` | `LLM qwen/qwen3.8-27b respondió en 1.7s` **desde la IP de Render** |
| CI | roja desde 08-29 | verde (3.12 y 3.14) |
| `x-render-origin-server` | `uvicorn` | `Render` |

Commits en `main`: `9cfe631` (cadena LLM + CI), `f380283` (render progresivo), `bd9ac67` (flag refined + log del modelo). Todo deployado (backend `dep-…` live 14:49, frontend en Vercel con el chip nuevo en el bundle).

### Perf backend (mergeado y deployado después, `bcdb5f9` + `55c7ec5`)
- Enriquecimiento de candidatos en paralelo (`_enrich_candidates`, 6 → 8 workers tras medir ~210ms/llamada desde Render), guards `KeyError` en los `move_to_end` de las caches, bloque duplicado de `_finish_recommend` borrado, middleware con HSTS/nosniff/referrer-policy (verificado en `curl -I`), fixtures de conftest (SQLite sin fsync + PBKDF2 corto: `test_auth`+`test_db` 14,6s → 1,9s). 537 tests.
- Perfil frío en prod: 28,2s → 14,9s con 6 workers (timeline por logs: ~5,7s de perfil+discover secuencial, ~7s de enriquecimiento, ~2s de scoring/DB). Con 8 workers ver la medición final abajo. Lo que queda secuencial es la fase de discover (~6 `search/person` + ~10 `discover`, ~2-3s) — próxima palanca si el frío sigue molestando; se paga una vez por usuario (cache 24h).
- **Hallazgo nuevo del agente:** varios tests de `test_main.py` salen a la red de verdad (`TMDB_API_KEY="fake-key"` + `taste_profile.match_titles` pegando a `api.themoviedb.org`, 401 tragado por el `except`). Un solo test hace 82 llamadas HTTPS reales; por eso la suite oscila entre 37s y 100s. Fix propuesto, no hecho: fixture autouse en `conftest.py` que haga fallar `urllib.request.urlopen` (destaparía tests que hoy pasan por el fallback). Aparte: la suite tarda 4x más desde el repo principal (OneDrive) que desde un worktree fuera de OneDrive.

### Para Matías
- **Rotar `BUTACA_ADMIN_TOKEN`** (quedó en un access log de Render por error mío al auditar).
- ~~Decidir el WIP de la branch `wip/mi-perfil-tab-y-estrellas-touch`~~ **Resuelto**: era el trabajo de la sesión del 2026-09-02 ("Reordenar opciones de recomendación": picker Mi perfil / Letterboxd / A mano, marco "cómo funciona", estrellas arrastrables en touch). Matías pidió rebasarlo y mergearlo; hecho con el único ajuste de `refine: false` en `/recommend/profile`, verificado en dev server (`POST /recommend/profile` → `/refine`, picks <0,5s) y publicado (`2b45626`). Los puntos 2-6 de "aspectos explicativos" de esa sesión también quedaron hechos a pedido de Matías (solo texto en `/recommend`, ES/EN, verificados en dev server en los dos idiomas): cartel "¿No tenés Letterboxd? Elegí A mano" bajo el picker; una línea bajo cada grupo del paso 2 (géneros = TMDb; vibras = tono, curadas a mano desde keywords; movimientos = clusters de embeddings, nombres del agente); bloque "[CÓMO LEERLO]" arriba de la grilla (qué es el %, qué es S/D, que las reacciones entrenan la próxima tanda); "Entrena la próxima tanda" bajo los botones del modal; bloque "[SIGUIENTE PASO]" tras la grilla con links a `/rate` y `/games`. Visto de paso, fuera de alcance: las opciones de género/vibra/movimiento vienen del backend en español aunque la página esté en inglés.
- El worktree `.claude/worktrees/nifty-margulis-b14e64` (branch de julio, mergeada) tiene 2 archivos modificados sin commitear (`AGENTS.md`, `docs/architecture.md`); no lo borré por eso.
- Branch `backup-before-history-rewrite` y la remota `claude/recommendations-slow-heuristic-9m0huf` quedaron; borrarlas es decisión tuya.
- Tests que salen a la red (arriba): ¿lo encaro la próxima?

### Incidente de la limpieza (reportado, resuelto)
Al borrar los worktrees viejos, un junction de `node_modules` no se soltó y `git worktree remove --force` vació el `node_modules` real del repo principal. Nada trackeado se perdió (git status limpio); se regeneró con `npm ci` y el build volvió a andar. Lección guardada en memoria.

### Medición final (deploy `55c7ec5`, 8 workers, guest nuevo con perfil distinto)
| Perfil frío | 28,2s → **13,1s** |
|---|---|
| Refine | 1,6s, 6/6 whys del LLM |
| Perfil cacheado | 1,0s |

### Reportado por Matías después del cierre: "sacaste varias animaciones"
No fue de esta sesión: el commit de accesibilidad del 2026-08-25 (`2d967d5`, auditoría nocturna vía Codex) pasó el panel del menú lateral (`StaggeredMenu`) a montarse solo con `open`, y `toggleMenu` llama a `playOpen()` en el mismo tick que `setOpen(true)`, antes de que el portal exista: `buildOpenTimeline()` no encontraba el panel y devolvía null; al cerrar, el unmount se llevaba el elemento antes del tween de salida. Fix: el panel vuelve a estar siempre montado (offscreen vía GSAP) y la accesibilidad que buscaba ese cambio la da `inert={!open}`; de paso, el effect que devolvía el foco al botón corría también al montar y robaba el foco en cada carga de página (guard con `wasOpenRef`). Verificado en Chrome real contra el dev server: tween de apertura 460px → 0 en 0,65s y de cierre 0 → 460px en 0,32s, `inert` solo cerrado, foco en `body` al cargar. Con la pestaña oculta el browser congela rAF y GSAP no avanza, así que la medición fue forzando `progress()` de los tweens, no a ojo.
