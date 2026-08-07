import { useLang } from "@/lib/i18n";

// mismo tamaño y borde que ThemeToggle para que convivan en la navbar sin
// romper la línea. Muestra el idioma AL QUE se cambia, no el activo — un
// botón que dice "ES" estando en español no le dice a nadie qué hace.
export function LanguageToggle() {
  const { lang, toggle, t } = useLang();
  const target = lang === "es" ? "EN" : "ES";

  return (
    <button
      onClick={toggle}
      aria-label={t("nav.langAria")}
      title={lang === "es" ? t("nav.langToEn") : t("nav.langToEs")}
      className="group relative size-8 grid place-items-center border border-foreground/20 hover:border-accent hover:text-accent transition-colors"
    >
      <span className="font-mono text-[10px] tracking-widest">{target}</span>
    </button>
  );
}
