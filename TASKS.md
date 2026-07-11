# TASKS.md

Coordinación entre agentes trabajando en paralelo sobre este repo, cada uno
en su propio worktree/branch. Reglas:

- Antes de tocar código: marcá tu tarea como `In Progress` acá, con tu
  nombre de agente como owner.
- Al terminar: movela a `Done`, resumí qué archivos tocaste (para que los
  demás sepan si hay conflicto potencial), y dejá la rama lista — **no
  mergees a `main` vos solo**, avisale al dueño del repo.
- Si algo te bloquea o afecta una tarea de otro agente, anotalo en
  `Blocked` con el motivo en vez de improvisar una solución que lo pise.
- Regla general del proyecto: primero arreglamos lo que esté roto, después
  avanzamos con features nuevas. No asumas nada sobre lo que hizo otro
  agente — leé este archivo antes de cada acción.

## Pending

- [ ] [cache-001] Caché de resultados de TMDb (in-memory, TTL simple,
      stdlib, sin dependencias nuevas) — evita pegarle a `/discover/movie`
      y `/discover/tv` en cada request si el mood+página ya se pidió hace
      poco | owner: none | depende_de: -
- [ ] [auth-001] Recuperación de contraseña + rate limiting de login |
      owner: none | depende_de: -
- [ ] [cast-001] Cast y tráiler en el modal de detalle de película (nueva
      función en `tmdb_client.py` para `/movie/{id}/credits` y
      `/movie/{id}/videos`, expuesta en un endpoint, consumida por el modal
      del frontend) | owner: none | depende_de: cache-001 (mismo archivo
      `tmdb_client.py` — mergear cache-001 primero para evitar conflicto)
- [ ] [historial-001] Historial de sesiones de recomendación revisitables
      (nuevo endpoint de listado sobre `db.py`, nueva página de frontend) |
      owner: none | depende_de: -
- [ ] [perfil-001] Perfil de gusto visual (radar de géneros, heatmap de
      décadas, directores/actores favoritos) — scope grande, necesita
      matchear el historial del usuario contra TMDb y una página nueva con
      gráficos | owner: none | depende_de: -

## In Progress

(vacío)

## Blocked

(vacío)

## Done

- [x] [zip-001] Import del `.zip` completo de Letterboxd, reemplaza el CSV
      suelto pegado/subido. Combina `ratings.csv`/`reviews.csv` (base),
      boost de rewatch desde `diary.csv`, likes sin puntuar desde
      `likes/films.csv`, favoritos explícitos desde `profile.csv`
      (resueltos cruzando URIs contra `watched.csv`), y exclusión ampliada
      con todo `watched.csv` | owner: claude | rama: `claude/zip-upload` |
      archivos: `backend/app/letterboxd_zip.py` (nuevo),
      `backend/app/main.py`, `backend/app/models.py`,
      `backend/app/recommender.py`, `backend/requirements.txt`,
      `frontend/src/pages/Recommend.tsx`, `docs/api.md`,
      `docs/architecture.md`, `docs/mvp-status.md`, `docs/build-log.md`,
      `docs/letterboxd-zip-format.md` (renombrado de `csv-format.md`),
      tests de `letterboxd_zip`, `recommender`, `main`, `auth`
