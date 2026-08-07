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
  // ojo: el copy promete explícitamente que el par sale de títulos YA vistos
  // y puntuados igual, y que elegir NO cambia el puntaje -- es el fix de un
  // bug real (2026-08-03), no suavizar la promesa al traducir.
  "games.pairwise.intro": {
    es: "Dos pelis que ya viste y puntuaste igual. Elegí la que más te gustó -- nos ayuda a desempatar entre tus favoritas, no te cambia el puntaje.",
    en: "Two movies you've already seen and gave the same rating. Pick the one you liked more -- it helps us break ties between your favorites, it doesn't change your rating.",
  },
  "games.pairwise.loading": { es: "Buscando un par...", en: "Looking for a pair..." },
  "games.pairwise.error": { es: "No pude armar un par para jugar.", en: "Couldn't put together a pair to play." },
  "games.pairwise.saveError": { es: "No se pudo guardar tu elección.", en: "Couldn't save your pick." },
  "games.pairwise.playedOne": { es: "Jugaste {n} ronda.", en: "You played {n} round." },
  "games.pairwise.playedMany": { es: "Jugaste {n} rondas.", en: "You played {n} rounds." },
  "games.pairwise.needMore": {
    es: 'Necesitás al menos dos pelis vistas con el mismo puntaje para jugar -- puntuá más en "Puntuar más".',
    en: 'You need at least two movies you\'ve seen with the same rating to play -- rate a few more in "Rate more".',
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
