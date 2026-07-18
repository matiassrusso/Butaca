# Log de sesión — 2026-07-17

> Deploy hardening + persistencia Postgres + rediseño visual completo + fix cold start.
> Todo commiteado y pusheado a `main`. Backend en Render, frontend en Vercel (redeploy
> automático al pushear).

## Hecho esta sesión

### 1. Verificación de deploys
- Frontend [pelipick.vercel.app](https://pelipick.vercel.app/) y backend
  [pelipick-backend.onrender.com](https://pelipick-backend.onrender.com) confirmados
  funcionando. Docs (`CLAUDE.md`, `AGENTS.md`) actualizados con las URLs (commits
  `c77023f` y anterior).

### 2. CORS cerrado
- `backend/app/main.py` ya no usa `allow_origins=["*"]`. Ahora lista explícita vía env
  var `PELIPICK_ALLOWED_ORIGINS` (default: dominio de Vercel + localhost de dev).
  Seteado en `render.yaml`. Commit `805a1ab`.

### 3. Persistencia migrada a Postgres (Neon)
- **Problema:** el free tier de Render tiene filesystem efímero → el SQLite se borraba
  en cada redeploy/restart. Los discos persistentes no existen en el plan free de
  Render; Supabase free se pausa a la semana; **Neon** es la única opción gratis
  permanente.
- `backend/app/db.py` ahora soporta los dos backends vía `DATABASE_URL`: sin setear
  usa SQLite (dev local + los 150 tests, sin cambios); seteada usa Postgres. Wrapper
  `_PostgresConnWrapper` traduce `?`→`%s`, `_last_insert_id` para los 3 INSERTs con
  `RETURNING id`. Dependencia nueva: `psycopg2-binary`. Commit `805a1ab`.
- **Matías ya configuró `DATABASE_URL` en Render** con el connection string de Neon y
  redeployó. Verificado en vivo: registro/login contra el backend deployado devuelven
  201/200, los datos ahora sobreviven a un restart. (La password de esa DB quedó en
  texto plano en el chat de esta sesión — si en algún momento compartís el historial,
  rotarla desde el dashboard de Neon.)

### 4. Rediseño visual "Hybrid critic notebook" (lo más grande)
- Flujo: brief en Stitch → doc `DESIGN.md` → iteración visual en **Lovable** (repo
  `matiassrusso/pixel-perfect-clone-61381`, privado, visual-only con datos mock,
  TanStack Router) → **port a mano** al frontend real (`wouter` + fetch real) sin
  tocar la lógica. Commit `68bbe27`.
- Sistema: paleta papel/tinta/terracota `#C2410C` con **dark mode real** vía toggle
  (antes el tema "cinematic" era dark-first sin toggle), tipografía `Inter Black`
  uppercase + `Playfair Display Italic` (el "why" de cada pick) + `JetBrains Mono`
  (labels/callouts/metadata), `radius: 0`, bordes gruesos editoriales.
- Nav y footer centralizados en `App.tsx` (antes cada página montaba su `<Navbar/>`).
  Nuevos: `ThemeToggle.tsx`, `Footer.tsx`. Retirados: `PixelCard`, `GooeyNav` (sin
  otros consumidores).
- **Gaps de datos reales vs. mock de Lovable, resueltos por honestidad:** se sacó
  "Dir. X" de las cards/modal (ni `Recommendation` ni `MovieDetails` traen director),
  las stats fabricadas del footer ("42.8k films"), y la tabla de "Vistas" en History
  quedó con las columnas que `WatchedItem` sí tiene (sin año/director).
- **Regresión encontrada y arreglada en el camino:** el grano animado full-screen que
  traía el clone de Lovable trababa el scroll (repaints continuos) — mismo problema ya
  diagnosticado antes en este proyecto. Ahora es grano estático (comentario `ponytail:`
  en `index.css`).
- Verificado end-to-end en local con el username real `scorsese`: registro, login,
  recomendación con Gemini citando títulos reales del historial, modal con cast/tráiler
  real, feedback, History (ambas pestañas), Profile, toggle dark/light. `npm run build`
  limpio.
- Docs corregidos: `DESIGN.md`, `docs/design-directions.md`, `docs/mvp-status.md`,
  `CLAUDE.md` describían "Crítico Moderno" (papel claro) como tema vigente, pero el
  frontend real seguía con el tema "cinematic" dark-first hasta este port.

### 5. Fix cold start de Render en login/registro
- **Reporte del usuario:** "hay problemas para loguearse o registrarse".
- **Diagnóstico:** NO era bug de código. El backend free de Render se duerme tras ~15
  min de inactividad; la primera request tarda 17-50s en despertar (medido: health en
  17s, register en ~8s ya caliente). El fetch colgaba sin feedback → parecía roto.
- **Fix:** `frontend/src/pages/Login.tsx` ahora muestra un aviso ("Despertando el
  servidor... esperá sin recargar") si la request pasa de 4s. Commit `e85e6a5`.

## Pendiente / lo que queda

### Decisión abierta (bloquea nada, pero sin resolver)
- **Eliminar la espera del cold start.** El aviso ya lo suaviza, pero la espera de
  ~30s en la primera carga sigue. Opciones planteadas:
  - Dejarlo con el aviso (cero costo — recomendado para portfolio).
  - Keep-warm con cron gratis (ping a `/health` cada ~10 min vía GitHub Actions o
    UptimeRobot). **OJO:** consume las 750h/mes del free tier de Render que Matías
    comparte con BalonPie y Quien Mató El Grupo — tenerlo siempre prendido puede
    dejar sin horas a los otros.
  - Pagar Render Starter ($7/mes/servicio). Descartado antes por no querer pagar.
  - **Matías no eligió todavía — retomar acá.**

### Bugs funcionales de `NOTAS_DEL_PROYECTO.md` (nunca resueltos, viven en el backend)
- A veces recomienda muy pocas pelis → falta garantizar un número fijo de picks.
- "Nuevos picks" con la misma categoría devuelve los mismos títulos → falta
  variedad/no-repetición entre regeneraciones.
- El "why" de la IA no respeta mayúsculas (Matías quiere la web "impoluta" en eso).
- El slider de la tarjeta de detalle arrastra el scroll de la página cuando el cursor
  sale de la tarjeta (esto quizá ya no aplica con el modal reescrito del port — hay
  que re-chequear en el diseño nuevo).

### De `docs/mvp-status.md` ("Falta para un MVP más serio")
- ~~Reportar filas descartadas del CSV/zip al usuario.~~ **Hecho** (sesión
  2026-07-17 tarde): `parse_ratings_csv` cuenta filas sin título/rating,
  `parse_letterboxd_zip` lo propaga como tercer valor de la tupla,
  `RecommendResponse.discarded_rows` lo expone en `/recommend/zip`, toast de
  aviso en `Recommend.tsx`. Verificado end-to-end contra el backend real
  (zip con 2 filas malformadas → `discarded_rows: 2`). 151 tests en verde.
- ~~Observabilidad mínima.~~ **Hecho** (misma sesión): `logging.basicConfig`
  en `main.py` — sin esto los `logger.warning` de fallback (TMDb/Gemini/taste
  profile) dependían del handler de último recurso de Python (solo WARNING+,
  sin timestamp/módulo, nada de INFO). Ahora estructurado, más un log INFO
  por cada `/recommend/*` completado (user, mode, kind_filter, personalized,
  llm, picks, discarded_rows). Verificado en vivo, log real capturado.
- Envío real de mail para recuperación de contraseña (hoy el token no llega al usuario
  sin `PELIPICK_DEBUG=1`). **Sigue pendiente** — necesita que Matías elija
  proveedor (Resend vs Gmail SMTP) y cree la cuenta/API key él mismo antes de
  que se pueda implementar; quedó preguntado, sin responder por corte de sesión.

### Features planeadas pero shelved
- **Affinity Map** (mapa espacial de afinidades por co-ocurrencia, en reemplazo del
  radar+heatmap de `/profile`): se planeó a fondo, después se pausó al pivotear a
  Lovable. El plan quedó documentado; retomar si se quiere.
- **Sistema de "Notes"** (reemplazar rating por estrellas): explícitamente fuera de
  alcance por decisión de Matías.

### Nota de scope del fix de cold start
- El aviso de cold start solo está en login/registro. El flujo de Recommend tiene su
  propia pantalla de carga ("Buscando tus pelis..."), así que un cold start ahí se ve
  como una búsqueda un poco larga, no como algo roto — no se tocó a propósito.
