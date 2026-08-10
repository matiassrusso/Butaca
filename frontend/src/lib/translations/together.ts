import type { Entry } from "./shared";

export const TOGETHER: Record<string, Entry> = {
  "together.tag": { es: "Para dos", en: "For two" },
  "together.titlePrefix": { es: "¿Qué vemos ", en: "What do we watch " },
  "together.titleAccent": { es: "juntos", en: "together" },
  "together.titleSuffix": { es: "?", en: "?" },
  "together.intro": {
    es: "Poné el usuario de Letterboxd de con quien vas a ver algo. Cruzamos tu historial con el de esa persona y te muestro solo cosas que ninguno de los dos vio.",
    en: "Drop the Letterboxd username of whoever you're watching with. We cross your history with theirs and only show things neither of you has seen.",
  },
  "together.noAccountNeeded": {
    es: "No necesita cuenta de Butaca: alcanza con que su perfil de Letterboxd sea público.",
    en: "They don't need a Butaca account: their Letterboxd profile just has to be public.",
  },
  "together.warning": {
    es: "Ojo: de su perfil solo podemos leer la actividad reciente (~50 entradas), no el historial completo.",
    en: "Heads up: we can only read their recent activity (~50 entries), not their full history.",
  },
  "together.label": { es: "Usuario de Letterboxd", en: "Letterboxd username" },
  "together.placeholder": { es: "ej: scorsese", en: "e.g. scorsese" },
  "together.kindLabel": { es: "¿Peli o serie?", en: "Movie or show?" },
  "together.submit": { es: "Buscar algo para los dos", en: "Find something for both" },
  "together.hint": {
    es: "Escribí su usuario de Letterboxd para continuar.",
    en: "Type their Letterboxd username to continue.",
  },
  "together.loadingTitle": { es: "Cruzando los dos gustos…", en: "Crossing both tastes…" },
  "together.loadingBody": {
    es: "Leemos su diario, lo mezclamos con el tuyo y descartamos todo lo que alguno ya vio.",
    en: "We read their diary, merge it with yours and drop everything either of you already saw.",
  },
  "together.resultsBadge": { es: "{n} para los dos", en: "{n} for both of you" },
  "together.resultsFor": { es: "Vos + {name}", en: "You + {name}" },
  "together.notSaved": {
    es: "Nada de esto se guarda: los puntajes de la otra persona no entran a tu perfil.",
    en: "None of this is saved: the other person's ratings never touch your profile.",
  },
  "together.tryAnother": { es: "Probar con otro usuario", en: "Try another username" },
  "together.empty": {
    es: "No encontré nada que le pegue a los dos. Probá cambiando de películas a series.",
    en: "I couldn't find anything that lands for both of you. Try switching between movies and shows.",
  },
  "together.failed": { es: "No pude armar los picks.", en: "I couldn't build the picks." },
};
