# (C) Plan de trabajo — próxima etapa de PeliPick

> **Creado:** 2026-07-16 · **Autor:** Claude (Opus 4.8) · **Estado:** propuesto, esperando luz verde
> Documento vivo. Se actualiza a medida que avanzan las fases. Para el estado real del producto ver [mvp-status.md](mvp-status.md); para producto/MVP ver [product-mvp.md](product-mvp.md); para arquitectura ver [architecture.md](architecture.md).

Este plan sale de una lectura completa del repo (todos los commits, los 8 docs, y el núcleo del código: `recommender.py`, `llm_client.py`, `tmdb_client.py`, `taste_profile.py`, `main.py`) más una entrevista corta con Matías. Registra **qué** hacemos, **por qué**, y **con qué skills** para que Claude/Codex rindan gastando el mínimo de recursos.

---

## 1. Diagnóstico (el hallazgo central)

PeliPick tiene **mucha infraestructura sólida** (auth + reset + rate limiting, caché TMDb, import zip robusto, historial, perfil visual, cadena de fallback de Gemini, 128 tests) construida **alrededor de un motor de recomendación que es el eslabón más débil** y que hoy no puede personalizar mucho. Dos causas verificadas en el código:

1. **Los candidatos no dependen del usuario.** `main.py:217` → `tmdb_client.fetch_candidates(mood)` trae el top global de TMDb por `vote_average` (con `vote_count ≥ 200`), filtrado a lo sumo por **un** género si el mood coincide con uno de 4. Dos usuarios con gustos opuestos reciben casi el mismo pool base (Padrino, Parasite, Interstellar…).
2. **El matching es un vocabulario de ~20 tags coarse, por substring en inglés.** La señal de gusto sale de escanear reviews buscando literalmente `"slow"`, `"action"`, `"funny"`. Sin reviews (o en español), el vector de gusto queda casi vacío, todo scorea ~50 y el orden final ≈ `vote_average` de TMDb. Es decir: para el usuario típico, **PeliPick ≈ "las mejores de TMDb que todavía no viste"**.

Gemini reordena y reescribe el *why*, pero está atado a ese pool → puede explicar lindo un pick genérico. Es exactamente el **"Riesgo 3: explicaciones humo"** que ya estaba anotado en `product-mvp.md`.

**El insight que ordena todo el plan:** `taste_profile.py` **ya calcula el gusto real** del usuario (géneros pesados por rating, décadas, directores, actores)… pero solo para dibujar el radar en `/profile`. **El motor lo ignora.** Esa desconexión es el problema y también la solución más barata.

---

## 2. El norte

> El 80% de la calidad de pick está en **de dónde salen los candidatos**. Hoy salen del top global de TMDb. Tienen que salir del gusto del usuario. Todo lo demás se ordena alrededor de eso.

Regla práctica heredada del proyecto: cada iteración tiene que mover **calidad real de recomendación** o **claridad real del flujo**. Si no mueve ninguna, es complejidad al pedo.

---

## 3. Contexto de la entrevista (por qué priorizamos esto)

Respuestas de Matías (2026-07-16):

| Pregunta | Respuesta |
|---|---|
| ¿Para qué querés PeliPick ahora? | **Las dos por igual** — producto real *y* portfolio |
| ¿Cómo sentís hoy los picks? | **A veces sí, a veces no** (inconsistente) |
| ¿Qué de lo hecho revisar? | **Las 4**: import username, perfil visual, agente Gemini, diseño heredado (Manus) |
| ¿Cuánto meterle al motor? | **A fondo** — candidatos derivados del gusto real |

Implicancia: el foco es el **motor** (Fase 1), pero como portfolio también pesa, hay que **deployar** (Fase 2) y darle **identidad visual propia** (Fase 3). Las 4 dudas se resuelven dentro de esas fases (ver §5 y §7).

---

## 4. Fase 1 — Motor a fondo (prioridad, el core)

**Objetivo:** que el pool de candidatos se construya *desde el perfil de gusto del usuario*, reutilizando lo que ya existe.

