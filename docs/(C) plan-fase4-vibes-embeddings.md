# Fase 4 — Sistema 1 real: metadata → embeddings → Leiden

> Documento de handoff (2026-08-02). Contexto completo de por qué existe esto:
> ver "Historial de sesiones" en `CLAUDE.md`, entrada 2026-08-02 ("picker 'a
> tu elección'"). Fases 1, 2, 3 y 5 de ese trabajo ya están en `main`
> (commit `5af2817`) — géneros ampliados (18) + vibras curadas a mano (8,
> keywords de TMDb), picker dirigido, frontend agrupado. Esta fase es la
> pieza que falta: categorías de "vibe" descubiertas por clustering real en
> vez de curadas a mano, calcando el Sistema 1 de Flick (el otro sistema de
> Flick, el que clusteriza reseñas de usuarios para dar vibes tipo
> "MindBender", es inviable en Butaca — solo 68 títulos con reseña real en
> toda la base, ver discusión completa en el historial de CLAUDE.md).

## Ya verificado, no hace falta re-chequear

- `GEMINI_API_KEY` en `backend/.env` es real y anda: probado con requests
  reales (no simuladas) a `gemini-embedding-001` (200 OK, vector 3072-d) y a
  `gemini-embedding-2` (200 OK, vector 3072-d, el modelo que vamos a usar,
  el mismo que menciona el video de Flick).
- `batchEmbedContents` funciona de verdad: 3 textos distintos en un solo
  request devolvieron 3 embeddings distintos (no un vector combinado).
  Confirma que se puede batchear en vez de 1 request por título.
- `text-embedding-004` y `gemini-embedding-exp-03-07` dan 404 con esta key
  — no están disponibles, no los uses.

## Primer paso, antes de escribir nada más

**Riesgo real sin confirmar todavía:** el Python de este entorno es 3.14
(muy nuevo). `python-igraph` y `leidenalg` son paquetes con extensión en C
— no hay garantía de que ya existan wheels precompiladas para 3.14 en
Windows. Si `pip install python-igraph leidenalg` falla o intenta compilar
desde source:

- Fallback: `networkx` + `python-louvain` (Louvain, el algoritmo que Leiden
  mejora — más simple, pero es puro Python, sin fricción de build). Cambia
  el nombre de la función de clustering, no la arquitectura del resto del
  plan (grafo KNN → clusters → reclusterizar → etiquetar sigue igual).
- Si tampoco eso anda por algún motivo, un k-means simple a mano sobre los
  vectores (sin necesidad de grafo) es la última opción — pura stdlib, ver
  la discusión descartada en el historial de esta conversación por qué no
  era la primera opción (peor calidad de cluster que un método basado en
  grafo/comunidad, pero funciona sin dependencias nuevas).

Correr el `pip install` real y confirmar cuál camino toca ANTES de escribir
`vibes_clustering.py` — no asumir.

## Diseño de embeddings (actualizado — usar batching, no 1 request por título)

`_embed_batch(texts: list[str]) -> list[list[float]]`: un POST a
`https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-2:batchEmbedContents`
con lotes de ~100 textos por request (`requests: [{model, content: {parts:
[{text}]}}, ...]`, ver forma exacta ya probada arriba). Para 1.500 títulos
semilla, esto son **~15 requests**, no 1.500 — mucho más rápido y ni cerca
de ningún límite de rate. Cachear el embedding por `tmdb_id` en la tabla
nueva para que un recompute posterior no vuelva a pedir los que ya tiene.

## El resto del plan (sin cambios)

### Esquema de tablas nuevas (sumar a `SCHEMA_SQLITE` y `SCHEMA_POSTGRES` en
`backend/app/db.py`, mismo patrón dual ya existente; `CREATE TABLE IF NOT
EXISTS` alcanza, no hace falta migración):

```sql
title_embeddings(tmdb_id INTEGER, kind TEXT, vector_json TEXT NOT NULL,
                  computed_at TEXT NOT NULL DEFAULT (datetime('now')),
                  PRIMARY KEY (tmdb_id, kind))

title_clusters(tmdb_id INTEGER, kind TEXT,
                l1_cluster_id INTEGER, l2_cluster_id INTEGER,
                computed_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (tmdb_id, kind))

cluster_labels(level INTEGER NOT NULL, cluster_id INTEGER NOT NULL,
               label TEXT NOT NULL, sample_titles TEXT NOT NULL DEFAULT '',
               size INTEGER NOT NULL DEFAULT 0,
               computed_at TEXT NOT NULL DEFAULT (datetime('now')),
               PRIMARY KEY (level, cluster_id))
```
(Postgres: `DEFAULT ({_PG_NOW})` en vez de `datetime('now')`, sin `SERIAL`
— ambas PK son naturales. `vector_json`/`sample_titles` como TEXT-de-JSON,
mismo precedente que `taste_profiles.profile_json`.)

`backend/app/db.py` — funciones nuevas siguiendo el estilo de
`save_taste_profile`/`get_admin_stats`: `save_vibe_clusters(clusters,
assignments)` (delete-all + insert en una transacción), `get_title_clusters_
by_tmdb_ids(ids) -> dict[int, int]` (una query batcheada, nunca por ítem),
`get_vibe_clusters()`.

