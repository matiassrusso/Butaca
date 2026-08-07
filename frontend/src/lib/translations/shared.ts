// Diccionario ES/EN de toda la UI (pedido de Matías, 2026-08-06).
//
// Los "why" y el taste_summary NO viven acá: los escribe el LLM (o el motor
// heurístico) del lado del backend, que recibe el idioma como parámetro — ver
// backend/app/llm_client.py y backend/app/recommender.py. Acá va solo el
// chrome de la app.
//
// Está partido por pantalla (prefijo de la clave) para que se pueda editar de
// a una sección sin releer el archivo entero.

export type Entry = { es: string; en: string };

export const SHARED: Record<string, Entry> = {
  // ─── Navbar / menú ────────────────────────────────────────────────────
  "nav.tagline": { es: "Cineclub", en: "Film Club" },
  "nav.recommend": { es: "Recomendar", en: "Recommend" },
  "nav.login": { es: "Entrar", en: "Sign in" },
  "nav.menu": { es: "Menú", en: "Menu" },
  "nav.menuOpen": { es: "Abrir menú", en: "Open menu" },
  "nav.menuClose": { es: "Cerrar menú", en: "Close menu" },
  "nav.profile": { es: "Perfil", en: "Profile" },
  "nav.profileAria": { es: "Ir a tu perfil", en: "Go to your profile" },
  "nav.rate": { es: "Puntuar más", en: "Rate more" },
  "nav.rateAria": { es: "Puntuar más películas", en: "Rate more movies" },
  "nav.games": { es: "Juegos", en: "Games" },
  "nav.gamesAria": { es: "Ir a juegos", en: "Go to games" },
  "nav.history": { es: "Archivo", en: "Archive" },
  "nav.historyAria": { es: "Ver tu archivo", en: "View your archive" },
  "nav.lightMode": { es: "Modo claro", en: "Light mode" },
  "nav.darkMode": { es: "Modo oscuro", en: "Dark mode" },
  "nav.themeAria": { es: "Cambiar tema", en: "Toggle theme" },
  // el botón suelto de la navbar deslogueada: describe la ACCIÓN, a diferencia
  // de nav.lightMode/darkMode que son etiquetas del item del menú
  "theme.toLight": { es: "Cambiar a modo claro", en: "Switch to light mode" },
  "theme.toDark": { es: "Cambiar a modo oscuro", en: "Switch to dark mode" },
  "nav.logout": { es: "Salir", en: "Log out" },
  "nav.logoutAria": { es: "Cerrar sesión", en: "Log out" },
  "nav.langAria": { es: "Cambiar idioma", en: "Change language" },
  "nav.langToEn": { es: "English", en: "English" },
  "nav.langToEs": { es: "Español", en: "Español" },

  // ─── Buscador ─────────────────────────────────────────────────────────
  "search.placeholder": { es: "Buscar película o serie…", en: "Search a movie or show…" },
  "search.aria": { es: "Buscar títulos", en: "Search titles" },
  "search.noResults": { es: "Sin resultados", en: "No results" },
  "search.loading": { es: "Buscando…", en: "Searching…" },
  "search.verdictLoading": { es: "Calculando tu veredicto…", en: "Working out your verdict…" },

  // ─── Match score ──────────────────────────────────────────────────────
  "match.unknown": { es: "Match desconocido", en: "Match unknown" },
  "match.unknownShort": { es: "S/D", en: "N/A" },
  "match.label": { es: "Match", en: "Match" },

  // ─── Común ────────────────────────────────────────────────────────────
  "common.loading": { es: "Cargando…", en: "Loading…" },
  "common.error": { es: "Algo salió mal.", en: "Something went wrong." },
  "common.retry": { es: "Reintentar", en: "Try again" },
  "common.close": { es: "Cerrar", en: "Close" },
  "common.cancel": { es: "Cancelar", en: "Cancel" },
  "common.save": { es: "Guardar", en: "Save" },
  "common.back": { es: "Volver", en: "Back" },
  "common.next": { es: "Siguiente", en: "Next" },
  "common.movies": { es: "Películas", en: "Movies" },
  "common.series": { es: "Series", en: "Shows" },
  "common.both": { es: "Ambas", en: "Both" },
  "common.movie": { es: "Película", en: "Movie" },
  "common.show": { es: "Serie", en: "Show" },
};