**Punto de inyección exacto:** `backend/app/main.py:217`, dentro de `_finish_recommend`, donde hoy dice `candidates = tmdb_client.fetch_candidates(mood)`.

### Pasos

| # | Qué | Reusa | Dependencia |
|---|-----|-------|-------------|
| 1 | **Persistir el perfil de gusto por usuario.** Hoy `build_taste_profile` corre a demanda en `/profile/taste` y hace ~200 requests a TMDb — carísimo por recomendación. Calcularlo al importar y guardarlo (tabla nueva o JSON asociado al usuario) para reusarlo sin recomputar. | `taste_profile.py` entero (ya calcula `genre_breakdown`, `decade_breakdown`, `top_directors`, `top_actors`) | — |
| 2 | **`fetch_personalized_candidates(profile, mood, kind_filter)`** en `tmdb_client.py`: discover de TMDb sesgado al perfil — `with_genres` (2-3 géneros top, OR), `with_people` (directores/actores top; mapear nombre→`person_id` vía `/search/person`, cacheado), `primary_release_date.gte/lte` / `first_air_date` (décadas favoritas, soft), manteniendo `sort_by=vote_average.desc` + `vote_count.gte` como piso de calidad. Combinar varias queries (una sesgada a gente, otra a géneros+década) y unir → pool diverso pero personalizado. | patrones de discover + caché ya en `tmdb_client.py` | Paso 1 |
| 3 | **Mezcla con exploración.** 3-4 slots del perfil + 1-2 "apuesta distinta" fuera del perfil estricto, para no encerrar al usuario en su burbuja (el *why* de "ampliar tu mapa" ya existe en `recommender.py`). | `recommender.py` | Paso 2 |
| 4 | **Sumar señal de director/actor/década al score**, no solo tags coarse. El score de `recommend()` ahora opera sobre un pool ya bueno; el match por tags deja de ser el único filtro. | `recommender.py` | Paso 2 |

### Resultado esperado
- Dos usuarios con gustos opuestos → pools genuinamente distintos.
- El **radar de perfil pasa de decorativo a ser la ventana de las señales que ahora manejan el pick** (resuelve la duda "¿aporta o es decorativo?").
- La **vía username mejora justo la que hoy es más pobre**: aunque no traiga reviews, el género de los títulos amados alcanza para sesgar el pool.

### Riesgos honestos
- El mapeo nombre→`person_id` suma requests a TMDb → **cachear agresivo** (como ya hace `search_title` a 24h). El free tier de TMDb aguanta (~50 req/s), no es Gemini.
- El perfil persistido (paso 1) evita las ~200 requests por recomendación — sin eso, la latencia es inaceptable.
- Cuidar que la combinación de queries no explote el número de requests: pocas queries bien elegidas > muchas.

### Verificación
- Tests de backend en verde (red de seguridad: 128 a la fecha), nuevos tests para `fetch_personalized_candidates`, persistencia y scoring.
- Prueba en vivo con el Letterboxd real de Matías: comparar pool viejo vs nuevo y confirmar que los picks cambian y representan mejor.

---

## 5. Las 4 revisiones que marcó Matías — veredicto

| Cosa | Veredicto | Por qué | Fase |
|---|---|---|---|
| **Perfil visual (radar)** | **Reconvertir, no cortar** | Deja de ser decorativo: es el insumo del motor. Retroactivamente justificado. | 1 |
| **Agente Gemini** | **Mantener best-effort + cachear** | Con el pool ya personalizado, Gemini pesa menos en calidad y más en texto. Cachear por (fuente, mood, picks) mata latencia/quota repetida. No hacerlo protagonista hasta ver si el pool nuevo alcanza. | 1 (caché) |
| **Import por username** | **Mantener** *(decisión abierta, §9)* | Es la vía de entrada más fácil (no exportás nada) → suma para "producto real". Su señal pobre la mejora la Fase 1. | — |
| **Diseño heredado (Manus)** | **Diferir a Fase 3** | No mueve calidad de pick. El tema actual (ámbar/dorado, Instrument Serif) es defendible, no es el violeta-blur genérico. Para portfolio pesa más deploy + buen pick. | 3 |

