# Estado del MVP

## Ya hecho

- definición de producto base
- recorte de MVP
- dirección visual inicial
- backend local con FastAPI
- frontend local con React + Vite
- recomendador heurístico simple
- ingesta del `.zip` completo del export de Letterboxd (no un CSV suelto):
  combina rating base, boost por rewatch, likes sin puntuar, favoritos
  explícitos del perfil, tags propios por film y exclusión ampliada por todo lo visto — ver
  `docs/letterboxd-zip-format.md`
- login/registro real con passwords hasheadas (PBKDF2, stdlib) y sesiones por
  token opaco
- persistencia en SQLite: usuarios, ratings importados, recomendaciones
  servidas y feedback
- feedback explícito por pick (me interesa / no me interesa / ya la vi)
- catálogo real con `TMDb` (`/discover/movie` y `/discover/tv`, mapeo género +
  overview a tags propios, fallback al mock si falla o no hay key), con
  póster/backdrop/overview/rating viajando hasta el frontend
- agente de IA con `Gemini` (free tier, sin pagar OpenAI de entrada): refina
  el resumen de gusto y el orden/razones de los picks ya filtrados por el
  heurístico, con fallback al resultado heurístico si falla o no hay key
- rate limiting de login (backoff exponencial por username, tope 15 min) y
  recuperación de contraseña (token hasheado en SQLite, expira a la hora,
  invalida sesiones viejas al resetear) — el token solo viaja en la
  respuesta con `PELIPICK_DEBUG=1`, salvo con Resend configurado (ver abajo)
- envío real del mail de recuperación vía Resend: `users` suma columna
  `email` (nullable, migración vía `_run_migrations` en `backend/app/db.py`
  para instalaciones existentes), registro pasa a pedir email
  (`RegisterRequest`, validado con un regex simple — no se suma
  `email-validator` para no meter una dependencia nueva por una validación de
  forma). `backend/app/mailer.py` (mismo patrón stdlib `urllib` que
  `llm_client.py`/`tmdb_client.py`, sin dependencia nueva) manda el mail vía
  la API REST de Resend si `RESEND_API_KEY` está seteada; si no, se
  comporta exactamente como antes (degrade gracioso, mismo patrón que
  TMDb/LLM). Frontend suma el campo email al registro, un flujo "¿Olvidaste
  tu contraseña?" en `Login.tsx`, y la página `ResetPassword.tsx` que
  consume el link del mail. Verificado end-to-end en local con
  `PELIPICK_DEBUG=1` (sin Resend real configurado todavía): registro con
  email → forgot-password → reset con el token real → login con la
  contraseña nueva. **Pendiente de Matías:** crear la cuenta en Resend y
  setear `RESEND_API_KEY` (local y en Render) — sin dominio propio
  verificado, Resend solo deja mandar al mail de la cuenta dueña de la key,
  así que además hace falta un dominio real para que llegue a usuarios
  reales (no solo a vos)
- caché en memoria de resultados de TMDb (`/discover/movie` y
  `/discover/tv`, TTL de 5 min, tope de 32 entradas)
- historial revisitables de sesiones: cada request de `/recommend/zip` queda
  guardado como sesión y se puede volver a ver desde `/history` sin resubir
  el zip
- modal de detalle con reparto y link al tráiler para recomendaciones de
  TMDb; si TMDb no está disponible o el pick viene del catálogo mock, el
  resto del detalle sigue funcionando
- flujo de "qué querés ver hoy" con 3 modos (perfil completo / últimas
  películas vistas / selección de géneros con lógica OR y cobertura
  garantizada por género elegido) y split Películas/Series/Ambas —
  reemplaza el dropdown de mood único
- historial separado en dos secciones: "Vistas" (`GET /history/watched`,
  películas ya vistas según el zip importado, deduplicadas por título) y
  "Recomendadas" (lo que ya había en `/history`)
- mensaje "why" del heurístico personalizado por película y por usuario:
  cita los tags concretos que matchearon (no una plantilla fija) y, cuando
  hay señal, el título específico del historial del usuario detrás del
  match
- modal de detalle renderizado vía React Portal a `document.body`, para
  que quede siempre centrado en el viewport sin importar el scroll de la
  página al abrirlo (antes se cortaba si la página no estaba scrolleada
  arriba)
