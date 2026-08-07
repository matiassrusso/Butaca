import type { Entry } from "./shared";

// Pantalla /recommend (wizard de 3 pasos). Los "why" y el taste_summary NO
// están acá: los escribe el LLM del backend, que recibe `lang`.

export const RECOMMEND: Record<string, Entry> = {
  // ─── Header ───────────────────────────────────────────────────────────
  "recommend.eyebrow": { es: "[Personalizado para vos]", en: "[Made for you]" },
  "recommend.titlePre": { es: "Tus", en: "Your movie" },
  "recommend.titleAccent": { es: "picks", en: "picks" },
  "recommend.titlePost": { es: "de peli", en: "" },

  // ─── Stepper ──────────────────────────────────────────────────────────
  "recommend.step1Label": { es: "Tu historial", en: "Your history" },
  "recommend.step2Label": { es: "Qué ver", en: "What to watch" },
  "recommend.step3Label": { es: "Formato", en: "Format" },

  // ─── Paso 1: fuente ───────────────────────────────────────────────────
  "recommend.step1Title": { es: "¿De dónde sacamos tu gusto?", en: "Where do we get your taste from?" },
  "recommend.step1Intro": {
    es: "Para recomendarte en serio primero tenemos que conocerte. Elegí cómo nos contás qué viste y qué te gustó.",
    en: "To recommend anything worth watching we need to know you first. Pick how you tell us what you've seen and what you loved.",
  },
  "recommend.tabZip": { es: "Subir .zip", en: "Upload .zip" },
  "recommend.tabUsername": { es: "Username", en: "Username" },
  "recommend.tabManual": { es: "Sin cuenta", en: "No account" },

  "recommend.zipHint": {
    es: "La mejor opción: trae tu historial completo (ratings, reviews, likes, watchlist). Descargalo desde Letterboxd: Settings → Data → Export your data.",
    en: "Best option: it brings your whole history (ratings, reviews, likes, watchlist). Grab it from Letterboxd: Settings → Data → Export your data.",
  },
  "recommend.dropActive": { es: "Soltalo acá", en: "Drop it here" },
  "recommend.dropIdle": { es: "Arrastrá tu .zip acá", en: "Drag your .zip here" },
  "recommend.dropClick": { es: "o click para elegir", en: "or click to browse" },
  "recommend.dropOnlyZip": { es: "Solo .zip", en: ".zip only" },
  "recommend.notAZip": {
    es: "Eso no es un .zip — exportá tu data desde Letterboxd y subí ese archivo.",
    en: "That's not a .zip — export your data from Letterboxd and upload that file.",
  },

  "recommend.usernameHint": {
    es: "Leemos tu diario público de Letterboxd (ratings, fechas, rewatches). Tu perfil tiene que ser público.",
    en: "We read your public Letterboxd diary (ratings, dates, rewatches). Your profile has to be public.",
  },
  "recommend.usernameWarning": {
    es: "Ojo: esto solo trae tu actividad reciente (~50 entradas) — para tu historial completo, usá el .zip.",
    en: "Heads up: this only pulls your recent activity (~50 entries) — for the full history, use the .zip.",
  },
  "recommend.usernamePlaceholder": { es: "ej: scorsese", en: "e.g. scorsese" },
  "recommend.foreignAccount": {
    es: "Ojo: «{name}» no es tu cuenta ({own}). Te muestro los picks igual, pero no lo guardo en tu perfil.",
    en: "Heads up: “{name}” isn't your account ({own}). You'll get the picks anyway, but we won't save any of it to your profile.",
  },

  "recommend.manualHint": {
    es: "Estas pelis no son recomendaciones — son para conocerte. Puntuá las que hayas visto y con eso armamos tu perfil. Tus picks aparecen al final.",
    en: "These movies aren't recommendations — they're how we get to know you. Rate the ones you've seen and we'll build your profile from that. Your picks come at the end.",
  },
  "recommend.manualWarning": {
    es: "Ojo: acá solo sabemos de las pelis que puntúes en esta lista, así que algún pick puede ser una que ya viste. Si tenés Letterboxd, el .zip evita eso.",
    en: "Heads up: here we only know the movies you rate on this list, so a pick might be something you've already seen. If you're on Letterboxd, the .zip avoids that.",
  },
  // sufijo suelto: el contador se arma en JSX porque el número va resaltado
  "recommend.ratedSuffix": { es: "puntuadas", en: "rated" },
  "recommend.viewGrid": { es: "Grilla", en: "Grid" },
  "recommend.viewSwipe": { es: "Una por una", en: "One by one" },
  "recommend.searchPlaceholder": { es: "¿Viste otra? Buscala por nombre…", en: "Seen something else? Search it by name…" },
  "recommend.searchEmpty": { es: "Sin resultados para “{query}”.", en: "No results for “{query}”." },

  "recommend.letterboxdRating": { es: "Rating de Letterboxd", en: "Letterboxd rating" },
  "recommend.notSeen": { es: "No la vi", en: "Haven't seen it" },
  "recommend.swipeAllRated": { es: "Puntuaste todas las de la lista.", en: "You've rated every movie on the list." },
  "recommend.swipeEmpty": { es: "No hay pelis para puntuar.", en: "Nothing to rate here." },
  "recommend.swipeHint": {
    es: "Elegí las estrellas o deslizá hacia abajo si no la viste.",
    en: "Tap the stars, or swipe down if you haven't seen it.",
  },

  "recommend.hintZip": { es: "Subí tu .zip para continuar.", en: "Upload your .zip to continue." },
  "recommend.hintUsername": {
    es: "Escribí tu usuario de Letterboxd para continuar.",
    en: "Type your Letterboxd username to continue.",
  },
  "recommend.hintManual": {
    es: "Puntuá al menos {n} pelis para continuar.",
    en: "Rate at least {n} movies to continue.",
  },

  // ─── Paso 2: modo ─────────────────────────────────────────────────────
  "recommend.step2Title": { es: "¿Qué querés ver hoy?", en: "What are you in the mood for?" },
  "recommend.step2Intro": {
    es: "Todos los modos usan tu perfil — lo que cambia es desde dónde arranca la búsqueda.",
    en: "Every mode uses your profile — what changes is where the search starts from.",
  },
  "recommend.modeProfile": { es: "Perfil completo", en: "Full profile" },
  "recommend.modeProfileDesc": {
    es: "Cruzamos todo tu historial: géneros, directores, décadas y tags.",
    en: "We cross your whole history: genres, directors, decades and tags.",
  },
  "recommend.modeRecent": { es: "Últimas vistas", en: "Recently watched" },
  "recommend.modeRecentDesc": {
    es: "Le damos más peso a lo último que viste — para seguir la racha.",
    en: "We lean on what you watched last — to keep the streak going.",
  },
  "recommend.modeGenres": { es: "A tu elección", en: "Your call" },
  "recommend.modeGenresDesc": {
    es: "Elegís vos: géneros clásicos o vibras más específicas, y buscamos ahí adentro.",
    en: "You choose: classic genres or more specific vibes, and we dig in there.",
  },
  "recommend.modeWatchlist": { es: "De mi watchlist", en: "From my watchlist" },
  "recommend.modeWatchlistDesc": {
    es: "Ordenamos tu propia watchlist según tu perfil: cuál va primero.",
    en: "We rank your own watchlist against your profile: what to watch first.",
  },
  "recommend.modeWatchlistDisabled": {
    es: "Solo con .zip: la watchlist no viene por las otras vías.",
    en: "Only with the .zip: the watchlist doesn't come through the other options.",
  },
  "recommend.modeRecentDisabled": {
    es: "Necesita fechas de visto, que el modo sin cuenta no tiene.",
    en: "Needs watch dates, which the no-account mode doesn't have.",
  },

  "recommend.groupGeneros": { es: "Géneros", en: "Genres" },
  "recommend.groupVibras": { es: "Vibras", en: "Vibes" },
  "recommend.groupMovimientos": { es: "Movimientos", en: "Movements" },
  "recommend.picksSelected": { es: "{n}/{max} elegidas", en: "{n}/{max} selected" },
  "recommend.pickAtLeastOne": { es: "Elegí al menos una opción.", en: "Pick at least one option." },

  // ─── Paso 3: formato ──────────────────────────────────────────────────
  "recommend.step3Title": { es: "¿Películas, series o ambas?", en: "Movies, shows or both?" },
  "recommend.step3Intro": {
    es: "Último paso. Elegí el formato y pedí tus picks.",
    en: "Last step. Choose the format and get your picks.",
  },
  "recommend.recapSource": { es: "Fuente:", en: "Source:" },
  "recommend.recapMode": { es: "Modo:", en: "Mode:" },
  "recommend.recapManualCount": { es: "{n} pelis puntuadas", en: "{n} movies rated" },
  "recommend.howSummary": { es: "¿Cómo se calculan tus picks?", en: "How are your picks calculated?" },
  "recommend.howP1": {
    es: "Armamos tu perfil con lo que puntuaste: géneros, directores, décadas y tags de lo que amaste y lo que odiaste. Con eso buscamos candidatos en TMDb y los puntuamos contra tu perfil — cada pick trae la razón concreta del match, no un promedio global.",
    en: "We build your profile from what you rated: genres, directors, decades and tags from what you loved and what you hated. Then we pull candidates from TMDb and score them against that profile — every pick comes with the concrete reason it matched, not a global average.",
  },
  "recommend.howP2": {
    es: "Arriba de eso, un agente de IA revisa los candidatos y reescribe las razones citando películas reales de tu historial. Tu feedback (ya la vi / no me interesa) entra al cálculo de la próxima tanda.",
    en: "On top of that, an AI agent reviews the candidates and rewrites those reasons citing real movies from your history. Your feedback (seen it / not interested) feeds into the next batch.",
  },

  // ─── Navegación ───────────────────────────────────────────────────────
  "recommend.back": { es: "← Volver", en: "← Back" },
  "recommend.continue": { es: "Continuar →", en: "Continue →" },
  "recommend.generate": { es: "Dame mis recomendaciones", en: "Give me my picks" },

  // ─── Loading / resultados ─────────────────────────────────────────────
  "recommend.loadingTitle": { es: "Buscando tus pelis...", en: "Hunting down your movies..." },
  "recommend.loadingBody": {
    es: "Leyendo tu historial y buscando candidatos que encajen con tu gusto.",
    en: "Reading your history and looking for candidates that fit your taste.",
  },
  "recommend.resultsBadge": { es: "[Resultados · {n}]", en: "[Results · {n}]" },
  "recommend.newPicks": { es: "↻ Nuevos picks", en: "↻ New picks" },
  "recommend.changeSearch": { es: "Cambiar búsqueda", en: "Change search" },

  // ─── Errores / toasts ─────────────────────────────────────────────────
  "recommend.backendError": { es: "No pude hablar con el backend.", en: "Couldn't reach the backend." },
  "recommend.noNewPicks": {
    es: "No encontré picks nuevos para esta búsqueda — ya te mostré todo lo que tenemos. Probá cambiar el modo, el género o el formato.",
    en: "No new picks for this search — you've already seen everything we have. Try changing the mode, the genre or the format.",
  },
  "recommend.noValidRatings": {
    es: "No pude leer ratings válidos de esa fuente.",
    en: "Couldn't read any valid ratings from that source.",
  },
  "recommend.picksReady": { es: "Tus picks están listos.", en: "Your picks are ready." },
  "recommend.generateFailed": { es: "Falló la recomendación.", en: "The recommendation failed." },
  "recommend.feedbackFailed": { es: "No se pudo guardar el feedback.", en: "Couldn't save your feedback." },
  "recommend.ratePreserved": {
    es: "Tu {rating}/5 de Letterboxd tiene prioridad. Cambialo ahí y volvé a importar.",
    en: "Your {rating}/5 from Letterboxd wins. Change it there and import again.",
  },
  "recommend.rateSaved": { es: "Guardado en tu perfil: {title}", en: "Saved to your profile: {title}" },
  "recommend.rateFailed": { es: "No se pudo guardar el puntaje.", en: "Couldn't save your rating." },
};
