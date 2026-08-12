import type { Entry } from "./shared";

export const TOGETHER: Record<string, Entry> = {
  "together.tag": { es: "Para dos", en: "For two" },
  "together.titlePrefix": { es: "¿Qué vemos ", en: "What do we watch " },
  "together.titleAccent": { es: "juntos", en: "together" },
  "together.titleSuffix": { es: "?", en: "?" },
  "together.intro": {
    es: "Poné el usuario de con quien vas a ver algo: de Letterboxd, o de Butaca si activó «dejar que me usen» en su perfil. Cruzamos tu historial con el de esa persona y te muestro solo cosas que ninguno de los dos vio.",
    en: "Drop the username of whoever you're watching with: their Letterboxd, or their Butaca username if they turned on \"let others use me\" in their profile. We cross your history with theirs and only show things neither of you has seen.",
  },
  "together.noAccountNeeded": {
    es: "Si usa Letterboxd no necesita cuenta de Butaca: alcanza con que su perfil sea público. Si no tiene Letterboxd, puede activar el toggle de su perfil de Butaca en vez de crear uno.",
    en: "If they use Letterboxd they don't need a Butaca account: their profile just has to be public. If they don't have Letterboxd, they can turn on the toggle in their Butaca profile instead.",
  },
  "together.warning": {
    es: "Ojo: de un perfil de Letterboxd solo podemos leer la actividad reciente (~50 entradas), no el historial completo.",
    en: "Heads up: from a Letterboxd profile we can only read recent activity (~50 entries), not their full history.",
  },
  "together.label": { es: "Usuario de Letterboxd o de Butaca", en: "Letterboxd or Butaca username" },
  "together.placeholder": { es: "ej: scorsese", en: "e.g. scorsese" },
  "together.kindLabel": { es: "¿Peli o serie?", en: "Movie or show?" },
  "together.submit": { es: "Buscar algo para los dos", en: "Find something for both" },
  "together.hint": {
    es: "Escribí su usuario para continuar.",
    en: "Type their username to continue.",
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
