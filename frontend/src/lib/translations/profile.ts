import type { Entry } from "./shared";

export const PROFILE: Record<string, Entry> = {
  // ─── Header ───────────────────────────────────────────────────────────
  "profile.kicker": { es: "[Perfil]", en: "[Profile]" },
  "profile.avatarAlt": { es: "Still de {title}", en: "Still from {title}" },
  "profile.avatarFallbackAlt": { es: "Avatar", en: "Avatar" },
  "profile.memberSince": { es: "Miembro desde {date}", en: "Member since {date}" },
  "profile.emailVerified": { es: "✓ verificado", en: "✓ verified" },
  "profile.emailUnverified": { es: "sin verificar", en: "unverified" },
  "profile.avatarFrom": {
    es: "Tu avatar sale de tu mejor puntuada: {title}",
    en: "Your avatar comes from your top-rated one: {title}",
  },

  // ─── Cuenta de Letterboxd ─────────────────────────────────────────────
  "profile.letterboxdLabel": { es: "Tu cuenta de Letterboxd", en: "Your Letterboxd account" },
  "profile.letterboxdPlaceholder": { es: "sin vincular", en: "not linked" },
  "profile.letterboxdSaving": { es: "Guardando…", en: "Saving…" },
  "profile.letterboxdSaved": { es: "Guardado.", en: "Saved." },
  "profile.letterboxdUnlinked": {
    es: "Cuenta de Letterboxd desvinculada.",
    en: "Letterboxd account unlinked.",
  },
  "profile.letterboxdError": {
    es: "No pude guardar tu usuario de Letterboxd.",
    en: "Couldn't save your Letterboxd username.",
  },
  "profile.letterboxdNote": {
    es: "Solo los imports de esta cuenta se guardan en tu perfil. Si alguien más prueba Butaca con su usuario desde tu sesión, ve sus picks pero no toca tus datos.",
    en: "Only imports from this account get saved to your profile. If someone else tries Butaca with their own username from your session, they see their picks but never touch your data.",
  },

  // ─── Stats ────────────────────────────────────────────────────────────
  "profile.statWatched": { es: "Vistas", en: "Watched" },
  "profile.statSessions": { es: "Sesiones de picks", en: "Pick sessions" },
  "profile.statWatchlist": { es: "En watchlist", en: "On watchlist" },
  "profile.statFeedback": { es: "Feedback dado", en: "Feedback given" },

  // ─── Mapa de afinidad ─────────────────────────────────────────────────
  "profile.affinityMap": { es: "[Mapa de afinidad]", en: "[Affinity map]" },
  "profile.matchedCount": {
    es: "{matched} de {total} títulos matcheados",
    en: "{matched} of {total} titles matched",
  },
  "profile.loading": {
    es: "Cruzando tu historial con TMDb...",
    en: "Cross-checking your history with TMDb...",
  },
  "profile.tasteError": {
    es: "No pude armar tu perfil de gusto.",
    en: "Couldn't build your taste profile.",
  },
  "profile.emptyTitle": {
    es: "Todavía no hay suficiente para armar tu perfil",
    en: "Not enough yet to build your profile",
  },
  "profile.emptyBody": {
    es: "Importá tu Letterboxd o puntuá pelis desde la pantalla de recomendaciones.",
    en: "Import your Letterboxd or rate some movies from the recommendations screen.",
  },
  "profile.goRecommend": { es: "Ir a recomendar", en: "Get recommendations" },
  "profile.genreSignature": { es: "[Firma de géneros]", en: "[Genre signature]" },
  "profile.decadeTimeline": { es: "[Timeline · décadas]", en: "[Timeline · decades]" },
  "profile.directors": { es: "[Directores]", en: "[Directors]" },
  "profile.cast": { es: "[Reparto]", en: "[Cast]" },
  "profile.watchedCount": { es: "{n} vistas", en: "{n} watched" },

  // ─── Zona de peligro ──────────────────────────────────────────────────
  "profile.dangerZone": { es: "[Zona de peligro]", en: "[Danger zone]" },
  "profile.deleteTitle": { es: "Borrar cuenta", en: "Delete account" },
  "profile.deleteBody": {
    es: "Borra tu cuenta y todos tus datos (ratings, historial, perfil de gusto). No se puede deshacer.",
    en: "Deletes your account and all your data (ratings, history, taste profile). There's no undo.",
  },
  "profile.deleteConfirmLabel": {
    es: "Escribí tu usuario ({username}) para confirmar",
    en: "Type your username ({username}) to confirm",
  },
  "profile.deletePassword": { es: "Contraseña", en: "Password" },
  "profile.deleting": { es: "Borrando…", en: "Deleting…" },
  "profile.deleteButton": {
    es: "Borrar mi cuenta para siempre",
    en: "Delete my account forever",
  },
  "profile.deleteSuccess": {
    es: "Tu cuenta y tus datos fueron borrados.",
    en: "Your account and your data are gone.",
  },
  "profile.deleteError": {
    es: "No pude borrar la cuenta.",
    en: "Couldn't delete the account.",
  },
};
