import type { Entry } from "./shared";

export const HOME: Record<string, Entry> = {
  // ─── Home / hero ──────────────────────────────────────────────────────
  "home.hero.badge": {
    es: "Basado en tu gusto real, no en un ranking",
    en: "Based on what you actually like, not on a ranking",
  },
  // el h1 se anima palabra por palabra y la del medio va en cursiva acento —
  // por eso van tres claves y no una sola frase
  "home.hero.title1": { es: "Pelis que", en: "Movies that" },
  "home.hero.title2": { es: "te", en: "know" },
  "home.hero.title3": { es: "conocen.", en: "you." },
  "home.hero.method": {
    es: "[Método] Importás tu Letterboxd o puntuás a mano, sin cuenta si querés. Leemos tus ratings, tus reviews cuando las hay, tus patrones. Después recomendamos con explicaciones basadas en tu gusto real, no en un ranking genérico.",
    en: "[Method] Import your Letterboxd or rate a few by hand, no account needed. We read your ratings, your reviews when there are any, your patterns. Then we recommend with reasons based on what you actually like, not on a generic ranking.",
  },
  "home.hero.sync": { es: "Sync con Letterboxd →", en: "Sync with Letterboxd →" },
  "home.cta.authed": { es: "Ir a mis recomendaciones", en: "Go to my picks" },
  "home.cta.guest": { es: "Empezar gratis", en: "Start free" },

  // ─── Semanales ────────────────────────────────────────────────────────
  "home.weekly.label": { es: "[Recomendaciones de la semana]", en: "[This week's picks]" },
  "home.weekly.blurbLead": {
    es: "3 de tendencia esta semana + 2 de otras épocas, todo TMDb real — las mismas para todo el mundo —",
    en: "3 trending this week + 2 from other eras, all real TMDb — the same ones for everyone —",
  },
  "home.weekly.blurbAuthed": {
    es: " esto es lo que tu perfil dice sobre cada una.",
    en: " here's what your profile says about each one.",
  },
  "home.weekly.loginLink": { es: "Iniciá sesión", en: "Sign in" },
  "home.weekly.blurbGuest": {
    es: "para ver qué tan bien va cada una con vos.",
    en: "to see how well each one fits you.",
  },

  // ─── Current picks ────────────────────────────────────────────────────
  "home.currentPicks.label": { es: "[Current picks]", en: "[Current picks]" },
  "home.currentPicks.seeAll": { es: "Ver todo →", en: "See all →" },

  // ─── Metodología ──────────────────────────────────────────────────────
  "home.method.title": { es: "La metodología", en: "The method" },
  "home.method.subtitle": {
    es: "Detrás de cada elección hay un patrón rastreable en tu historial — nunca un ranking global.",
    en: "Behind every pick there's a pattern you can trace back to your own history — never a global ranking.",
  },
  "home.steps.1.title": { es: "Contanos qué viste", en: "Tell us what you've seen" },
  "home.steps.1.desc": {
    es: "Subí tu export de Letterboxd, importalo por usuario, o puntuá a mano en un minuto, sin cuenta si querés.",
    en: "Upload your Letterboxd export, import it by username, or rate a few by hand in a minute — no account needed.",
  },
  "home.steps.2.title": { es: "Leemos tus patrones", en: "We read your patterns" },
  "home.steps.2.desc": {
    es: "Ratings, reviews cuando las hay, género, director. Buscamos el patrón real detrás de lo que premiás o rechazás.",
    en: "Ratings, reviews when there are any, genre, director. We look for the real pattern behind what you love or drop.",
  },
  "home.steps.3.title": { es: "Recibís picks con razón", en: "You get picks with reasons" },
  "home.steps.3.desc": {
    es: "Cada recomendación viene con una explicación basada en tu propio historial, no en un ranking genérico.",
    en: "Every pick comes with an explanation drawn from your own history, not from a generic ranking.",
  },

  // ─── CTA final ────────────────────────────────────────────────────────
  "home.finalCta.title": { es: "¿Lista tu próxima", en: "Ready for your next" },
  "home.finalCta.titleAccent": { es: "peli?", en: "movie?" },
  "home.finalCta.subtitle": {
    es: "Subí tu historial y recibí recomendaciones personalizadas en menos de un minuto.",
    en: "Upload your history and get picks made for you in under a minute.",
  },

  // ─── Toasts ───────────────────────────────────────────────────────────
  "home.toast.feedbackError": {
    es: "No se pudo guardar el feedback.",
    en: "Couldn't save your feedback.",
  },
  "home.toast.ratePreserved": {
    es: "Tu {rating}/5 de Letterboxd tiene prioridad. Cambialo ahí y volvé a importar.",
    en: "Your {rating}/5 from Letterboxd wins. Change it there and import again.",
  },
  "home.toast.rateSaved": { es: "Guardado en tu perfil: {title}", en: "Saved to your profile: {title}" },
  "home.toast.rateError": { es: "No se pudo guardar el puntaje.", en: "Couldn't save your rating." },

  // ─── 404 ──────────────────────────────────────────────────────────────
  "home.notFound.title": { es: "Esta página no existe", en: "This page doesn't exist" },
  "home.notFound.body": {
    es: "Puede que se haya movido o que el link esté roto.",
    en: "It may have moved, or the link is broken.",
  },
  "home.notFound.back": { es: "Volver al inicio", en: "Back home" },

  // ─── Footer ───────────────────────────────────────────────────────────
  "home.footer.tagline": { es: "para el que mira con criterio", en: "for people who watch with taste" },
  "home.footer.author": {
    es: "Un proyecto de Matías Russo Lacerna",
    en: "A project by Matías Russo Lacerna",
  },
  "home.footer.stats": { es: "Catalog statistics", en: "Catalog statistics" },
  "home.footer.genres": { es: "Géneros", en: "Genres" },
  "home.footer.tmdbCredit": { es: "Datos de películas por", en: "Movie data by" },

  // ─── Banner de cuenta ─────────────────────────────────────────────────
  "home.banner.guest": {
    es: "Estás como invitado. Poné usuario y contraseña para no perder tus puntuaciones.",
    en: "You're browsing as a guest. Set a username and password so you don't lose your ratings.",
  },
  "home.banner.guestCta": { es: "Crear mi cuenta", en: "Create my account" },
  "home.banner.verify": {
    es: "Confirmá tu email para asegurar tu cuenta. Te mandamos un link al registrarte.",
    en: "Confirm your email to secure your account. We sent you a link when you signed up.",
  },
  "home.banner.resend": { es: "Reenviar", en: "Resend" },
  "home.banner.sending": { es: "Enviando…", en: "Sending…" },
  "home.banner.dismissAria": { es: "Cerrar aviso", en: "Dismiss notice" },
  "home.banner.resendOk": {
    es: "Te reenviamos el mail de verificación.",
    en: "We resent the verification email.",
  },
  "home.banner.resendError": {
    es: "No pude reenviar el mail. Probá más tarde.",
    en: "Couldn't resend the email. Try again later.",
  },
};
