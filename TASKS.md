# TASKS.md

> Nota: esto es un artefacto de proceso interno (coordinación entre agentes
> de IA trabajando en paralelo), no documentación de producto. Para
> entender qué es Butaca y cómo correrlo, ver [README.md](README.md); para
> el estado real del producto, ver [docs/mvp-status.md](docs/mvp-status.md).

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

Nota: se armó un worktree `pelipick-gemini` (`gemini/cache-001`) pero
Gemini no terminó participando — quedó sin usar, `cache-001` se
reasignó a Codex en `pelipick-codex`.

Nota: revisá siempre el diff antes de commitear con encoding — un editor
metió BOM + mojibake (cp1252) en todos los archivos que tocó en `auth-001`/
`cache-001`. Si ves acentos raros (`Ã³` en vez de `ó`) en tu propio diff,
pará y arreglalo antes de seguir, no lo dejes pasar.

`cache-001` y `auth-001` ya están en `main` (`bf855e0`, pusheado a GitHub).
`cast-001` ya no depende de `cache-001` por ese motivo.

## Pending

- [x] **Pedido de Matías (2026-07-30): buscar una peli en "Sin cuenta"
      mostraba los resultados en un dropdown angosto, no como posters** —
      `Recommend.tsx`. El dropdown flotante (fila chica con thumbnail 8x12 +
      texto, click para "agregar") se reemplazó: mientras hay una búsqueda
      activa (`isSearching`, mismo umbral de 2 caracteres que el debounce
      existente), la grilla de posters de abajo muestra directo
      `searchResults` en vez de la lista semilla, reusando el mismo
      `ManualRatingGrid`/`ManualRatingCard` de siempre — mismo tamaño, mismo
      estilo, se puntúa igual. `addSearchedTitle` (agregar sin puntuar) pasó
      a `rateSearchResult` (agrega a `addedTitles` Y puntúa en el mismo
      click, ya no hace falta un paso intermedio); al puntuar se limpia la
      búsqueda y vuelve a la grilla normal con el título ya arriba de todo.
      Sin resultados → mensaje en vez de grilla vacía. Verificado en el
      preview local mockeando `/onboarding/search` (la key de TMDb local
      está vencida): tipear "spiderman" muestra los posters reales de
      Spider-Man en la grilla, puntuar uno lo agrega (10→11 puntuadas),
      limpia la búsqueda y lo deja arriba de la lista normal; sin resultados
      muestra el mensaje. `tsc --noEmit` y `npm run build` limpios.
- [x] **Bug real de Matías (2026-07-30): recomendaba pelis ya vistas, y citaba
      un puntaje falso en el why de las puntuadas en "Sin cuenta"** — dos
      bugs de fondo distintos, reportados juntos con capturas.
      1. **Exclusión no unificada entre fuentes.** `_finish_recommend`
         (`main.py`) excluía candidatos con `extra_seen` (solo lo puntuado
         EN ESE request) + feedback explícito + "ya recomendado antes" —
         nunca consultaba `db.get_watched_items` (el historial completo,
         ya unificado a nivel DB porque `save_rated_items` solo hace
         INSERT). Puntuar en "Sin cuenta" y después generar con Letterboxd
         (u otra sesión) no sabía nada de lo puntuado por la otra fuente, y
         encima el perfil de gusto (sí construido desde el historial
         completo) sesgaba el descubrimiento de TMDb hacia esas mismas
         películas — autorreforzante. Fix: `also_seen` ahora suma
         `{item["title"] for item in watched}` (hard exclusion, igual en el
         retry que relaja solo `already_recommended`). Test de regresión
         (`test_recommend_manual_excludes_titles_rated_in_a_different_session`,
         falla con el código viejo, validado reintroduciéndolo a propósito).
      2. **El why citaba un puntaje que el usuario nunca dio.** El prompt del
         LLM (`llm_client._build_prompt`) formateaba TODO rating igual —
         `"{title} ({rating}/5): {review}"` — sin importar si venía de un
         puntaje real de Letterboxd o de un click de botón en "Sin cuenta"
         (`manualRatingOptions`: Me encantó→4.5, Bien→3.5, No me gustó→1.5,
         un rating sintético solo para el scoring interno). El LLM
         simplemente repetía ese "(4.5/5)" tal cual en el why. Fix: nueva
         columna `rated_items.source` ('import' | 'manual', migración +
         default 'import' para filas viejas), campo `RatedItem.source`
         propagado desde la persistencia real hasta el prompt; los items
         `source="manual"` se citan como `"(le encantó, sin puntaje
         numérico)"` en vez de `"(X/5)"`. Sumada una instrucción explícita
         en el prompt para no inventar puntajes. Test de regresión
         (`test_build_prompt_does_not_cite_a_numeric_score_for_manual_ratings`,
         mismo criterio de validar reintroduciendo el bug) + test de
         persistencia (`test_recommend_manual_persists_source_as_manual`).
      235 tests.
- [ ] **Hallazgo relacionado, no arreglado esta sesión:** el mismo problema
      de "puntaje sintético citado como preciso" existe también DENTRO de
      un import real de Letterboxd — `letterboxd_zip.py` usa
      `LIKE_RATING = 4.5` para títulos que el usuario marcó "like" sin
      puntuarlos con estrellas, y `FAVORITE_RATING` para "favoritos" — ambos
      quedan con `source="import"` (correcto a nivel de fuente) pero
      también son ratings inventados, no un puntaje real que el usuario
      haya dado. Si esto molesta igual que el caso de "Sin cuenta", hace
      falta otro eje además de `source` (algo como "rating preciso sí/no")
      para distinguirlo del caso de un rating real de Letterboxd que
      justo también sea 4.5.
- [ ] **Backlog de Matías repasado el 2026-07-30:**
      1. [x] Ampliar `KEYWORD_TAG_MAP` — hecho, ver entrada de Done más abajo.
      2. Typewriter para los "why" de la IA al abrir el poster (ya anotado
         más abajo, "a diseñar bien antes de implementar").
      3. Onboarding manual estilo swipe (ya anotado, punto 7 del feedback).
      4. Bugs de amigos: 19/20 + ronda 2 ya resueltos; queda el "Load failed"
         de Bauti (despriorizado, sin logs).
      5. [x] Banner "Usar mi perfil" en modo manual — hecho, ver entrada de
         Done más abajo (2026-07-30).
      6. Idea nueva sin desarrollar: pensar qué análisis (sobre `rated_items`
         u otra data ya existente) podría sacar a la luz resultados
         "escondidos" que hoy no se ven a simple vista — distinto de ampliar
         KEYWORD_TAG_MAP (punto 1), que es vocabulario ya visible. Sin scope
         concreto todavía, pensarlo antes de picar código.

