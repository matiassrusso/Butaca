import { API_BASE_URL } from "../hooks/useAuth";

// Manda Accept-Language en cada request al backend, para que los mensajes de
// error (`detail` de las HTTPException) vengan en el idioma elegido — sin
// esto, la página en inglés seguía mostrando "Subí el .zip que exporta
// Letterboxd." Ver backend/app/errors.py.
//
// Va acá y no en cada fetch a propósito: hay ~40 llamadas repartidas en 15
// archivos y ninguna pasa por un wrapper común, así que tocarlas una por una
// sería un diff enorme que además se rompe cada vez que alguien agrega una
// llamada nueva. Envolver fetch una sola vez cubre todas, incluidas las
// futuras.
//
// El idioma se lee de localStorage EN CADA LLAMADA (no al instalar el
// wrapper), así el toggle aplica sin recargar la página. Misma clave que usa
// LanguageProvider en i18n.tsx.
const LANG_KEY = "butaca_lang";

function currentLang(): string {
  try {
    return localStorage.getItem(LANG_KEY) === "en" ? "en" : "es";
  } catch {
    return "es";
  }
}

export function installApiLangHeader() {
  const original = window.fetch;
  window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
    const url =
      typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (!url.startsWith(API_BASE_URL)) return original(input, init);

    // el header explícito del llamador gana: si alguna llamada necesita fijar
    // el idioma a mano, este wrapper no se lo pisa
    const headers = new Headers(
      init?.headers ?? (input instanceof Request ? input.headers : undefined),
    );
    if (!headers.has("Accept-Language")) headers.set("Accept-Language", currentLang());
    return original(input, { ...init, headers });
  };
}
