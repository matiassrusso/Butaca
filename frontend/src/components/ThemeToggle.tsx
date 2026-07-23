import { useEffect, useState } from "react";

const STORAGE_KEY = "butaca-theme";

function getInitial(): "light" | "dark" {
  if (typeof window === "undefined") return "light";
  const saved = window.localStorage.getItem(STORAGE_KEY);
  if (saved === "dark" || saved === "light") return saved;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const t = getInitial();
    setTheme(t);
    document.documentElement.classList.toggle("dark", t === "dark");
    setMounted(true);
  }, []);

  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.classList.toggle("dark", next === "dark");
    window.localStorage.setItem(STORAGE_KEY, next);
  }

  return (
    <button
      onClick={toggle}
      aria-label={theme === "dark" ? "Cambiar a modo claro" : "Cambiar a modo oscuro"}
      title={theme === "dark" ? "Cambiar a modo claro" : "Cambiar a modo oscuro"}
      className="group relative size-8 grid place-items-center border border-foreground/20 hover:border-accent hover:text-accent transition-colors overflow-hidden"
    >
      <span className="font-mono text-[10px] tracking-widest">
        {mounted ? (theme === "dark" ? "☾" : "☀") : "·"}
      </span>
    </button>
  );
}
