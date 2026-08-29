import type { Entry } from "./shared";

export const GAMES: Record<string, Entry> = {
  // ─── Hub de juegos ────────────────────────────────────────────────────
  "games.tag": { es: "[Juegos]", en: "[Games]" },
  "games.tagSingle": { es: "[Juego]", en: "[Game]" },
  "games.titlePrefix": { es: "Jugá ", en: "Play " },
  "games.titleAccent": { es: "un rato", en: "for a bit" },
  "games.badgeSignal": { es: "Mejora tus picks", en: "Sharpens your picks" },
  "games.badgeFun": { es: "Solo por diversión", en: "Just for fun" },

  // ─── Juego: ¿cuál te gustó más? ───────────────────────────────────────
  "games.pairwise.cardTitle": { es: "¿Cuál te gustó más?", en: "Which one did you like more?" },
  "games.pairwise.cardDescription": {
    es: "Dos pósters, elegís uno. Cada elección afina tu perfil de gusto.",
    en: "Two posters, you pick one. Every pick sharpens your taste profile.",
  },
  "games.pairwise.titlePrefix": { es: "¿Cuál te ", en: "Which one did you " },
  "games.pairwise.titleAccent": { es: "gustó", en: "like" },
  "games.pairwise.titleSuffix": { es: " más?", en: " more?" },
  // rediseño 2026-08-29: el par ya NO es "mismo puntaje" -- son dos que te
  // gustaron (del mismo tipo), aunque tengan distinto puntaje o género, y elegir
  // SÍ afina tu perfil (pesa en el scoring, no solo en el "why"). El puntaje que
  // les pusiste no es tu preferencia actual: podés preferir una que puntuaste
  // más bajo.
  "games.pairwise.intro": {
    es: "Dos títulos que te gustaron. Elegí el que preferís hoy -- no importa qué puntaje les pusiste, tu elección afina tu perfil.",
    en: "Two titles you liked. Pick the one you prefer today -- the rating you gave doesn't matter, your choice sharpens your profile.",
  },
  "games.pairwise.loading": { es: "Buscando un par...", en: "Looking for a pair..." },
  "games.pairwise.error": { es: "No pude armar un par para jugar.", en: "Couldn't put together a pair to play." },
  "games.pairwise.saveError": { es: "No se pudo guardar tu elección.", en: "Couldn't save your pick." },
  "games.pairwise.skip": { es: "Me gustan los dos igual, saltear", en: "I like both the same, skip" },
  "games.pairwise.playedOne": { es: "Jugaste {n} ronda.", en: "You played {n} round." },
  "games.pairwise.playedMany": { es: "Jugaste {n} rondas.", en: "You played {n} rounds." },
  "games.pairwise.needMore": {
    es: 'Necesitás al menos dos títulos que te hayan gustado (del mismo tipo) para jugar -- puntuá más en "Puntuar más".',
    en: 'You need at least two titles you liked (of the same type) to play -- rate a few more in "Rate more".',
  },
  "games.pairwise.roundsOne": { es: "{n} ronda jugada", en: "{n} round played" },
  "games.pairwise.roundsMany": { es: "{n} rondas jugadas", en: "{n} rounds played" },

  // ─── Juego: trivia ────────────────────────────────────────────────────
  // Las preguntas las escribe el backend (campo `question` del JSON): acá
  // solo va el chrome alrededor.
  "games.trivia.cardTitle": { es: "Trivia de cine", en: "Movie trivia" },
  "games.trivia.cardDescription": {
    es: "Adiviná director, año o reparto. Puro entretenimiento, no toca tu perfil.",
    en: "Guess the director, year or cast. Pure fun, it doesn't touch your profile.",
  },
  "games.trivia.titlePrefix": { es: "Trivia de ", en: "Movie " },
  "games.trivia.titleAccent": { es: "cine", en: "trivia" },
  "games.trivia.intro": {
    es: "Sobre pelis y series que ya viste. Puro entretenimiento -- esto no toca tu perfil de gusto.",
    en: "About movies and shows you've already seen. Pure fun -- this doesn't touch your taste profile.",
  },
  "games.trivia.loading": { es: "Armando una pregunta...", en: "Putting a question together..." },
  "games.trivia.error": { es: "No pude armar una pregunta.", en: "Couldn't put a question together." },
  "games.trivia.empty": {
    es: "Necesitás tener pelis puntuadas (y variedad de otras en el catálogo) para armar una pregunta.",
    en: "You need some rated movies (and enough variety in the catalog) to build a question.",
  },
  "games.trivia.score": { es: "{correct}/{total} correctas", en: "{correct}/{total} correct" },
};
