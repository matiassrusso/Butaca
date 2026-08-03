import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "wouter";

import { SearchBox } from "@/components/SearchBox";
import { ThemeToggle, useTheme } from "@/components/ThemeToggle";
import { useAuth } from "@/hooks/useAuth";

// feedback: "Recomendar" es LA acción de la app y pesaba igual que el resto —
// ahora es un pill destacado (estilo "+ Crear" de YouTube) y lo secundario
// (Perfil, Archivo, tema, Salir) vive en el dropdown del avatar.

const menuItemCls =
  "block w-full text-left px-4 py-3 font-mono text-[10px] uppercase tracking-widest hover:bg-accent/10 hover:text-accent transition-colors";

export function Navbar() {
  const { user, isAuthenticated, logout } = useAuth();
  const [location] = useLocation();
  const { theme, toggle: toggleTheme } = useTheme();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // cerrar con click afuera / Escape
  useEffect(() => {
    if (!menuOpen) return;
    function onDown(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setMenuOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  // cerrar al navegar
  useEffect(() => {
    setMenuOpen(false);
  }, [location]);

  return (
    <nav className="sticky top-0 z-50 flex items-center justify-between px-6 py-4 bg-background/70 backdrop-blur-xl border-b border-foreground/5">
      <Link to="/" className="font-mono text-xs tracking-widest font-medium uppercase">
        Butaca <span className="text-accent">//</span> Cineclub
      </Link>

      {isAuthenticated ? (
        <div className="flex items-center gap-3">
          <SearchBox />
          <Link
            to="/recommend"
            className={`px-5 py-2 font-mono text-[10px] uppercase tracking-widest transition-colors ${
              location === "/recommend"
                ? "bg-foreground text-background"
                : "bg-accent text-accent-foreground hover:bg-foreground hover:text-background"
            }`}
          >
            Recomendar
          </Link>

          <div className="relative" ref={menuRef}>
            <button
              onClick={() => setMenuOpen((o) => !o)}
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              aria-label="Menú de usuario"
              className={`size-8 grid place-items-center font-mono text-xs font-bold uppercase border transition-colors ${
                menuOpen
                  ? "bg-accent text-accent-foreground border-accent"
                  : "bg-foreground text-background border-foreground hover:bg-accent hover:text-accent-foreground hover:border-accent"
              }`}
            >
              {user?.username?.[0]?.toUpperCase() ?? "?"}
            </button>

            {menuOpen && (
              <div
                role="menu"
                className="absolute right-0 mt-2 w-56 border-2 border-foreground bg-background shadow-xl"
              >
                <div className="px-4 py-3 border-b border-foreground/10 font-mono text-xs text-muted-foreground">
                  {user?.username}
                </div>
                <Link to="/profile" role="menuitem" className={menuItemCls}>
                  Perfil
                </Link>
                <Link to="/rate" role="menuitem" className={menuItemCls}>
                  Puntuar más
                </Link>
                <Link to="/history" role="menuitem" className={menuItemCls}>
                  Archivo
                </Link>
                <button onClick={toggleTheme} role="menuitem" className={menuItemCls}>
                  {theme === "dark" ? "Modo claro ☀" : "Modo oscuro ☾"}
                </button>
                <button
                  onClick={() => logout()}
                  role="menuitem"
                  className={`${menuItemCls} border-t border-foreground/10`}
                >
                  Salir
                </button>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-4 font-mono text-[10px] tracking-widest uppercase">
          <ThemeToggle />
          <Link
            to="/login"
            className="px-3 py-2 border border-foreground/20 hover:bg-foreground hover:text-background transition-colors"
          >
            Entrar
          </Link>
        </div>
      )}
    </nav>
  );
}