> Estado al 2026-07-21: dominio propio comprado y en producción. Frontend en
> [butaca.xyz](https://butaca.xyz) (Vercel), backend en
> [api.butaca.xyz](https://api.butaca.xyz) (Render). `pelipick.vercel.app` /
> `pelipick-backend.onrender.com` siguen andando en paralelo (mismos
> proyectos, no se borró nada). Ver Done de hoy (`domain-001`) para el
> detalle completo.

- [x] **Tags de keywords de TMDb (2026-07-29)** — 3 commits
      (`0fdeb78`..`e936f9f`), 215 → 228 tests. Salió de un video sobre Flick
      (app que categoriza por "vibes" con embeddings + Leiden): se descartó
      replicar ese pipeline (necesita un corpus enorme de reviews que Butaca no
      tiene) y en cambio se explotó data que ya estaba a la vista —
      `/movie/{id}/keywords`, que el proyecto nunca consumía usando solo los 19
      `genre_ids` gruesos. `KEYWORD_TAG_MAP` (19 strings → 10 tags, **todos
      verificados contra páginas públicas de TMDb**, lo que descartó "one
      location" → es `huis clos`, "robbery" → es `caper`, "assassin" → es
      `hitman`), `fetch_keywords` calcado de `fetch_taste_credits`, entradas de
      `TAG_PHRASES`/`POSITIVE_HINTS`, y enganche en el loop de enriquecimiento
      (movies **y series**, que antes no recibían ninguno). Detalle largo en
      `docs/build-log.md` (entrada 2026-07-29). Sin tocar frontend ni schema.
- [x] **Verificado en producción (2026-07-29)** — hizo falta un 4to commit
      (`8445e9d`) porque el enriquecimiento **moría en silencio**: 3 tandas de
      picks, 18 candidatos, cero keyword tags, y sin logs no se distinguía "map
      angosto" de "roto". Con el log agregado, veredicto: **funciona, 0 fallos
      en 20 candidatos, hit rate ~30%** (Fight Club → dystopian, City of God →
      coming-of-age + true-story, Gladiator → revenge, Blade Runner →
      dystopian, Thelma & Louise → road-trip, Lords of Dogtown → true-story).
      Latencia real de los 20 enriquecimientos con cache frío: **1,44s**
      (~72ms cada uno), mucho menos de lo estimado — no hace falta tocar
      ningún cap.
- [x] **Enriquecer también el slice de exploration con keyword tags
      (2026-07-30)** — una de las dos palancas para subir la visibilidad de
      los tags. `fetch_personalized_candidates` (`tmdb_client.py`) llamaba
      `_enrich_with_keyword_tags` solo para profile/series; la exploration
      (`fetch_candidates(mood, pages=1)`) nunca pasaba por ahí, así que jamás
      competía en igualdad de condiciones en el scoring de `recommend()`.
      Mismo patrón que movies/series: loop sobre `exploration[:CREDITS_ENRICH_CAP]`
      llamando `_enrich_with_keyword_tags(item, item["kind"])` (los items de
      exploration ya traen `kind` desde `_map_result`, sirve para movie y
      series por igual). Test nuevo
      (`test_fetch_personalized_candidates_enriches_exploration_keyword_tags`).
      **Verificado en producción con logs de Render**: títulos que antes
      nunca aparecían en el log de keywords (Sinners, The Killer, Weapons)
      ahora sí, con tags reales (`time-travel`, `hitman`+`revenge`). La
      verificación encontró un 2do bug real el mismo día: `fetch_candidates`
      devuelve "movies + series" (movies siempre primero), así que cortar el
      cap sobre la lista combinada dejaba a las series de exploration sin
      enriquecer siempre que hubiera ≥ 20 movies (el caso normal, confirmado
      en los logs — cero líneas "(series)"). Fix: cap aplicado por separado a
      movies y series de exploration, igual que profile/series. Test de
      regresión (`..._enriches_exploration_series_past_the_movie_cap`, falla
      con el código viejo, validado reintroduciéndolo a propósito). 230 tests.
- [ ] **Otra palanca pendiente: subir `CREDITS_ENRICH_CAP`** (hoy 20) — la
      exploration ya se enriquece, pero sigue acotada al mismo cap que
      profile/series. Falta ver en producción si con esto solo ya sube la
      visibilidad o si además hace falta subir el cap.
- [x] **Ampliar `KEYWORD_TAG_MAP` (2026-07-30)** — 9 strings nuevos, todos
      re-verificados contra el buscador público de keywords de TMDb
      (`themoviedb.org/search/keyword?query=...`) antes de sumarlos. Reusan
      tag existente donde el concepto ya calzaba 1:1 (`hold-up robbery`→
      `heist`, `psychological thriller`→`psychological`, `character study`→
      `character`); tag nuevo donde forzarlo a uno existente perdía el matiz
      (`dark comedy`, `neo-noir`, `folk horror`, `survival`, `on the run`,
      `revisionist western` — cada uno con su entrada en `TAG_PHRASES` y en
      `POSITIVE_HINTS`). `historical` quedó afuera a propósito: existe en
      TMDb pero es tan genérico como el género History y no se lee como una
      razón específica de un pick — sumarlo solo diluiría el tope de 2 tags
      por título. Tests nuevos
      (`test_tags_from_keywords_maps_ronda_2_entries`); el guard existente
      (`test_recommender.py`, cada tag de `KEYWORD_TAG_MAP` tiene frase en
      `TAG_PHRASES`) valida los agregados sin cambios. 231 tests.
- [x] **Rediseño del banner "Usar mi perfil" en modo manual (2026-07-30)** —
      el banner era todo-o-nada: una vez usado, no dejaba sumar películas
      nuevas ni cambiar el rating de las ya puntuadas. `GET
      /onboarding/titles` (`main.py`) ahora mezcla la lista semilla con
      cualquier título que el usuario ya haya puntuado antes (de cualquier
      fuente, vía `db.get_watched_items`; resueltos contra TMDb best-effort
      sin año curado para los que no son semilla) y devuelve el `rating` de
      cada uno (`OnboardingTitle.rating`, nuevo campo opcional). El frontend
      (`Recommend.tsx`) precarga `manualRatings` con eso al abrir "Sin
      cuenta" — se eliminó el fork `useSavedProfile`/banner/`savedProfileCount`
      y el llamado a `POST /recommend/profile` (el endpoint backend queda,
      solo sin caller en el frontend). Verificado en el preview local
      end-to-end: puntuar 10 semillas → generar picks (persiste el rating) →
      reabrir "Sin cuenta" muestra las 10 precargadas con su rating real, sin
      banner — y son editables: se cambió una existente (Me encantó → Bien)
      y se sumó una no-semilla (Pulp Fiction) en la misma sesión, contador a
      "11 / 10". Test nuevo
      (`test_onboarding_titles_merges_previously_rated_titles`). 232 tests.
- [ ] **Ideas descartadas de la línea Flick, por si se retoman:** embeddings +
      Leiden clustering real, o embeddings + k-means/coseno. Ambas resuelven
      *descubrir* una taxonomía desconocida y necesitan corpus de reviews en
      volumen; Butaca no lo tiene (TMDb `/reviews` es escaso, Letterboxd da 403
      desde datacenter). El activo propio de largo plazo es otro: cuando haya
      cientos de usuarios reales, `rated_items` guarda qué pelis puntúan juntas
      *nuestros* usuarios — data que ni TMDb ni Letterboxd tienen y que Butaca
      genera sola. Hoy no hay escala para que sirva.

- [x] **Feedback de amigos ronda 2 (2026-07-29): modo manual no reusaba el
      perfil guardado** — el usuario que puntuaba a mano tenía que
      re-tildar las mismas pelis en cada sesión aunque el backend ya las
      guardaba. Fix: endpoint `POST /recommend/profile` (regenera con
      `_rebuild_ratings`, sin resubir fuente, `persist=False` para no
      duplicar `rated_items`) + banner "Ya tenés un perfil guardado" con
      botón "Usar mi perfil" en el paso 1 del wizard, visible con ≥10 pelis
      guardadas. Verificado en el browser local **y en producción**
      (butaca.xyz, cuenta `claude-verify-qa`): banner "Ya tenés un perfil
      guardado" aparece y "Usar mi perfil" regenera picks sin re-tildar
      nada. 213 → 215 tests. Detalle en
      [`03 Iteration Logs/(C) 2026-07-29 feedback-amigos-ronda-2.md`](<03 Iteration Logs/(C) 2026-07-29 feedback-amigos-ronda-2.md>)
      y `docs/build-log.md` (entrada 2026-07-29).
- [x] **Confirmar en producción que los picks salen con razón real del
      LLM** (pendiente desde la sesión 3, "lo primero a chequear al
      retomar") — confirmado 2026-07-29 en butaca.xyz: 6 "why" distintos,
      cada uno cita títulos reales del historial rateado (Fight Club, Pulp
      Fiction, Terminator 2, City of God, The Godfather), nada de la
      plantilla vieja "tira para el foco...".
- [ ] **Bauti: "Load failed" al importar por username (feedback ronda 2)**
      — no prioritario por ahora (Matías). Sin logs del momento no se pudo
      confirmar la causa. Sospechoso principal: cold start de Render +
      latencia extra del RSS de Letterboxd. Si vuelve a salir, revisar
      logs de Render en el momento exacto.

- [x] **Feedback de amigos: 19 de 20 puntos resueltos (2026-07-23, sesión
      2)** — lote rápido (1,4,5,6,12,13,19), wizard multi-step en
      `/recommend` (3,8,9,10,11 + aviso del 17), grilla a 3 columnas (2),
      navbar estilo YouTube (14,15), perfil real con avatar de película
      (16,20). 5 commits (`7512cf3`..`1f08904`), 207 tests, todo deployado.
      Detalle punto por punto (tachados con fecha) en
      [`03 Iteration Logs/(C) 2026-07-23 feedback-amigos-pre-lanzamiento.md`](<03 Iteration Logs/(C) 2026-07-23 feedback-amigos-pre-lanzamiento.md>)
      y en `docs/build-log.md` (entrada 2026-07-23 sesión 2).
- [ ] **Único punto de feedback abierto: 7 (onboarding manual estilo
      swipe/Tinder)** — a propósito: validar primero si el wizard nuevo ya
      resolvió la confusión antes de invertir en un rediseño de
      interacción. Decidir cuando los amigos vuelvan a probar.

- [x] **Bugs post-feedback + refine del LLM (2026-07-23, sesión 3)** — 4
      commits (`0feed46`..`eb393be`), 213 tests, todo deployado. Detalle en
      `docs/build-log.md` (entradas de sesión 3):
      - Poster equivocado en onboarding (Toy Story 1995 mostraba Toy Story 5):
        `search_title` ahora acepta `year` y lo pasa como `primary_release_year`.
      - Tilt 3D + glare en los posters de la grilla "Sin cuenta" (faltaba).
      - Default del wizard a Películas en vez de Ambas.
      - **El refine del LLM caía SIEMPRE al heurístico en prod** (los "why"
        calcados "tira para el foco..."): NVIDIA devolvía JSON casi-válido
        intermitente; fix con `response_format: json_object` (medido 8/8 vs
        4/6). Diagnosticado con logs de Render + repro contra la API real.
      - Reintento + fallback de modelo (nemotron → llama-3.1-70b).

- [x] **Confirmar en producción que los picks salen con razón real del LLM**
      — confirmado 2026-07-29 (ver entrada duplicada más arriba en este
      mismo `Pending`, cerca del feedback ronda 2).

- [x] **Esconder los "why" del menú y revelarlos con efecto máquina de
      escribir al entrar al poster (2026-07-30)** — pedido de Matías, hecho.
      `RecommendationCard` (`Recommend.tsx`) ya no muestra la frase del
      "why" — solo poster, score, título/año y la línea de director/tags.
      `MovieModal.tsx` suma `useTypewriterWhy`: anima el texto letra por
      letra (18ms/char, cursor parpadeante) solo la primera vez que se abre
      cada poster en la sesión — el estado de "ya lo vi" vive en
      `Recommend.tsx` (`seenWhysRef`, un `Map<recId, why>` en un `useRef`,
      no `useState`, porque nada en la página necesita re-renderizar cuando
      cambia) y se pasa a `MovieModal` porque el modal se desmonta al cerrar
      (`{selectedRec && <MovieModal key={selectedRec.id} .../>}`) así que un
      estado local ahí no sobrevive a cerrar/reabrir. Respeta
      `prefers-reduced-motion` (salta directo a texto completo) y es
      opcional (`seenWhys?:`) — `Home.tsx` no lo pasa, así que su modal de
      "current picks" queda exactamente como antes, sin animación.
      **Dos bugs reales encontrados y arreglados en el camino:**
      1. El "why" que ve el modal es una copia (`selectedRec`, un state
         aparte que no deriva de `result`) tomada al abrirlo — si el refine
         del LLM llegaba con el modal ya abierto, `result` se actualizaba
         pero el modal se quedaba con el "why" heurístico viejo para
         siempre. Fix: `refineSession` ahora también sincroniza
         `selectedRec` cuando corresponde.
      2. El typewriter marcaba "visto" al EMPEZAR a animar, no al terminar
         — con `StrictMode` (dev monta → corre el effect → cleanup → monta
         nuevo) la 2da pasada ya encontraba "visto" (marcado por la 1ra) y
         mataba la animación real por completo antes de que corriera un
         solo tick, mostrando el texto completo instantáneo siempre.
         Reproducido y confirmado con snapshots de texto en el tiempo en el
         preview local (longitud del texto constante en 0/30/80/150/400ms:
         nunca crecía). Fix: se marca "visto" recién cuando el intervalo
         termina de tipear, no al arrancar (mismo patrón de guard contra
         double-invoke que ya usa `VerifyEmail.tsx`, adaptado porque acá el
         effect sí necesita poder re-correr de verdad cuando cambia el
         `why`, no solo una vez por vida del componente).
      Verificado end-to-end en el preview local: texto creciendo
      progresivamente (4→21→66→178→284 caracteres en el tiempo), reabrir el
      mismo poster muestra el texto completo al instante sin re-animar,
      `tsc --noEmit` y `npm run build` limpios, sin errores nuevos de
      consola ni de logs del backend.

- [ ] **Decidir el fallback del LLM: ¿sumar kimi-k2.6 o quedarnos con
      llama-3.1-70b?** — hoy el fallback es `meta/llama-3.1-70b-instruct`
      (drop-in probado 5/5). Kimi-k2.6 lo pidió Matías: aparece en el catálogo
      con la misma `NVIDIA_API_KEY` (119 modelos accesibles con una key vía
      `integrate.api.nvidia.com`), PERO al invocarlo por el endpoint estándar
      da `404 "Function not found"` — necesita otro endpoint/deployment. Queda
      decidir: dejarlo con llama (recomendado, anda) o investigar cómo se
      invoca kimi de verdad. Recordar: cualquier modelo del mismo NVIDIA
      comparte key/host → no cubre caída total ni rate limit de cuenta; para
      eso haría falta otro proveedor.

- [x] **Setear `NVIDIA_API_KEY` en Render** — hecho por Matías. Verificado
      en vivo el 2026-07-23: cuenta de prueba descartable en butaca.xyz,
      picks con `refine` real (razones generadas cruzando películas
      específicas del perfil, no la plantilla heurística) — el agente de IA
      corre en producción.
- [x] **Rotar credenciales** — hecho por Matías (Neon, `RESEND_API_KEY`,
      `TMDB_API_KEY`). Verificado indirectamente: TMDb y la DB (Neon)
      responden bien en el smoke test del 2026-07-23.
- [x] **Cuentas de prueba en producción** (`test-resend-qa`,
      `claude-verify-qa`) — descartado 2026-07-29: a Matías no le importa
      que queden, no vale la pena la acción.
- [ ] **Aprovechar el `tmdb:movieId` del RSS** (mejora, no bug) — el feed trae
      el id de TMDb ya resuelto por entrada, pero el flujo sigue matcheando
      por título como con el zip. Usarlo ahorraría requests a TMDb y evitaría
      errores de matcheo, pero pedía tocar el pipeline compartido con el zip,
      así que quedó afuera. Detalle en `docs/letterboxd-username-import.md`.
- [x] **Avisar en el frontend que el import por username trae solo historial
      reciente** (~50 entradas del RSS, contra el historial completo del zip).
      **Resuelto 2026-07-29:** el tab "Username" del wizard ahora separa la
      descripción del aviso, mismo patrón que el "Ojo:" del modo manual —
      "Ojo: esto solo trae tu actividad reciente (~50 entradas) — para tu
      historial completo, usá el .zip." Verificado en el browser local.
- [x] **Despausar el monitor de UptimeRobot** — activo, confirmado por
      Matías el 2026-07-23.
- [x] **Auto-renew de `butaca.xyz`** — descartado 2026-07-29: a Matías no le
      importa, queda apagado a propósito. Vence 21 de julio de 2027; si en
      algún momento quiere renovarlo a mano, tiene tiempo de sobra.
- [x] **Ola 4 del plan de implementación** (`docs/(C) plan-implementacion-codigo.md`):
      H (onboarding sin Letterboxd), I (verificación de email + borrar cuenta),
      J (README) — las tres cerradas. J se resolvió en bilingüe:
      `README.md` en inglés (primario, portfolio internacional) +
      `README.es.md` en español, cruzados entre sí, con link a producción
      (`butaca.xyz`), pitch del producto y feature list actualizada. **Ola 4
      cerrada.**
- [ ] **Renombrar la carpeta del proyecto** (`03 Projects/PeliPick/` →
      `03 Projects/Butaca/`) y la lista de proyectos del `CLAUDE.md` raíz del
      vault (fuera de este repo) — pendiente, requiere permiso explícito
      porque toca archivos fuera de este repo.
- [ ] **Borrar el proyecto viejo de Neon** (São Paulo) una vez confirmado
      que el nuevo (Oregon) anda sin sobresaltos unos días.

## In Progress

## Blocked

(vacío)

## Done

- [x] [account-i-001] **Ola 4 · Tarea I — Verificación de email + borrar cuenta**
      | owner: claude | Higiene mínima para usuarios desconocidos. Todo calcado
      del flujo de reset de contraseña existente (token hasheado + TTL + mismo
      degrade sin Resend).
      - **Verificación de email:** columna `email_verified INTEGER DEFAULT 0` en
        `users` (ambos schemas + migración `_run_migrations` para DBs
        existentes), tabla `email_verification_tokens` (espejo de
        `password_reset_tokens`, entra por el schema `IF NOT EXISTS`).
        `mailer.send_verification_email` (mismo esqueleto que el de reset, TTL
        24h). `main.py`: al registrarse se genera token + se manda mail (sin
        Resend queda logueado; con `BUTACA_DEBUG=1` el token sale en la
        respuesta de register vía `RegisterResponse`). `POST /auth/verify-email`
        (público, como reset) confirma; `POST /auth/verify-email/resend`
        (auth'd) reenvía; `GET /auth/me` ahora devuelve `email` + `email_verified`.
        **No bloquea ninguna feature** — es aviso, no muro. Frontend:
        `VerifyEmail.tsx` (calcada de `ResetPassword.tsx`, con guard de
        StrictMode porque el token es de un solo uso) + `VerifyEmailBanner.tsx`
        (banner discreto no bloqueante con reenviar/cerrar, bajo el navbar).
      - **Borrar cuenta:** `db.delete_user_completely(user_id, username)` — DELETE
        en orden hijo→padre (feedback → recommendations_served →
        recommendation_sessions → rated_items → taste_profiles → watchlist_items
        → email_verification_tokens → password_reset_tokens → sessions →
        login_attempts por username → users), todo en una conexión/transacción.
        `DELETE /auth/account` con password en el body (re-confirmación: el token
        de sesión solo no alcanza). Frontend: `deleteAccount` en `useAuth` +
        zona "danger" al pie de `Profile.tsx` con confirm de dos pasos (tipear el
        usuario + password, estilo GitHub) → borra, limpia sesión local,
        redirige a home.
      - Modelos: `RegisterResponse`, `EmailVerificationConfirmRequest`,
        `DeleteAccountRequest`. Auth: `EMAIL_VERIFICATION_TTL_SECONDS`,
        `create_email_verification_token`.
      - Tests: 8 nuevos en `test_auth.py` (register→verify→me; me unverified por
        default; token inválido/expirado; resend con token + noop una vez
        verificado; delete con password mala → 401; delete sin auth → 401; delete
        exitoso → login falla + cero filas huérfanas en 7 tablas). **194 → 202**.
      Verificado end-to-end en local (front+back): banner aparece sin verificar y
      desaparece al confirmar; `/verify-email` marca `email_verified=1` y consume
      el token; danger zone bloquea el botón hasta usuario+password correctos,
      borra la cuenta, redirige a home y el login posterior da 401 sin filas
      huérfanas.
      **Pendiente de cierre de ola:** `build-log.md` + "Current Status" de
      `CLAUDE.md` (requieren permiso, sin prefijo `(C)`), y la tarea J (README).

- [x] [onboarding-001] **Ola 4 · Tarea H — Onboarding sin Letterboxd** | owner:
      claude | Que alguien sin cuenta de Letterboxd pueda usar el producto:
      puntúa a mano ≥10 películas conocidas y con eso arma perfil + picks.
      - **`backend/app/onboarding_titles.py`** (nuevo): 39 títulos curados
        (1972-2024, variados en género/década) como constantes públicas
        estables. Curados a mano, no de `/movie/popular` (que ordena por clics
        del sitio y sesga a estrenos), y unambiguos a propósito porque
        `search_title` toma `results[0]` (orden de popularidad de TMDb).
      - **`GET /onboarding/titles`** (`main.py`): resuelve poster/tmdb_id de cada
        título contra TMDb en paralelo (mismo `ThreadPoolExecutor` que
        `_watchlist_candidates`, reusa `search_title` cacheado 24h — sin
        endpoint fetch-by-id nuevo). Sin `TMDB_API_KEY` degrada a título/año.
      - **`POST /recommend/manual`** (`main.py`): body JSON `{ratings:[{title,
        rating}], mood, mode, kind_filter, genres, refine}`; valida ≥10 ratings
        (`MIN_MANUAL_RATINGS`), arma `RatedItem`s y delega en el
        `_finish_recommend` compartido (enriquecimiento de tags, perfil,
        candidatos, persistencia, refine). Los títulos puntuados entran a
        `extra_seen` para no recomendarlos de vuelta.
      - **Modelos** (`models.py`): `ManualRating`, `ManualRecommendRequest`,
        `OnboardingTitle`, `OnboardingTitlesResponse`.
      - **Frontend** (`frontend/src/pages/Recommend.tsx`): en vez de una página
        nueva que duplicaría todo el render de picks/modal/feedback/refine, se
        agregó "manual" como **tercera fuente** ("Sin cuenta") junto a
        zip/username — reusa la vista de resultados tal cual. Grilla de posters
        con botones Me encantó/Bien/No me gustó/No la vi (4.5/3.5/1.5/skip) en
        la columna derecha, contador N/10, y `POST /recommend/manual` en
        `handleGenerate`. Modos `watchlist`/`recent` deshabilitados para manual
        (sin zip / sin fechas de visto).
      - **Búsqueda de pelis fuera del catálogo** (pedido de Matías): la lista
        curada es fija, así que se sumó una caja de búsqueda arriba de la grilla
        para agregar una peli vista que no esté ahí. `tmdb_client.search_titles`
        (multi-resultado, movies, forma mínima título/año/tmdb_id/poster) +
        `GET /onboarding/search?q=` (degrada a lista vacía sin key / query <2
        chars / error de TMDb). Frontend: input con debounce 350ms + dropdown de
        resultados; al elegir uno se agrega arriba de la grilla y se puntúa con
        los mismos botones (deduplica contra la lista curada y lo ya agregado).
      - Tests: 10 nuevos en `test_main.py` (titles con/sin TMDb + auth; manual
        con picks/exclusión/validación de mode y mínimo; search con match/query
        corta/sin key). **184 → 194**.
      Verificado end-to-end en local (front+back corriendo): grilla renderiza
      los 39, contador y botón de generar reaccionan, submit aterriza en la
      vista de picks reusada. Nota: el TMDb local devuelve 401 (el `.env` local
      tiene la key vieja rotada la sesión pasada — config local, no bug), así
      que en local degrada al catálogo mock; producción tiene la key nueva.
      **Pendiente de cierre de ola:** entrada en `build-log.md` y "Current
      Status" de `CLAUDE.md` (requiere permiso, sin prefijo `(C)`).

- [x] [llm-match-001] **Dos bugs que tiraban los picks del LLM al heurístico**
      | owner: claude | Encontrados al verificar el import por RSS: el log
      decía `LLM refine failed: NVIDIA no devolvió picks válidos`, con los 6
      "why" idénticos — el mismo síntoma que originó `rec-quality-001`.
      - **Match por string exacto** (`llm_client.py`): los picks del modelo se
        buscaban con `title.strip().lower()` contra los candidatos, así que
        `"GoodFellas (1990)"`, un acento distinto o un guion cambiado
        descartaba **los 6 picks de una** y caía todo al heurístico. Ahora
        `_title_key()` normaliza año al final, acentos y puntuación antes de
        comparar, y se loguean los títulos que quedaron afuera (para detectar
        si alguna vez el modelo empieza a traducir títulos, que era la otra
        hipótesis).
      - **Se cacheaba la respuesta antes de validarla:** `_store_cached_refine`
        corría apenas volvía el modelo, así que una respuesta inservible
        quedaba pegada los 15 min del TTL y **todo reintento fallaba idéntico
        sin volver a preguntar**. Ahora se cachea recién después de validar.
      Verificado en producción end-to-end: misma request pasó de
      `refined=False` con 6 "why" iguales a `refined=True` con razones
      distintas citando títulos reales del historial ("Al igual que en 'The
      Grand Budapest Hotel' y 'Punch-Drunk Love'..."). 181 → 184 tests.

- [x] [letterboxd-rss-001] **Import por username reescrito sobre el feed RSS
      oficial** | owner: claude | Reemplaza el scraping de HTML que estaba
      roto en producción (ver `letterboxd-scrape-403` abajo). Letterboxd
      publica un RSS por perfil — lo recomiendan ellos mismos en la página de
      la API como alternativa oficial — que sale con `urllib` pelado, sin
      challenge de Cloudflare. Por entrada trae **más** que el HTML del
      diario: rating, fecha de visto, rewatch como flag explícito, si el
      miembro le puso like (el scraper no podía), y `tmdb:movieId` ya resuelto
      (todavía sin aprovechar, ver `Pending`). Los likes sin puntuar entran
      con rating sintético 4.5, igual que `likes/films.csv` en el zip.
      **El costo es el alcance:** el feed expone ~50 entradas contra las ~2000
      que paginaba el scraper — medido contra `scorsese`: 254 ratings por
      scraping vs 19 por RSS (10 puntuadas + 9 likes) + 31 vistas. El `.zip`
      sigue siendo la vía para historial completo. De paso se **borró la
      dependencia `curl_cffi`**, que existía solo para el scraping.
      Verificado en producción: 200 con 6 picks (antes 400).

- [x] [letterboxd-scrape-403] **Diagnosticado el 403 del import por username**
      (no arreglable en código, resuelto después con RSS — ver
      `letterboxd-rss-001` arriba) | owner: claude | Apareció al probar el flujo
      end-to-end después de activar el LLM. Síntoma: `POST /recommend/letterboxd`
      devuelve 400 con "Letterboxd devolvió un error (403)" en producción,
      pero **el mismo código anda perfecto en local** (200, con la misma
      versión pinneada `curl_cffi==0.15.0` y el mismo `impersonate="chrome"`).
      Diagnóstico en dos pasos, agregando logging del lado del server (mismo
      método que sirvió con Resend): primero el código de error de Cloudflare
      (salió `?`, o sea sin código numérico → descarta el 1010 de fingerprint
      y los 1006/1007/1008 de IP baneada), después un snippet del body →
      **`"Just a moment..."`, la página de challenge de JavaScript**, con
      `cf_ray=...-PDX` (Portland, la región de Render) y `server=cloudflare`.
      **Conclusión:** no es fingerprint TLS (`curl_cffi` sigue pasando esa
      parte), es la **reputación de IP** — Cloudflare le sirve challenge a las
      IPs de datacenter y no a las residenciales. Resolverlo requiere ejecutar
      JS (browser headless, inviable en el free tier de Render) o un proxy
      residencial (cuesta plata y agrava el tema ToS ya marcado como riesgo en
      el plan maestro). **Lo que sí se hizo:** el 403/503 ahora devuelve un
      mensaje que manda al usuario al import por `.zip` en vez de un código
      crudo, el logging de diagnóstico queda para futuras regresiones, y la
      limitación quedó documentada arriba de todo en
      `docs/letterboxd-username-import.md`. 182 → 184 tests.

- [x] [resend-001] **Resend activado end-to-end** | owner: claude + Matías |
      Dominio `butaca.xyz` verificado en Resend (región `us-east-1`, la misma
      costa que Render, mismo criterio que la migración de Neon). DNS en
      Namecheap: `TXT resend._domainkey` (DKIM), `TXT send` (SPF) y
      `MX send` → `feedback-smtp.us-east-1.amazonses.com`. El SPF de Resend
      va en el subdominio `send`, así que no chocó con el SPF de email
      forwarding que Namecheap tenía en `@` — igual ese se borró solo al
      pasar Mail Settings a **Custom MX** (necesario para poder cargar el MX).
      **Bug real encontrado y arreglado (`42a9a3f`):** la API de Resend está
      detrás de Cloudflare, que rechazaba el `User-Agent` default de urllib
      (`Python-urllib/3.x`) con `403 error code: 1010` — no era la key ni el
      dominio. Con cualquier UA propio pasa; **no** hizo falta `curl_cffi`
      como en `letterboxd_scrape.py` (ahí el bloqueo era por fingerprint TLS,
      acá es solo el header). Verificado contra la API real con una key falsa:
      sin UA da 1010, con UA da el 401 de auth esperado. Test de regresión
      agregado (180 → 182 tests).
      **Dos fallbacks mudos arreglados en el camino** (`e224297`, `c477d5c`),
      que eran la razón de que nada de esto se viera: `/auth/forgot-password`
      no logueaba nada si `RESEND_API_KEY` faltaba, y el `MailError` se comía
      el body de la respuesta HTTP (que es donde Resend explica el motivo);
      el refine del LLM devolvía el heurístico sin loguear si faltaba la key.
      Ese segundo caso destapó el bug de `NVIDIA_API_KEY` (ver `Pending`).

- [x] [render-dup-001] **Servicio duplicado en Render, borrado** | owner:
      claude | Al pushear el `render.yaml` actualizado, el Blueprint "PeliPick"
      buscó un servicio llamado `pelipick-backend` (el nombre que dice el
      yaml), no lo encontró porque Matías había renombrado el servicio real a
      `butaca-backend` en el dashboard, y **creó uno nuevo desde cero**
      (`srv-d9fs564ab06s73fr8620`, url `pelipick-backend-k36q.onrender.com`).
      Nacía roto: solo tomaba las 2 env vars que el yaml define con `value:`,
      sin `DATABASE_URL` ni API keys (las `sync: false` quedan vacías), y
      consumía horas del free tier — que según el plan maestro alcanza para
      exactamente un servicio. Es el riesgo exacto que se había documentado en
      `rebrand-externo-001` y que motivó no tocar el campo `name:` del yaml.
      Borrado el servicio duplicado **y el Blueprint** (el servicio real sigue
      auto-deployando desde GitHub igual; `render.yaml` queda en el repo solo
      como documentación de qué variables hacen falta). También se borraron
      del servicio real dos env vars muertas: `GEMINI_API_KEY` y
      `PELIPICK_ALLOWED_ORIGINS` (ninguna se lee en el código, verificado).
      Nota de proceso: esto se hizo vía la **API REST de Render**, con la key
      en una env var de usuario de Windows (`RENDER_API_KEY`, leída del
      registro en cada llamada) para no exponerla en el chat.

- [x] [domain-001] Comprado `butaca.xyz` (Namecheap, $1,58 el año 1 + $0,20
      ICANN fee, sin auto-renew) y configurado de punta a punta como dominio
      real de producción | owner: claude + Matías (compra y checkout manual,
      resto vía CLI/DNS) | DNS en Namecheap (Advanced DNS de `butaca.xyz`):
      - `A` `@` → `76.76.21.21` (Vercel)
      - `CNAME` `www` → `cname.vercel-dns.com.` (Vercel)
      - `CNAME` `api` → `pelipick-backend.onrender.com.` (Render)
      Se borró el CNAME `www → parkingpage.namecheap.com` que Namecheap
      arma solo por default (competía con el registro de Vercel) y el
      "Redirect Domain" automático (`butaca.xyz → www.butaca.xyz` vía el
      servicio de forwarding de Namecheap, también hubiera competido con el
      A record). `api.butaca.xyz` agregado como Custom Domain en Render
      (verificado, certificado emitido). `butaca.xyz`/`www.butaca.xyz`
      agregados al proyecto de Vercel vía `vercel domains add`, verificados
      (`vercel domains verify`), redeploy manual disparado para que tomen el
      alias nuevo. Código actualizado: `render.yaml`
      (`BUTACA_ALLOWED_ORIGINS` → `https://butaca.xyz,https://www.butaca.xyz,
      https://pelipick.vercel.app`, sin tocar el campo `name` por el riesgo
      ya documentado en `rebrand-externo-001`), `backend/app/main.py`
      (`_DEFAULT_ALLOWED_ORIGINS`), `backend/app/mailer.py`
      (`DEFAULT_RESET_URL`), env var `VITE_API_BASE_URL` en Vercel (borrada y
      recreada apuntando a `https://api.butaca.xyz`, requirió redeploy manual
      porque Vite la hornea en build time, no runtime). Docs actualizados a
      las URLs nuevas donde reflejaban estado actual (no logs fechados):
      `AGENTS.md`, `CLAUDE.md`, `DESIGN.md`, `docs/mvp-status.md`. 180 tests
      de backend siguen en verde (ninguno dependía de las URLs viejas).
      Verificado en vivo: `curl https://api.butaca.xyz/health` → 200;
      `curl http://butaca.xyz` sirve el HTML real de la app (HTTPS del
      apex/www tardó unos minutos más en terminar de emitir el certificado,
      normal en Vercel tras verificar un dominio nuevo).

- [x] [rebrand-externo-001] Commit + push de lo acumulado del 2026-07-20
      (`c698ad3`, 180 tests en verde) y rebrand externo parcial | owner:
      claude | GitHub: `gh repo rename` de `matiassrusso/PeliPick` →
      `matiassrusso/Butaca` (remote local actualizado automáticamente, sin
      downtime — GitHub deja redirect). Vercel: `vercel project rename
      pelipick butaca` (mismo project ID, sin recrear nada). **Hallazgo
      importante:** ninguna de las dos URLs públicas cambió, y no van a
      cambiar sin comprar un dominio propio:
      - `butaca.vercel.app` ya pertenece a un proyecto de terceros ajeno
        (namespace `*.vercel.app` es global entre todos los usuarios de
        Vercel, no solo la cuenta) — confirmado comparando `<title>` de
        `pelipick.vercel.app` (nuestro, "Butaca") contra `butaca.vercel.app`
        ("Butaca: Peliculas, libros y videojuegos", de otro dueño).
        `pelipick.vercel.app` sigue siendo nuestra producción real.
      - Render: el nombre del servicio es solo un label de dashboard, la URL
        `.onrender.com` queda fija desde la creación del servicio y no se
        puede cambiar sin recrearlo — Matías lo renombró a `butaca-backend`
        en el dashboard, la URL siguió siendo `pelipick-backend.onrender.com`.
        Recrear el servicio para forzar la URL nueva perdería las env vars
        `sync: false` (`TMDB_API_KEY`, `NVIDIA_API_KEY`, `RESEND_API_KEY`,
        `DATABASE_URL`) — **no se intentó**, demasiado riesgo para cero
        beneficio real.
      - **No se tocó `render.yaml`** (ni el `name:` ni `BUTACA_ALLOWED_ORIGINS`)
        porque cambiar el campo `name` de un servicio ya existente en un
        Blueprint sync puede hacer que Render lo interprete como un servicio
        nuevo en vez de un rename — mismo riesgo de perder las env vars
        `sync: false` de arriba.
      Conclusión: el único camino real para URLs `butaca.*` es comprar el
      dominio (ya en `Pending`) y setearlo como custom domain en ambos.

- [x] [rebrand-butaca] Rebrand completo **PeliPick → Butaca** | owner: claude |
      Script de reemplazos ordenados (no sed global, que habría roto las URLs
      de deploy): `PELIPICK_`→`BUTACA_`, `PeliPick`→`Butaca`,
      `pelipick-frontend`/`pelipick_token`/`pelipick-theme`/`pelipick.db` →
      equivalentes con `butaca`. 35 archivos + `.claude/launch.json` +
      renombrado el archivo físico `backend/pelipick.db` → `butaca.db`.
      **NO renombrado a propósito:** `pelipick.vercel.app`,
      `pelipick-backend.onrender.com`, `name: pelipick-backend` de
      `render.yaml` (identidad real del deploy) y los worktrees históricos.
      Disponibilidad de dominio chequeada por RDAP: libres `butaca.io/.co/
      .me/.film`, tomados `.com/.app/.tv/.ar/.com.ar`. 180 tests en verde,
      build limpio. Detalle en `docs/build-log.md`.

- [x] [health-head-405] Fix de `/health`: devolvía 405 a los monitores de
      uptime (UptimeRobot prueba con `HEAD`, el endpoint era GET-only) —
      falso positivo, no una caída. `@app.api_route("/health", methods=["GET",
      "HEAD"])` + test de regresión | owner: claude | archivos:
      `backend/app/main.py`, `backend/tests/test_main.py`. 179 → 180 tests.

- [x] [neon-oregon] Migración de la base de Neon `sa-east-1` (São Paulo) a
      `us-west-2` (Oregon), misma región que el backend en Render — cada
      query cruzaba de continente | owner: claude | copiado con script
      `psycopg2` ad-hoc reusando `db.get_connection()` para el schema,
      verificado por conteo de filas en las 9 tablas con datos. Medido contra
      producción: login de ~2.85s (baseline São Paulo) a **0.59s**. Proyecto
      viejo sin borrar como colchón. Detalle en `docs/build-log.md`.

- [x] [release-ola1/2/3] Ejecución de las primeras 3 olas del plan de
      implementación (`docs/(C) plan-implementacion-codigo.md`). Owner: claude
      (secuencial, una sesión, sin subagentes). 160 → 179 tests de backend en
      verde, build de frontend limpio. Detalle completo en
      `docs/build-log.md` (entrada 2026-07-20 "olas 1-3"). Resumen:
      - **Ola 1:** warm-up de `/health` (`useAuth.tsx`); rate limiting de
        `/recommend/*` por usuario + `GET /admin/stats` (`main.py`, `db.py`);
        feedback loop en el scoring (`recommender.py`, `main.py`, `db.py` —
        exclusión dura de seen/not_interested + penalización de tags
        rechazados 2+ veces).
      - **Ola 2:** modo watchlist (`letterboxd_zip.py::parse_watchlist_titles`,
        tabla `watchlist_items`, `main.py`, `Recommend.tsx`); "dónde verla"
        vía `fetch_watch_providers` (`tmdb_client.py`, `models.py`, `main.py`,
        modal en `Recommend.tsx`); `_search_one` extendido con
        poster/overview/vote.
      - **Ola 3:** render progresivo — `refine` form field + endpoint
        `POST /recommend/sessions/{id}/refine` (`main.py`, `db.py`,
        `models.py`) + dos fases en `Recommend.tsx`.
      - Archivos de test tocados: `test_main.py`, `test_recommender.py`,
        `test_tmdb_client.py`, `test_letterboxd_zip.py` (+19 tests).
      - **Pendiente (Ola 4, no ejecutado):** onboarding sin Letterboxd (H),
        verificación email + borrar cuenta (I), README en inglés (J, bloqueado:
        ya hay `README.md` en español sin prefijo `(C)`).

- [x] [motor-fase1-003/004/005] Cierre de la Fase 1 del motor
      (`docs/(C) plan-de-trabajo.md` §4): los candidatos ahora salen del
      gusto real del usuario, no del top global de TMDb. Implementado en una
      sola sesión (sin subagentes ni worktrees — secuencial, con
      dependencias reales entre los 3 pasos):
      - **#3 `fetch_personalized_candidates`** | archivos:
        `backend/app/tmdb_client.py` (`GENRE_NAME_ID_MAP`/
        `TV_GENRE_NAME_ID_MAP` inversos, `_resolve_person_id` vía
        `/search/person` cacheado 24h, `_fetch_personalized_discover`
        cacheado 5 min por huella de perfil, `fetch_personalized_candidates`
        combina géneros OR + personas OR + década ±1 en una sola query por
        kind — `with_people` solo aplica a `/discover/movie`, confirmado en
        `docs/(C) research-tmdb-discover-personalization.md` que
        `/discover/tv` lo ignora en silencio — más una porción de
        exploración sin personalizar vía `fetch_candidates` reusado tal
        cual, todo deduplicado por `(kind, título)`). Enriquece hasta 20
        candidatos de película con director/cast (`fetch_taste_credits`,
        mismo caché que ya usaba `taste_profile.py`) para que el scoring
        (#5) tenga con qué comparar.
      - **`backend/app/main.py`** (`_finish_recommend`): corregida la
        secuencia que había quedado pendiente de #2 — `save_rated_items` y
        el cómputo del perfil ahora ocurren *antes* de traer candidatos (no
        después), así que incluso la primera recomendación de un usuario
        nuevo ya sale personalizada, no solo las siguientes. Cae a
        `fetch_candidates` sin personalizar cuando el perfil no tiene
        `genre_breakdown` (usuario sin match a TMDb, o error de red —
        guardado con el mismo `try/except Exception` amplio que ya traía #2).
      - **#4 mezcla con exploración** | archivo: `backend/app/recommender.py`
        (`_pick_with_exploration`, reserva 1 slot de los 5 para el
        mejor-puntuado con `_source: "exploration"`, así el pool
        personalizado no se cierra del todo sobre el mismo gusto).
      - **#5 scoring por director/actor/década** | mismo archivo
        (`_profile_signals` extrae directores/actores/década pesada del
        perfil persistido; +18 puntos por director match, +9 por actor,
        +6 por década — mismo orden de magnitud que los bonus de tags
        existentes; el "why" nombra la persona/década concreta cuando fue
        el motivo real, no un genérico).
      - **Bug encontrado y arreglado en el camino** (no relacionado a la
        feature en sí): `_tag_phrases` tiraba `IndexError` si un candidato
        no tenía ningún tag — nunca se disparaba porque
        `tmdb_client._map_result` ya filtra esos casos del pipeline real,
        pero es alcanzable por cualquier catalog dict sin tags (ej. mock
        catalog a mano) y lo expusieron los tests nuevos. Arreglado en el
        fallback de `recommend()`, no en `_tag_phrases` (los demás call
        sites ya vienen guardados con `if matched_xxx:`).
      Tests: 134 → 148 (14 nuevos: 8 en `test_tmdb_client.py`, 6 en
      `test_recommender.py`, 1 test existente en `test_main.py` corregido
      para no depender de que la red real falle rápido). Owner: claude,
      pedido explícito del usuario de hacerlas todas en una sola sesión en
      vez de repartir con Codex/subagentes esta vez.

- [x] [motor-fase1-001/002/006] Primera ronda de la Fase 1 del motor
      (`docs/(C) plan-de-trabajo.md` §4): tres tasks independientes
      despachadas en paralelo, cada una en su worktree, ya mergeadas a `main`
      (fast-forward + merge commit, sin conflictos):
      - **#1 research** (sin código): confirmado en vivo contra la API real
        de TMDb que `with_genres`/`with_people` usan pipe para OR (no comma,
        que es AND), que `with_people` **no existe en `/discover/tv`**
        (silenciosamente ignorado, confirmado con `total_results` idéntico
        con/sin el parámetro — el sesgo por director/actor solo puede
        aplicarse al pool de películas), que los tres filtros (género +
        persona + década) se combinan en una sola request con AND entre
        parámetros, y que el rate limit viejo de TMDb (~40 req/10s) se
        desactivó en 2019 (hoy ~40 req/s). Doc completo:
        `docs/(C) research-tmdb-discover-personalization.md`. Sin cambios de
        código.
      - **#2 persistir perfil de gusto** | archivos:
        `backend/app/db.py` (tabla `taste_profiles`, upsert vía
        `save_taste_profile`/`get_taste_profile`), `backend/app/main.py`
        (`_finish_recommend` persiste el perfil tras guardar los ratings
        importados; `taste_profile_endpoint` lee el persistido primero, cae
        al recompute on-demand solo si no hay nada guardado — usuarios
        pre-feature o antes del primer import), `backend/tests/test_main.py`
        (2 tests nuevos). Evita recomputar ~200 requests a TMDb en cada carga
        de `/profile/taste`. 128→130 tests. Reviewed y verificado en verde
        por Claude antes de mergear.
      - **#6 cachear Gemini refine** | archivos: `backend/app/llm_client.py`
        (`_REFINE_CACHE`, mismo patrón OrderedDict TTL+LRU que
        `_DISCOVER_CACHE` de `tmdb_client.py`; TTL 15 min, key = mood +
        tupla de `tmdb_id`s de los candidatos del heurístico; cachea el dict
        crudo de Gemini, revalida contra los candidatos de cada call — un
        cache hit no se salta la validación "solo títulos de la lista"),
        `backend/tests/test_llm_client.py` (4 tests nuevos). 128→132 tests.
        Reviewed y verificado en verde por Claude antes de mergear.
      Tests combinados en `main` tras mergear ambas: 134 en verde
      (128 base + 2 + 4). Owner: claude (3 subagentes, worktrees separados,
      despachados en paralelo desde una sesión orquestadora que revisó cada
      diff antes de mergear — Codex no participó en esta ronda, corrección
      del usuario pendiente de aplicar en la próxima).

- [x] [rec-quality-001] 3 bugs de calidad de recomendación reportados en uso
      real (probando el import por username recién agregado): el "why" era
      siempre casi el mismo texto ("humor y tono liviano"), no estaba claro
      si el import por username realmente leía el perfil, y las
      recomendaciones eran casi siempre estrenos/taquilla. Causas: (1)
      `_collect_preference_tags` (`backend/app/recommender.py`) sumaba
      ciegamente `funny/light/character/intimate` a cualquier título
      puntuado ≥4.5 sin mirar su contenido — con la mayoría de la gente
      puntuando varias cosas alto, ese ruido dominaba toda la señal real
      (texto de review, Tags propios); (2) el import por username no trae
      texto de review, así que sin ese bug la señal de gusto quedaba
      directamente en cero para esa vía; (3) `tmdb_client.fetch_candidates`
      pedía `sort_by=popularity.desc` a discover — eso es qué está sonando
      ahora, no qué es bueno, y sesgaba el pool de candidatos a estrenos.
      Fixes: se sacó el bonus ciego; se agregó
      `_enrich_loved_ratings_with_genre_tags` (`backend/app/main.py`) que
      completa el género real de TMDb (vía `tmdb_client.search_title`,
      extendido para devolver también `tags` del vocabulario interno, mismo
      request cacheado 24h que ya usaba `taste_profile.py`) para los
      títulos puntuados ≥4, capado a 30 por request (`TASTE_TAG_LOOKUP_CAP`)
      y gateado a "amado" para no colar señal falsa desde títulos odiados;
      se cambió `sort_by` a `vote_average.desc` | owner: claude | archivos:
      `backend/app/recommender.py`, `backend/app/tmdb_client.py`,
      `backend/app/main.py`, tests actualizados/nuevos en
      `test_recommender.py`, `test_tmdb_client.py`, `test_main.py`. 126
      tests de backend en verde (121→126).
      Al verificar en vivo apareció una 4ta causa, más de infraestructura que
      de lógica: el agente Gemini nunca estaba corriendo realmente. Dos bugs
      reales en `llm_client.py`: (a) la ruta IPv6 de esta red hacia
      `generativelanguage.googleapis.com` está rota — Python intenta la
      IPv6 primero, cuelga sin error hasta el timeout; forzar IPv4 (nuevo
      `_force_ipv4_dns()`, scopeado solo a esa llamada) lo evita; (b)
      `gemini-flash-latest` "piensa" antes de responder (`thoughtSignature`
      en la respuesta) y tarda ~19-20s incluso en un prompt trivial —
      `REQUEST_TIMEOUT=15` descartaba silenciosamente cada llamada real;
      subido a 30. Con ambos fixes, una llamada real terminó en 20.3s. Un
      tercer factor detectado (no arreglable en código): el rate limit
      gratuito de Gemini (`429`) se agotó en medio de tanto test seguido —
      cuando eso pasa cae al heurístico igual que un timeout. El fallback
      a heurístico era 100% silencioso en ambos casos (`except ...: pass`
      sin loggear nada) — se agregó `logger.warning(...)` en los dos
      catches de `_finish_recommend` (TMDb y Gemini) para que la próxima
      vez que "el why se vea igual" se pueda confirmar por qué en los logs
      del server en vez de tener que re-investigar todo de cero.
      El cupo gratis de Gemini resultó ser por modelo concreto, no por el
      alias `-latest`: el dashboard de Google AI Studio mostró
      `gemini-flash-latest` resolviendo hoy a "Gemini 3.5 Flash" con
      22/20 RPD (agotado), mientras `gemini-2.5-flash` y `gemini-3-flash`
      seguían casi sin usar (cupos separados). A pedido explícito del
      usuario, `_call_gemini` ahora prueba una cadena de modelos en orden
      (`GEMINI_MODELS` en `llm_client.py`: `gemini-flash-latest` →
      `gemini-2.5-flash` → `gemini-3-flash` → `gemini-3.1-flash-lite`,
      este último con 500 RPD de colchón) y cae al siguiente ante
      cualquier `LlmError` del anterior, en vez de ir directo al
      heurístico apenas falla el primero. Confirmado en vivo: cayó a
      `gemini-2.5-flash` y respondió en 3.5s con un "why" real citando
      "GoodFellas" del historial | archivos adicionales:
      `backend/app/llm_client.py`, 2 tests nuevos en `test_llm_client.py`
      (128 tests de backend en verde, 126→128). Sin commitear todavía.
- [x] [lb-username-001] Import por username de Letterboxd (scraping),
      alternativa a subir el zip: nuevo endpoint `POST /recommend/letterboxd`
      que scrapea el diario público (`/diary/films/page/N/`, hasta 20
      páginas) — rating, fecha real de visto, y rewatch (título repetido en
      el diario suma +0.5, tope 5.0). No cubre likes/favoritos/tags/ratings
      sin diario: las grillas `/films/` y `/films/ratings/` de Letterboxd
      hidratan el rating client-side vía React y no se pueden leer sin JS,
      así que el diario es la única vista pública server-rendered
      disponible. Hallazgo no anticipado: Letterboxd está detrás de
      Cloudflare bloqueando por fingerprint TLS (JA3) del handshake, no por
      headers — el stdlib `urllib`/`requests` de Python devuelve 403 pase lo
      que pase con el `User-Agent`; se agregó `curl_cffi` (imita el
      fingerprint TLS de Chrome vía libcurl) como única forma real de
      pasarlo. Confirmado end-to-end con datos reales del diario público de
      `scorsese` (254 ratings, 5 picks generados) | owner: claude |
      archivos: `backend/app/letterboxd_scrape.py` (nuevo),
      `backend/app/main.py` (`_validate_recommend_params`/
      `_finish_recommend` extraídos para compartir el flujo con
      `/recommend/zip`), `backend/requirements.txt` (`curl_cffi`),
      `frontend/src/pages/Recommend.tsx` (toggle zip/username), tests
      nuevos en `test_letterboxd_scrape.py` y `test_main.py`,
      `docs/letterboxd-username-import.md` (nuevo), `docs/api.md`,
      `docs/mvp-status.md`. 121 tests de backend en verde (105→121), build
      de frontend limpio.
- [x] [llm-001] Prompt de Gemini enriquecido: en vez de mandarle solo la
      lista cruda de reseñas, se le arma un "perfil de gusto" explícito
      (promedio, tags recurrentes en lo que más valoró, títulos que amó/odió)
      y se endurecen las instrucciones para que la razón de cada pick nombre
      un patrón concreto de ese perfil o del historial, no un elogio
      genérico. Gemini sigue eligiendo solo entre los candidatos ya
      filtrados por el heurístico — no rescorea ni trae títulos propios,
      eso queda para una iteración futura si hace falta | owner: claude |
      archivos: `backend/app/llm_client.py` (`_build_taste_digest`,
      `_phrase_for_tags`, `_build_prompt` reescrito), tests nuevos en
      `test_llm_client.py`. 105 tests de backend en verde (97→105 sumando
      data-001). Verificado el contenido del prompt armado a mano
      (perfil correcto con tags/títulos reales); una llamada real a Gemini
      dio timeout de red en este entorno, no se pudo confirmar la
      respuesta final del modelo en vivo.
- [x] [data-001] Usar más señal del zip de Letterboxd: Tags propios del
      usuario (diary.csv prioriza sobre reviews.csv si ambos los traen,
      solo se suman como señal positiva si matchean el vocabulario interno
      de tags) y fecha real de "visto" persistida (antes se parseaba desde
      diary.csv pero se perdía al guardar en `rated_items`; la pestaña
      "Vistas" mostraba la fecha de import, no la real) | owner: codex |
      archivos: `backend/app/models.py` (`RatedItem.tags`,
      `WatchedItem.watched_date`), `backend/app/letterboxd_zip.py`
      (`_parse_tags`), `backend/app/db.py` (columna `watched_date` +
      migración), `backend/app/main.py`, `backend/app/recommender.py`
      (`_collect_preference_tags` suma tags de usuario que matchean
      vocabulario), `frontend/src/pages/History.tsx`, tests en
      `test_letterboxd_zip.py`, `test_recommender.py`, `test_main.py`,
      docs (`letterboxd-zip-format.md`, `api.md`, `mvp-status.md`).
      Bug encontrado y arreglado por Claude en revisión: `History.tsx`
      reutilizaba `formatSessionDate` (pensada para timestamps con hora)
      para `watched_date` (solo fecha) — al interpretarla como medianoche
      UTC y mostrarla en hora local, en timezones detrás de UTC (Argentina,
      UTC-3) el día mostrado quedaba corrido un día para atrás. Se agregó
      `formatWatchedDate` con `timeZone: "UTC"` para mostrar el día literal.
      Verificado en vivo: zip con diary.csv (Whiplash, Watched Date
      2025-05-28) mostró "28 may 2025" en la pestaña Vistas.
- [x] [perfil-001] Perfil de gusto visual: radar de géneros, décadas y
      directores/actores favoritos, matcheando el historial "vistas" del
      usuario contra TMDb | owner: claude | archivos:
      `backend/app/tmdb_client.py` (`GENRE_ID_NAME_MAP`/`TV_GENRE_ID_NAME_MAP`,
      `search_title` con caché de 24h por título, `fetch_taste_credits` para
      director + top-3 cast), `backend/app/taste_profile.py` (nuevo,
      `build_taste_profile`), `backend/app/models.py`
      (`TasteProfileResponse` y afines), `backend/app/main.py`
      (`GET /profile/taste`), tests nuevos en `test_tmdb_client.py`,
      `test_taste_profile.py`, `test_main.py`, `frontend/src/pages/Profile.tsx`
      (nuevo, radar SVG + heatmap de décadas + listas de directores/actores,
      sin librería de gráficos), `frontend/src/App.tsx` y
      `frontend/src/components/Navbar.tsx` (ruta y link `/profile`). Cap
      deliberado: matchea hasta 150 títulos (los mejor puntuados primero) y
      pide créditos (director/cast) solo para los 50 mejores de esos, para
      que la carga no dependa de cientos de requests secuenciales a TMDb en
      exports grandes — motivo documentado con comentario `ponytail:` en
      `taste_profile.py`. 97 tests de backend en verde (85→97), build de
      frontend limpio, verificado en vivo con TMDb real: 10 títulos
      sembrados vía `/recommend/zip`, perfil resultante mostró 8 géneros, 4
      décadas y directores/actores correctos (Christopher Nolan, George
      Miller, Bong Joon Ho, etc.).
- [x] [scroll-001] Modal de detalle cortado cuando la página no está
      scrolleada arriba: `PageTransition` (framer-motion) siempre aplica
      `transform`/`filter` inline aunque estén "en reposo", lo que rompe el
      containing block de `position: fixed` para los descendientes — el
      modal terminaba posicionado contra el alto completo de la página en
      vez del viewport. Fix: `MovieModal` se renderiza vía React Portal a
      `document.body` | owner: codex | archivos:
      `frontend/src/pages/Recommend.tsx`. Verificado en vivo: el overlay
      queda como hijo directo de `<body>` y su rect coincide exactamente
      con el viewport sin importar el scroll de la página.
- [x] [why-001] Personalización del mensaje "why" por usuario y por
      película: antes eran frases plantilla fijas: ahora cita los tags
      específicos que matchearon (traducidos a frases legibles) y, cuando
      es posible, el título concreto del historial del usuario detrás del
      match (ej. "como lo que valoraste en «Mad Max: Fury Road»"); el
      mood también se menciona textualmente, y el fallback sin match varía
      según los propios tags de la película | owner: claude | archivos:
      `backend/app/recommender.py`, `backend/tests/test_recommender.py`.
      85 tests de backend en verde. Verificado en vivo con TMDb real.
- [x] [historial-002] Separar historial en "Vistas" (rated_items, deduplicado
      por título) y "Recomendadas" (lo ya existente) | owner: codex (3
      intentos por bloqueos de entorno del sandbox — worktree vacío sin
      `.git`, luego worktree hermano fuera del sandbox permitido; el tercer
      intento con worktree adentro de `Butaca/.claude/worktrees/` sí pudo
      escribir el código pero no pudo correr pytest/vite ni commitear por
      permisos del sandbox de Codex — Claude verificó tests+build y
      commiteó por él) | archivos: `backend/app/db.py`
      (`get_watched_items`), `backend/app/main.py` (`GET /history/watched`),
      `backend/app/models.py` (`WatchedItem`, `WatchedHistoryResponse`),
      `backend/tests/test_main.py`, `frontend/src/pages/History.tsx` (tabs
      Vistas/Recomendadas). Mergeado con el trabajo de modos-001 vía
      3-way patch (`git apply --3way`) sin conflictos. 81 tests de backend
      en verde, build de frontend limpio.
- [x] [modos-001] Rediseño del flujo "qué querés ver hoy": 3 modos (perfil
      completo / últimas pelis vistas / selección de géneros con lógica OR
      y cobertura garantizada por género) + split Películas/Series/Ambas |
      owner: claude | archivos: `backend/app/models.py` (campo
      `watched_date` en `RatedItem`), `backend/app/csv_ingest.py` (parsea
      fecha), `backend/app/letterboxd_zip.py` (prioriza `Watched Date` de
      diary.csv), `backend/app/recommender.py` (`GENRE_OPTIONS`,
      `kind_filter`, `required_any_tags` con cobertura, `preference_ratings`
      para separar señal de gusto de exclusión), `backend/app/main.py`
      (form fields `mode`/`kind_filter`/`genres` en `/recommend/zip`, valida
      y arma `required_any_tags`/`preference_ratings`),
      `frontend/src/pages/Recommend.tsx` (3 botones de modo, chips de
      género, toggle Películas/Series/Ambas, reemplaza el dropdown de mood),
      tests nuevos en `test_recommender.py` y `test_main.py`,
      `docs/api.md`. 77 tests de backend en verde (67→77), build de
      frontend limpio, verificado en vivo con TMDB real (genre OR-filter,
      kind_filter movie/series, modo recent) y sin regresión en el modal de
      detalle (cast/tráiler/scroll-lock siguen funcionando).
- [x] [cast-001] Cast y tráiler en el modal de detalle | owner: codex |
      rama: `codex/cast-001` | archivos: `frontend/src/pages/Recommend.tsx`,
      `TASKS.md`, `docs/api.md`, `docs/architecture.md`,
      `docs/mvp-status.md`. El modal pide los detalles solo si hay `tmdb_id`,
      muestra un estado discreto de carga, cast con fallback de foto y link
      al tráiler; ante fallo o catálogo mock mantiene el detalle base. Build,
      63 tests de backend y verificación visual con TMDb real en verde.

- [x] [historial-001] Historial de sesiones de recomendación revisitables
      (nuevo endpoint de listado sobre `db.py`, nueva página de frontend) |
      owner: codex | rama: `codex/historial-001` | archivos:
      `backend/app/db.py`, `backend/app/main.py`, `backend/app/models.py`,
      `backend/tests/test_main.py`, `frontend/src/App.tsx`,
      `frontend/src/components/Navbar.tsx`, `frontend/src/pages/History.tsx`,
      `docs/api.md`, `docs/architecture.md`, `docs/mvp-status.md`
- [x] [cache-001] Caché de resultados de TMDb (in-memory, TTL simple,
      stdlib, sin dependencias nuevas) — evita pegarle a `/discover/movie`
      y `/discover/tv` en cada request si el mood+página ya se pidió hace
      poco | owner: codex | rama: `codex/auth-001` | archivos:
      `backend/app/tmdb_client.py`, `backend/tests/test_tmdb_client.py`,
      `docs/tmdb-setup.md`
- [x] [auth-001] Recuperación de contraseña + rate limiting de login |
      owner: codex | rama: `codex/auth-001` | archivos:
      `backend/app/auth.py`, `backend/app/db.py`, `backend/app/main.py`,
      `backend/app/models.py`, `backend/tests/test_auth.py`, `docs/api.md`.
      Revisado por Claude: `/auth/forgot-password` devolvía el
      `reset_token` en la respuesta a cualquiera (toma de cuenta completa
      en 3 requests sin tocar el email del usuario) — arreglado en un
      commit aparte (`4b7f80e`), ahora solo se expone con
      `BUTACA_DEBUG=1`, nunca por default. También se arregló encoding
      roto (BOM + mojibake por cp1252) en los 10 archivos que tocó
      Codex (commit `a5b4a4e`), sin cambios de comportamiento.
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
