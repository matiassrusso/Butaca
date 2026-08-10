import type { Entry } from "./shared";

export const MAP: Record<string, Entry> = {
  "map.tag": { es: "[Mapa]", en: "[Map]" },
  "map.titlePrefix": { es: "El mapa del ", en: "The map of the " },
  "map.titleAccent": { es: "universo", en: "universe" },
  "map.titleSuffix": { es: " de Butaca", en: " behind Butaca" },
  "map.nav": { es: "Mapa", en: "Map" },
  "map.navAria": { es: "Ver el mapa de movimientos", en: "See the map of movements" },
  "map.intro": {
    es: "Cada título del catálogo se convierte en un vector de 2.048 dimensiones a partir de su sinopsis, sus keywords, su reparto y su dirección. Después un algoritmo de comunidades (Leiden) los agrupa en movimientos que nadie escribió a mano: salen de los datos. Esto es ese espacio, aplastado a dos dimensiones para poder mirarlo.",
    en: "Every title in the catalog becomes a 2,048-dimension vector built from its synopsis, keywords, cast and director. Then a community algorithm (Leiden) groups them into movements nobody wrote by hand: they come out of the data. This is that space, flattened to two dimensions so you can look at it.",
  },
  "map.statTitles": { es: "títulos", en: "titles" },
  "map.statMovements": { es: "movimientos", en: "movements" },
  "map.statDimensions": { es: "dimensiones por título", en: "dimensions per title" },
  "map.loading": { es: "Proyectando el universo...", en: "Projecting the universe..." },
  "map.empty": {
    es: "Todavía no se calcularon los movimientos en este entorno. El mapa aparece cuando corre el clustering.",
    en: "Movements haven't been computed in this environment yet. The map shows up once the clustering runs.",
  },
  "map.error": { es: "No pude cargar el mapa.", en: "Couldn't load the map." },
  "map.legendTitle": { es: "Regiones", en: "Regions" },
  "map.legendHint": {
    es: "Tocá una región para aislarla y ver los movimientos que tiene adentro.",
    en: "Tap a region to isolate it and see the movements inside.",
  },
  "map.legendClear": { es: "Ver todo", en: "Show everything" },
  "map.yours": { es: "Las que ya viste", en: "Ones you've seen" },
  "map.yoursHint": {
    es: "Los títulos que puntuaste aparecen marcados: es tu recorrido sobre el mapa.",
    en: "The titles you rated show up marked: that's your path across the map.",
  },
  "map.yoursGuest": {
    es: "Entrá con tu cuenta para ver marcado en el mapa todo lo que ya viste.",
    en: "Log in to see everything you've watched marked on the map.",
  },
  "map.tooltipMovement": { es: "Movimiento", en: "Movement" },
  "map.verdictLoading": { es: "Calculando tu veredicto...", en: "Working out your verdict..." },
  "map.guestWhy": {
    es: "Este título cayó en el movimiento “{movement}” cuando el clustering agrupó el catálogo. Entrá con tu cuenta para saber si te va a gustar a vos.",
    en: "This title landed in the “{movement}” movement when the clustering grouped the catalog. Log in to find out whether you'd like it.",
  },
  "map.homeCta": { es: "Ver el mapa", en: "See the map" },
  "map.homeLead": {
    es: "Mil títulos, agrupados en movimientos por sus propios vectores. Nadie escribió esas categorías a mano.",
    en: "A thousand titles, grouped into movements by their own vectors. Nobody wrote those categories by hand.",
  },
};
