# Build Log

## 2026-07-23 (sesión 2 — lote rápido del feedback de amigos)

Primer lote del feedback pre-lanzamiento (7 de 20 puntos, los marcados como
"rápidos" en `03 Iteration Logs/(C) 2026-07-23 feedback-amigos-pre-lanzamiento.md`,
donde quedaron tachados con fecha). Todo frontend, verificado con build
limpio y en vivo en el preview local (deslogueado y logueado):

- **CTA "Empezar gratis" abría el login en modo "Entrá"** — ahora apunta a
  `/login?register=1` y `Login.tsx` lee el query param para arrancar en
  modo registro (punto 1).
- **Badge del hero con bajo contraste** sobre el orb terracota — pasó de
  `text-muted-foreground` a `text-foreground` (punto 4).
- **"Sync con Letterboxd →" quedaba fijo aunque ya estuvieras logueado** —
  ahora solo se muestra sin sesión (punto 5).
- **Botón de dark mode sin explicación visual** — `title` nativo dinámico
  ("Cambiar a modo claro/oscuro") + `aria-label` alineado (punto 6).
- **"Home" fuera del navbar** (el logo ya lleva a `/`) y **labels en
  español**: Recomendar / Archivo / Perfil / Entrar (puntos 12 y 13).
- **La pantalla del zip no explicaba cómo conseguirlo** — línea de
  instrucción arriba del dropzone: "Descargalo desde Letterboxd:
  Settings → Data → Export your data" (punto 19).

Análisis del feedback completo: los 20 puntos se reducen a 4 problemas de
fondo — (1) un usuario nuevo no entiende el flujo de `/recommend` (8, 9,
10, 11, 19), (2) la navegación no refleja qué es central ni da entidad al
usuario (12-16, 20), (3) el producto no explica su lógica ni sus límites
donde importa (3, 17), (4) densidad visual en desktop (2). Lo positivo
(paleta, watchlist, explicación de picks) confirma que motor e identidad
visual funcionan — falla el camino de entrada. Próximo: rediseño de
`/recommend` como multi-step (absorbe 7, 8, 9, 10, 11, 17 y mete el 3
adentro).

### Rediseño de `/recommend`: wizard de 3 pasos

Segunda parte de la sesión — ataca el problema de fondo nº 1 (usuarios
nuevos no entendían el flujo). Todo dentro de `Recommend.tsx`, sin rutas
ni componentes nuevos; la lógica de fetch/estado no cambió, solo el shell:

- **Paso 1 "Tu historial"** (fuente): zip / username / manual, cada vía con
  su explicación en contexto. El manual lleva la grilla de puntuar acá, con
  dos textos nuevos: "estas pelis no son recomendaciones — son para
  conocerte" (punto 8, Gaspi) y el aviso honesto de que el modo manual solo
  conoce lo puntuado en la lista, así que puede recomendar algo ya visto
  (punto 17, Simón/Gerardo).
- **Paso 2 "Qué ver"** (modo): cada modo con descripción de una línea
  (punto 10); los deshabilitados muestran el motivo inline. Inaccesible
  hasta completar el paso 1 (punto 9) — Continuar deshabilitado con hint de
  qué falta.
