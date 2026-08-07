import type { Entry } from "./shared";

export const RATE: Record<string, Entry> = {
  // ─── Header ───────────────────────────────────────────────────────────
  "rate.tag": { es: "[Puntuar]", en: "[Rate]" },
  "rate.titlePrefix": { es: "¿Qué más ", en: "What else have you " },
  "rate.titleAccent": { es: "viste", en: "seen" },
  "rate.titleSuffix": { es: "?", en: "?" },
  "rate.intro": {
    es: "Cuanto más puntúes, mejores matches. Te mostramos lo más popular real de TMDb que todavía no tenés en tu perfil -- pensado para lo que quizás viste y te olvidaste de anotar.",
    en: "The more you rate, the better your matches. We show you what's actually popular on TMDb and isn't in your profile yet -- for the stuff you probably saw and forgot to log.",
  },

  // ─── Estados ──────────────────────────────────────────────────────────
  "rate.loading": { es: "Buscando pelis...", en: "Looking for movies..." },
  "rate.error": { es: "No pude traer pelis para puntuar.", en: "Couldn't load any movies to rate." },
  "rate.saveError": { es: "No se pudo guardar el puntaje.", en: "Couldn't save your rating." },
  "rate.exhausted": {
    es: "Por ahora no encontramos más pelis populares que no tengas en tu perfil.",
    en: "For now we couldn't find any more popular movies that aren't already in your profile.",
  },
  "rate.ratedCount": { es: "{n} puntuadas", en: "{n} rated" },

  // ─── Card / swipe ─────────────────────────────────────────────────────
  "rate.hintSeen": { es: "La vi", en: "Seen it" },
  "rate.hintNotSeen": { es: "No la vi", en: "Haven't seen it" },
  "rate.seenQuestion": { es: "¿La viste?", en: "Did you see it?" },
  "rate.seenYes": { es: "Sí, la vi", en: "Yes, I saw it" },
  "rate.seenNo": { es: "No la vi", en: "Haven't seen it" },
  "rate.wantToSee": { es: "La quiero ver", en: "I want to see it" },
  "rate.wantToSeeSaved": { es: "Va a tu watchlist", en: "Added to your watchlist" },
  "rate.wantToSeeError": {
    es: "No se pudo guardar en tu watchlist.",
    en: "Couldn't save it to your watchlist.",
  },
  "rate.swipeHint": {
    es: "O deslizá: derecha si la viste, izquierda si no.",
    en: "Or swipe: right if you saw it, left if you didn't.",
  },
  "rate.ratingQuestion": { es: "¿Qué te pareció?", en: "What did you think?" },
};