### `backend/app/vibes_clustering.py` (nuevo módulo, stdlib + lo que se
elija en "primer paso" de arriba):

- `_seed_titles(cap=1500)`: pool de arranque reusando las funciones de
  discover ya existentes en `tmdb_client.py` a través de varios
  géneros/décadas para diversidad, deduplicado por tmdb_id. 1.500 títulos a
  propósito (no "todo el catálogo") — Flick corre a escala de producción
  que Butaca no tiene; se puede subir el cap después si vale la pena.
- `_metadata_text(item, credits, keywords)`: arma el texto que se embebe —
  géneros + sinopsis + keywords + director/cast + año/país (calca "all
  these genres, all the metadata... into an embedder" del video).
- `_embed_batch(texts)`: ver arriba.
- `_build_knn_graph(vectors, k=15)`: grafo de similaridad coseno, k vecinos
  más cercanos por nodo.
- `_cluster_l1(graph)`: clustering sobre el grafo completo → clusters
  grandes (el "L1" del video, 56 en Flick — acá, escalado a 1.500 títulos
  en vez de decenas de miles, un k mucho menor, pensar ~8-12).
- `_cluster_l2(l1_cluster_members)`: por cada cluster L1, arma el subgrafo
  de sus miembros y reclusteriza → subclusters (el "step 5, cluster the
  clusters" del video — con un pool tan chico, capaz alcanza con 2-4
  subclusters por L1, no busques replicar los 507 de Flick).
- `_label_cluster(sample_titles_metadata)`: un llamado a
  `llm_client._call_nvidia_with_fallback` (reusa la voz/infra que ya
  funciona, es un proveedor DISTINTO — NVIDIA NIM, no Gemini) pidiendo un
  nombre corto en español a partir de 4-6 títulos representativos. ~40-50
  llamados totales offline (no compite con Gemini), con `time.sleep(2)`
  entre cada uno para no pisar el ~40 req/min compartido de NIM
  (`docs/nvidia-setup.md`).
- `recompute(seed_cap=1500, ...) -> dict` (resumen): orquesta todo,
  upsert final a las tablas nuevas.

### `POST /admin/vibes/recompute`
Mismo guard que `admin_stats` (`main.py`, línea ~321: token en
`X-Admin-Token`, 404 si `BUTACA_ADMIN_TOKEN` no está seteado).
`threading.Lock()` a nivel módulo → 409 si ya está corriendo. Corre
sincrónico, tarda minutos. **No se dispara solo en cada deploy ni por
request de usuario.**

### Integración con el scoring
En `_finish_recommend` (`main.py`), al armar el pool de candidatos: un
lookup batcheado `db.get_title_clusters_by_tmdb_ids(ids)` inyecta
`vibe-l2:<id>` (preferir L2, el nivel que Flick mismo valida como el bueno)
a `item["tags"]`. `GET /recommend/options` (ya existe, hecho en la Fase 2)
suma un tercer grupo `"movimientos"` leído de `cluster_labels` (level=2) —
**el frontend no necesita cambios**, ya renderiza grupos dinámicamente
desde ese endpoint (`PICK_GROUP_LABELS` en `Recommend.tsx` sí necesita una
entrada nueva para la key `"movimientos"`, una línea).

**Cuidado con el "why":** `_tag_phrases` (`recommender.py`) no tiene forma
de mostrar un label dinámico — un tag `vibe-l2:7` caería al fallback y
mostraría el slug crudo. Necesita un `extra_phrases: dict[str,str] | None`
opcional threaded desde el caller (`_finish_recommend` ya tiene los labels
vía `db.get_vibe_clusters()`).

### Tests
- `backend/tests/test_vibes_clustering.py`: clustering sobre 3 grupos
  sintéticos bien separados a mano recupera 3 clusters limpios; mismo seed
  → mismos ids; cluster vacío se reasigna sin crashear; `_label_cluster`
  cae a un fallback simple (top keyword capitalizado) si `llm_client` tira
  error.
- `backend/tests/test_db.py`: round-trip de las 3 tablas nuevas.
- `backend/tests/test_main.py`: endpoint de recompute — 404 sin token, 403
  con token incorrecto, 200 con token correcto (mockeando
  `vibes_clustering.recompute`, nunca gastar cuota real en tests), y que
  `vibe-l2:<id>` se inyecte en los tags de un candidato.

**Antes de correr el recompute completo contra las APIs reales**: una
corrida chica (50-100 títulos, k bajo) a mano, revisar que los labels
generados tengan sentido — recién ahí correr el `recompute` grande y
habilitar el grupo en la UI.

## Checklist de retomada

1. `pip install python-igraph leidenalg` real — confirmar si hay fricción,
   elegir el camino de clustering según el resultado.
2. Tablas nuevas en `db.py` (ambos schemas).
3. `vibes_clustering.py` con `_embed_batch` en lotes (no 1x1).
4. Endpoint admin + integración de tags + `extra_phrases` en `_tag_phrases`.
5. `PICK_GROUP_LABELS["movimientos"]` en el frontend (una línea).
6. Tests, correr los 320 existentes + los nuevos.
7. Corrida chica de prueba (50-100 títulos) antes de la grande.
