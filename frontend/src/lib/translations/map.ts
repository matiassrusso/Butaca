import type { Entry } from "./shared";

export const MAP: Record<string, Entry> = {
  "map.tag": { es: "[Mapa]", en: "[Map]" },
  "map.titlePrefix": { es: "El mapa del ", en: "The map of the " },
  "map.titleAccent": { es: "universo", en: "universe" },
  "map.titleSuffix": { es: " de Butaca", en: " behind Butaca" },
  "map.nav": { es: "Mapa", en: "Map" },
  "map.navAria": { es: "Ver el mapa de movimientos", en: "See the map of movements" },
  "map.intro": {
    es: "El mapa empieza con los géneros reales de TMDb. Cerca, los embeddings separan movimientos más finos que emergen del catálogo: un título puede vivir justo entre sus géneros, como los superhéroes entre acción y ciencia ficción.",
    en: "The map starts with TMDb's real genres. Up close, embeddings separate finer movements that emerge from the catalog: a title can live between its genres, like superheroes between action and science fiction.",
  },
  "map.statTitles": { es: "títulos", en: "titles" },
  "map.statMovements": { es: "movimientos", en: "movements" },
  "map.statGenres": { es: "géneros", en: "genres" },
  "map.statDimensions": { es: "dimensiones por título", en: "dimensions per title" },
  "map.loading": { es: "Proyectando el universo...", en: "Projecting the universe..." },
  "map.empty": {
    es: "Todavía no se calcularon los movimientos en este entorno. El mapa aparece cuando corre el clustering.",
    en: "Movements haven't been computed in this environment yet. The map shows up once the clustering runs.",
  },
  "map.error": { es: "No pude cargar el mapa.", en: "Couldn't load the map." },
  "map.legendTitle": { es: "Géneros", en: "Genres" },
  "map.legendHint": {
    es: "Tocá un género para aislarlo; acercate para revelar sus movimientos y títulos.",
    en: "Tap a genre to isolate it; zoom in to reveal its movements and titles.",
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
  "map.filterAll": { es: "Todo", en: "All" },
  "map.filterMovies": { es: "Pelis", en: "Movies" },
  "map.filterSeries": { es: "Series", en: "Series" },
  "map.shapeMovie": { es: "Película", en: "Movie" },
  "map.shapeSeries": { es: "Serie", en: "Series" },
  "map.shapeLegend": { es: "Formato", en: "Format" },
  "map.search": { es: "Buscar un título…", en: "Search a title…" },
  "map.searchNone": { es: "nada con ese nombre", en: "nothing by that name" },
  "map.searchCount": { es: "{n} en el mapa", en: "{n} on the map" },
  "map.resetView": { es: "Reencuadrar", en: "Reset view" },
  "map.zoomHint": {
    es: "Rueda para acercar, arrastrá para moverte.",
    en: "Wheel to zoom, drag to pan.",
  },
  "map.homeCta": { es: "Ver el mapa", en: "See the map" },
  "map.homeLead": {
    es: "Mil títulos, agrupados en movimientos por sus propios vectores. Nadie escribió esas categorías a mano.",
    en: "A thousand titles, grouped into movements by their own vectors. Nobody wrote those categories by hand.",
  },
};
