// "Tu año en Butaca" — resumen anual compartible.
//
// Los nombres de mes NO están acá: salen de Intl (toLocaleDateString), que ya
// sabe español e inglés y no hay que mantener 24 claves a mano.

import type { Entry } from "./shared";

export const WRAPPED: Record<string, Entry> = {
  "wrapped.nav": { es: "Tu año", en: "Your year" },
  "wrapped.navAria": { es: "Ver tu año en Butaca", en: "See your year in Butaca" },
  "wrapped.kicker": { es: "Resumen anual", en: "Year in review" },
  "wrapped.title": { es: "Tu año en Butaca", en: "Your year in Butaca" },
  "wrapped.inProgress": {
    es: "Todavía va por la mitad: este año no terminó.",
    en: "Still in progress: this year isn't over.",
  },
  "wrapped.yearPicker": { es: "Elegí el año", en: "Pick a year" },
  "wrapped.loading": { es: "Armando tu año…", en: "Putting your year together…" },
  "wrapped.error": { es: "No pude armar tu año.", en: "I couldn't put your year together." },

  // ─── Estados vacíos ─────────────────────────────────────────────────
  "wrapped.emptyTitle": { es: "Todavía no hay año que contar", en: "No year to tell yet" },
  "wrapped.emptyBody": {
    es: "Importá tu historial de Letterboxd o puntuá unas cuantas películas y volvé. Con cinco títulos ya alcanza.",
    en: "Import your Letterboxd history or rate a handful of movies and come back. Five titles is enough.",
  },
  "wrapped.emptyCta": { es: "Puntuar películas", en: "Rate movies" },
  "wrapped.emptyYearTitle": { es: "{year} quedó flojo", en: "{year} came up short" },
  "wrapped.emptyYearNone": {
    es: "No tenés nada anotado en {year}. Probá con otro año.",
    en: "You have nothing logged in {year}. Try another year.",
  },
  "wrapped.emptyYearBody": {
    es: "Tenés {n} título(s) en {year}, y con menos de cinco cualquier número diría más de lo que sabemos. Probá otro año.",
    en: "You have {n} title(s) in {year}, and under five any number would claim more than we know. Try another year.",
  },

  // ─── Números ────────────────────────────────────────────────────────
  "wrapped.statTitles": { es: "Títulos", en: "Titles" },
  "wrapped.statAverage": { es: "Promedio", en: "Average" },
  "wrapped.statReviews": { es: "Reseñas", en: "Reviews" },
  "wrapped.statPicks": { es: "Picks de Butaca", en: "Butaca picks" },
  "wrapped.averageNote": {
    es: "Sobre {n} con puntaje real",
    en: "Across {n} with a real rating",
  },
  "wrapped.noAverage": { es: "S/D", en: "N/A" },
  "wrapped.countingNote": {
    es: "Contamos {dated} de {total} por la fecha en que las viste. El resto no trae fecha (se puntuaron en Butaca o el import no la traía), así que valen por el día que quedaron registradas.",
    en: "We count {dated} of {total} by the date you watched them. The rest carry no date (rated in Butaca, or the import had none), so they land on the day they were logged.",
  },
  "wrapped.countingNoteAll": {
    es: "Las {total} van por la fecha real en que las viste.",
    en: "All {total} go by the date you actually watched them.",
  },
  "wrapped.countingNoteNone": {
    es: "Ninguna de las {total} trae fecha de visto, así que este año va por el día en que las registraste en Butaca.",
    en: "None of the {total} carry a watch date, so this year goes by the day you logged them in Butaca.",
  },

  // ─── Secciones ──────────────────────────────────────────────────────
  "wrapped.favorites": { es: "Lo mejor del año", en: "Best of the year" },
  "wrapped.favoritesNote": {
    es: "Solo puntajes que diste de verdad: un click de \"ya la vi\" no elige favoritas.",
    en: "Real ratings only: a \"seen it\" click doesn't pick favourites.",
  },
  "wrapped.ratedInButaca": { es: "Marcada en Butaca", en: "Marked in Butaca" },
  "wrapped.months": { es: "Mes a mes", en: "Month by month" },
  "wrapped.topMonth": { es: "Tu mes más de cine: {month}", en: "Your biggest month: {month}" },
  "wrapped.decades": { es: "De qué épocas viste", en: "Which eras you watched" },
  "wrapped.decadesNote": {
    es: "Sobre las {n} que Butaca pudo cruzar contra TMDb.",
    en: "Across the {n} Butaca could match against TMDb.",
  },
  "wrapped.movements": { es: "Tus movimientos", en: "Your movements" },
  "wrapped.movementsNote": {
    es: "Los movimientos de cine que aparecen en tu año, según el mapa de vibras de Butaca. Solo cuenta lo que ya está en ese mapa, así que es una muestra, no el total.",
    en: "The film movements showing up in your year, per Butaca's vibe map. It only counts what's already on that map, so it's a sample, not the whole picture.",
  },
  "wrapped.matchCurve": { es: "Cómo te fue leyendo Butaca", en: "How Butaca read you" },
  "wrapped.matchCurveNote": {
    es: "Promedio de match de los picks que te sirvió cada mes.",
    en: "Average match of the picks it served you each month.",
  },
  "wrapped.vibes": { es: "Tus vibras", en: "Your vibes" },
  "wrapped.vibesNote": {
    es: "Las etiquetas que más se repitieron en tus picks.",
    en: "The tags that came up most across your picks.",
  },

  // ─── Compartir ──────────────────────────────────────────────────────
  "wrapped.share": { es: "Compartir", en: "Share" },
  "wrapped.copyText": { es: "Copiar resumen", en: "Copy summary" },
  "wrapped.copyLink": { es: "Copiar link", en: "Copy link" },
  "wrapped.copied": { es: "Copiado", en: "Copied" },
  "wrapped.copyError": { es: "No pude copiar", en: "Couldn't copy" },
  "wrapped.shareNote": {
    es: "El link es tuyo: cualquiera que lo abra ve su propio año, no el tuyo. Para mandarlo por chat, copiá el resumen o mandá una captura.",
    en: "The link is yours: anyone opening it sees their own year, not yours. To send it over chat, copy the summary or share a screenshot.",
  },
  "wrapped.shareText": {
    es: "Mi {year} en Butaca: {total} títulos, promedio {average}. Lo mejor: {top}. Armá el tuyo en {url}",
    en: "My {year} in Butaca: {total} titles, {average} average. Best of it: {top}. Build yours at {url}",
  },
};
