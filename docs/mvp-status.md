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
  respuesta con `PELIPICK_DEBUG=1`, nunca por default (no hay proveedor de
  mail todavía)
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
- tests de backend (128, incluyendo auth, feedback, historial, TMDb, Gemini, el
  desempate por score crudo, el parser del zip de Letterboxd (incluyendo
  Tags de usuario), el scraper del diario por username, el enriquecimiento de
  tags por TMDb para títulos amados, rate limiting/reset de contraseña, la
  caché de TMDb, los 3 modos de recomendación + kind_filter, el historial de
  vistas con fecha real, la personalización del "why" (heurístico y del
  agente Gemini), y el perfil de gusto visual)
- pasada de UX/UI: tema "cinematic" (paleta ámbar/dorada, `Instrument Serif` +
  `IBM Plex Sans`), animaciones con Framer Motion, páginas Home / Login /
  Recommend (upload del zip + mood + resultados con feedback) / History /
  NotFound
- build verificado de frontend

## Hecho pero verde

- parser del zip de Letterboxd
  - lee `reviews.csv`/`ratings.csv`, `diary.csv`, `likes/films.csv`,
    `watched.csv`, `profile.csv`
  - usa `Tags` propios del usuario cuando coinciden directamente con el
    vocabulario interno de recomendación
  - no reporta filas descartadas del CSV base

- recomendación
  - ya scorea contra películas y series reales de TMDb, no solo el mock
  - el mapeo género/overview → tags es heurístico y coarse, sin nuance real
    de tono/ritmo
  - el agente de Gemini reordena y reescribe texto sobre esos candidatos,
    pero no rescorea ni trae candidatos propios — sigue acotado a lo que
    ya filtró el heurístico

- UX web
  - diseño generado con otra IA (plataforma "Manus"), adaptado a mano: nos
    quedamos con la UI/tema y descartamos enteros el server Node/tRPC/
    Drizzle/MySQL, el auth OAuth y el LLM de esa plataforma
  - la página de historial ya está, pero es una primera pasada: revisita
    picks y resumen; no recupera el zip original ni analytics más finos

## Falta para un MVP más serio

- reportar filas descartadas del CSV base
- observabilidad mínima
- envío real de mail para recuperación de contraseña (hoy el token nunca
  sale de la respuesta salvo con `PELIPICK_DEBUG=1`, así que el flujo
  funciona pero no hay forma real de que el usuario lo reciba)

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