- **Paso 3 "Formato"**: formato + recap de lo elegido ("Fuente: @user ·
  Modo: Perfil completo") + `<details>` nativo "¿Cómo se calculan tus
  picks?" con la explicación honesta del heurístico + refine de IA
  (punto 3) + botón de generar.
- Stepper arriba con pasos completados clickeables para volver; "Cambiar
  búsqueda" desde los resultados vuelve al paso 3 con todo el estado
  preservado (paso 1 y 2 accesibles por el stepper). Cierra el punto 11
  (Pedro) y con él los puntos 8, 9 y 10 de una.

Verificado end-to-end en el preview local: los 3 pasos renderizan y gatean
bien por las tres fuentes, generar produce 6 picks (catálogo mock local por
la TMDb key vieja del `.env`, esperado), volver/avanzar preserva estado.
Build de frontend limpio. Del feedback quedan: 2 (grilla de resultados), 7
(swipe), 14/15 (navbar), 16 (avatares), 20 (perfil real).

## 2026-07-23 (Ola 4 cierre, pulido pre-lanzamiento a amigos, seguridad de sesiones)

Sesión enfocada en cerrar el MVP para mostrarlo a amigos y eventualmente
LinkedIn. Verificado en producción con una cuenta descartable en cada paso
en vez de asumir que un deploy exitoso significa que funciona.

### Ola 4 cerrada + verificación de producción

- Confirmado que Matías ya había seteado `NVIDIA_API_KEY` en Render y
  rotado las credenciales filtradas el 21/07. Verificado en vivo (cuenta de
  prueba en butaca.xyz, borrada después): `refine` de la IA corriendo de
  verdad, ya no cae mudo al heurístico.
- README reescrito bilingüe: `README.md` (inglés, primario — pensado para
  portfolio internacional) + `README.es.md`, cruzados entre sí, con link a
  producción y feature list actualizada. Cierra la tarea J de la Ola 4 —
  **Ola 4 completa** (H onboarding sin Letterboxd, I verificación de email +
  borrar cuenta, J README).
- UptimeRobot confirmado activo por Matías.

### Pulido de UI

- Validación de formulario en Login/Registro reemplazada: se sacaron los
  tooltips nativos feos del browser (`required`/`minLength`/`type="email"`)
  por errores inline en la estética del sitio (`noValidate` + chequeo en
  JS, se limpian al tipear).
- Citas de cine rotativas: `frontend/src/lib/quotes.ts`, 26 frases (12 de
  directores + 14 líneas icónicas de personajes/series), dos distintas por
  carga de página (panel de login + footer), cambian en cada refresh.
- Favicon propio: butaca de cine (papel sobre terracota), SVG + PNG 32px +
  apple-touch-icon 180px. El sitio no tenía ninguno.
- Los 3 picks de "Current picks" en el home ahora son clickeables y abren
  el mismo modal de detalle que `/recommend` (reparto, tráiler, dónde
  verla, feedback). El modal se extrajo de `Recommend.tsx` a un componente
  compartido (`components/MovieModal.tsx`) en vez de duplicarlo.

### Mails con la estética del sitio

- Los mails de reset de contraseña y verificación de email (`mailer.py`)
  pasaron de `<p>` sueltos a un template HTML compartido con la paleta
  "Hybrid critic notebook" (papel/tinta/terracota, radius 0, wordmark +
  labels mono, botón terracota). Confirmado por Matías: el mail de
  verificación llega bien.

### Observabilidad

- Vercel Web Analytics + Speed Insights agregados (`@vercel/analytics`,
  `@vercel/speed-insights`, imports `/react` — el proyecto es Vite, no
  Next, así que las instrucciones default de Vercel no aplicaban tal
  cual). Detalle técnico: el pre-bundling de Vite en dev le daba a estos
  paquetes su propia copia de React ("Invalid hook call"); se resolvió con
  `optimizeDeps.exclude` en `vite.config.ts`. El build de producción ya
  dedupeaba bien — se confirmó sirviendo el `dist/` real antes de asumir
  que estaba roto.

### Seguridad: sesiones con expiración + tokens hasheados

Auditoría rápida de seguridad a pedido de Matías (auth, SQL injection,
CORS, XSS, secretos, rate limiting) — la mayoría ya estaba bien resuelto
(PBKDF2 260k iteraciones, queries parametrizadas, tokens de reset/
verificación ya hasheados con expiración, CORS con allowlist). Dos huecos
reales, corregidos:

- **Sesiones ahora expiran** (30 días) — antes un token de sesión era
  válido para siempre hasta logout o reset de password.
- **Tokens de sesión hasheados en DB** (sha256, mismo criterio que los de
  reset/verificación) — antes vivían en texto plano en `sessions.token`;
  una filtración de la DB de Neon habría regalado todas las sesiones
  activas.
- Migración: agrega `sessions.expires_at`, borra las filas viejas (token
  crudo sin expiración) — un solo re-login para usuarios existentes,
  confirmado contra Neon en producción antes de dar por cerrado.
- 2 tests nuevos (sesión vencida rechaza, token crudo nunca toca la DB).
  204 tests en verde.

### Feedback de amigos (pendiente de trabajar)

Se juntaron 20 puntos de feedback de gente probando el sitio (Gaspi,
Pedro, Simón, Gerardo) más notas propias — sin actuar sobre ellos todavía,
a propósito. Detalle completo, agrupado, en
[`03 Iteration Logs/(C) 2026-07-23 feedback-amigos-pre-lanzamiento.md`](../03%20Iteration%20Logs/(C)%202026-07-23%20feedback-amigos-pre-lanzamiento.md).

## 2026-07-20 (rebrand a Butaca + fix de /health para uptime monitors)

### Fix: `/health` devolvía 405 a los monitores de uptime

Al conectar UptimeRobot (Fase 0.3 del plan maestro) el monitor empezó a
reportar "incident: 405 Method Not Allowed" desde 4 regiones. **Falso
positivo, no una caída**: UptimeRobot prueba con `HEAD` por default y el
endpoint estaba declarado como `@app.get("/health")` únicamente, así que
FastAPI respondía 405 a cualquier HEAD. Confirmado a mano contra producción:
`GET` → 200, `HEAD` → 405, `POST` → 405. Fix: `@app.api_route("/health",
methods=["GET", "HEAD"])` en `backend/app/main.py` + test de regresión
(`test_health_accepts_get_and_head`, primer test que cubría `/health`).
179 → 180 tests.

Cambiar el método del monitor a GET del lado de UptimeRobot resultó ser
feature paga, así que **el monitor quedó pausado** hasta que se deploye este
fix — sin deploy, seguiría alertando falsos positivos cada 5 minutos.

### Rebrand: PeliPick → Butaca

Decisión de producto: "PeliPick" no convencía (claro pero genérico, no
transmitía la voz editorial/de crítico del producto). Se eligió **Butaca**
(la butaca del cine): cálido, cinéfilo, alineado con la identidad visual
"Hybrid critic notebook". Momento deliberado: sin lanzar, con 4 usuarios y
sin dominio comprado — el punto más barato para renombrar.

Disponibilidad de dominio chequeada vía RDAP (registro oficial, más confiable
que el buscador de un registrador): `butaca.com`, `.app`, `.tv`, `.net`,
`.club`, **`.ar` y `.com.ar`** están **tomados** ("butaca" es palabra común,
registrada hace años). **Libres:** `butaca.io`, `butaca.co`, `butaca.me`,
`butaca.film`, `butaca.cool`, `butaca.fun`, más los `.com` con prefijo
(`getbutaca`, `verbutaca`, `butacacine`). Sin comprar todavía.

Rename ejecutado con un script de reemplazos ordenados y específicos (no un
sed global, que habría roto las URLs de deploy). Reglas aplicadas:
`PELIPICK_` → `BUTACA_` (env vars), `PeliPick` → `Butaca` (marca),
`pelipick-frontend` → `butaca-frontend`, `pelipick_token` → `butaca_token`,
`pelipick-theme` → `butaca-theme`, `pelipick.db` → `butaca.db`. 35 archivos
+ `.claude/launch.json` (editado aparte). El archivo físico
`backend/pelipick.db` se renombró también, para no perder los datos de dev
local. 180 tests en verde, build de frontend limpio.

**Deliberadamente NO renombrado** (identidad real del deploy — cambiarlo en
código sin renombrar antes los proyectos en Vercel/Render rompe CORS y la
API): `pelipick.vercel.app`, `pelipick-backend.onrender.com`, y el
`name: pelipick-backend` de `render.yaml`. Esas ~6 referencias se actualizan
recién *después* de renombrar los proyectos en los dashboards (o de comprar
un dominio propio y apuntarlo). También se dejaron los nombres históricos de
worktree (`pelipick-codex`, `pelipick-gemini`) como registro del pasado.

## 2026-07-20 (migración de Neon a la misma región que Render)

Fase 0.1 del plan maestro (`docs/(C) plan-maestro-release.md`): la base de
Postgres vivía en Neon `sa-east-1` (São Paulo), mientras el backend en Render
corre en Oregon (US West) — cada query cruzaba de continente. Hallazgo
concreto: no era "otra región de AWS", era otro continente entero, peor de lo
que documentaba `architecture.md` hasta ahora (que hablaba de "~400-500ms,
cross-region" en genérico).

Migración: proyecto Neon nuevo creado en `us-west-2` (Oregon, matchea la
región de Render), connection string **sin pooling** (el backend ya pooleaba
conexiones propias vía `ThreadedConnectionPool` en `db.py` — sumar el pooler
de Neon encima habría sido un intermediario redundante con restricciones de
PgBouncer transaction-mode sin beneficio real a esta escala). Copiado con un
script Python ad-hoc (`psycopg2` directo, ya dependencia del proyecto — no
hizo falta instalar `pg_dump`/`psql`), reusando `backend/app/db.py::
get_connection()` para crear el schema en el destino con la misma lógica que
ya corre la app, en vez de duplicar el SQL. Copia tabla por tabla en orden
FK-safe, preservando IDs y reseteando las secuencias `SERIAL` al final.
Verificado con conteo de filas por tabla antes de cortar: 4 usuarios, 11
sesiones, 856 `rated_items`, 4 `recommendation_sessions`, 20 recomendaciones
servidas, 1 feedback, 1 taste profile — coincidencia exacta en las 9 tablas
con datos (`watchlist_items` no existía en el origen, tabla nueva de esta
sesión, aún no deployada en ese momento).

Medido con curl contra producción tras cambiar `DATABASE_URL` en Render:
login con credenciales inválidas (3 idas a la base: `get_login_attempt`,
`get_user_by_username`, `save_login_attempt`) pasó de un baseline de ~2.85s
(login exitoso, 4 idas a la base, medido 2026-07-18 con la base en São Paulo)
a **0.59s** con la base en Oregon. Proyecto viejo de Neon (São Paulo) se deja
sin borrar unos días como colchón antes de eliminarlo.

## 2026-07-20 (plan de release, olas 1-3: velocidad, feedback loop, watchlist, providers, render progresivo)

Ejecución de las primeras 3 olas del plan de implementación
(`docs/(C) plan-implementacion-codigo.md`, compañero de
`docs/(C) plan-maestro-release.md`). 160 → 179 tests de backend en verde,
build de frontend limpio en cada ola. Todo secuencial en una sesión (Opus),
no repartido a subagentes.

### Ola 1 — velocidad y fundaciones

- **Warm-up del backend** (`frontend/src/hooks/useAuth.tsx`): `fetch("/health")`
  fire-and-forget al montar la app, para que el cold start de Render (~1min)
  transcurra mientras el usuario mira la landing / tipea el password, en vez
  de bloquear su primera request real. Cubre al visitante deslogueado (el
  logueado ya despertaba el backend vía `/auth/me`).
- **Rate limiting de `/recommend/*` por usuario** (`main.py`, `db.py`): tope
  diario configurable por `BUTACA_RECOMMEND_DAILY_LIMIT` (default 20, `0`
  = off), contando `recommendation_sessions` del día actual — sin tabla ni
  estado en memoria nuevos, sobrevive restarts y multi-proceso. Protege las
  cuotas de TMDb/NIM antes de abrir al público. 429 al pasarse.
- **Endpoint de métricas** (`GET /admin/stats`): lee por fin las métricas
  definidas en `product-mvp.md` (usuarios, sesiones totales/7d/30d, feedback
  por status y su % sobre picks servidos). Gateado por header
  `X-Admin-Token` == `BUTACA_ADMIN_TOKEN`; sin esa env el endpoint 404ea
  (no existe en prod sin setup deliberado), token malo → 403. Sin dashboard,
  se consulta con curl.
- **Feedback loop en el scoring** (`recommender.py`, `main.py`, `db.py`): la
  tabla `feedback` se escribía pero nunca se leía. Ahora `get_feedback_signals`
  arma las señales y `_finish_recommend` las usa: los títulos marcados
  `seen`/`not_interested` son exclusión **dura** (no se relaja en el retry de
  pool agotado, a diferencia de "ya recomendado"), y los tags de los picks
  rechazados **2+ veces** penalizan el score (`-15 * proporción`; umbral de 2
  para no fundir un género entero del perfil por un rechazo suelto).

### Ola 2 — calidad del pick

- **Modo watchlist** (`letterboxd_zip.py`, `db.py`, `main.py`,
  `Recommend.tsx`): cuarto modo "de mi watchlist". `parse_watchlist_titles`
  lee `watchlist.csv` del zip (función separada a propósito, para no cambiar
  la aridad del return de `parse_letterboxd_zip` y romper todos los
  unpackings de tests). Tabla `watchlist_items` (replace-all por import,
  solo si el zip trae la lista no-vacía). En modo watchlist los candidatos
  salen de matchear la watchlist contra TMDb (`search_title` en paralelo,
  cap 60) en vez del discover. El import por username no la trae → se apoya
  en un zip previo; watchlist vacía → 400 con mensaje claro. En el frontend
  el modo se deshabilita (con nota) cuando la fuente es username.
- **"Dónde verla"** (`tmdb_client.py`, `models.py`, `main.py`,
  `Recommend.tsx`): `fetch_watch_providers` contra `/watch/providers` de TMDb
  (datos JustWatch), región por `BUTACA_WATCH_REGION` (default AR), cacheado
  24h. Sección nueva en el modal de detalle con streaming/alquiler/compra y
  atribución obligatoria a JustWatch; degrade gracioso si falla (el resto del
  detalle sigue). `_search_one` se extendió para devolver
  poster/backdrop/overview/vote (los consume el modo watchlist).

### Ola 3 — render progresivo

- **Picks heurísticos al instante, razones del LLM después** (`main.py`,
  `db.py`, `models.py`, `Recommend.tsx`): los endpoints de recomendación
  aceptan `refine` (default "1"); el frontend manda `refine=0` y renderiza el
  heurístico al toque, después llama a `POST /recommend/sessions/{id}/refine`
  que re-corre el LLM sobre los picks ya servidos, persiste las razones
  reescritas + el resumen, y devuelve `refined: true` (o `false`, 200 no
  error, si el LLM no está o falla → el frontend deja el texto heurístico).
  El frontend parchea `why` + `taste_summary` por id (preserva director y
  orden, sin migración de schema), con guarda anti-refine-viejo por
  `session_id`. Indicador discreto "puliendo las razones…" mientras corre.
  No acelera nada real, pero saca los ~5-15s del LLM del camino crítico del
  primer render.

### Pendiente de la Ola 4 (no ejecutado en esta sesión)

Onboarding sin Letterboxd (H) y verificación de email + borrar cuenta (I)
quedan para una próxima sesión (mayor superficie de frontend nuevo, e I está
acoplado al setup de Resend en curso). README en inglés (J) bloqueado: ya
existe un `README.md` en español en la raíz (sin prefijo `(C)`), no se pisa
sin permiso.

## 2026-07-20 (rediseño de /recommend: showcase, scoring nuevo, fix de regenerado)

### Botón Home en el nav

Faltaba un link directo al home en el navbar — se agregó a `NAV_ITEMS` en
`Navbar.tsx`, entre el logo y "Recommend".

### Comparación línea por línea con `/recommend` de Lovable

Se había portado la home ("Current picks") del prototipo de Lovable el
18/07, pero no la página `/recommend` completa (sidebar de fuente/modo +
grilla de resultados), que resultó tener su propia data mock ("The Long
Goodbye" 94%, "Yi Yi" 89%, etc.) y su propio markup. Comparando el HTML
generado clase por clase contra el real:

- **6 recomendaciones en vez de 5**: límites de `_pick_with_genre_coverage`
  y `_pick_with_exploration` (`recommender.py`) y el corte `reordered[:5]`
  del refine de NVIDIA (`llm_client.py`) pasaron a 6.
- **Grilla a 2 columnas** (`grid-cols-1 sm:grid-cols-2`, sin
  `lg:grid-cols-3`) en vez de 3 — posters más grandes, coincide con el
  original.
- **Animación de tilt 3D + glare en el poster al hacer hover**: rotateX/
  rotateY calculado a partir de la posición del mouse relativa a la card
  (imperativo, escribe directo al DOM vía ref para no perder cuadros en
  cada mousemove), gradiente radial que sigue el cursor vía CSS custom
  properties (`--mx`/`--my`) con `mix-blend-overlay`, badge de match con
  `translateZ(40px)` para el efecto de profundidad. Extraído a
  `frontend/src/hooks/useTiltCard.ts` (hook compartido) y reusado en
  `CurrentPickCard` del home — mismo tratamiento en los dos lugares donde
  se muestran posters de recomendaciones.
- **Línea "Dir. X • género"** en el pie de cada card en vez del dump crudo
  de tags: se agregó `director: str | None` a `Recommendation`
  (`models.py`), poblado desde el dato que `tmdb_client.py` ya calculaba
  para el scoring de director pero nunca exponía. Solo está disponible
  para el subset de candidatos enriquecidos con créditos de TMDb (no
  series, no el slice de "exploration") — cuando falta, cae al formato
  anterior de tags.

### `match_score`: de aditivo-y-clampeado a curva `tanh`

El score viejo (`50 + bonus fijos por señal`, clampeado a `[1, 99]`)
empujaba cualquier pila de bonus grande al mismo 99% — varios picks fuertes
quedaban indistinguibles, y el desempate cae al orden de catálogo. Nuevo
criterio en `recommender.py`:

- Evidencia proporcional en vez de conteo crudo: matchear 3 de 3 tags del
  candidato pesa más que 3 de 8 (un match focalizado vs. uno diluido).
- `match_score = round(50 + 49 * tanh(puntos / 40))`: 50% sigue siendo el
  punto neutro (cero evidencia), pero la curva tiene rendimientos
  decrecientes y 99% queda asintótico — hace falta casi evidencia perfecta
  para rozarlo, en vez de cualquier stack de bonus grande.
- El orden del ranking usa los puntos float sin redondear, así el
  redondeo del % mostrado nunca genera empates falsos.

Dos tests nuevos fijan el comportamiento (picks fuertes mantienen scores
distintos sin clavarse en 99, candidato focalizado le gana al diluido); un
test viejo que fijaba el empate-en-99-desde-el-score-interno quedó
reescrito para fijar la propiedad que sigue importando (orden por score,
nunca por posición de catálogo).

### Bug real: "Nuevos picks" agotaba el pool de candidatos

A pedido de Matías, "↻ Nuevos picks" pasó de volver al menú a regenerar
in-place con la misma fuente/modo/género ya cargados (nuevo botón separado
"Cambiar búsqueda" para lo que hacía antes). Esto expuso un bug preexistente:
cada `/recommend` excluye del pool todo lo ya recomendado antes al usuario
(`get_recently_recommended_titles`, últimos 100 títulos) — con el regenerado
in-place ese pool se agota mucho más rápido, y al agotarse el backend
devolvía `recommendations: []` con **200 OK** (no un error de red). El
frontend interpretaba cualquier lista vacía como "No pude leer ratings
válidos de esa fuente" — mensaje falso: el archivo se había leído bien, lo
que se acabó fueron los candidatos nuevos. Reproducido en logs reales de
Matías (`picks=0 discarded_rows=4`, cuatro veces seguidas). Fix:

- Backend (`main.py`): si `recommend()` devuelve vacío por la exclusión de
  ya-recomendados, reintenta sin esa exclusión antes de fallar — mismo
  criterio que ya usaba `recommender.py` ("preferimos resurfacear un pick
  viejo a devolver cero").
- Frontend: si la lista vuelve vacía en un regenerate (ya había `result`
  previo), el mensaje ahora dice lo que realmente pasó — "no encontré picks
  nuevos, ya te mostré todo lo que tenemos, probá cambiar modo/género/
  formato" — en vez de acusar a la fuente de datos.

Verificado hammereando el botón contra el backend real hasta agotar el pool
de un usuario de prueba (6→3 resultados en clicks sucesivos, sin ningún
`picks=0` ni error después del fix).

### Cartel de "N filas no se pudieron importar": sacado

El toast de `discarded_rows` (que además tenía un bug de gramática —
"no se pudoieron importar", por concatenar "pudo" + "ieron" en vez de
conjugar singular/plural bien) aparecía en cada `/recommend/zip`,
incluidos los regenerados con el mismo archivo. Al revisar `csv_ingest.py`
quedó claro que esas filas descartadas son casi siempre títulos logueados
**sin rating** en Letterboxd (uso normal — se puede loguear una vista sin
puntuarla), no un problema real del import. Matías pidió sacarlo
directamente: se quitó el toast en `Recommend.tsx`, pero se dejó intacto
el resto de la cadena (`discarded_rows` lo sigue devolviendo la API y
logueando el backend), por si en algún momento sirve para un panel menos
intrusivo.

### Header de resultados: resumen de gusto ya no se corta

El `taste_summary` iba en la misma línea que "↻ Nuevos picks", con
`truncate max-w-md` — con resúmenes largos se leía cortado contra el
botón. Pasó a su propia línea debajo del header, sin truncar.

Verificado en vivo contra el backend local (con TMDb/NVIDIA reales) en
cada paso: 160 tests de backend en verde, typecheck de frontend limpio.

## 2026-07-18 (comparación con Lovable, fixes de producción, performance)

### Dark mode: grain layer se aplastaba a negro

El fondo con textura granulada del hero (`grain-layer` en `index.css`) se
veía bien en modo claro pero prácticamente invisible en oscuro. Causa:
`mix-blend-mode: overlay` con ruido negro sobre un fondo casi negro da
`2*base*blend ≈ 0` — el overlay funde el ruido con el fondo en vez de
resaltarlo. Fix: en `.dark .grain-layer` se invierte el ruido a blanco
(`filter: invert(1)`) y se cambia a `mix-blend-mode: screen` (el
equivalente que aclara en vez de oscurecer), para que la textura se lea con
la misma intensidad en los dos temas.

### Comparación con el prototipo de Lovable (`pixel-perfect-clone-61381`)

Se navegó el prototipo visual hecho en Lovable (datos mock, sin backend
real) para identificar diferencias que valía la pena portar al proyecto
real:

1. **Current picks en el home** — integrado usando la sesión de
   recomendaciones más reciente del usuario vía `GET /history` (no datos
   de relleno): 3 picks con poster, badge de `match_score`, título/año y el
   "why", reusando el patrón de tarjeta que ya existía en `History.tsx`.
   Solo se muestra si el usuario está logueado y ya tiene al menos una
   sesión — para el resto, la sección no aparece.
2. **Catalog statistics en el footer** — los números de Lovable (42.8k
   películas, 1.2k directores, 250+ géneros) eran inventados para el
   prototipo estático. Se optó por traer datos reales: nuevo endpoint
   `GET /catalog/stats` en `tmdb_client.py`/`main.py` que cuenta
   películas/series del mismo pool de TMDb del que salen las
   recomendaciones (`vote_count.gte=200`, igual que `fetch_candidates`) y
   géneros (unión de los ids de género de película+TV ya mapeados en el
   cliente), cacheado 24hs. Números reales en prod: ~15K películas, ~2.5K
   series, 27 géneros.
3. **Mapa de afinidad roto en producción** — reportado como "Failed to
   fetch" en `/profile/taste`. Causa raíz: `save_taste_profile`
   (`db.py`) usaba `datetime('now')`, función de SQLite que no existe en
   Postgres (Neon en Render) — cada perfil nuevo tiraba una excepción no
   manejada. Como esa excepción escapaba el middleware de CORS antes de
   poder adjuntar los headers `Access-Control-*`, el browser la reportaba
   como fallo de red en vez de mostrar el 500 real, lo que hizo el
   diagnóstico bastante más largo de lo que hubiera sido con un error
   claro. Fix: el timestamp se calcula en Python (mismo formato
   `YYYY-MM-DD HH:MM:SS` UTC que ya usan el resto de las tablas vía
   `_PG_NOW`) en vez de un literal SQL específico de un solo motor. Se
   sumó además un exception handler global (`@app.exception_handler(Exception)`)
   para que cualquier futuro 500 no manejado mantenga los headers CORS —
   que el error real llegue al frontend en vez de disfrazarse de "Failed
   to fetch".

Verificado en vivo contra producción (Render + Neon) reproduciendo el bug
con curl antes del fix y confirmando el 200 después del redeploy.

### Performance: por qué todo se sentía lento

A pedido explícito de Matías ("que no tarde en loguearse, que elija las
películas más rápido"), se perfiló en vivo contra el backend de
producción y se encontraron dos cuellos de botella reales, no percepción:

1. **Cada llamada a `db.get_connection()` recreaba el schema entero y
   corría las migraciones**, además de abrir una conexión nueva por
   request sin pool — y cada round trip cruza la región de Render a la
   de Neon (São Paulo). Un login hacía 2-3 de estas conexiones. Medido con
   curl contra producción: cada `get_connection()` bajó de ~2.9s a ~0.85s
   (ya no repite schema/migraciones, solo paga el round trip real de la
   query), y **login completo pasó de ~8s a ~2.85s** — sigue
   dominado por esas 2-3 queries secuenciales cruzando región, que el pool
   no elimina, solo el trabajo redundante que se hacía antes de cada una.
   Cambio en `db.py`: `ThreadedConnectionPool` de `psycopg2` (ya era una
   dependencia, sin sumar nada nuevo) creado una sola vez, y el schema/
   migraciones ahora corren una única vez por proceso (guardado por
   target — db path para SQLite, URL para Postgres — no un bool global,
   para no romper el aislamiento de tests que apuntan cada uno a su propio
   archivo temporal).
2. **`build_taste_profile` y `_enrich_loved_ratings_with_genre_tags`
   hacían hasta ~200 llamadas secuenciales a TMDb** (una película a la
   vez, cada una ~0.9s desde acá). Paralelizado con
   `concurrent.futures.ThreadPoolExecutor` (10 workers, stdlib, sin
   dependencia nueva) — son llamadas de red bloqueantes, no cómputo, así
   que un thread pool da concurrencia real pese al GIL. Con un import de
   45 películas nuevas (peor caso, nada cacheado): de lo que hubiera sido
   ~100s+ secuencial a **~11.6s** medido en vivo. De paso se corrigió una
   condición de carrera latente en las 5 cachés en memoria de
   `tmdb_client.py` (`del cache[key]` → `cache.pop(key, None)`): con
   acceso concurrente, dos threads pueden evaluar la misma entrada vencida
   al mismo tiempo, y el segundo `del` tiraba `KeyError` al intentar
   borrar algo que el primero ya había borrado.

Verificado: 158 tests en verde, timing medido con curl antes/después
contra Neon real (incluyendo una prueba de carga concurrente de 8
requests simultáneos al pool, sin errores), y contra el backend de
producción para el fix de conexión.

### Limpieza

Se registraron y luego borraron (en cascada, todas las tablas
relacionadas) varias cuentas de prueba usadas para reproducir bugs y medir
performance, tanto en el SQLite local como en el Postgres de producción
(Neon) — nada de esto quedó en ninguna de las dos bases.

### Pendiente

- pushear el fix de performance (conexiones + paralelización TMDb) — se
  hace en este mismo commit
- sigue pendiente de antes: Matías tiene que crear la cuenta de Resend y
  setear `RESEND_API_KEY` en Render para que el mail de recuperación de
  contraseña funcione con usuarios reales (no solo en debug)

## 2026-07-11 (flujo multi-agente: TASKS.md, Codex, review, merge)

### Qué se armó

Se decidió sumar Codex (y evaluar Gemini) trabajando en paralelo sobre el
mismo repo, dividiendo tareas en vez de duplicar trabajo. Setup:

- `TASKS.md` en la raíz: tablero de coordinación (Pending/In
  Progress/Blocked/Done, owner, archivos tocados, dependencias).
- Un worktree de git por agente (`pelipick-codex`, `pelipick-gemini`),
  cada uno en su propia rama, arrancando desde `claude/zip-upload` para no
  repetir ese trabajo.
- Gemini no terminó participando — `pelipick-gemini` quedó sin usar.
- A Codex se le asignaron `cache-001` (caché de TMDb) y `auth-001` (rate
  limiting de login + recuperación de contraseña), con un prompt que
  incluía las restricciones de stack de `AGENTS.md` explícitas (para no
  repetir el problema de la sesión de Gemini, que había reescrito todo el
  backend a Node sin que se lo pidieran).

### Lo que entregó Codex

`auth-001`: rate limiting por username con backoff exponencial (tope 15
min), recuperación de contraseña con token de un solo uso hasheado en
SQLite, expira a la hora, invalida sesiones viejas al usarse. `cache-001`:
caché en memoria de `/discover/movie` y `/discover/tv` (TTL 5 min, tope 32
entradas, LRU). 51 tests, todo documentado.

### Revisión de Claude antes de mergear — 2 problemas reales encontrados

1. **Encoding roto**: el editor de Codex metió BOM + mojibake (bytes UTF-8
   reinterpretados como cp1252 y reencodeados, ej. "ó" → "Ã³") en los 10
   archivos que tocó. Se detectó comparando el diff, se revirtió con el
   mecanismo inverso (encode cp1252 → decode UTF-8), verificado a nivel de
   codepoint. Commit `a5b4a4e`, sin cambios de comportamiento.
2. **Crítico de seguridad**: `POST /auth/forgot-password` devolvía el
   `reset_token` en la respuesta HTTP a cualquiera que supiera un
   username — combinado con que `/auth/register` ya confirma con `409` si
   un username existe, esto permitía tomar cualquier cuenta en 3 requests
   sin tocar el email de nadie. Estaba documentado como limitación
   temporal (sin proveedor de mail), pero exponerlo así igual era
   inseguro. Fix: `reset_token` ahora solo viaja en la respuesta si
   `BUTACA_DEBUG=1` está seteado a mano — nunca por default, nunca en
   producción. Verificado en vivo (con y sin la env var) y con test
   negativo nuevo. Commit `4b7f80e`.

También se sincronizaron `mvp-status.md`/`architecture.md`, que habían
quedado desactualizadas (seguían listando cache/rate-limiting/recuperación
de contraseña como pendientes).

### Merge y push

`codex/auth-001` (que ya traía `claude/zip-upload` en su base) se
fast-forward-mergeó a `main` sin conflictos y se pusheó a GitHub —
`bf855e0`. 52/52 tests, build de frontend limpio (con `node_modules`
recién instalado en el worktree de Codex, no venía).

### Siguiente ronda

`TASKS.md` actualizado: `cast-001` (cast y tráiler, yo/Claude, rama
`claude/cast-001`) e `historial-001` (historial de sesiones, Codex, rama
`codex/historial-001`), ambas arrancando desde el `main` ya actualizado.
`perfil-001` queda pendiente para después.

**Nota para quien retome esto**: antes de pedir cast/tráiler hace falta
guardar el `id` real de TMDb en el pipeline — hoy `Recommendation` y
`recommendations_served` solo tienen título/año, no id. Ver la entrada de
`cast-001` en `TASKS.md` para el detalle de qué archivos hay que tocar.

## 2026-07-11 (import del .zip completo de Letterboxd)

### Por qué

Se miró un export real de Letterboxd de un usuario (`letterboxd-*.zip`,
~20KB, 227 pelis vistas): trae `watched.csv`, `ratings.csv`, `diary.csv`
(con `Rewatch`/`Tags`), `reviews.csv`, `watchlist.csv`, `profile.csv` (con
`Favorite Films`), `likes/films.csv`, y más — mucha señal de gusto real que
un solo CSV pegado a mano no tiene. Se decidió que el usuario suba el
`.zip` completo en vez de pegar/subir un CSV suelto.

### Backend

- nuevo `backend/app/letterboxd_zip.py`: abre el zip en memoria
  (`zipfile`+`io` stdlib) y combina señales:
  - base: `reviews.csv` (preferido, trae texto) o `ratings.csv`
  - `diary.csv` → boost de +0.5 al rating si `Rewatch` es `Yes`
  - `likes/films.csv` → rating sintético 4.5 para lo que tiene ❤️ y no
    estaba puntuado
  - `profile.csv` → `Favorite Films` (URIs `boxd.it/xxxx`) resueltas
    cruzando contra `Letterboxd URI` de `watched.csv` — sin pegarle a
    ningún servicio externo, todo sale del mismo zip — y agregadas como
    rating sintético 5.0
  - `watched.csv` → set de exclusión ampliado (antes solo se excluía lo
    puntuado, ahora todo lo visto)
- `recommender.py`: `recommend()` suma un parámetro `also_seen` para la
  exclusión ampliada
- `main.py`: se reemplazó `POST /recommend/csv` (JSON con `csv_content`)
  por `POST /recommend/zip` (`multipart/form-data`, campo `file` + `mood`)
  — un zip es binario, no tiene sentido meterlo en JSON. Se sacó
  `CsvRecommendRequest` de `models.py`, ya no se usa.
- nueva dependencia real (antes transitiva): `python-multipart`, la pide
  FastAPI para parsear `multipart/form-data`
- límite de 20MB por zip (los reales pesan decenas de KB, es solo un techo
  de seguridad)

### Frontend

- `Recommend.tsx`: se sacó el textarea de "pegar CSV" (no tiene sentido
  pegar un zip como texto) y el file input ahora solo acepta `.zip`. El
  POST se arma con `FormData`, no JSON.

### Verificado

- 45 tests de backend (35 → 45: 10 nuevos entre `letterboxd_zip` y
  `recommender`, más migración de los viejos tests de `/recommend/csv` a
  `/recommend/zip`)
- build de frontend limpio
- probado end-to-end contra el zip real: 209 ratings base + 5 likes sin
  puntuar previamente + favoritos resueltos correctamente vía cruce de
  URIs = 214 ratings finales, 226 títulos en la exclusión ampliada por
  `watched.csv`

### Limpieza

- se borró `docs/prompt-for-gemini-csv-parser.md`: quedó obsoleto, ya no
  tiene sentido endurecer un parser de CSV pegado a mano cuando ahora se
  lee el zip con formato fijo de Letterboxd directamente
- `docs/csv-format.md` renombrado a `docs/letterboxd-zip-format.md`

## 2026-07-11 (series en el catálogo)

### `/discover/tv` sumado al catálogo real

- `backend/app/tmdb_client.py`: agrega `DISCOVER_TV_URL` + `TV_GENRE_ID_TAG_MAP`
  (los ids de género de TV de TMDb son un set distinto al de películas — sin
  Romance/Thriller/Horror standalone) + `MOOD_TV_GENRE_ID_MAP` (solo `funny` y
  `action` tienen género de TV limpio)
- `_map_result` ahora recibe `kind` y `genre_tag_map`, y lee `name`/
  `first_air_date` para series en vez de `title`/`release_date`
- `fetch_candidates` pega a `/discover/movie` y `/discover/tv` y devuelve
  ambos catálogos concatenados

### Bug encontrado y arreglado: empates de score enmascaraban a las series

- al probar el flujo real con series de por medio, nunca aparecían en el
  top 5 pese a llegar bien taggeadas como candidatas
- causa raíz: `recommend()` ordenaba por `match_score`, que ya viene
  clampeado a 99 — muchos candidatos empatan ahí, y con orden estable el
  empate siempre caía del lado de las películas (listadas primero en el
  catálogo combinado), agravado por la penalización de -8 a series
- fix: ordenar por el score crudo (sin clamp) y clampear solo para mostrar;
  este bug ya afectaba la calidad del ranking en general (no solo series),
  simplemente era invisible con el catálogo mock de 8 títulos
- test de regresión: dos candidatos que empatan en `match_score` (99) pero
  difieren en score crudo deben ordenarse por el crudo, no por posición en
  el catálogo
- badge "Serie" agregado en el frontend (`Recommend.tsx`) — el campo `kind`
  ya viajaba pero nunca se renderizaba, y ahora que aparecen series reales
  hacía falta distinguirlas visualmente de las películas
- 3 tests nuevos (32 → 35)
- verificado end-to-end contra TMDb real: series aparecen en el top 5 y se
  ven con el badge correcto en la UI

## 2026-07-11 (agente de IA)

### Gemini conectado

- se evaluó pagar $5 de créditos en OpenAI; se optó por arrancar gratis con
  Gemini (`gemini-2.0-flash`, free tier de Google AI Studio, sin tarjeta) y
  reevaluar OpenAI solo si la calidad no alcanza o se pega el límite
- `backend/app/llm_client.py`: cliente stdlib `urllib` (mismo patrón que
  `tmdb_client.py`, sin sumar SDK), pide `responseSchema` para JSON
  estructurado
- el agente recibe los candidatos ya filtrados por el heurístico + TMDb,
  elige y ordena como máximo 5 y reescribe resumen/razones — nunca inventa
  títulos ni metadata (se descarta cualquier pick que no matchee por título
  exacto contra la lista)
- fallback al resultado heurístico si Gemini falla, no está configurada, o
  devuelve picks fuera de la lista de candidatos — mismo patrón que TMDb
- 7 tests nuevos (25 → 32), mockeando la llamada HTTP a mano
- doc nueva: [gemini-setup.md](gemini-setup.md)
- se probó contra la API real con la key del usuario: `gemini-2.0-flash`
  devolvía cuota 0 en el free tier para esa key puntual, se cambió a
  `gemini-flash-latest` y ahí sí respondió — verificado end-to-end
  (reordena picks, reescribe resumen y razones en base al historial real)

## 2026-07-11

### Persistencia, login y feedback

- SQLite (stdlib `sqlite3`, sin ORM), tokens de sesión opacos, passwords con
  PBKDF2 — cero dependencias nuevas
- feedback explícito por pick (me interesa / no me interesa / ya la vi)

### Catálogo real con TMDb

- `/discover/movie` mapeado a nuestro vocabulario de tags (género + overview)
- fallback al catálogo mock si TMDb falla o no hay key configurada

### UI/UX generada externamente, adaptada a mano

- el usuario generó un frontend completo con otra IA (plataforma "Manus"):
  Node/tRPC/Drizzle/MySQL en el server, React/Tailwind/Radix con tema
  "cinematic" en el cliente
- se investigó el zip con agentes antes de tocar nada: el diseño asumía un
  backend más rico que el nuestro (perfil de gusto con gráficos, sesiones
  revisitables, cast/tráiler, explicaciones por LLM)
- decisión: nos quedamos solo con la UI/tema, tiramos el server entero, y
  reconectamos las páginas a nuestro FastAPI existente — sin construir las
  features que ese backend hubiera necesitado
- se verificó código real (no solo lo "disponible") antes de portar
  dependencias: ninguna página usaba los componentes shadcn/ui/Radix del zip,
  así que no se portaron
- póster/backdrop/overview/rating de TMDb ahora viajan hasta el frontend
  (ya venían gratis en la respuesta que se pedía)
- quedó afuera, documentado: perfil de gusto con gráficos, historial de
  sesiones, cast/tráiler en el modal

## 2026-07-10

### Base del producto

- se definió el MVP en [product-mvp.md](product-mvp.md)
- se eligió la dirección visual `Crítico Moderno` en [design-directions.md](design-directions.md)

### Vertical slice técnica

- se armó `FastAPI` para health y recomendación
- se armó `React + Vite` para onboarding y results
- se agregó recomendador heurístico con catálogo mock
- se validó backend con tests y frontend con build

### Ingesta manual

- se reemplazó el historial hardcodeado por carga manual de `CSV`
- se agregó parser backend para columnas tipo `Name`, `Rating`, `Review`
- se agregó endpoint `POST /recommend/csv`

### Iteración web

- se mejoró la home para que explique mejor qué hace el producto
- se agregó una sección de workflow y una de señales de gusto
- se buscó que la app se sienta menos "formulario técnico" y más producto editorial

### Documentación técnica mínima

- se agregó una doc de arquitectura actual
- se agregó una doc del formato CSV soportado
- se agregó una doc mínima de endpoints
- se agregó una doc de estado del MVP

### Siguiente foco

- endurecer parser contra export real de Letterboxd
- persistir feedback del usuario
- conectar catálogo real
