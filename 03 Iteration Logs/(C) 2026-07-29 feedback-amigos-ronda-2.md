# Feedback de amigos — ronda 2 (2026-07-29)

> Matías siguió juntando reseñas de amigos después de la ronda del
> 2026-07-23 (`(C) 2026-07-23 feedback-amigos-pre-lanzamiento.md`). Mismo
> criterio: se tacha acá cuando se resuelve, detalle técnico en
> `docs/build-log.md`.

21. ~~**Modo manual ("Sin cuenta") no persistía entre sesiones** — el
    usuario que puntuaba pelis a mano tenía que volver a tildar las mismas
    pelis cada vez que quería una tanda nueva de recomendaciones, aunque el
    perfil ya quedaba guardado en el backend.~~ **Resuelto 2026-07-29:**
    causa raíz era que el wizard no ofrecía ninguna forma de reusar el
    perfil ya guardado (`db.save_rated_items` sí persistía, pero no había
    endpoint ni UI para regenerar sin resubir una fuente). Nuevo endpoint
    `POST /recommend/profile` + banner "Ya tenés un perfil guardado (N
    pelis)" con botón "Usar mi perfil" en el paso 1 del wizard, visible
    cuando el usuario ya tiene ≥10 pelis guardadas (cualquiera sea el
    origen: manual, zip o username). Verificado en el browser local: cuenta
    nueva → 10 pelis manual → picks → salir y volver → banner → picks
    nuevos sin re-tildar nada y sin duplicar filas en `rated_items`
    (`persist=False` en `_finish_recommend` para este camino). 213 → 215
    tests.

22. **Bauti probó el import por username y le dio "Load failed".** Sin
    logs del momento exacto no se puede confirmar la causa, pero el
    sospechoso principal es el cold start de Render (free tier, el backend
    se duerme a los 15 min sin uso) combinado con la latencia extra que
    agrega el username (llamada a Letterboxd vía RSS, timeout 15s, antes
    de tocar TMDb) — el zip y el modo manual no tienen ese salto de red
    extra. El código de `letterboxd_scrape.py` en sí se ve sólido (timeout,
    manejo de 404 / error de conexión). **Pendiente:** pedirle a Bauti que
    reintente con el backend ya despierto; si repite, revisar logs de
    Render en el momento exacto del intento.

## Para retomar

- 21: cerrado y deployado localmente verificado, falta el deploy a
  producción (butaca.xyz) para que Bauti y el resto lo vean resuelto.
- 22: abierto, necesita repro o logs para confirmar diagnóstico antes de
  tocar código.