- perfil de gusto visual (`/profile`): radar de géneros (pesado por rating,
  no solo por cantidad), heatmap de décadas, y top de directores/actores —
  matchea el historial "vistas" del usuario contra TMDb (`GET
  /profile/taste`). Acotado a los 150 títulos mejor puntuados para el
  match de género/año y a los 50 mejores de esos para pedir créditos
  (director/cast), para que la carga no dependa de cientos de requests
  secuenciales en exports grandes; la UI avisa cuántos títulos matcheó
  sobre el total. Sin librería de gráficos nueva: radar y heatmap son SVG
  a mano
- fecha real de "visto" persistida: `watched_date` de `diary.csv` (antes se
  parseaba pero se perdía al guardar) ahora se guarda en `rated_items` y la
  pestaña "Vistas" la muestra en vez de la fecha de import, con fallback si
  no hay diary.csv
- prompt de Gemini enriquecido con un "perfil de gusto" explícito (promedio,
  tags recurrentes en lo valorado, títulos que amó/odió) para que las
  razones de cada pick nombren un patrón concreto del historial en vez de
  un elogio genérico — sigue sin rescorear ni traer candidatos propios
- import por username de Letterboxd (`POST /recommend/letterboxd`),
  alternativa al zip: scrapea el diario público (rating, fecha real de
  visto, rewatch), sin exportar nada — ver
  `docs/letterboxd-username-import.md`. No cubre likes/favoritos/tags ni
  ratings sin entrada de diario (esas grillas de Letterboxd hidratan client-
  side y no se pueden leer sin ejecutar JS), así que el zip sigue siendo la
  opción más completa. Requirió sumar `curl_cffi` como dependencia: el
  stack `urllib`/`requests` de Python queda bloqueado con `403` por
  Cloudflare según el fingerprint TLS del handshake, sin importar los
  headers que se manden
- corrección de 3 bugs de calidad de recomendación detectados en uso real: (1)
  `_collect_preference_tags` sumaba ciegamente `funny/light/character/intimate`
  a cualquier título puntuado ≥4.5 sin mirar su contenido — con la mayoría de
  la gente puntuando varias cosas alto, ese ruido dominaba el resto de la
  señal y explicaba por qué el "why" siempre terminaba citando humor/tono
  liviano sin importar el historial real; (2) el import por username no trae
  texto de review, así que sin ese bug la señal de gusto quedaba en cero —
  ahora `_enrich_loved_ratings_with_genre_tags` (`backend/app/main.py`)
  completa el género real de TMDb para los títulos puntuados ≥4 (capado a 30
  por request, reutiliza `tmdb_client.search_title` ya cacheado 24h), gateado
  a "amado" para no colar señal falsa desde títulos que el usuario odió; (3)
  el discover de TMDb pedía `sort_by=popularity.desc` (qué está sonando
  ahora, no qué es bueno), lo que sesgaba todo el catálogo de candidatos a
  estrenos recientes — cambiado a `vote_average.desc`
- perfil de gusto persistido por usuario (`taste_profiles` en SQLite): antes
  `build_taste_profile` se recomputaba entero (hasta ~200 requests a TMDb)
  cada vez que se abría `/profile/taste`; ahora se calcula y guarda una sola
  vez por import (`/recommend/zip` o `/recommend/letterboxd`), antes de traer
  candidatos, para que la propia recomendación de ese request ya lo use
- el motor de recomendación arma el pool de candidatos desde el gusto real
  del usuario, no desde el top global de TMDb: `fetch_personalized_candidates`
  sesga `/discover/movie` y `/discover/tv` por los géneros top del perfil
  (OR), los directores/actores top resueltos a `person_id` vía
  `/search/person` (solo aplica a películas — TMDb ignora `with_people` en
  `/discover/tv`, confirmado en vivo) y la década más pesada (sesgo suave,
  ±1 década), todo en una sola query por tipo. Se mezcla con una porción sin
  personalizar ("apuesta distinta") de la que el ranking siempre reserva un
  lugar, para no cerrar el pool sobre el mismo gusto. El scoring ahora suma
  puntos por director/actor/década concretos (no solo tags de género/tono) y
  el "why" nombra a la persona o década cuando fue el motivo real del match.
  Dos usuarios con gustos distintos ya reciben pools genuinamente distintos,
  en vez del mismo top de TMDb reordenado
- caché en memoria de las respuestas de Gemini refine (TTL 15 min, mismo
  patrón que la caché de TMDb), keyeada por mood + los candidatos exactos
  que le pasó el heurístico — evita repetir la llamada (y gastar cupo
  gratuito) cuando se regeneran picks con la misma entrada
