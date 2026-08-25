import { useEffect, useState } from "react";

import { useLang } from "../lib/i18n";

const STORAGE_KEY = "butaca-theme";

function applyTheme(theme: "light" | "dark") {
  document.documentElement.classList.toggle("dark", theme === "dark");
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "dark" ? "#211c19" : "#faf6ed");
}

function getInitial(): "light" | "dark" {
  if (typeof window === "undefined") return "light";
  const saved = window.localStorage.getItem(STORAGE_KEY);
  if (saved === "dark" || saved === "light") return saved;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

// lógica compartida entre el botón suelto (navbar deslogueado) y el item del
// dropdown de usuario (navbar logueado)
export function useTheme() {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const t = getInitial();
    setTheme(t);
    applyTheme(t);
    setMounted(true);
  }, []);

  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    applyTheme(next);
    window.localStorage.setItem(STORAGE_KEY, next);
  }

  return { theme, toggle, mounted };
}

export function ThemeToggle() {
  const { theme, toggle, mounted } = useTheme();
  const { t } = useLang();
  const label = theme === "dark" ? t("theme.toLight") : t("theme.toDark");

  return (
    <button
      onClick={toggle}
      aria-label={label}
      title={label}
      className="group relative size-8 grid place-items-center border border-foreground/20 hover:border-accent hover:text-accent transition-colors overflow-hidden"
    >
      <span className="font-mono text-[10px] tracking-widest">
        {mounted ? (theme === "dark" ? "☾" : "☀") : "·"}
      </span>
    </button>
  );
}
