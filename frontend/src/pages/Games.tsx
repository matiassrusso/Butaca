import { Loader2 } from "lucide-react";
import { useEffect } from "react";
import { Link, useLocation } from "wouter";

import { PageTransition } from "@/components/PageTransition";
import { useAuth } from "@/hooks/useAuth";

// Hub de juegos (idea de Matías, 2026-08-02). Criterio de selección: priorizar
// los que además generan señal de gusto -- "¿cuál te gustó más?" cumple eso,
// la trivia no (Matías la pidió igual, como puro entretenimiento).
const GAMES = [
  {
    href: "/games/pairwise",
    title: "¿Cuál te gustó más?",
    description: "Dos pósters, elegís uno. Cada elección afina tu perfil de gusto.",
    signal: true,
  },
  {
    href: "/games/trivia",
    title: "Trivia de cine",
    description: "Adiviná director, año o reparto. Puro entretenimiento, no toca tu perfil.",
    signal: false,
  },
];

export default function Games() {
  const { isAuthenticated, loading: authLoading } = useAuth();
  const [, navigate] = useLocation();

  useEffect(() => {
    if (!authLoading && !isAuthenticated) navigate("/login");
  }, [authLoading, isAuthenticated, navigate]);

  if (authLoading || !isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-accent" />
      </div>
    );
  }

  return (
    <PageTransition>
      <main className="max-w-4xl mx-auto px-6 pt-16 pb-24">
        <header className="pb-8 border-b-2 border-foreground mb-8">
          <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-4">
            [Juegos]
          </div>
          <h1 className="text-6xl md:text-7xl font-black uppercase tracking-tighter leading-[0.9]">
            Jugá <span className="text-accent italic font-serif normal-case tracking-normal">un rato</span>
          </h1>
        </header>

        <div className="grid sm:grid-cols-2 gap-6">
          {GAMES.map((game) => (
            <Link
              key={game.href}
              to={game.href}
              className="block p-6 border-2 border-foreground/20 hover:border-accent transition-colors"
            >
              <div className="font-mono text-[9px] uppercase tracking-widest text-accent mb-2">
                {game.signal ? "Mejora tus picks" : "Solo por diversión"}
              </div>
              <h2 className="text-2xl font-black uppercase tracking-tighter mb-2">{game.title}</h2>
              <p className="font-mono text-xs text-muted-foreground">{game.description}</p>
            </Link>
          ))}
        </div>
      </main>
    </PageTransition>
  );
}
