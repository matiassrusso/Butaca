import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";

import { DICTIONARY } from "./translations/index";

export type Lang = "es" | "en";

const LANG_KEY = "butaca_lang";

// el idioma viaja al backend (query param / form field) porque los "why" del
// agente los escribe el LLM, no el frontend — ver backend/app/llm_client.py
export function normalizeLang(value: string | null): Lang {
  return value === "en" ? "en" : "es";
}

type Vars = Record<string, string | number>;

type LanguageState = {
  lang: Lang;
  setLang: (lang: Lang) => void;
  toggle: () => void;
  t: (key: string, vars?: Vars) => string;
};

const LanguageContext = createContext<LanguageState | null>(null);

function interpolate(template: string, vars?: Vars): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, name) =>
    name in vars ? String(vars[name]) : match,
  );
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() =>
    normalizeLang(localStorage.getItem(LANG_KEY)),
  );

  useEffect(() => {
    localStorage.setItem(LANG_KEY, lang);
    // sin esto los lectores de pantalla y la heurística de traducción del
    // browser siguen anunciando la página como española en modo inglés
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback((next: Lang) => setLangState(next), []);
  const toggle = useCallback(() => setLangState((prev) => (prev === "es" ? "en" : "es")), []);

  const t = useCallback(
    (key: string, vars?: Vars) => {
      const entry = DICTIONARY[key];
      // una clave sin traducir se ve en pantalla en vez de romper el render:
      // preferible una cadena cruda visible a una página en blanco
      if (!entry) return key;
      return interpolate(entry[lang] ?? entry.es, vars);
    },
    [lang],
  );

  return (
    <LanguageContext.Provider value={{ lang, setLang, toggle, t }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLang(): LanguageState {
  const ctx = useContext(LanguageContext);
  if (!ctx) {
    throw new Error("useLang debe usarse dentro de LanguageProvider.");
  }
  return ctx;
}