---

## 6. Fase 2 — Deploy (porque también es portfolio)

Backend → **Render**, frontend → **Vercel** (stack estándar de Matías). Deployeado 2026-07-16: [pelipick.vercel.app](https://pelipick.vercel.app/) + [pelipick-backend.onrender.com](https://pelipick-backend.onrender.com).

**CORS cerrado (2026-07-16):** `allow_origins=["*"]` reemplazado por lista explícita (`PELIPICK_ALLOWED_ORIGINS` en `render.yaml`, default incluye el dominio de Vercel + localhost de dev). Ver `backend/app/main.py`.

**Persistencia cerrada (2026-07-16):** el plan free de Render tiene **filesystem efímero** (confirmado en docs de Render) y los discos persistentes no existen ahí (hace falta plan Starter $7/mes). Supabase free se pausa a la semana de inactividad. Matías no quería pagar nada recurrente, así que se eligió **Neon** (Postgres serverless, plan free permanente, sin tarjeta, sin expiración por tiempo — solo el compute hace scale-to-zero a los 5 min de inactividad, sin borrar datos).

`backend/app/db.py` ahora soporta los dos backends vía la env var `DATABASE_URL`: sin setear, sigue usando SQLite exactamente como antes (dev local y los 150 tests, sin cambios); seteada, usa Postgres. Detalle: dos DDL (`SCHEMA_SQLITE`/`SCHEMA_POSTGRES`), un wrapper chico (`_PostgresConnWrapper`) que traduce `?`→`%s` y expone `execute`/`executemany`/`commit`/`close` para que los ~25 helpers de abajo no se enteren de la diferencia, y `_last_insert_id` para los 3 INSERTs que necesitaban `cursor.lastrowid` (Postgres no lo tiene — usan `RETURNING id`). Nueva dependencia: `psycopg2-binary`. `render.yaml` suma `DATABASE_URL` (`sync: false`, se carga a mano en el dashboard de Render con el connection string de Neon).

Pendiente: el envío real de mail para reset de password (hoy el token no llega al usuario sin `PELIPICK_DEBUG=1`).

---

## 7. Fase 3 — Identidad visual propia (+ evaluar Stitch)

**Objetivo:** que la UI deje de ser "generada por otra IA" y sea identidad propia. Pulido sobre lo que hay, no rehacer de cero. Solo cuando motor + deploy estén.

### Stitch (Google) — a evaluar
Matías pasó un doc de referencia externa (base44), hoy en `D:\Descargas\stitch-code-flow-base44-app.md` — conviene copiarlo a `02 Attachments/` del proyecto al arrancar Fase 3 para versionarlo con el repo. Flujo que propone ese doc:
1. Diseñar en [stitch.withgoogle.com](https://stitch.withgoogle.com/) (gratis, 350 generaciones/mes con cuenta Google), describiendo la app + 2-3 referencias de Dribbble/Pinterest para no caer en look genérico.
2. Exportar el sistema de diseño de dos formas: **(a) `DESIGN.md`** en la raíz del proyecto (vía rápida, tokens exactos de color/tipografía/espaciado), o **(b) servidor MCP de Stitch** conectado a Claude (acceso completo, mejor para multipantalla con cada pantalla mapeada a una ruta).
3. Rematar en Claude Code **instrucción por instrucción** (no un prompt gigante): conectar navegación, animaciones/hover, responsive, y por último espaciados. Stitch da pantallas estáticas; Claude las hace funcionar.

**Notas de Matías (importante):**
- **No va a seguir todo el documento al pie** — hay un par de pasos que no piensa hacer (a definir cuáles cuando lleguemos).
- Se inclina por la **vía MCP** ("exportar el diseño como MCP y conectarlo a Claude, así tiene acceso completo") por sobre el `DESIGN.md` estático.
- "Ya veremos todo eso" → **queda como exploración, no decidido.** Se cierra al arrancar Fase 3.

### Skills de diseño para esta fase
`impeccable` (rediseño/audit/polish/iteración en vivo), `emil-design-eng` (polish de componentes y detalles), `web-design-guidelines` (auditar accesibilidad/UX). Si se meten animaciones: `vercel-react-view-transitions`, `review-animations`, `animation-vocabulary`.

---

## 8. Skills a usar por fase (para que Claude/Codex rindan con mínimo gasto)

Inventario completo en `06 Agent Skills/README.md` del vault. Mapeo por fase:

| Fase / tarea | Skill(s) | Para qué |
|---|---|---|
| **Investigar TMDb Discover API** (Fase 1, paso 2) | `research` | Confirmar params (`with_people`, `with_keywords`, `with_genres` OR, `primary_release_date`), combinación de queries y rate limits contra fuentes primarias, en background, sin gastar contexto principal |
| **Implementar el motor** (Fase 1) | `tdd` | Feature test-first; el backend ya tiene suite (128 tests) y la regla es no cerrar sin tests en verde |
| **Partir el plan en tasks** | `to-issues` + board `TaskCreate` + plugin `codex` | Vertical slices independientes despachadas en paralelo a Codex/subagentes en worktrees separados (ver `AGENTS.md` y `TASKS.md`) |
| **Cerrar cada fase** | `code-review` | Revisar Standards + Spec en paralelo antes de mergear |
| **Cuando algo rompe/está lento** | `diagnosing-bugs` | Loop de diagnóstico para bugs difíciles o rate-limits inesperados |
| **Deploy** (Fase 2) | `research` (Render efímero/Postgres) + `gh` CLI + `webapp-testing` | Confirmar opciones de persistencia, tocar repo/CI, smoke test del deploy |
| **Identidad visual** (Fase 3) | `impeccable`, `emil-design-eng`, `web-design-guidelines`; animaciones: `vercel-react-view-transitions`, `review-animations` | Rediseño, polish, auditoría de UX/accesibilidad |
| **Verificar frontend en vivo** | `webapp-testing` (Playwright) o las preview tools del harness | Screenshots, logs de consola, testear interacciones |
| **Scraping/research web** (import username si Letterboxd cambia) | Nimble MCP / `defuddle` | Extraer markdown limpio de páginas, research web |
| **Cortar sesión a mitad** | `handoff` | Traspaso a otra sesión/agente sin perder contexto |
| **Siempre activo** | plugin `ponytail` (nivel full) | Mantener cada cambio en el mínimo que funcione |

---

## 9. Decisiones abiertas (a cerrar antes o durante cada fase)

1. **Import por username** — ¿mantener (recomendado, la Fase 1 lo mejora) o cortar para simplificar? *(bloquea nada, pero define scope)*
2. **Arrancar por Fase 1** — la primera sub-tarea (persistir perfil + enchufarlo al pool) es acotada y verificable en vivo. ¿Luz verde?
3. **Persistencia en deploy** (Fase 2) — disco persistente de Render (SQLite) vs migrar a Postgres.
4. **Stitch en diseño** (Fase 3) — vía MCP vs `DESIGN.md`; y qué pasos del doc base44 se saltan.

---

## 10. Cómo se ejecuta

- **Workflow multi-agente** vía `TASKS.md` + board `TaskCreate`: Fase 1 se parte en (1) persistir perfil, (2) `fetch_personalized_candidates` + person_id, (3) scoring con nuevas señales, (4) caché de Gemini. La 1→2 tienen dependencia; 3 y 4 pueden ir en paralelo. Worktrees separados si tocan los mismos archivos.
- **Regla de oro:** primero arreglamos lo roto, después avanzamos. No dejar bugs conocidos para después.
- **Tests en verde** antes de cerrar cada tarea. Prefijo `(C)` en archivos generados por Claude; pedir permiso antes de editar archivos sin ese prefijo.
