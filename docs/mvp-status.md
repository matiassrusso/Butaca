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
  explícitos del perfil, y exclusión ampliada por todo lo visto — ver
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
- tests de backend (55, incluyendo auth, feedback, historial, TMDb, Gemini, el
  desempate por score crudo, el parser del zip de Letterboxd, rate
  limiting/reset de contraseña, y la caché de TMDb)
- pasada de UX/UI: tema "cinematic" (paleta ámbar/dorada, `Instrument Serif` +
  `IBM Plex Sans`), animaciones con Framer Motion, páginas Home / Login /
  Recommend (upload del zip + mood + resultados con feedback) / History /
  NotFound
- build verificado de frontend

## Hecho pero verde

- parser del zip de Letterboxd
  - lee `reviews.csv`/`ratings.csv`, `diary.csv`, `likes/films.csv`,
    `watched.csv`, `profile.csv`
  - no usa `Tags` propios del usuario (raro que estén completos, pero son
    señal directa cuando existen)
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
  - el modal de detalle de película no tiene cast ni tráiler (pediría un
    fetch extra por película a TMDb)

## Falta para un MVP más serio

- perfil de gusto visual (radar de géneros, heatmap de décadas, directores/
  actores favoritos) — necesita matchear cada título del CSV del usuario
  contra TMDb, no es trivial con exports grandes
- cast y tráiler en el detalle de cada película — necesita empezar a
  guardar el id real de TMDb por título, que hoy no viaja por el pipeline
- import de historial por username de Letterboxd (scraping), como alternativa
  al zip manual — evaluado, pendiente por ser la parte más frágil técnicamente
- soportar `Tags` de usuario del zip cuando estén presentes
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
