# Feedback de amigos — pre-lanzamiento (2026-07-23)

> Le pasé butaca.xyz a un grupo de amigos antes de postear en LinkedIn. Esto
> es lo que devolvieron, más notas propias. Solo juntado, todavía sin
> priorizar ni atacado — eso queda para retomar. Cuando se resuelva algo, se
> tacha acá y se documenta el cambio en `docs/build-log.md` como siempre.

## Chicos, UI/UX general

1. ~~**CTA "Empezar gratis" del home lleva a `/login`, no a registro.**
   Confirmado en código: `ctaHref` apunta siempre a `/login`
   (`frontend/src/pages/Home.tsx`), y `/login` arranca en modo "Entrá" por
   default — alguien nuevo tiene que buscar el link de abajo para
   registrarse.~~ **Resuelto 2026-07-23:** el CTA sin sesión ahora apunta a
   `/login?register=1` y `Login.tsx` lee el query param para arrancar en
   modo registro.

2. ~~**Grilla de resultados en `/recommend`: posters demasiado grandes en
   pantallas anchas, mucho scroll.** Los posters usan `aspect-[2/3]
   w-full` en una grilla de 2 columnas — en desktop ancho (1280px) cada
   poster sale ~900px de alto, más que el viewport. Confirmado con
   screenshot.~~ **Resuelto 2026-07-23:** `lg:grid-cols-3` — en desktop
   ancho los 6 picks entran en 2 filas de 3 con posters de ~600px.

3. ~~**(producto) No está explicado en el sitio cómo se calculan las
   recomendaciones.** La gente pregunta. Hay una explicación honesta lista
   para reusar (heurístico por tags + IA que refina arriba), solo falta
   ponerla visible en algún lado del sitio.~~ **Resuelto 2026-07-23:**
   `<details>` "¿Cómo se calculan tus picks?" en el paso final del wizard,
   justo antes del botón de generar.

4. ~~**Badge "Basado en tu historial de Letterboxd" del hero: bajo
   contraste.** `text-muted-foreground` sobre el orb `bg-accent` — dos
   colores de luminosidad parecida (gris 0.45 vs terracota 0.58 en oklch),
   se funden. Confirmado con los valores reales de `index.css`.~~
   **Resuelto 2026-07-23:** el badge pasó a `text-foreground` (tinta sobre
   papel, contraste alto en ambos temas).

5. ~~**"Sync con Letterboxd →" queda pegado arriba del CTA aunque ya estés
   logueado.** Es texto fijo en `Home.tsx` que no reacciona a
   `isAuthenticated`, a diferencia del label del botón que sí cambia.~~
   **Resuelto 2026-07-23:** solo se muestra sin sesión.

