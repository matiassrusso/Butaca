import { Link, useLocation } from "wouter";

import { SearchBox } from "@/components/SearchBox";
import { StaggeredMenu, type StaggeredMenuItem } from "@/components/StaggeredMenu";
import { ThemeToggle, useTheme } from "@/components/ThemeToggle";
import { useAuth } from "@/hooks/useAuth";

// feedback: "Recomendar" es LA acción de la app y pesaba igual que el resto —
// ahora es un pill destacado (estilo "+ Crear" de YouTube) y lo secundario
// (Perfil, Puntuar más, Juegos, Archivo, tema, Salir) vive en el StaggeredMenu.

const SOCIAL_ITEMS = [
  { label: "LinkedIn", link: "https://www.linkedin.com/in/matias-russo-lacerna/" },
  { label: "GitHub", link: "https://github.com/matiassrusso" },
];

export function Navbar() {
  const { user, isAuthenticated, logout } = useAuth();
  const [location] = useLocation();
  const { theme, toggle: toggleTheme } = useTheme();

  const menuItems: StaggeredMenuItem[] = [
    { label: "Perfil", ariaLabel: "Ir a tu perfil", link: "/profile" },
    { label: "Puntuar más", ariaLabel: "Puntuar más películas", link: "/rate" },
    { label: "Juegos", ariaLabel: "Ir a juegos", link: "/games" },
    { label: "Archivo", ariaLabel: "Ver tu archivo", link: "/history" },
    {
      label: theme === "dark" ? "Modo claro" : "Modo oscuro",
      ariaLabel: "Cambiar tema",
      onSelect: toggleTheme,
    },
    { label: "Salir", ariaLabel: "Cerrar sesión", onSelect: () => logout() },
  ];

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

          <StaggeredMenu
            items={menuItems}
            socialItems={SOCIAL_ITEMS}
            eyebrow={user?.username}
            triggerLabel={user?.username ?? "Menú"}
          />
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