- tests de backend (150, incluyendo auth, feedback, historial, TMDb, Gemini, el
  desempate por score crudo, el parser del zip de Letterboxd (incluyendo
  Tags de usuario), el scraper del diario por username, el enriquecimiento de
  tags por TMDb para títulos amados, rate limiting/reset de contraseña, la
  caché de TMDb, los 3 modos de recomendación + kind_filter, el historial de
  vistas con fecha real, la personalización del "why" (heurístico y del
  agente Gemini), el perfil de gusto visual, el motor personalizado
  (candidatos por perfil, resolución de persona en TMDb, scoring por
  director/actor/década, mezcla con exploración), y la traducción de
  placeholders SQL del wrapper de Postgres)
- pasada de UX/UI: tema "cinematic" (paleta ámbar/dorada, `Instrument Serif` +
  `IBM Plex Sans`), animaciones con Framer Motion, páginas Home / Login /
  Recommend (upload del zip + mood + resultados con feedback) / History /
  NotFound
- rediseño completo "Hybrid critic notebook" (2026-07-17): identidad propia
  iterada primero en Stitch y después en Lovable (repo
  `matiassrusso/pixel-perfect-clone-61381`, visual only con datos mock), portada
  a mano al frontend real conservando toda la lógica/fetch existente. Paleta
  papel/tinta/terracota `#C2410C` con dark mode real (antes el tema "cinematic"
  no tenía toggle), tipografía `Inter Black` uppercase + `Playfair Display
  Italic` (el "why" de cada pick) + `JetBrains Mono` (labels/callouts/metadata),
  `radius: 0`, bordes gruesos editoriales. Nav y footer se centralizaron en
  `App.tsx` en vez de repetirse por página. Se retiraron `PixelCard` y
  `GooeyNav` (reemplazados por elementos planos del nuevo sistema). Gaps de
  datos reales vs. el mock de Lovable resueltos por honestidad en vez de
  inventar: se sacó "Dir. X" de las cards/modal (ni `Recommendation` ni
  `MovieDetails` traen director hoy) y las stats fabricadas del footer ("42.8k
  films indexed"); la tabla de "Vistas" en History quedó con las columnas que
  sí tiene `WatchedItem` (sin año/director). Verificado en vivo end-to-end con
  el username real `scorsese`: registro, login, import por username, picks con
  Gemini citando títulos reales del historial, modal con cast/tráiler real,
  feedback, History (ambas pestañas) y Profile con datos reales, toggle de
  tema dark⇄light
- build verificado de frontend
- deploy: frontend en Vercel ([pelipick.vercel.app](https://pelipick.vercel.app/)),
  backend en Render ([pelipick-backend.onrender.com](https://pelipick-backend.onrender.com)).
  CORS restringido al dominio de Vercel (antes `allow_origins=["*"]`)
- persistencia en producción vía Postgres (Neon, free tier permanente): el
  free tier de Render tiene filesystem efímero y borra el SQLite en cada
  redeploy, así que `backend/app/db.py` ahora soporta los dos backends por
  `DATABASE_URL` (sin setear sigue usando SQLite igual que siempre, para dev
  local y tests); en Render se setea a mano con el connection string de Neon
- current picks en el home (última sesión de recomendaciones real del
  usuario logueado) y catalog statistics reales en el footer (`GET
  /catalog/stats`, del mismo pool de TMDb del que salen las
  recomendaciones) — ver `docs/build-log.md` 2026-07-18
- fix de mapa de afinidad roto en producción (`datetime()` de SQLite no
  existe en Postgres) + exception handler global para que un 500 no
  manejado no se disfrace de "Failed to fetch" en el browser
- performance: pool de conexiones a Postgres (antes se recreaba el schema
  entero en cada request — login bajó de ~8s a ~2.85s en producción,
  medido) y paralelización con `ThreadPoolExecutor` de las llamadas a TMDb
  en el perfil de gusto (antes secuenciales, ~200 requests uno por uno —
  un import de 45 títulos nuevos bajó de ~100s+ a ~11.6s) — ver
  `docs/build-log.md` 2026-07-18

## Hecho pero verde

- parser del zip de Letterboxd
  - lee `reviews.csv`/`ratings.csv`, `diary.csv`, `likes/films.csv`,
    `watched.csv`, `profile.csv`
  - usa `Tags` propios del usuario cuando coinciden directamente con el
    vocabulario interno de recomendación

- recomendación
  - ya scorea contra películas y series reales de TMDb, no solo el mock
  - el mapeo género/overview → tags es heurístico y coarse, sin nuance real
    de tono/ritmo
  - el agente de IA (NVIDIA NIM) reordena y reescribe texto sobre esos
    candidatos, pero no rescorea ni trae candidatos propios — sigue acotado
    a lo que ya filtró el heurístico

- UX web
  - diseño generado con otra IA (plataforma "Manus"), adaptado a mano: nos
    quedamos con la UI/tema y descartamos enteros el server Node/tRPC/
    Drizzle/MySQL, el auth OAuth y el LLM de esa plataforma
  - la página de historial ya está, pero es una primera pasada: revisita
    picks y resumen; no recupera el zip original ni analytics más finos

- `parse_ratings_csv` (`backend/app/csv_ingest.py`) ahora cuenta las filas del
  CSV base sin título o sin rating parseable y ese conteo viaja hasta el
  usuario: `parse_letterboxd_zip` lo devuelve como tercer valor de la tupla,
  `RecommendResponse.discarded_rows` lo expone en `/recommend/zip`, y el
  frontend (`Recommend.tsx`) muestra un toast de advertencia cuando es > 0.
  El import por username no lo necesita (no viene de un CSV)

- observabilidad mínima: antes los `logger.warning` de fallback (TMDb, LLM,
  taste profile) dependían del "handler de último recurso" de Python, que solo
  muestra WARNING+ sin timestamp/módulo — nada por debajo de WARNING llegaba a
  los logs de Render. `logging.basicConfig` en `backend/app/main.py` los deja
  estructurados (`timestamp LEVEL module: mensaje`) y le suma un log INFO por
  cada `/recommend/*` completado (usuario, mode, kind_filter, si fue
  personalizado, si pasó por el LLM, cantidad de picks, filas descartadas) —
  visibilidad de uso real, no solo de errores

- migrado el agente de IA de Gemini a **NVIDIA NIM**
  (`nvidia/nemotron-3-super-120b-a12b`, con
  `chat_template_kwargs.enable_thinking=false`), reemplazando por completo
  la sección de arriba sobre Gemini. Motivo: el modo "thinking" de
  `gemini-flash-latest` no se podía desactivar (~20s por call) y forzaba una
  cadena de 4 modelos de fallback solo para esquivar la cuota diaria. NVIDIA
  da un solo endpoint compatible con la API de OpenAI
  (`https://integrate.api.nvidia.com/v1/chat/completions`) con +100 modelos
  gratis bajo una key. Se probó primero `llama-3.3-nemotron-super-49b-v1`
  (con el toggle viejo de system prompt `"detailed thinking off"`), pero
  resultó tener ~11 meses de antigüedad — se cambió a la familia Nemotron 3
  (arquitectura MoE híbrida Mamba-Transformer propia de NVIDIA, más nueva),
  eligiendo Super (120B total/12B activos) sobre Nano (30B/3B, más rápido
  pero menos capaz) y Ultra (550B/55B, frontier, mismo riesgo de latencia que
  Gemini) — apaga el razonamiento vía un parámetro real de la API, no un
  truco de system prompt, ver `docs/nvidia-setup.md`. Ya no hay
  `responseSchema`/JSON estructurado garantizado (no todos los modelos del
  catálogo NIM lo soportan): el prompt pide JSON explícitamente y
  `_extract_json` limpia el fence de markdown si el modelo lo agrega.
  `GEMINI_API_KEY` → `NVIDIA_API_KEY`. 158 tests en verde

## Falta para un MVP más serio
- terminar de activar el envío real de mail (ver más arriba): falta que
  Matías cree la cuenta de Resend, setee `RESEND_API_KEY`, y consiga un
  dominio propio verificado para que el mail le llegue a usuarios reales
  (no solo a la cuenta dueña de la key)

## No entra todavía

- scraping complejo
- app mobile
- social features
- chat agente largo

## Riesgos abiertos

- que el export real de Letterboxd no coincida con el supuesto actual
- que el ranking mock dé una falsa sensación de calidad
- que el producto se vea prometedor visualmente antes de validar la calidad del pick

## Regla práctica para seguir

Cada iteración debería mover una de estas dos cosas:

- calidad real de recomendación
- claridad real del flujo de uso

Si no mejora una de esas dos, probablemente estamos metiendo complejidad al pedo.
