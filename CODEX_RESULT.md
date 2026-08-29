# Resultado - fix/profile-page

## Los dos problemas

### 1. El perfil era larguísimo (renderizaba 140+ items inline)

**Qué hice:** saqué del perfil la lista inline completa de "Tus ratings y reseñas" y la
reemplacé por un solo botón "Tus ratings y reseñas" (con el conteo de títulos) que lleva
a `/history`.

### 2. No se veían las reseñas, solo los ratings

Se resuelve de la misma forma: al mandar al usuario a `/history` (pestaña Vistas), que YA
muestra las reseñas correctamente (toggle "Tu reseña") y ademas aplica bien la regla de
estrellas-vs-texto por `source`.

## Decisión: página aparte vs modal vs reusar /history

Elegí **reusar la vista existente `/history` (pestaña Vistas)** en vez de crear una
página nueva `/profile/ratings` o un modal.

Motivo: `/history` con la pestaña "Vistas" ya renderiza EXACTAMENTE esta misma lista. La
data del perfil (`GET /profile/summary` -> `items`) es literalmente el mismo
`db.get_watched_items(user_id)` que sirve `/history/watched`. Y esa vista ya está mejor
hecha que la lista que tenía el perfil:

- Muestra las reseñas con el toggle "Tu reseña" (problema 2 ya resuelto ahí).
- Aplica la regla correcta: estrellas solo para `source === "import"/"star"` (rating real
  de Letterboxd) y texto ("te encantó", etc.) para los sintéticos. La lista del perfil, en
  cambio, renderizaba `★★★★` para TODOS los items sin mirar el source, lo cual inventaba
  un rating de estrellas para los ratings sintéticos (bug real que desaparece al borrarla).
- Trae ordenamiento (rating/título/fecha/fuente) que la lista del perfil no tenía.
- Ya está linkeada en la navbar ("bitácora"), así que no es una vista escondida.

Crear `/profile/ratings` habría sido una TERCERA copia de la misma lista
(`get_watched_items`) para mantener en paralelo. La opción más simple y consistente con el
resto del sitio es no duplicar: borrar la lista peor del perfil y linkear a la canónica.

Tradeoff: el botón "Tus ratings y reseñas" cae en `/history` que está framebeado como "Tu
bitácora / [Vistas]". Es la misma data y es la pestaña por default, así que el salto es
natural, pero si preferís un destino con ese título exacto, se puede envolver
`get_watched_items` en su propia página después - lo dejo señalado por si querés
empujarlo.

## Cambios (frontend only)

- `frontend/src/pages/Profile.tsx`
  - Saqué el campo `items` del type `ProfileSummary` y el state `openReview` (ya no se usan).
  - Reemplacé la `<section>` con la lista inline por un botón que navega a `/history`
    (mismo estilo que el botón de "Wrapped" que ya estaba abajo). Se muestra solo si
    `rated_count > 0`.
- `frontend/src/lib/translations/profile.ts`
  - Saqué `profile.ratings` (ya no se usa).
  - Agregué `profile.viewRatings` y `profile.viewRatingsCount` (ES/EN).

No toqué backend, ni `/history`, ni el router (no hizo falta ruta nueva).

## Verificación

- `npm run build` en `frontend/`: **limpio** (`tsc -b` + `vite build` OK, 2041 módulos, 9s).
  El warning de chunk > 500 kB es preexistente y no relacionado.
- Verificación visual en dev server: no se hizo porque `/profile` requiere login y no tengo
  credenciales de una cuenta local (además la TMDb key local está vieja, degrada a mock).
  El build es el typecheck real del proyecto y quedó limpio.

## Riesgos

- Bajo. Es un borrado + un link a una vista que ya existía y ya andaba. La regla de
  estrellas-vs-texto y las reseñas ya estaban probadas en `/history`.
