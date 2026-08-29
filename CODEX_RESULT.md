# Resultado — fix/frontend-kind-cartel

## Tarea A — mandar `kind` al puntuar

Se agregó `kind` al body JSON de cada call site de rate donde el kind está disponible
en scope. Detalle importante: los "similares" del modal se piden con
`kind=rec.kind`, así que el kind del rec/selectedRec es el correcto tanto para el
título en sí como para sus similares (no hizo falta cambiar la firma de `onRate`).

Call sites tocados:
- `frontend/src/components/SearchBox.tsx` — `POST /profile/rate` → `kind: selectedRec.kind`
- `frontend/src/pages/VibesMap.tsx` — `POST /profile/rate` → `kind: selectedRec.kind`
- `frontend/src/pages/Home.tsx` (`rateTitle`) — `POST /profile/rate` → `kind: rec.kind`
- `frontend/src/pages/History.tsx` (`rateTitle`) — `POST /profile/rate` → `kind: rec.kind`
- `frontend/src/pages/Recommend.tsx` (`rateTitle`) — `POST /profile/rate` → `kind: rec.kind`
- `frontend/src/pages/Rate.tsx` (`submitRating`) — `POST /profile/rate` → `kind: current.kind`
- `frontend/src/pages/Recommend.tsx` (`handleGenerate`, `POST /recommend/manual`) —
  `manualRatings` solo guarda título→puntaje; el kind real se re-adjunta por título
  buscándolo en `manualTitles` (`kind: manualTitles.find(...)?.kind ?? "movie"`).

`rateManual` (~483) no hace llamada de red (solo actualiza estado local), así que no
se toca; el kind se manda al momento del `/recommend/manual`. Donde el kind no está
en scope no se fuerza — el default `'movie'` del backend cubre.

## Tarea B — cartel roto del dropzone del zip

Bug: el `<label>` del dropzone (`frontend/src/pages/Recommend.tsx`, paso 1 del wizard)
no tenía clase de display, así que quedaba `display: inline` por default. Con hijos en
bloque (`<div>`) y `border-2 border-dashed p-8 text-center`, un elemento inline no
forma una caja rectangular propia: el borde punteado se fragmentaba y se veía
descuadrado en una esquina (lo que reportó el dueño).

Fix: se agregó `block` al className del label, así forma una caja rectangular que llena
el contenedor `max-w-xl` y el borde punteado se ve prolijo y consistente con el tema
"Hybrid critic notebook". No se tocó la lógica de subida.

Nota: el paso 1 está gateado por login (redirige a `/login` si no hay sesión), así que
se arregló por inspección del JSX/clases como indicaba la tarea, sin reproducir en vivo.

## Verificación

`npm run build` (tsc -b + vite build) pasa limpio, sin errores. Solo queda el warning
preexistente de tamaño de chunk (>500 kB), no relacionado con estos cambios.
