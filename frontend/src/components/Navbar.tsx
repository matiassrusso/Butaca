import { motion, useScroll, useTransform } from "framer-motion";
import { Film, LogIn, LogOut } from "lucide-react";
import { Link, useLocation } from "wouter";

import GooeyNav, { GooeyNavItem } from "@/components/GooeyNav";
import { useAuth } from "@/hooks/useAuth";

const NAV_ITEMS: GooeyNavItem[] = [
  { label: "Inicio", href: "/" },
  { label: "Recomendaciones", href: "/recommend" },
  { label: "Historial", href: "/history" },
];

export function Navbar() {
  const { user, isAuthenticated, logout } = useAuth();
  const [location, navigate] = useLocation();
  const { scrollY } = useScroll();

  const navBg = useTransform(scrollY, [0, 80], ["oklch(0.08 0.005 260 / 0)", "oklch(0.08 0.005 260 / 0.95)"]);
  const navBorder = useTransform(scrollY, [0, 80], ["oklch(0.20 0.01 260 / 0)", "oklch(0.20 0.01 260 / 1)"]);

  const activeIndex = Math.max(
    0,
    NAV_ITEMS.findIndex((item) => item.href === location),
  );

  return (
    <motion.nav
      style={{ backgroundColor: navBg, borderBottomColor: navBorder }}
      className="fixed top-0 left-0 right-0 z-50 border-b backdrop-blur-sm"
    >
      <div className="container flex items-center justify-between h-16">
        <Link href="/" className="flex items-center gap-2.5 group">
          <div className="w-8 h-8 rounded-lg bg-primary/10 border border-primary/30 flex items-center justify-center group-hover:bg-primary/20 transition-colors duration-200">
            <Film className="w-4 h-4 text-primary" />
          </div>
          <span className="font-serif text-lg font-medium tracking-tight" style={{ fontFamily: "'Instrument Serif', serif" }}>
            Peli<span className="text-primary">Pick</span>
          </span>
        </Link>

        {isAuthenticated && (
          <div className="hidden md:block">
            <GooeyNav
              items={NAV_ITEMS}
              initialActiveIndex={activeIndex}
              onSelect={(_, item) => navigate(item.href)}
            />
          </div>
        )}

        <div className="flex items-center gap-3">
          {isAuthenticated ? (
            <div className="flex items-center gap-3">
              <span className="hidden sm:block text-sm text-muted-foreground">{user?.username}</span>
              <button
                onClick={() => logout()}
                className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors duration-200 px-3 py-1.5 rounded-md hover:bg-secondary"
              >
                <LogOut className="w-3.5 h-3.5" />
                <span className="hidden sm:block">Salir</span>
              </button>
            </div>
          ) : (
            <Link
              href="/login"
              className="flex items-center gap-2 text-sm font-medium bg-primary text-primary-foreground px-4 py-2 rounded-lg hover:bg-primary/90 transition-all duration-200 active:scale-95"
            >
              <LogIn className="w-3.5 h-3.5" />
              Entrar
            </Link>
          )}
        </div>
      </div>
    </motion.nav>
  );
}
