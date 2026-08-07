import { Link, useLocation } from "wouter";

import { LanguageToggle } from "@/components/LanguageToggle";
import { SearchBox } from "@/components/SearchBox";
import { StaggeredMenu, type StaggeredMenuItem } from "@/components/StaggeredMenu";
import { ThemeToggle, useTheme } from "@/components/ThemeToggle";
import { useAuth } from "@/hooks/useAuth";
import { useLang } from "@/lib/i18n";

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
  const { t } = useLang();

  const menuItems: StaggeredMenuItem[] = [
    { label: t("nav.profile"), ariaLabel: t("nav.profileAria"), link: "/profile" },
    { label: t("nav.rate"), ariaLabel: t("nav.rateAria"), link: "/rate" },
    { label: t("nav.games"), ariaLabel: t("nav.gamesAria"), link: "/games" },
    { label: t("nav.history"), ariaLabel: t("nav.historyAria"), link: "/history" },
    {
      label: theme === "dark" ? t("nav.lightMode") : t("nav.darkMode"),
      ariaLabel: t("nav.themeAria"),
      onSelect: toggleTheme,
    },
    { label: t("nav.logout"), ariaLabel: t("nav.logoutAria"), onSelect: () => logout() },
  ];

  return (
    <nav className="sticky top-0 z-50 flex items-center justify-between px-6 py-4 bg-background/70 backdrop-blur-xl border-b border-foreground/5">
      <Link to="/" className="font-mono text-xs tracking-widest font-medium uppercase">
        Butaca <span className="text-accent">//</span> {t("nav.tagline")}
      </Link>

      {isAuthenticated ? (
        <div className="flex items-center gap-3">
          <SearchBox />
          <LanguageToggle />
          <Link
            to="/recommend"
            className={`px-5 py-2 font-mono text-[10px] uppercase tracking-widest transition-colors ${
              location === "/recommend"
                ? "bg-foreground text-background"
                : "bg-accent text-accent-foreground hover:bg-foreground hover:text-background"
            }`}
          >
            {t("nav.recommend")}
          </Link>

          <StaggeredMenu
            items={menuItems}
            socialItems={SOCIAL_ITEMS}
            eyebrow={user?.username}
            triggerLabel={user?.username ?? t("nav.menu")}
          />
        </div>
      ) : (
        <div className="flex items-center gap-4 font-mono text-[10px] tracking-widest uppercase">
          <LanguageToggle />
          <ThemeToggle />
          <Link
            to="/login"
            className="px-3 py-2 border border-foreground/20 hover:bg-foreground hover:text-background transition-colors"
          >
            {t("nav.login")}
          </Link>
        </div>
      )}
    </nav>
  );
}