6. ~~**Botón de dark mode (☾/☀) no se entiende qué hace.** Cuadrado de 32px
   con solo el glifo a 10px, sin tooltip visible (`ThemeToggle.tsx`). Tiene
   `aria-label` para lectores de pantalla pero nada visual para el resto.~~
   **Resuelto 2026-07-23:** `title` nativo dinámico ("Cambiar a modo
   claro/oscuro") + `aria-label` alineado.

7. **(cambio grande) Onboarding manual (puntuar sin Letterboxd): poco
   feedback visual.** Sugerencia: interacción tipo swipe/Tinder en vez de
   4 botones estáticos siempre visibles por poster.

## Gaspi

8. ~~Al tocar "recomendaciones" no queda claro si las pelis que aparecen
   abajo son los picks generados o las que hay que puntuar — falta
   jerarquía visual entre "esto es para puntuar" y "esto es tu resultado".~~
   **Resuelto 2026-07-23** con el multi-step: la grilla de puntuar vive en
   el paso 1 con el texto "Estas pelis no son recomendaciones — son para
   conocerte [...] Tus picks aparecen al final"; los resultados son una
   vista aparte. (Positivo: le gustó la paleta de colores.)

## Pedro

9. ~~Paso 2 ("Qué querés ver hoy") debería estar bloqueado hasta completar
   el paso 1 (fuente) — hoy se puede tocar sin que tenga efecto todavía,
   lo cual confunde.~~ **Resuelto 2026-07-23:** el wizard no deja avanzar
   al paso 2 sin fuente válida (botón Continuar deshabilitado + hint de
   qué falta).
10. ~~No entiende qué significa cada opción del paso 2.~~ **Resuelto
    2026-07-23:** cada modo lleva una descripción de una línea; los
    deshabilitados muestran el motivo inline en vez de solo un tooltip.
11. ~~**(cambio grande)** Propone convertir `/recommend` en un multi-step
    form real (una pantalla por paso), para poder ir explicando cada
    decisión en el momento en el que importa. Englobaría los puntos 8, 9 y
    10 de una.~~ **Resuelto 2026-07-23:** `/recommend` es ahora un wizard
    de 3 pasos (Tu historial → Qué ver → Formato) con stepper clickeable
    hacia atrás, recap de lo elegido en el paso final y "Cambiar búsqueda"
    que vuelve al wizard con todo el estado preservado.
12. ~~Sacaría "Home" de la navegación, no suma mucho como link propio.~~
    **Resuelto 2026-07-23:** "Home" fuera del navbar (el logo ya lleva a `/`).
13. ~~Los labels del navbar están en inglés ("Home"/"Recommend"/"Archive"/
    "Profile"/"Sign in") en un sitio que es todo en español —
    confirmado, están hardcodeados así en `Navbar.tsx`.~~
    **Resuelto 2026-07-23:** "Recomendar"/"Archivo"/"Perfil"/"Entrar".
14. "Recommend" debería destacar más en el navbar — es la función central
    de la app y hoy tiene el mismo peso visual que los otros tres links.
15. **(cambio grande)** Navbar estilo YouTube: "Recommend" como botón
    pill destacado (como el "+ Crear" de YouTube) + avatar de perfil que
    abre un dropdown con lo secundario (dark mode, Profile, Archive)
    adentro. Resolvería 12, 13 y 14 de una sola vez.
16. Avatares random generados con fotos/stills de películas en vez de un
    círculo con inicial — hoy no existe ningún concepto de avatar en el
    sitio.

## Simón

17. **(confirmado en código, corroborado por Gerardo)** El onboarding
    manual le recomendó varias de Nolan que ya había visto (Oppenheimer,
    Inception, Dark Knight Rises, Dunkerque, Interestelar). Causa raíz: en
    modo manual el sistema solo conoce las ~10-15 pelis puntuadas a mano
    de la lista curada — no tiene ningún dato de qué más vio fuera de esa
    lista, a diferencia del import del zip que trae el historial
    completo. Al reintentar, con feedback marcado, salieron picks
    distintos (American Sniper, King Richard) — confirma que la exclusión
    por feedback (`main.py::_finish_recommend`) funciona, el problema es
    la falta de dato de entrada, no el algoritmo de exclusión en sí.
    Ambos (Simón y Gerardo) valoraron bien la explicación / experiencia
    general de todas formas.
18. 👍 Bancó el modo watchlist.
19. ~~**(confirmado en código)** La pantalla de subir `.zip` no explica cómo
    conseguirlo — solo dice "Arrastrá tu .zip acá / o click para elegir /
    Solo .zip". La instrucción real ("Settings → Data → Export en
    Letterboxd") solo vive en la sección de marketing del Home, no en la
    pantalla donde se necesita.~~ **Resuelto 2026-07-23:** línea de
    instrucción arriba del dropzone ("Descargalo desde Letterboxd:
    Settings → Data → Export your data").

## Notas propias (Matías)

20. Hacer una sección de perfil propio real. Hoy `/profile` es solo el
    mapa de afinidad (géneros/directores/décadas/actores) + la zona de
    borrar cuenta — nada de "vos" (sin avatar, sin bio, sin datos de
    cuenta ni resumen de actividad). Conecta con la idea 16.

## Para retomar

Sin priorizar todavía. A ojo, agrupando:

- **Rápidos / bajo esfuerzo:** ~~1, 4, 5, 6, 12, 13, 19~~ — **lote completo
  resuelto el 2026-07-23** (ver tachados arriba), verificado en local con
  build + navegador.
- **Medianos:** 3, 8, 9, 10, 16, 18(ya está, solo falta reconocerlo), 20
- **Grandes / rediseño:** 2 (grilla de resultados), 7 (swipe onboarding),
  11 (multi-step form), 15 (navbar estilo YouTube) — 11 y 15 en particular
  se solapan bastante con 9, 10, 12, 13, 14 y podrían resolverse juntos en
  una sola pasada de rediseño de navegación + flujo de recomendación.
- **No es un bug, es una limitación conocida:** 17 — mejor resuelto
  explicando el trade-off del modo manual en el momento (conecta con el
  punto 3), no forzando el algoritmo a adivinar lo que no sabe.
  **Atacado 2026-07-23:** el modo manual ahora avisa "acá solo sabemos de
  las pelis que puntúes en esta lista, así que algún pick puede ser una
  que ya viste — el .zip evita eso".
- **Estado 2026-07-23 (sesión 2):** resueltos 1, 2, 3, 4, 5, 6, 8, 9, 10,
  11, 12, 13, 19 + aviso del 17. Quedan: 7 (swipe onboarding), 14/15
  (navbar destacando Recomendar / estilo YouTube), 16 (avatares), 20
  (perfil real).
