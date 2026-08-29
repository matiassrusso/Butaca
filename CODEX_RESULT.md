# Fix: rated_items sin columna `kind` (series con poster/año equivocado)

Branch: `fix/rated-items-kind`. NO mergeado.

## Causa raíz (confirmada)

`rated_items` no tenía columna `kind`. `_resolve_watched_title` resolvía TODO
contra `/movie/<id>`, pero los ids de movie y TV en TMDb son espacios
separados, así que una serie por id devolvía una peli random (Breaking Bad ->
poster ajeno + año 1975). Además `_pairwise_tied_pair` agrupaba solo por
rating, así que enfrentaba una serie contra una peli.

## Qué cambié

- **backend/app/db.py**
  - Columna `kind TEXT NOT NULL DEFAULT 'movie'` agregada a `rated_items` en
    los dos `CREATE TABLE` (SQLite y Postgres) y en `_run_migrations`
    (idempotente, mismo patrón `_has_column` del proyecto; filas viejas quedan
    en 'movie').
  - `save_rated_items`: el INSERT ahora incluye `kind`. Acepta tuplas de 6 o 7
    elementos (7mo = kind); las de 6 defaultean a 'movie', para no romper
    callers/tests existentes.
  - `get_watched_items`: `kind` agregado al SELECT (ya viaja en el dict via
    `dict(row)`).

- **backend/app/models.py**: campo `kind: str = "movie"` agregado a
  `RatedItem`, `RateTitleRequest` y `ManualRating`.

- **backend/app/main.py**
  - `_finish_recommend` (save), `_rebuild_ratings`, `/recommend/manual` y
    `/profile/rate`: propagan el `kind` real al escribir.
  - `_resolve_watched_title`: usa `row["kind"]`; para el fallback sin tmdb_id y
    kind='series' usa `search_any_titles` (/search/multi) y toma el primer
    resultado de kind 'series' (antes `search_title` probaba movie primero).
  - `_pairwise_tied_pair`: agrupa por `(rating, kind)`. Nunca compara series
    con pelis.

- **backend/tests/test_main.py**: dos tests nuevos
  - `test_pairwise_match_never_pairs_a_series_with_a_movie`
  - `test_pairwise_match_pairs_two_series_and_resolves_against_tv_endpoint`
    (verifica que ambas series se resuelven contra el endpoint de TV, no movie)

## Tests

`python -m pytest backend/` -> **527 passed** (525 previos + 2 nuevos).

Verificación de bug reintroducido: revertí temporalmente el group-by a solo
rating y los dos tests nuevos fallaron (emparejaban "Some Movie" dentro del
grupo de series); restaurado y verde de nuevo.

## Riesgo / decisión abierta para revisar

**El frontend todavía NO manda `kind` en `/profile/rate` ni
`/recommend/manual`.** El backend ya lo acepta y persiste, pero como esas
requests salen sin `kind`, una serie NUEVA puntuada desde el buscador se sigue
guardando como 'movie' (el default) y seguiría resolviéndose mal. La consigna
pedía explícitamente no tocar el frontend, así que quedó afuera, pero **para
que el bug quede realmente cerrado end-to-end hay que wire-ear el `kind` en los
call sites de rate** (el valor ya está disponible, ej. `selectedRec.kind` en
SearchBox.tsx:223, y el `kind` de cada OnboardingTitle en el modo manual de
Recommend.tsx). Es una línea por call site. Call sites de `/profile/rate`:
SearchBox.tsx, History.tsx, Home.tsx, Rate.tsx, Recommend.tsx, VibesMap.tsx.

Las filas viejas (incluidas las series ya guardadas como 'movie' antes de este
fix) no se pueden migrar de forma confiable: quedan en 'movie'. Si hace falta,
se podrían re-resolver por nombre contra /search/multi en una migración de
datos aparte, pero no es parte de este fix.
