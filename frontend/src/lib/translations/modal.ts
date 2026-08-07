import type { Entry } from "./shared";

// Modal de detalle (MovieModal + DisagreePanel), buscador, póster y estrellas.
// El "why" y el overview NO viven acá: vienen del backend ya en el idioma
// pedido (query param `lang`).

export const MODAL: Record<string, Entry> = {
  // ─── Panel "no estoy de acuerdo" ──────────────────────────────────────
  "modal.disagree": { es: "¿No estás de acuerdo?", en: "Don't agree?" },
  "modal.similarLoading": { es: "Buscando parecidas...", en: "Looking for similar ones..." },
  "modal.noSimilar": {
    es: "No encontré títulos parecidos para votar.",
    en: "I couldn't find similar titles to vote on.",
  },
  "modal.outOfSimilarOne": {
    es: "Me quedé sin títulos parecidos. Con 1 voto ya afiné algo tu perfil.",
    en: "I ran out of similar titles. With 1 vote I already tuned your profile a bit.",
  },
  "modal.outOfSimilarMany": {
    es: "Me quedé sin títulos parecidos. Con {n} votos ya afiné algo tu perfil.",
    en: "I ran out of similar titles. With {n} votes I already tuned your profile a bit.",
  },
  "modal.recalcAnyway": { es: "Recalcular igual", en: "Recalculate anyway" },
  "modal.adjustMatch": { es: "Ajustá el match", en: "Tune the match" },
  "modal.seenIt": { es: "¿La viste?", en: "Have you seen it?" },
  "modal.yesSaw": { es: "Sí, la vi", en: "Yes, I saw it" },
  "modal.notSeen": { es: "No la vi", en: "Haven't seen it" },
  "modal.whatDidYouThink": { es: "¿Qué te pareció?", en: "What did you think?" },
  "modal.recalculating": { es: "Recalculando…", en: "Recalculating…" },

  // ─── Detalle ──────────────────────────────────────────────────────────
  "modal.loadingDetails": {
    es: "Cargando reparto y tráiler...",
    en: "Loading cast and trailer...",
  },
  "modal.watchTrailer": { es: "Ver tráiler", en: "Watch trailer" },
  "modal.cast": { es: "Reparto", en: "Cast" },
  "modal.whereToWatch": { es: "Dónde verla", en: "Where to watch" },
  "modal.rentBuy": { es: "Alquiler/compra:", en: "Rent/buy:" },
  "modal.notStreaming": {
    es: "No está en streaming en Argentina ahora.",
    en: "Not streaming in Argentina right now.",
  },
  "modal.justwatch": { es: "Datos de JustWatch", en: "Data from JustWatch" },

  // ─── Feedback ─────────────────────────────────────────────────────────
  "modal.whatAboutPick": { es: "¿Qué te parece este pick?", en: "What do you think of this pick?" },
  "modal.interested": { es: "Me interesa", en: "I'm in" },
  "modal.alreadySeen": { es: "Ya la vi", en: "Already seen it" },
  "modal.notInterested": { es: "No me interesa", en: "Not for me" },
  "modal.letterboxdPriority": {
    es: "Este rating viene de Letterboxd y tiene prioridad. Para cambiarlo, actualizalo ahí y volvé a importar.",
    en: "This rating comes from Letterboxd and takes priority. To change it, update it there and import again.",
  },

  // ─── Buscador ─────────────────────────────────────────────────────────
  "modal.clearSearch": { es: "Limpiar búsqueda", en: "Clear search" },
  "modal.verdictError": { es: "No pude analizar ese título.", en: "I couldn't analyze that title." },
  "modal.ratePreserved": {
    es: "Tu {n}/5 de Letterboxd tiene prioridad. Cambialo ahí y volvé a importar.",
    en: "Your {n}/5 from Letterboxd takes priority. Change it there and import again.",
  },
  "modal.rateSaved": { es: "Guardado en tu perfil: {title}", en: "Saved to your profile: {title}" },
  "modal.rateError": { es: "No se pudo guardar el puntaje.", en: "Couldn't save that rating." },

  // ─── Póster ───────────────────────────────────────────────────────────
  "modal.viewDetail": { es: "Ver detalle de {title}", en: "See details for {title}" },
  "modal.unknownMatchHint": {
    es: "Match desconocido: todavía no hay evidencia real en tu perfil",
    en: "Match unknown: there's no real evidence in your profile yet",
  },
  "modal.heuristic": { es: "heurístico", en: "heuristic" },
  "modal.heuristicHint": {
    es: "Elegido por el motor de recomendación, sin pasar por la IA",
    en: "Picked by the recommendation engine, without going through the AI",
  },

  // ─── Estrellas ────────────────────────────────────────────────────────
  "modal.yourRating": { es: "Tu rating", en: "Your rating" },
  "modal.pickRating": { es: "Elegí tu rating", en: "Pick your rating" },
  "modal.starsAria": { es: "{n} estrellas: {label}", en: "{n} stars: {label}" },
  "modal.starsTitle": { es: "{n} estrellas · {label}", en: "{n} stars · {label}" },
  "modal.star0_5": { es: "No te gustó nada", en: "You hated it" },
  "modal.star1": { es: "Muy mala", en: "Really bad" },
  "modal.star1_5": { es: "Mala", en: "Bad" },
  "modal.star2": { es: "Floja", en: "Weak" },
  "modal.star2_5": { es: "Regular", en: "So-so" },
  "modal.star3": { es: "Te gustó", en: "You liked it" },
  "modal.star3_5": { es: "Te gustó bastante", en: "You quite liked it" },
  "modal.star4": { es: "Te gustó mucho", en: "You really liked it" },
  "modal.star4_5": { es: "Te encantó", en: "You loved it" },
  "modal.star5": { es: "Una favorita", en: "An all-time favorite" },
};
