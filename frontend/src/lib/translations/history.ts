import type { Entry } from "./shared";

export const HISTORY: Record<string, Entry> = {
  // ─── Header / tabs ────────────────────────────────────────────────────
  "history.kicker": { es: "[Archivo]", en: "[Archive]" },
  "history.titleLead": { es: "Tu", en: "Your" },
  "history.titleAccent": { es: "bitácora", en: "logbook" },
  "history.tabWatched": { es: "[Vistas]", en: "[Watched]" },
  "history.tabRecommended": { es: "[Recomendadas]", en: "[Recommended]" },

  // ─── Estados ──────────────────────────────────────────────────────────
  "history.loading": { es: "Cargando tu historial...", en: "Loading your history..." },
  "history.loadError": { es: "No pude cargar tu historial.", en: "Couldn't load your history." },

  // ─── Toasts ───────────────────────────────────────────────────────────
  "history.feedbackError": {
    es: "No se pudo guardar el feedback.",
    en: "Couldn't save your feedback.",
  },
  "history.ratePreserved": {
    es: "Tu {rating}/5 de Letterboxd tiene prioridad. Cambialo ahí y volvé a importar.",
    en: "Your {rating}/5 from Letterboxd wins. Change it there and import again.",
  },
  "history.rateSaved": { es: "Guardado en tu perfil: {title}", en: "Saved to your profile: {title}" },
  "history.rateError": {
    es: "No se pudo guardar el puntaje.",
    en: "Couldn't save your rating.",
  },

  // ─── Vistas ───────────────────────────────────────────────────────────
  "history.emptyWatchedTitle": {
    es: "Todavía no importaste vistas",
    en: "You haven't imported anything yet",
  },
  "history.emptyWatchedBody": {
    es: "Importá tu Letterboxd o puntuá pelis para verlas acá.",
    en: "Import your Letterboxd or rate some movies to see them here.",
  },
  "history.colTitle": { es: "Título", en: "Title" },
  "history.colWatched": { es: "Vista", en: "Watched" },
  "history.colSource": { es: "Dónde", en: "Where" },
  "history.colRating": { es: "Rating", en: "Rating" },
  "history.showReview": { es: "Tu reseña", en: "Your review" },
  "history.hideReview": { es: "Ocultar reseña", en: "Hide review" },

  // mismos textos que usa el backend para los ratings sintéticos
  "history.ratingLoved": { es: "Te encantó", en: "You loved it" },
  "history.ratingLiked": { es: "Te gustó", en: "You liked it" },
  "history.ratingDisliked": { es: "No te gustó", en: "You didn't like it" },

  // ─── Recomendadas ─────────────────────────────────────────────────────
  "history.emptyPicksTitle": {
    es: "Todavía no generaste picks",
    en: "You haven't generated any picks yet",
  },
  "history.emptyPicksBody": {
    es: "Cuando hagas tu primera sesión de recomendaciones, va a aparecer acá.",
    en: "Your first recommendation session will show up here.",
  },
  "history.goRecommend": { es: "Ir a recomendar", en: "Get recommendations" },
  "history.session": { es: "[SESIÓN {id}]", en: "[SESSION {id}]" },
  "history.noFilter": { es: "sin filtro", en: "no filter" },
  "history.picksCount": { es: "{n} picks", en: "{n} picks" },
};
